import unittest

from aip.database import MIGRATION_SCHEMA, POSTGRES_SCHEMA_VERSION, SCHEMA
from aip.intelligence import SCHEMA as INTELLIGENCE_SCHEMA
from aip.postgres import postgres_query, postgres_schema


class PostgresCompatibilityTests(unittest.TestCase):
    def test_schema_converts_sqlite_ids_defaults_and_pragmas(self):
        schema = postgres_schema(SCHEMA, INTELLIGENCE_SCHEMA, MIGRATION_SCHEMA)
        self.assertNotIn("PRAGMA", schema)
        self.assertIn("id BIGSERIAL PRIMARY KEY", schema)
        self.assertIn("session_id BIGINT", schema)
        self.assertIn("DEFAULT (CURRENT_DATE::text)", schema)
        self.assertIn("request_key TEXT UNIQUE", schema)
        self.assertEqual(POSTGRES_SCHEMA_VERSION, 3)

    def test_query_converts_parameters_dates_collation_and_utc_timestamp(self):
        query = postgres_query(
            "SELECT * FROM sprint_capture_sessions WHERE date(created_at)=? ORDER BY distance COLLATE NOCASE"
        )
        self.assertIn("CAST(created_at AS DATE)=%s", query)
        self.assertNotIn("NOCASE", query)
        timestamp = postgres_query("UPDATE sprint_capture_sessions SET completed_at=CURRENT_TIMESTAMP")
        self.assertIn("to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC'", timestamp)

    def test_schema_translation_is_not_applied_twice_by_executescript(self):
        class RawConnection:
            def __init__(self):
                self.statements = []

            def execute(self, statement):
                self.statements.append(statement)

        from aip.postgres import Connection
        raw = RawConnection()
        translated = postgres_schema("CREATE TABLE sample (created_at TEXT DEFAULT CURRENT_TIMESTAMP);")
        Connection(raw).executescript(translated)
        self.assertEqual(raw.statements, [translated.rstrip(";")])
        self.assertEqual(raw.statements[0].count("AT TIME ZONE"), 1)


if __name__ == "__main__":
    unittest.main()
