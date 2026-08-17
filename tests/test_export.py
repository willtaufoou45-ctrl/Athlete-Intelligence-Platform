import csv
import io
import tempfile
import unittest
from pathlib import Path

from aip.export import CSV_HEADERS
from aip.web import create_app


class SprintExportTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.app = create_app(Path(self.tempdir.name) / "export.sqlite3")

    def tearDown(self):
        self.tempdir.cleanup()

    def get(self, url):
        path, _, query = url.partition("?")
        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_LENGTH": "0",
            "wsgi.input": io.BytesIO(),
        }
        response = {}

        def start(status, headers):
            response["status"] = status
            response["headers"] = dict(headers)

        response["body"] = b"".join(self.app(environ, start))
        return response

    @staticmethod
    def rows(response):
        return list(csv.DictReader(io.StringIO(response["body"].decode("utf-8-sig"))))

    def test_current_session_export_has_headers_encoding_filename_and_derived_values(self):
        athlete = self.app.database.add_athlete("Avery")
        session = self.app.database.add_session(
            "10", "yards", surface_type="turf", timing_method="timing-gates",
            environment="indoor", protocol_notes="Cleats",
        )
        first = self.app.database.add_attempt(session, athlete, 1800)
        second = self.app.database.add_attempt(session, athlete, 1750)
        with self.app.database.connect() as connection:
            connection.execute(
                "UPDATE sprint_attempts SET captured_at=? WHERE id=?", ("2026-07-01 09:00:00", first)
            )
            connection.execute(
                "UPDATE sprint_attempts SET captured_at=? WHERE id=?", ("2026-07-01 09:01:00", second)
            )

        response = self.get(f"/sessions/{session}/export.csv")
        rows = self.rows(response)

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["headers"]["Content-Type"], "text/csv; charset=utf-8")
        self.assertRegex(response["headers"]["Content-Disposition"], rf'aip-session-{session}-\d{{4}}-\d{{2}}-\d{{2}}\.csv')
        self.assertTrue(response["body"].startswith(b"\xef\xbb\xbf"))
        self.assertEqual(list(rows[0]), CSV_HEADERS)
        self.assertEqual([row["Attempt number"] for row in rows], ["1", "2"])
        self.assertEqual([row["Performance status"] for row in rows], ["baseline", "PR"])
        self.assertEqual([row["Session best"] for row in rows], ["1.75", "1.75"])
        self.assertEqual(rows[0]["Attempt time in milliseconds"], "1800")
        self.assertEqual(rows[0]["Protocol"], "Flying 10-yard acceleration test with a 5-yard run-in")
        self.assertEqual(rows[0]["Legacy protocol alias"], "10-yard sprint")
        self.assertEqual(rows[0]["Timed segment"], "5–15 yards")
        self.assertEqual(
            (rows[0]["Surface type"], rows[0]["Timing method"], rows[0]["Environment"], rows[0]["Protocol notes"]),
            ("turf", "timing-gates", "indoor", "Cleats"),
        )

    def test_group_export_covers_multiple_athletes_sessions_and_units_in_snapshot_order(self):
        group = self.app.database.add_group("Sprint Group")
        first_athlete = self.app.database.add_group_athlete(group, "First Runner")
        second_athlete = self.app.database.add_group_athlete(group, "Second Runner")
        yards = self.app.database.add_group_session(group, "10", "yards")
        meters = self.app.database.add_group_session(group, "10", "meters")
        self.app.database.add_attempt(yards, second_athlete, 1700)
        self.app.database.add_attempt(yards, first_athlete, 1800)
        self.app.database.add_attempt(meters, first_athlete, 1750)

        rows = self.rows(self.get(f"/groups/{group}/export.csv"))

        self.assertEqual(len(rows), 3)
        self.assertEqual(
            [(row["Session ID"], row["Athlete name"]) for row in rows],
            [(str(yards), "First Runner"), (str(yards), "Second Runner"), (str(meters), "First Runner")],
        )
        self.assertEqual([row["Unit"] for row in rows], ["yards", "yards", "meters"])
        self.assertEqual([row["Performance status"] for row in rows], ["baseline", "baseline", "baseline"])

    def test_group_export_date_range_is_inclusive_and_filters_by_session_date(self):
        group = self.app.database.add_group("Dated Group")
        athlete = self.app.database.add_group_athlete(group, "Runner")
        old_session = self.app.database.add_group_session(group, "10", "yards")
        included_session = self.app.database.add_group_session(group, "20", "yards")
        new_session = self.app.database.add_group_session(group, "30", "yards")
        for session in (old_session, included_session, new_session):
            self.app.database.add_attempt(session, athlete, 1800)
        with self.app.database.connect() as connection:
            connection.execute("UPDATE sprint_capture_sessions SET created_at=? WHERE id=?", ("2026-06-30 12:00:00", old_session))
            connection.execute("UPDATE sprint_capture_sessions SET created_at=? WHERE id=?", ("2026-07-15 12:00:00", included_session))
            connection.execute("UPDATE sprint_capture_sessions SET created_at=? WHERE id=?", ("2026-08-01 12:00:00", new_session))

        rows = self.rows(self.get(f"/groups/{group}/export.csv?start=2026-07-01&end=2026-07-31"))

        self.assertEqual([row["Session ID"] for row in rows], [str(included_session)])

        start_only = self.rows(self.get(f"/groups/{group}/export.csv?start=2026-07-15"))
        end_only = self.rows(self.get(f"/groups/{group}/export.csv?end=2026-07-15"))
        self.assertEqual([row["Session ID"] for row in start_only], [str(included_session), str(new_session)])
        self.assertEqual([row["Session ID"] for row in end_only], [str(old_session), str(included_session)])

    def test_attempt_order_and_standard_status_are_deterministic(self):
        athlete = self.app.database.add_athlete("Runner")
        session = self.app.database.add_session("10", "yards")
        later_id = self.app.database.add_attempt(session, athlete, 1850)
        earlier_id = self.app.database.add_attempt(session, athlete, 1800)
        with self.app.database.connect() as connection:
            connection.execute("UPDATE sprint_attempts SET captured_at=? WHERE id=?", ("2026-07-02 10:00:00", later_id))
            connection.execute("UPDATE sprint_attempts SET captured_at=? WHERE id=?", ("2026-07-02 09:00:00", earlier_id))

        rows = self.rows(self.get(f"/sessions/{session}/export.csv"))

        self.assertEqual([row["Attempt time in milliseconds"] for row in rows], ["1800", "1850"])
        self.assertEqual([row["Attempt number"] for row in rows], ["1", "2"])
        self.assertEqual([row["Performance status"] for row in rows], ["baseline", "standard"])

    def test_standalone_session_orders_athletes_by_name(self):
        zulu = self.app.database.add_athlete("Zulu Runner")
        alpha = self.app.database.add_athlete("Alpha Runner")
        session = self.app.database.add_session("10", "yards")
        self.app.database.add_attempt(session, zulu, 1700)
        self.app.database.add_attempt(session, alpha, 1800)

        rows = self.rows(self.get(f"/sessions/{session}/export.csv"))

        self.assertEqual([row["Athlete name"] for row in rows], ["Alpha Runner", "Zulu Runner"])

    def test_formula_injection_is_neutralized_in_text_fields(self):
        group = self.app.database.add_group("+Spreadsheet Formula")
        athlete = self.app.database.add_group_athlete(group, "=HYPERLINK example")
        session = self.app.database.add_group_session(group, "10", "yards")
        self.app.database.add_attempt(session, athlete, 1800)
        with self.app.database.connect() as connection:
            connection.execute("UPDATE athletes SET name=? WHERE id=?", ("  =HYPERLINK example", athlete))
            connection.execute("UPDATE training_groups SET name=? WHERE id=?", ("  +Spreadsheet Formula", group))

        row = self.rows(self.get(f"/groups/{group}/export.csv"))[0]

        self.assertEqual(row["Training Group"], "'  +Spreadsheet Formula")
        self.assertEqual(row["Athlete name"], "'  =HYPERLINK example")
        self.assertEqual(row["Attempt time in milliseconds"], "1800")

    def test_utf8_names_and_safe_group_filename(self):
        group = self.app.database.add_group("Élite Sprint / Group")
        athlete = self.app.database.add_group_athlete(group, "José Núñez")
        session = self.app.database.add_group_session(group, "10", "meters")
        self.app.database.add_attempt(session, athlete, 1800)

        response = self.get(f"/groups/{group}/export.csv")
        row = self.rows(response)[0]

        self.assertEqual(row["Training Group"], "Élite Sprint / Group")
        self.assertEqual(row["Athlete name"], "José Núñez")
        self.assertRegex(
            response["headers"]["Content-Disposition"],
            r'aip-group-lite-sprint-group-\d{4}-\d{2}-\d{2}\.csv',
        )

    def test_empty_export_returns_header_only_and_historical_snapshot_is_respected(self):
        empty_session = self.app.database.add_session("10", "yards")
        empty_response = self.get(f"/sessions/{empty_session}/export.csv")
        self.assertEqual(empty_response["status"], "200 OK")
        self.assertEqual(self.rows(empty_response), [])
        self.assertEqual(next(csv.reader(io.StringIO(empty_response["body"].decode("utf-8-sig")))), CSV_HEADERS)

        group = self.app.database.add_group("Historical Group")
        original = self.app.database.add_group_athlete(group, "Original Runner")
        historical_session = self.app.database.add_group_session(group, "10", "yards")
        self.app.database.add_attempt(historical_session, original, 1800)
        later = self.app.database.add_group_athlete(group, "Later Runner")
        with self.app.database.connect() as connection:
            connection.execute(
                "DELETE FROM training_group_members WHERE group_id=? AND athlete_id=?", (group, original)
            )
            connection.execute(
                "UPDATE training_group_members SET position=1 WHERE group_id=? AND athlete_id=?", (group, later)
            )

        rows = self.rows(self.get(f"/groups/{group}/export.csv"))
        self.assertEqual([row["Athlete name"] for row in rows], ["Original Runner"])

    def test_invalid_group_date_range_returns_controlled_error(self):
        group = self.app.database.add_group("Date Validation")
        invalid = self.get(f"/groups/{group}/export.csv?start=not-a-date")
        reversed_range = self.get(f"/groups/{group}/export.csv?start=2026-08-01&end=2026-07-01")
        self.assertEqual(invalid["status"], "400 Bad Request")
        self.assertEqual(reversed_range["status"], "400 Bad Request")

    def test_unknown_export_scopes_return_not_found(self):
        self.assertEqual(self.get("/sessions/99999/export.csv")["status"], "404 Not Found")
        self.assertEqual(self.get("/groups/99999/export.csv")["status"], "404 Not Found")

    def test_export_does_not_mutate_persisted_data(self):
        group = self.app.database.add_group("Read Only Export")
        athlete = self.app.database.add_group_athlete(group, "Runner")
        session = self.app.database.add_group_session(group, "10", "yards")
        self.app.database.add_attempt(session, athlete, 1800)
        before = self.app.database.all_attempts()

        session_response = self.get(f"/sessions/{session}/export.csv")
        group_response = self.get(f"/groups/{group}/export.csv")

        self.assertEqual(session_response["status"], "200 OK")
        self.assertEqual(group_response["status"], "200 OK")
        self.assertEqual(self.app.database.all_attempts(), before)


if __name__ == "__main__":
    unittest.main()
