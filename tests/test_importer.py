import tempfile
import unittest
from pathlib import Path

from aip.database import Database
from aip.domain import classify_attempts
from aip.importer import build_preview, confirm_import


def summit_csv(*rows):
    return ("Summit Football historical results\n" + "First Name,Last Name,FASTEST,initial 10,Qtr Rev,1/15/2024,2/20/2024\n" +
            "\n".join(rows) + "\n").encode()


class HistoricalImportTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "test.sqlite3"
        self.db = Database(self.path)
        self.db.initialize()
        self.group_id = self.db.add_group("Summit Football")
        self.jordan_id = self.db.add_group_athlete(self.group_id, "Jordan Lee")

    def tearDown(self):
        self.tempdir.cleanup()

    def preview(self, payload=None, year=None):
        return build_preview(self.db, payload or summit_csv(" Jordan , LEE ,1.69,1.8,note,1.72,1.68"),
                             "summit.csv", self.group_id, "10.0", "yards", year)

    def test_detects_two_row_header_dates_and_skips_summary_columns_without_writes(self):
        before = (len(self.db.all_sessions()), len(self.db.all_attempts()), len(self.db.all_athletes()))
        preview = self.preview()
        self.assertEqual(preview["header_row"], 2)
        self.assertEqual([column["date"] for column in preview["date_columns"]], ["2024-01-15", "2024-02-20"])
        self.assertEqual([column["label"] for column in preview["skipped_columns"]], ["FASTEST", "initial 10", "Qtr Rev"])
        self.assertEqual(preview["athletes"][0]["status"], "matched")
        self.assertEqual([result["elapsed_ms"] for result in preview["results"]], [1720, 1680])
        self.assertEqual(before, (len(self.db.all_sessions()), len(self.db.all_attempts()), len(self.db.all_athletes())))

    def test_month_day_headers_require_an_explicit_year(self):
        payload = b"First Name,Last Name,1/15\nJordan,Lee,1.72\n"
        with self.assertRaisesRegex(ValueError, "No usable testing-date"):
            self.preview(payload)
        preview = self.preview(payload, 2023)
        self.assertEqual(preview["date_columns"][0]["date"], "2023-01-15")

    def test_invalid_times_and_duplicate_dates_are_reported_with_positions(self):
        payload = b"First Name,Last Name,2024-01-15,01/15/2024,2024-02-30\nJordan,Lee,fast,1.72,1.80\n"
        preview = self.preview(payload)
        kinds = {issue["kind"] for issue in preview["issues"]}
        self.assertEqual(kinds, {"duplicate_date", "invalid_date", "invalid_time"})
        invalid = next(issue for issue in preview["issues"] if issue["kind"] == "invalid_time")
        self.assertEqual((invalid["row"], invalid["column"]), (2, 3))

    def test_exact_unmatched_and_ambiguous_identity_paths_do_not_fuzzy_match(self):
        self.db.add_group_athlete(self.group_id, "JORDAN   LEE")
        payload = b"First Name,Last Name,2024-01-15\nJordan,Lee,1.72\nJordyn,Lee,1.80\nNew,Runner,1.90\n"
        preview = self.preview(payload)
        self.assertEqual([athlete["status"] for athlete in preview["athletes"]],
                         ["ambiguous", "unmatched", "unmatched"])

    def test_confirmation_creates_sessions_rosters_attempts_and_provenance_atomically(self):
        payload = summit_csv("Jordan,Lee,,,,1.80,1.70", "New,Runner,,,,1.90,1.85")
        preview = self.preview(payload)
        summary = confirm_import(self.db, preview, {4: "create"}, {})
        self.assertEqual(summary["sessions_created"], 2)
        self.assertEqual(summary["created_athletes"], 1)
        self.assertEqual(summary["attempts_created"], 4)
        self.assertEqual(len(self.db.import_results(summary["batch_id"])), 4)
        for session_id in summary["session_ids_created"]:
            self.assertEqual([item["name"] for item in self.db.session_roster(session_id)],
                             ["Jordan Lee", "New Runner"])

    def test_identical_upload_is_blocked_and_changed_upload_skips_provenance_duplicates(self):
        payload = summit_csv("Jordan,Lee,,,,1.80,1.70")
        first = self.preview(payload)
        confirm_import(self.db, first, {}, {})
        with self.assertRaisesRegex(ValueError, "identical file"):
            confirm_import(self.db, first, {}, {})

        changed = payload + b"\n"
        changed_preview = self.preview(changed)
        self.assertTrue(all(result["possible_duplicate"] for result in changed_preview["results"]))
        summary = confirm_import(self.db, changed_preview, {}, {})
        self.assertEqual(summary["attempts_created"], 0)
        self.assertEqual(summary["duplicates_skipped"], 2)

    def test_existing_live_session_conflict_requires_explicit_resolution(self):
        session_id = self.db.add_group_session(self.group_id, "10", "yards")
        with self.db.connect() as connection:
            connection.execute("UPDATE sprint_capture_sessions SET created_at='2024-01-15 09:00:00' WHERE id=?", (session_id,))
        preview = self.preview(summit_csv("Jordan,Lee,,,,1.72,"))
        self.assertEqual(preview["conflicts"][0]["sessions"][0]["id"], session_id)
        with self.assertRaisesRegex(ValueError, "Resolve the existing-session conflict"):
            confirm_import(self.db, preview, {}, {})
        summary = confirm_import(self.db, preview, {}, {"2024-01-15": "separate"})
        self.assertEqual(summary["sessions_created"], 1)

    def test_session_with_imported_and_manual_attempts_remains_an_explicit_conflict(self):
        first = confirm_import(self.db, self.preview(summit_csv("Jordan,Lee,,,,1.72,")), {}, {})
        imported_session = first["session_ids_created"][0]
        self.db.add_attempt(imported_session, self.jordan_id, 1710)
        changed = self.preview(summit_csv("Jordan,Lee,,,,1.72,1.68"))
        conflict = next(item for item in changed["conflicts"] if item["date"] == "2024-01-15")
        self.assertEqual(conflict["sessions"][0]["id"], imported_session)

    def test_reusing_a_live_session_cannot_mutate_its_immutable_roster(self):
        session_id = self.db.add_group_session(self.group_id, "10", "yards")
        with self.db.connect() as connection:
            connection.execute("UPDATE sprint_capture_sessions SET created_at='2024-01-15 09:00:00' WHERE id=?", (session_id,))
        preview = self.preview(b"First Name,Last Name,2024-01-15\nNew,Runner,1.90\n")
        with self.assertRaisesRegex(ValueError, "immutable roster"):
            confirm_import(self.db, preview, {2: "create"}, {"2024-01-15": f"reuse:{session_id}"})
        self.assertEqual([item["name"] for item in self.db.group_roster(self.group_id)], ["Jordan Lee"])

    def test_failure_rolls_back_batch_athletes_memberships_sessions_attempts_and_provenance(self):
        preview = self.preview(summit_csv("Jordan,Lee,,,,1.80,1.70", "New,Runner,,,,1.90,1.85"))
        before_roster = self.db.group_roster(self.group_id)
        with self.assertRaisesRegex(RuntimeError, "Injected"):
            confirm_import(self.db, preview, {4: "create"}, {}, fail_after_attempts=1)
        self.assertEqual(self.db.group_roster(self.group_id), before_roster)
        self.assertEqual(self.db.all_sessions(), [])
        self.assertEqual(self.db.all_attempts(), [])
        with self.db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], 0)

    def test_confirmation_rejects_a_preview_invalidated_by_roster_changes(self):
        preview = self.preview(summit_csv("Jordan,Lee,,,,1.80,"))
        self.db.add_group_athlete(self.group_id, "JORDAN LEE")
        with self.assertRaisesRegex(ValueError, "changed after preview"):
            confirm_import(self.db, preview, {}, {})
        self.assertEqual(self.db.all_attempts(), [])

    def test_imported_attempts_use_existing_chronological_pr_semantics_and_exact_units(self):
        yards = self.preview(summit_csv("Jordan,Lee,,,,1.80,1.70"))
        confirm_import(self.db, yards, {}, {})
        meters_payload = b"First Name,Last Name,2024-03-01\nJordan,Lee,1.75\n"
        meters = build_preview(self.db, meters_payload, "meters.csv", self.group_id, "10", "meters")
        confirm_import(self.db, meters, {}, {})
        attempts = classify_attempts(self.db.all_attempts())
        self.assertEqual([item["status"] for item in attempts], ["baseline", "pr", "baseline"])

    def test_imported_attempts_retain_existing_edit_and_delete_behavior(self):
        summary = confirm_import(self.db, self.preview(summit_csv("Jordan,Lee,,,,1.80,")), {}, {})
        provenance = self.db.import_results(summary["batch_id"])[0]
        self.db.update_attempt(provenance["attempt_id"], 1750)
        self.assertEqual(self.db.all_attempts()[0]["elapsed_ms"], 1750)
        self.db.delete_attempt(provenance["attempt_id"])
        self.assertEqual(self.db.all_attempts(), [])
        retained = self.db.import_results(summary["batch_id"])[0]
        self.assertIsNone(retained["attempt_id"])
        self.assertEqual(retained["source_elapsed_ms"], 1800)


if __name__ == "__main__":
    unittest.main()
