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
