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


if __name__ == "__main__":
    unittest.main()
