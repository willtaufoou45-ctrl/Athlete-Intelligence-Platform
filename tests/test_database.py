import tempfile
import unittest
from pathlib import Path

from aip.database import Database
from aip.domain import classify_attempts


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "test.sqlite3"
        self.db = Database(self.path)
        self.db.initialize()
        self.athlete_id = self.db.add_athlete("Jordan")
        self.session_id = self.db.add_session("10", "yards")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_data_persists_across_database_instances(self):
        self.db.add_attempt(self.session_id, self.athlete_id, 1720)
        reopened = Database(self.path)
        self.assertEqual(reopened.all_athletes()[0]["name"], "Jordan")
        self.assertEqual(reopened.all_attempts()[0]["elapsed_ms"], 1720)

    def test_sprint_intelligence_preserves_session_rep_review_and_carry_forward(self):
        attempt_id = self.db.add_attempt(self.session_id, self.athlete_id, 1260)
        self.db.update_session_intelligence(
            self.session_id, "Acceleration", "Wall drills and starts", "Six resisted sprints after",
        )
        self.db.update_attempt_intelligence(
            attempt_id, effort_instruction="100%", coach_observation="Effortless and stayed low",
            athlete_feedback="Low and shot out", video_reference="video://rep-2",
        )
        self.db.update_athlete_session_intelligence(
            self.session_id, self.athlete_id, primary_intention="Consistent reps under 1.30",
            performance_target="Under 1.30", athlete_feedback="Low and shot out",
            coach_observation="Big arms; stable head, neck, and shoulders",
            interpretation="Intent changed after the fast rep",
            working_hypothesis="Chasing time may create tension", unknowns="Needs repeated sessions",
            carry_forward="Run every sprint the same. Do not think about beating your time.",
            reference_attempt_id=attempt_id,
        )
        self.assertEqual(self.db.session_intelligence(self.session_id)["shared_emphasis"], "Acceleration")
        context = self.db.attempt_intelligence_for_session_athlete(self.session_id, self.athlete_id)
        self.assertEqual(context[attempt_id]["athlete_feedback"], "Low and shot out")
        review = self.db.athlete_session_intelligence(self.session_id, self.athlete_id)
        self.assertEqual(review["reference_elapsed_ms"], 1260)

        later = self.db.add_session("10", "yards")
        brief = self.db.athlete_session_intelligence(later, self.athlete_id)
        self.assertEqual(
            brief["prior_carry_forward"]["carry_forward"],
            "Run every sprint the same. Do not think about beating your time.",
        )

    def test_reference_rep_must_match_the_athlete_and_session(self):
        other = self.db.add_athlete("Other")
        other_attempt = self.db.add_attempt(self.session_id, other, 1300)
        with self.assertRaisesRegex(ValueError, "belong"):
            self.db.update_athlete_session_intelligence(
                self.session_id, self.athlete_id, reference_attempt_id=other_attempt,
            )

    def test_attempt_request_key_makes_an_identical_retry_idempotent(self):
        first = self.db.add_attempt(self.session_id, self.athlete_id, 1720, "phone-request-1")
        retry = self.db.add_attempt(self.session_id, self.athlete_id, 1720, "phone-request-1")
        self.assertEqual(retry, first)
        self.assertEqual(len(self.db.all_attempts()), 1)
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.db.add_attempt(self.session_id, self.athlete_id, 1710, "phone-request-1")

    def test_flying_10_session_preserves_protocol_and_planned_attempt_count(self):
        session_id = self.db.add_session(
            "10", "yards", "flying_10_acceleration_5yd_run_in", target_attempts=4,
            surface_type="turf", timing_method="timing-gates", environment="indoor",
            protocol_notes="Cleats",
        )
        session = self.db.session(session_id)
        self.assertEqual(session["protocol_name"], "Flying 10-yard acceleration test with a 5-yard run-in")
        self.assertEqual(session["protocol_alias"], "10-yard sprint")
        self.assertEqual(
            (session["total_distance"], session["timed_distance"], session["run_in_distance"]),
            ("15", "10", "5"),
        )
        self.assertEqual((session["timed_segment"], session["start_type"], session["purpose"]),
                         ("5–15 yards", "two-point", "acceleration"))
        self.assertEqual(session["target_attempts"], 4)
        self.assertEqual(
            (session["surface_type"], session["timing_method"], session["environment"], session["protocol_notes"]),
            ("turf", "timing-gates", "indoor", "Cleats"),
        )

    def test_surface_and_timing_method_separate_comparison_sets(self):
        turf = self.db.add_session("10", "yards", surface_type="turf", timing_method="timing-gates")
        track = self.db.add_session("10", "yards", surface_type="track", timing_method="timing-gates")
        hand_timed = self.db.add_session("10", "yards", surface_type="turf", timing_method="hand-timed")
        for session_id, elapsed_ms in ((turf, 1800), (track, 1750), (hand_timed, 1700)):
            self.db.add_attempt(session_id, self.athlete_id, elapsed_ms)
        self.assertEqual([row["status"] for row in classify_attempts(self.db.all_attempts())],
                         ["baseline", "baseline", "baseline"])

    def test_unknown_protocol_is_not_silently_comparable_with_flying_10(self):
        known = self.db.add_session("10", "yards", "flying_10_acceleration_5yd_run_in")
        unknown = self.db.add_session("10", "yards", None)
        self.db.add_attempt(known, self.athlete_id, 1800)
        self.db.add_attempt(unknown, self.athlete_id, 1700)
        self.assertEqual([row["status"] for row in classify_attempts(self.db.all_attempts())],
                         ["baseline", "baseline"])
        reopened = Database(self.path)
        reopened.initialize()
        self.assertTrue(reopened.session(unknown)["protocol_key"].startswith("unspecified-session:"))

    def test_edit_and_delete_recalculate_derived_status(self):
        first = self.db.add_attempt(self.session_id, self.athlete_id, 1800)
        second = self.db.add_attempt(self.session_id, self.athlete_id, 1750)
        self.assertEqual([a["status"] for a in classify_attempts(self.db.all_attempts())], ["baseline", "pr"])
        self.db.update_attempt(first, 1700)
        self.assertEqual([a["status"] for a in classify_attempts(self.db.all_attempts())], ["baseline", "attempt"])
        self.db.delete_attempt(first)
        remaining = classify_attempts(self.db.all_attempts())
        self.assertEqual([(a["id"], a["status"]) for a in remaining], [(second, "baseline")])

    def test_session_best_is_derived_after_edit_and_delete(self):
        first = self.db.add_attempt(self.session_id, self.athlete_id, 1800)
        second = self.db.add_attempt(self.session_id, self.athlete_id, 1750)
        self.assertEqual(min(a["elapsed_ms"] for a in self.db.all_attempts()), 1750)
        self.db.update_attempt(second, 1850)
        self.assertEqual(min(a["elapsed_ms"] for a in self.db.all_attempts()), 1800)
        self.db.delete_attempt(first)
        self.assertEqual(min(a["elapsed_ms"] for a in self.db.all_attempts()), 1850)

    def test_training_group_roster_order_persists_across_sessions_and_restart(self):
        group_id = self.db.add_group("Sprint Group A")
        first = self.db.add_group_athlete(group_id, "Hudson")
        second = self.db.add_group_athlete(group_id, "James")
        first_session = self.db.add_group_session(group_id, "10", "yards")
        second_session = self.db.add_group_session(group_id, "20", "yards")

        reopened = Database(self.path)
        self.assertEqual([a["id"] for a in reopened.group_roster(group_id)], [first, second])
        self.assertEqual([a["id"] for a in reopened.session_athletes(first_session)], [first, second])
        self.assertEqual([a["id"] for a in reopened.session_athletes(second_session)], [first, second])
        self.assertEqual(reopened.session_group(first_session)["name"], "Sprint Group A")

    def test_group_session_rejects_athlete_outside_its_roster(self):
        group_id = self.db.add_group("Sprint Group B")
        member_id = self.db.add_group_athlete(group_id, "Peter")
        session_id = self.db.add_group_session(group_id, "10", "meters")
        outsider_id = self.db.add_athlete("Outside Athlete")

        self.db.add_attempt(session_id, member_id, 1800)
        with self.assertRaisesRegex(ValueError, "from this session roster"):
            self.db.add_attempt(session_id, outsider_id, 1750)

    def test_session_roster_does_not_change_after_later_group_addition(self):
        group_id = self.db.add_group("Stable Roster")
        original_id = self.db.add_group_athlete(group_id, "Original Athlete")
        session_id = self.db.add_group_session(group_id, "10", "yards")
        later_id = self.db.add_group_athlete(group_id, "Later Athlete")

        self.assertEqual([a["id"] for a in self.db.session_athletes(session_id)], [original_id])
        with self.assertRaisesRegex(ValueError, "from this session roster"):
            self.db.add_attempt(session_id, later_id, 1750)

    def test_session_roster_survives_group_removal_and_reordering(self):
        group_id = self.db.add_group("Changing Group")
        first_id = self.db.add_group_athlete(group_id, "First Athlete")
        second_id = self.db.add_group_athlete(group_id, "Second Athlete")
        session_id = self.db.add_group_session(group_id, "10", "yards")

        with self.db.connect() as connection:
            connection.execute(
                "DELETE FROM training_group_members WHERE group_id=? AND athlete_id=?", (group_id, first_id)
            )
            connection.execute(
                "UPDATE training_group_members SET position=1 WHERE group_id=? AND athlete_id=?", (group_id, second_id)
            )

        self.assertEqual(
            [(a["id"], a["position"]) for a in self.db.session_athletes(session_id)],
            [(first_id, 1), (second_id, 2)],
        )
        self.db.add_attempt(session_id, first_id, 1800)

    def test_roster_can_reorder_copy_move_and_remove_without_changing_session_snapshot(self):
        source = self.db.add_group("Source")
        target = self.db.add_group("Target")
        first = self.db.add_group_athlete(source, "First")
        second = self.db.add_group_athlete(source, "Second")
        session_id = self.db.add_group_session(source, "10", "yards")

        self.db.reorder_group_athlete(source, second, "up")
        self.assertEqual([a["id"] for a in self.db.group_roster(source)], [second, first])
        self.db.transfer_group_athlete(source, first, target, move=False)
        self.db.transfer_group_athlete(source, second, target, move=True)
        self.assertEqual([a["id"] for a in self.db.group_roster(source)], [first])
        self.assertEqual([a["id"] for a in self.db.group_roster(target)], [first, second])
        self.db.remove_group_athlete(target, first)
        self.assertEqual([a["id"] for a in self.db.group_roster(target)], [second])
        self.assertEqual([a["id"] for a in self.db.session_roster(session_id)], [first, second])

    def test_existing_athlete_can_join_another_group_without_changing_snapshot(self):
        source = self.db.add_group("Source")
        target = self.db.add_group("Target")
        athlete_id = self.db.add_group_athlete(source, "Jordan Lee")
        session_id = self.db.add_group_session(target, "10", "yards")

        self.db.add_existing_group_athlete(target, athlete_id)

        self.assertEqual([a["id"] for a in self.db.group_roster(target)], [athlete_id])
        self.assertEqual(self.db.session_roster(session_id), [])
        directory = self.db.athlete_directory()
        jordan = next(item for item in directory if item["id"] == athlete_id)
        self.assertEqual([group["name"] for group in jordan["groups"]], ["Source", "Target"])
        with self.assertRaisesRegex(ValueError, "already in"):
            self.db.add_existing_group_athlete(target, athlete_id)

    def test_group_creation_blocks_exact_existing_athlete_name(self):
        first = self.db.add_group("First")
        second = self.db.add_group("Second")
        self.db.add_group_athlete(first, "Jordan Lee")

        with self.assertRaisesRegex(ValueError, "already exists"):
            self.db.create_group_athlete(second, "jordan lee")

    def test_late_athlete_is_added_to_active_session_and_future_group_roster_only(self):
        group_id = self.db.add_group("Late Athlete Group")
        original = self.db.add_group_athlete(group_id, "Original Runner")
        earlier_session = self.db.add_group_session(group_id, "10", "yards")
        active_session = self.db.add_group_session(group_id, "10", "yards")

        late = self.db.add_session_athlete(active_session, "  Late Runner  ")

        self.assertEqual([a["id"] for a in self.db.session_athletes(earlier_session)], [original])
        self.assertEqual([a["id"] for a in self.db.session_athletes(active_session)], [original, late])
        self.assertEqual([a["id"] for a in self.db.group_roster(group_id)], [original, late])

    def test_existing_athlete_can_join_active_session_without_new_profile(self):
        source = self.db.add_group("Source")
        target = self.db.add_group("Target")
        existing = self.db.add_group_athlete(source, "Jordan Lee")
        session_id = self.db.add_group_session(target, "10", "yards")
        athlete_count = len(self.db.all_athletes())

        self.db.add_existing_session_athlete(session_id, existing)

        self.assertEqual([athlete["id"] for athlete in self.db.session_roster(session_id)], [existing])
        self.assertEqual([athlete["id"] for athlete in self.db.group_roster(target)], [existing])
        self.assertEqual(len(self.db.all_athletes()), athlete_count)
        with self.assertRaisesRegex(ValueError, "already in"):
            self.db.add_existing_session_athlete(session_id, existing)

    def test_existing_group_member_can_join_active_snapshot(self):
        group_id = self.db.add_group("Active Group")
        existing = self.db.add_group_athlete(group_id, "Jordan Lee")
        session_id = self.db.add_group_session(group_id, "10", "yards")
        with self.db.connect() as connection:
            connection.execute(
                "DELETE FROM session_roster_members WHERE session_id=? AND athlete_id=?",
                (session_id, existing),
            )

        self.db.add_existing_session_athlete(session_id, existing)

        self.assertEqual([athlete["id"] for athlete in self.db.group_roster(group_id)], [existing])
        self.assertEqual([athlete["id"] for athlete in self.db.session_roster(session_id)], [existing])

    def test_completed_session_closes_roster_and_attempt_mutation(self):
        group_id = self.db.add_group("Completed Group")
        athlete_id = self.db.add_group_athlete(group_id, "Runner")
        session_id = self.db.add_group_session(group_id, "10", "yards")
        attempt_id = self.db.add_attempt(session_id, athlete_id, 1700)

        self.db.complete_session(session_id)

        session = self.db.session(session_id)
        self.assertEqual(session["status"], "completed")
        self.assertTrue(session["completed_at"])
        with self.assertRaisesRegex(ValueError, "Completed|completed"):
            self.db.add_session_athlete(session_id, "Late Runner")
        with self.assertRaisesRegex(ValueError, "Completed|completed"):
            self.db.add_existing_session_athlete(session_id, athlete_id)
        with self.assertRaisesRegex(ValueError, "completed"):
            self.db.add_attempt(session_id, athlete_id, 1650)
        with self.assertRaisesRegex(ValueError, "completed"):
            self.db.update_attempt(attempt_id, 1600)
        with self.assertRaisesRegex(ValueError, "completed"):
            self.db.delete_attempt(attempt_id)

    def test_delete_session_removes_attempts_and_snapshot_but_preserves_group_roster(self):
        group_id = self.db.add_group("Deletion Group")
        athlete_id = self.db.add_group_athlete(group_id, "Runner")
        session_id = self.db.add_group_session(group_id, "10", "yards")
        self.db.add_attempt(session_id, athlete_id, 1700)

        returned_group = self.db.delete_session(session_id)

        self.assertEqual(returned_group, group_id)
        self.assertIsNone(self.db.session(session_id))
        self.assertEqual(self.db.all_attempts(), [])
        self.assertEqual([a["id"] for a in self.db.group_roster(group_id)], [athlete_id])
        with self.db.connect() as connection:
            self.assertIsNone(connection.execute(
                "SELECT 1 FROM session_roster_snapshots WHERE session_id=?", (session_id,)
            ).fetchone())

    def test_legacy_group_session_is_backfilled_once_without_overwrite(self):
        group_id = self.db.add_group("Legacy Group")
        first_id = self.db.add_group_athlete(group_id, "First Athlete")
        session_id = self.db.add_group_session(group_id, "10", "yards")

        with self.db.connect() as connection:
            connection.execute("DELETE FROM session_roster_snapshots WHERE session_id=?", (session_id,))
        second_id = self.db.add_group_athlete(group_id, "Present At Backfill")

        reopened = Database(self.path)
        reopened.initialize()
        self.assertEqual([a["id"] for a in reopened.session_athletes(session_id)], [first_id, second_id])

        reopened.add_group_athlete(group_id, "Added After Backfill")
        reopened_again = Database(self.path)
        reopened_again.initialize()
        self.assertEqual([a["id"] for a in reopened_again.session_athletes(session_id)], [first_id, second_id])

    def test_feedback_persists_with_optional_group_and_session_context(self):
        group_id = self.db.add_group("Feedback Group")
        session_id = self.db.add_group_session(group_id, "20", "meters")
        self.db.add_feedback("Athlete switching", "Fast save", "Queue", group_id, session_id)

        reopened = Database(self.path)
        feedback = reopened.all_feedback()[0]
        self.assertTrue(feedback["created_at"])
        self.assertEqual(feedback["group_name"], "Feedback Group")
        self.assertEqual(feedback["session_id"], session_id)
        self.assertEqual(feedback["slowed_down"], "Athlete switching")

    def test_feedback_supports_group_only_and_session_only_context(self):
        group_id = self.db.add_group("Optional Context Group")
        group_feedback_id = self.db.add_feedback("Group only", "", "", group_id=group_id)
        session_feedback_id = self.db.add_feedback("Session only", "", "", session_id=self.session_id)

        feedback = {entry["id"]: entry for entry in self.db.all_feedback()}
        self.assertEqual(feedback[group_feedback_id]["group_id"], group_id)
        self.assertIsNone(feedback[group_feedback_id]["session_id"])
        self.assertIsNone(feedback[session_feedback_id]["group_id"])
        self.assertEqual(feedback[session_feedback_id]["session_id"], self.session_id)

    def test_feedback_requires_a_response_and_valid_context(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            self.db.add_feedback("", "  ", "")
        with self.assertRaisesRegex(LookupError, "Training Group"):
            self.db.add_feedback("Slow", "", "", group_id=99999)

    def test_feedback_rejects_session_from_another_group(self):
        selected_group = self.db.add_group("Selected Group")
        other_group = self.db.add_group("Other Group")
        other_session = self.db.add_group_session(other_group, "10", "yards")

        with self.assertRaisesRegex(ValueError, "does not belong"):
            self.db.add_feedback("Wrong context", "", "", selected_group, other_session)


if __name__ == "__main__":
    unittest.main()
