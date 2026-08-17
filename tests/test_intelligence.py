import sqlite3
import tempfile
import unittest
import uuid
import io
import json
from pathlib import Path

from aip.database import Database
from aip.web import create_app


class AthleteIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "intelligence.sqlite3"
        self.db = Database(self.path)
        self.db.initialize()

    def tearDown(self):
        self.tempdir.cleanup()

    def add_verified_brody_sources(self):
        with self.db.connect() as connection:
            connection.execute("INSERT INTO athletes(id,name) VALUES (7,'Brody Bradford')")
            connection.execute("INSERT INTO training_groups(id,name) VALUES (3,'Bradford’s')")
            connection.execute(
                "INSERT INTO training_group_members(group_id,athlete_id,position) VALUES (3,7,2)"
            )
            for session_id, distance, session_date in (
                (5, "15", "2026-08-04"), (16, "10", "2026-08-13"),
            ):
                connection.execute(
                    """INSERT INTO sprint_capture_sessions(id,distance,unit,status,session_date)
                       VALUES (?,?,'yards','completed',?)""",
                    (session_id, distance, session_date),
                )
                connection.execute(
                    "INSERT INTO training_group_sessions(group_id,session_id) VALUES (3,?)",
                    (session_id,),
                )
                connection.execute(
                    "INSERT INTO session_roster_snapshots(session_id) VALUES (?)", (session_id,)
                )
                connection.execute(
                    """INSERT INTO session_roster_members(session_id,athlete_id,position)
                       VALUES (?,7,2)""",
                    (session_id,),
                )
            for attempt_id, session_id, elapsed_ms in (
                (19, 5, 1320), (20, 5, 1330), (21, 5, 1270), (22, 5, 1290), (23, 5, 1260),
                (184, 16, 1340), (185, 16, 1360), (186, 16, 1340), (187, 16, 1320),
            ):
                connection.execute(
                    """INSERT INTO sprint_attempts(id,session_id,athlete_id,elapsed_ms)
                       VALUES (?,?,7,?)""",
                    (attempt_id, session_id, elapsed_ms),
                )

    def test_canonical_athlete_creation_uses_stable_uuid(self):
        athlete_id = self.db.add_canonical_athlete("Case Athlete")
        reopened = Database(self.path)

        self.assertEqual(str(uuid.UUID(athlete_id)), athlete_id)
        self.assertEqual(reopened.canonical_athlete(athlete_id)["id"], athlete_id)

    def test_external_source_identity_can_map_to_only_one_canonical_athlete(self):
        first = self.db.add_canonical_athlete("First")
        second = self.db.add_canonical_athlete("Second")
        self.db.add_external_identity(first, "repbook", "lifter", "5", verified=True)

        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_external_identity(second, "repbook", "lifter", "5", verified=True)

    def test_sprint_source_identity_can_map_to_only_one_canonical_athlete(self):
        first = self.db.add_canonical_athlete("First")
        second = self.db.add_canonical_athlete("Second")
        self.db.add_external_identity(first, "sprint_capture", "athlete", "9", verified=True)

        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_external_identity(second, "sprint_capture", "athlete", "9", verified=True)

    def test_athlete_state_history_is_appended_not_overwritten(self):
        athlete_id = self.db.add_canonical_athlete("State Athlete")
        first = self.db.add_athlete_state(athlete_id, "offseason", effective_from="2026-01")
        second = self.db.add_athlete_state(athlete_id, "in_season", effective_from="2026-08")

        states = self.db.intelligence_snapshot(athlete_id)["states"]
        self.assertEqual([row["id"] for row in states], [first, second])
        self.assertEqual([row["state_type"] for row in states], ["offseason", "in_season"])

    def test_intelligence_record_supersession_preserves_history(self):
        athlete_id = self.db.add_canonical_athlete("Learning Athlete")
        prior = self.db.add_intelligence_record(
            athlete_id, "focus", "Drive is primary.", "active", confidence="high"
        )
        current = self.db.add_intelligence_record(
            athlete_id, "focus", "Load is primary.", "active", confidence="high",
            supersedes_record_id=prior,
        )

        records = {row["id"]: row for row in self.db.intelligence_snapshot(athlete_id)["records"]}
        self.assertEqual(records[prior]["status"], "superseded")
        self.assertEqual(records[current]["supersedes_record_id"], prior)

    def test_v02_semantics_preserve_epistemic_and_temporal_context(self):
        athlete_id = self.db.add_canonical_athlete("Temporal Athlete")
        record_id = self.db.add_intelligence_record(
            athlete_id, "relationship", "Exposure may affect force strategy.", "active",
            confidence="moderate", epistemic_class="hypothesis",
            first_observed_at="2026-03", effective_from="2026-03",
            freshness_review_at="2026-09",
        )
        evidence_id = self.db.add_evidence(
            athlete_id, "training_exposure", "coach_case_study", "athlete_report", "report-1",
            observed_at="2026-03-15T10:00:00", observed_date="2026-03-15",
            source_version_or_digest="digest-1", metadata={"source_role": "athlete"},
        )
        self.db.link_intelligence_evidence(record_id, evidence_id, "contextualizes")

        snapshot = self.db.intelligence_snapshot(athlete_id)
        record = snapshot["records"][0]
        evidence = snapshot["evidence"][0]
        self.assertEqual(record["epistemic_class"], "hypothesis")
        self.assertEqual(record["first_observed_at"], "2026-03")
        self.assertEqual(record["effective_from"], "2026-03")
        self.assertEqual(record["freshness_review_at"], "2026-09")
        self.assertEqual(evidence["evidence_type"], "training_exposure")
        self.assertEqual(evidence["observed_at"], "2026-03-15T10:00:00")
        self.assertEqual(evidence["source_version_or_digest"], "digest-1")
        self.assertEqual(snapshot["links"][0]["relationship_type"], "contextualizes")

    def test_v02_semantic_values_are_validated(self):
        athlete_id = self.db.add_canonical_athlete("Validation Athlete")
        with self.assertRaises(ValueError):
            self.db.add_intelligence_record(
                athlete_id, "observation", "Invalid class.", "active",
                epistemic_class="opinion",
            )
        with self.assertRaises(ValueError):
            self.db.add_evidence(
                athlete_id, "unsupported_evidence", "source", "record", "1"
            )

    def test_evidence_and_intelligence_are_separate_and_many_to_many(self):
        athlete_id = self.db.add_canonical_athlete("Evidence Athlete")
        first_record = self.db.add_intelligence_record(athlete_id, "observation", "Observed change.", "confirmed")
        second_record = self.db.add_intelligence_record(athlete_id, "open_question", "Will it persist?", "active")
        first_evidence = self.db.add_evidence(
            athlete_id, "sprint_session", "sprint_capture", "sprint_capture_session", "6"
        )
        second_evidence = self.db.add_evidence(
            athlete_id, "workout_session", "repbook", "workout_session", "20"
        )
        self.db.link_intelligence_evidence(first_record, first_evidence, "supports")
        self.db.link_intelligence_evidence(first_record, second_evidence, "supports")
        self.db.link_intelligence_evidence(second_record, first_evidence, "motivated_by")

        snapshot = self.db.intelligence_snapshot(athlete_id)
        self.assertEqual(len(snapshot["records"]), 2)
        self.assertEqual(len(snapshot["evidence"]), 2)
        self.assertEqual(len(snapshot["links"]), 3)
        self.assertNotIn("statement", snapshot["evidence"][0])
        self.assertNotIn("source_record_id", snapshot["records"][0])

    def test_rigby_seed_is_idempotent_and_maps_verified_source_ids(self):
        for number in range(1, 9):
            self.db.add_athlete(f"Placeholder {number}")
        self.assertEqual(self.db.add_athlete("Rigby young"), 9)

        first = self.db.seed_rigby_intelligence()
        second = self.db.seed_rigby_intelligence()
        snapshot = self.db.intelligence_snapshot(first)

        self.assertEqual(first, second)
        self.assertEqual(snapshot["athlete"]["display_name"], "Rigby Young")
        mappings = {
            (row["source_system"], row["source_entity_type"], row["source_record_id"])
            for row in snapshot["external_identities"]
        }
        self.assertEqual(mappings, {("sprint_capture", "athlete", "9"), ("repbook", "lifter", "5")})
        self.assertTrue(all(row["verified_at"] for row in snapshot["external_identities"]))
        self.assertEqual(snapshot["states"][0]["state_type"], "in_season")
        self.assertEqual(
            {(row["source_system"], row["source_record_id"]) for row in snapshot["evidence"]},
            {("repbook", "20")},
        )

    def test_brody_seed_creates_verified_identity_states_and_is_idempotent(self):
        self.add_verified_brody_sources()

        first = self.db.seed_brody_intelligence()
        counts_before = self.db.intelligence_snapshot(first)
        second = self.db.seed_brody_intelligence()
        counts_after = self.db.intelligence_snapshot(second)

        self.assertEqual(first, second)
        self.assertEqual(str(uuid.UUID(first)), first)
        self.assertEqual(counts_before, counts_after)
        self.assertEqual(counts_after["athlete"]["display_name"], "Brody Bradford")
        self.assertEqual(len(counts_after["external_identities"]), 1)
        identity = counts_after["external_identities"][0]
        self.assertEqual(
            (identity["source_system"], identity["source_entity_type"], identity["source_record_id"]),
            ("sprint_capture", "athlete", "7"),
        )
        self.assertTrue(identity["verified_at"])
        self.assertEqual(
            [state["state_type"] for state in counts_after["states"]],
            ["offseason", "in_season", "offseason"],
        )
        self.assertEqual(
            [(state["effective_from"], state["effective_to"]) for state in counts_after["states"]],
            [("2025-07", "2025-10"), ("2025-10", "2026-03"), ("2026-03", None)],
        )

    def test_brody_v02_records_preserve_epistemic_hypotheses_and_evidence_gap(self):
        self.add_verified_brody_sources()
        athlete_id = self.db.seed_brody_intelligence()
        snapshot = self.db.intelligence_snapshot(athlete_id)

        hypotheses = [
            row for row in snapshot["records"] if row["epistemic_class"] == "hypothesis"
        ]
        self.assertEqual(len(hypotheses), 4)
        self.assertTrue(all(row["status"] == "active" for row in hypotheses))
        gap = next(
            row for row in snapshot["records"]
            if row["statement"].startswith("No regular ACE force or sprint testing")
        )
        self.assertEqual((gap["type"], gap["epistemic_class"], gap["status"]),
                         ("observation", "unknown", "historical"))
        self.assertEqual((gap["effective_from"], gap["effective_to"]),
                         ("2025-10", "2026-03"))
        coach_learning = next(
            row for row in snapshot["records"]
            if row["statement"].startswith("After reviewing Offseason 1")
        )
        self.assertEqual(coach_learning["epistemic_class"], "interpretation")
        self.assertEqual(coach_learning["first_observed_at"], "2026-03")
        self.assertEqual((coach_learning["effective_from"], coach_learning["effective_to"]),
                         ("2025-07", "2025-10"))
        open_questions = [
            row for row in snapshot["records"] if row["type"] == "open_question"
        ]
        self.assertEqual(len(open_questions), 6)
        self.assertTrue(all(row["status"] == "active" for row in open_questions))
        self.assertTrue(all(row["epistemic_class"] == "unknown" for row in open_questions))

    def test_brody_evidence_preserves_force_scan_and_sprint_comparability_identity(self):
        self.add_verified_brody_sources()
        athlete_id = self.db.seed_brody_intelligence()
        snapshot = self.db.intelligence_snapshot(athlete_id)

        force = [row for row in snapshot["evidence"] if row["evidence_type"] == "force_test"]
        self.assertEqual(len(force), 11)
        april = [row for row in force if row["observed_date"] == "2026-04-19"]
        self.assertEqual(
            {row["source_record_id"] for row in april},
            {"8805cba3-0a57-416b-9805-0c7f01917fda", "86a67012-7152-44dd-a4c9-63227b4b2976"},
        )
        self.assertTrue(all(row["source_system"] == "force_sheet" for row in force))
        self.assertTrue(all("jump_height" in json.loads(row["metadata"])["metric_family"] for row in force))

        sprint = [row for row in snapshot["evidence"] if row["evidence_type"] == "sprint_result"]
        self.assertEqual(len(sprint), 9)
        sprint_contexts = {
            (json.loads(row["metadata"])["distance"], json.loads(row["metadata"])["unit"])
            for row in sprint
        }
        self.assertEqual(sprint_contexts, {(10, "yards"), (15, "yards")})
        for row in sprint:
            metadata = json.loads(row["metadata"])
            self.assertEqual(metadata["timing_method"], "unknown")
            self.assertEqual(metadata["protocol"], "unknown")
        fifteen_ids = {
            row["source_record_id"] for row in sprint
            if json.loads(row["metadata"])["distance"] == 15
        }
        ten_ids = {
            row["source_record_id"] for row in sprint
            if json.loads(row["metadata"])["distance"] == 10
        }
        self.assertEqual(fifteen_ids, {"19", "20", "21", "22", "23"})
        self.assertEqual(ten_ids, {"184", "185", "186", "187"})

    def test_brody_training_context_contextualizes_without_confirming_hypothesis(self):
        self.add_verified_brody_sources()
        athlete_id = self.db.seed_brody_intelligence()
        snapshot = self.db.intelligence_snapshot(athlete_id)
        evidence_by_id = {row["id"]: row for row in snapshot["evidence"]}
        records_by_id = {row["id"]: row for row in snapshot["records"]}

        exposure = [
            row for row in snapshot["evidence"] if row["evidence_type"] == "training_exposure"
        ]
        self.assertEqual(len(exposure), 2)
        self.assertTrue(all(json.loads(row["metadata"])["source_role"] == "coach" for row in exposure))
        contextual_links = [
            link for link in snapshot["links"] if link["relationship_type"] == "contextualizes"
        ]
        self.assertTrue(contextual_links)
        exposure_ids = {row["id"] for row in exposure}
        self.assertTrue(any(link["evidence_id"] in exposure_ids for link in contextual_links))
        linked_hypotheses = [
            records_by_id[link["intelligence_record_id"]]
            for link in contextual_links
            if records_by_id[link["intelligence_record_id"]]["epistemic_class"] == "hypothesis"
        ]
        self.assertTrue(linked_hypotheses)
        self.assertTrue(all(row["status"] == "active" for row in linked_hypotheses))
        self.assertTrue(all(evidence_by_id[link["evidence_id"]] for link in contextual_links))

    def test_brody_seed_leaves_existing_rigby_snapshot_unchanged(self):
        self.add_verified_brody_sources()
        with self.db.connect() as connection:
            for athlete_id in (1, 2, 3, 4, 5, 6, 8):
                connection.execute(
                    "INSERT INTO athletes(id,name) VALUES (?,?)",
                    (athlete_id, f"Placeholder {athlete_id}"),
                )
            connection.execute("INSERT INTO athletes(id,name) VALUES (9,'Rigby young')")
        rigby_id = self.db.seed_rigby_intelligence()
        rigby_before = self.db.intelligence_snapshot(rigby_id)

        self.db.seed_brody_intelligence()

        self.assertEqual(self.db.intelligence_snapshot(rigby_id), rigby_before)

    def test_brody_internal_inspection_is_read_only_and_shows_v02_semantics(self):
        self.add_verified_brody_sources()
        athlete_id = self.db.seed_brody_intelligence()
        app = create_app(self.path)
        before = self.db.intelligence_snapshot(athlete_id)
        response = {}

        def start(status, headers):
            response["status"] = status
            response["headers"] = headers

        body = b"".join(app({
            "REQUEST_METHOD": "GET", "PATH_INFO": "/internal/intelligence/brody",
            "CONTENT_LENGTH": "0", "REMOTE_ADDR": "127.0.0.1", "wsgi.input": io.BytesIO(),
        }, start))

        self.assertEqual(response["status"], "200 OK")
        self.assertIn(b"Case Study 002", body)
        self.assertIn(b"Brody Bradford", body)
        self.assertIn(b"hypothesis", body)
        self.assertIn(b"Active open questions", body)
        self.assertEqual(self.db.intelligence_snapshot(athlete_id), before)

    def test_internal_inspection_route_is_read_only(self):
        for number in range(1, 9):
            self.db.add_athlete(f"Placeholder {number}")
        self.db.add_athlete("Rigby young")
        athlete_id = self.db.seed_rigby_intelligence()
        app = create_app(self.path)
        before = self.db.intelligence_snapshot(athlete_id)
        response = {}

        def start(status, headers):
            response["status"] = status
            response["headers"] = headers

        body = b"".join(app({
            "REQUEST_METHOD": "GET", "PATH_INFO": "/internal/intelligence/rigby",
            "CONTENT_LENGTH": "0", "REMOTE_ADDR": "127.0.0.1", "wsgi.input": io.BytesIO(),
        }, start))

        self.assertEqual(response["status"], "200 OK")
        self.assertIn(b"Case Study 001", body)
        self.assertIn(athlete_id.encode(), body)
        self.assertEqual(self.db.intelligence_snapshot(athlete_id), before)


if __name__ == "__main__":
    unittest.main()
