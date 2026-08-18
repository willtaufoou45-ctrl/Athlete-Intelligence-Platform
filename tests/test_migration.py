import tempfile
import unittest
from pathlib import Path

from aip.database import Database
from scripts.migrate_sqlite_to_postgres import source_manifest


class MigrationManifestTests(unittest.TestCase):
    def test_manifest_records_counts_and_stable_digest_without_athlete_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backup.sqlite3"
            database = Database(path)
            database.initialize()
            database.add_athlete("Private Athlete Name")
            first = source_manifest(path)
            second = source_manifest(path)
            self.assertEqual(first, second)
            self.assertEqual(first["tables"]["athletes"]["count"], 1)
            self.assertEqual(first["derived"]["count"], 0)
            self.assertNotIn("Private Athlete Name", json_text(first))


def json_text(value):
    import json
    return json.dumps(value)


if __name__ == "__main__":
    unittest.main()
