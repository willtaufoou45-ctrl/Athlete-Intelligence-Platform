import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode

from aip.web import create_app


class InteractiveNestingParser(HTMLParser):
    interactive = {"a", "button", "input", "select", "textarea", "summary"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.nested = []

    def handle_starttag(self, tag, attrs):
        if tag in self.interactive and any(parent in self.interactive for parent in self.stack):
            self.nested.append(tag)
        if tag not in {"input"}:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            self.stack = self.stack[:index]


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.app = create_app(Path(self.tempdir.name) / "web.sqlite3")
        self.athlete_id = self.app.database.add_athlete("Avery")
        self.session_id = self.app.database.add_session("10", "yards")

    def tearDown(self):
        self.tempdir.cleanup()

    def call(self, method, path, data=None, form=False):
        payload = (urlencode(data or {}) if form else json.dumps(data or {})).encode()
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "CONTENT_LENGTH": str(len(payload)),
            "CONTENT_TYPE": "application/x-www-form-urlencoded" if form else "application/json",
            "REMOTE_ADDR": "192.168.0.27",
            "wsgi.input": io.BytesIO(payload),
        }
        response = {}
        def start(status, headers):
            response["status"] = status
            response["headers"] = headers
        response["body"] = b"".join(self.app(environ, start))
        response["header_map"] = dict(response["headers"])
        return response

    def upload_csv(self, path, csv_payload, **fields):
        boundary = "AIPHistoricalImportBoundary"
        chunks = []
        for name, value in fields.items():
            chunks.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
            )
        chunks.extend([
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"csv_file\"; filename=\"history.csv\"\r\nContent-Type: text/csv\r\n\r\n".encode(),
            csv_payload,
            f"\r\n--{boundary}--\r\n".encode(),
        ])
        payload = b"".join(chunks)
        environ = {
            "REQUEST_METHOD": "POST", "PATH_INFO": path, "CONTENT_LENGTH": str(len(payload)),
            "CONTENT_TYPE": f"multipart/form-data; boundary={boundary}", "REMOTE_ADDR": "192.168.0.27",
            "wsgi.input": io.BytesIO(payload),
        }
        response = {}
        def start(status, headers):
            response["status"], response["headers"] = status, headers
        response["body"] = b"".join(self.app(environ, start))
        response["header_map"] = dict(response["headers"])
        return response

    @staticmethod
    def body(response):
        return json.loads(response["body"])

    def test_save_endpoint_returns_baseline_then_pr(self):
        first = self.call("POST", f"/api/sessions/{self.session_id}/attempts", {"athlete_id": self.athlete_id, "elapsed_seconds": "1.80"})
        self.assertEqual(first["status"], "201 Created")
        self.assertEqual(json.loads(first["body"])["attempts"][0]["status"], "baseline")
        second = self.call("POST", f"/api/sessions/{self.session_id}/attempts", {"athlete_id": self.athlete_id, "elapsed_seconds": "1.75"})
        self.assertEqual(json.loads(second["body"])["attempts"][0]["status"], "pr")

    def test_save_endpoint_deduplicates_a_retried_request_identifier(self):
        payload = {"athlete_id": self.athlete_id, "elapsed_seconds": "1.80", "request_id": "retry-1"}
        first = self.call("POST", f"/api/sessions/{self.session_id}/attempts", payload)
        retry = self.call("POST", f"/api/sessions/{self.session_id}/attempts", payload)
        self.assertEqual(first["status"], "201 Created")
        self.assertEqual(retry["status"], "201 Created")
        self.assertEqual(len(self.app.database.all_attempts()), 1)

    def test_invalid_input_is_reported_without_saving(self):
        response = self.call("POST", f"/api/sessions/{self.session_id}/attempts", {"athlete_id": self.athlete_id, "elapsed_seconds": "fast"})
        self.assertEqual(response["status"], "400 Bad Request")
        self.assertEqual(self.app.database.all_attempts(), [])

    def test_athlete_results_endpoint_is_read_only(self):
        response = self.call("GET", f"/api/sessions/{self.session_id}/athletes/{self.athlete_id}")
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(json.loads(response["body"])["attempts"], [])
        self.assertEqual(self.app.database.all_attempts(), [])

    def test_edit_recalculates_session_best_and_pr_status(self):
        first_id = self.app.database.add_attempt(self.session_id, self.athlete_id, 1800)
        second_id = self.app.database.add_attempt(self.session_id, self.athlete_id, 1750)
        response = self.call("POST", f"/api/attempts/{first_id}/edit", {"elapsed_seconds": "1.70"})
        data = self.body(response)
        statuses = {attempt["id"]: attempt["status"] for attempt in data["attempts"]}
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(data["best"], "1.7")
        self.assertEqual(statuses[first_id], "baseline")
        self.assertEqual(statuses[second_id], "attempt")

    def test_delete_current_best_recalculates_results(self):
        first_id = self.app.database.add_attempt(self.session_id, self.athlete_id, 1800)
        best_id = self.app.database.add_attempt(self.session_id, self.athlete_id, 1750)
        response = self.call("POST", f"/api/attempts/{best_id}/delete")
        data = self.body(response)
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(data["best"], "1.8")
        self.assertEqual(data["attempts"], [{"id": first_id, "time": "1.8", "status": "baseline", "just_saved": False}])

    def test_capture_sessions_are_isolated_while_pr_history_is_shared(self):
        self.app.database.add_attempt(self.session_id, self.athlete_id, 1800)
        second_session = self.app.database.add_session("10", "yards")
        second_attempt = self.app.database.add_attempt(second_session, self.athlete_id, 1750)
        first = self.body(self.call("GET", f"/api/sessions/{self.session_id}/athletes/{self.athlete_id}"))
        second = self.body(self.call("GET", f"/api/sessions/{second_session}/athletes/{self.athlete_id}"))
        self.assertEqual([attempt["time"] for attempt in first["attempts"]], ["1.8"])
        self.assertEqual([attempt["id"] for attempt in second["attempts"]], [second_attempt])
        self.assertEqual(second["attempts"][0]["status"], "pr")

    def test_yards_and_meters_have_separate_baselines(self):
        self.app.database.add_attempt(self.session_id, self.athlete_id, 1800)
        meter_session = self.app.database.add_session("10", "meters")
        self.app.database.add_attempt(meter_session, self.athlete_id, 1750)
        data = self.body(self.call("GET", f"/api/sessions/{meter_session}/athletes/{self.athlete_id}"))
        self.assertEqual(data["attempts"][0]["status"], "baseline")

    def test_athlete_creation_route(self):
        response = self.call("POST", "/athletes", {"name": "  Morgan Lee  "}, form=True)
        self.assertEqual(response["status"], "303 See Other")
        self.assertEqual(response["header_map"]["Location"], "/")
        self.assertIn("Morgan Lee", [athlete["name"] for athlete in self.app.database.all_athletes()])

    def test_session_creation_and_resumption_routes(self):
        created = self.call("POST", "/sessions", {"distance": "20.00", "unit": "meters"}, form=True)
        self.assertEqual(created["status"], "303 See Other")
        location = created["header_map"]["Location"]
        resumed = self.call("GET", location)
        self.assertEqual(resumed["status"], "200 OK")
        self.assertIn(b"20 meters", resumed["body"])

    def test_unknown_and_malformed_paths_are_controlled(self):
        self.assertEqual(self.call("GET", "/unknown/route")["status"], "404 Not Found")
        self.assertEqual(self.call("GET", "/sessions/not-a-number")["status"], "400 Bad Request")
        self.assertEqual(self.call("POST", "/api/attempts/not-a-number/edit", {"elapsed_seconds": "1.8"})["status"], "400 Bad Request")

    def test_diagnostic_ping_is_tiny_plain_text_with_timing_headers(self):
        response = self.call("GET", "/diagnostics/ping")
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["body"], b"pong\n")
        self.assertEqual(response["header_map"]["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(response["header_map"]["Content-Length"], "5")
        self.assertRegex(response["header_map"]["Server-Timing"], r"^app;dur=\d+\.\d{3}$")
        self.assertEqual(response["header_map"]["Cache-Control"], "no-store")

    def test_request_log_contains_client_method_path_status_timing_and_size(self):
        output = io.StringIO()
        with redirect_stdout(output):
            response = self.call("GET", "/diagnostics/ping")
        self.assertEqual(response["status"], "200 OK")
        self.assertRegex(
            output.getvalue().strip(),
            r"^192\.168\.0\.27 GET /diagnostics/ping 200 app=\d+\.\dms bytes=5$",
        )

    def test_request_diagnostics_do_not_disable_caching_for_application_responses(self):
        page_response = self.call("GET", "/")
        redirect_response = self.call(
            "POST",
            "/athletes",
            {"name": "Timed Runner"},
            form=True,
        )

        for response in (page_response, redirect_response):
            self.assertIn("Server-Timing", response["header_map"])
            self.assertNotIn("Cache-Control", response["header_map"])
            self.assertIn("Content-Length", response["header_map"])

    def test_nonexistent_resources_return_not_found(self):
        self.assertEqual(self.call("GET", "/sessions/99999")["status"], "404 Not Found")
        self.assertEqual(self.call("GET", f"/api/sessions/99999/athletes/{self.athlete_id}")["status"], "404 Not Found")
        self.assertEqual(self.call("GET", f"/api/sessions/{self.session_id}/athletes/99999")["status"], "404 Not Found")
        self.assertEqual(self.call("POST", "/api/attempts/99999/delete")["status"], "404 Not Found")

    def test_training_group_routes_reuse_ordered_roster_in_new_sessions(self):
        created_group = self.call("POST", "/groups", {"name": "Sprint Group A"}, form=True)
        self.assertEqual(created_group["status"], "303 See Other")
        group_location = created_group["header_map"]["Location"]
        group_id = int(group_location.rsplit("/", 1)[-1])

        self.call("POST", f"/groups/{group_id}/athletes", {"name": "Hudson"}, form=True)
        self.call("POST", f"/groups/{group_id}/athletes", {"name": "James"}, form=True)
        created_session = self.call(
            "POST", f"/groups/{group_id}/sessions", {"distance": "10", "unit": "yards"}, form=True
        )
        session_id = int(created_session["header_map"]["Location"].rsplit("/", 1)[-1])
        roster = self.app.database.session_athletes(session_id)

        self.assertEqual([athlete["name"] for athlete in roster], ["Hudson", "James"])
        capture_page = self.call("GET", f"/sessions/{session_id}")
        self.assertIn(b"Next three", capture_page["body"])
        self.assertIn(b"Hudson", capture_page["body"])
        self.assertIn(b"James", capture_page["body"])

    def test_group_roster_is_reused_by_later_session(self):
        group_id = self.app.database.add_group("Recurring Team")
        first = self.app.database.add_group_athlete(group_id, "First Runner")
        second = self.app.database.add_group_athlete(group_id, "Second Runner")
        first_session = self.app.database.add_group_session(group_id, "10", "yards")
        second_session = self.app.database.add_group_session(group_id, "10", "yards")

        self.assertEqual([a["id"] for a in self.app.database.session_athletes(first_session)], [first, second])
        self.assertEqual([a["id"] for a in self.app.database.session_athletes(second_session)], [first, second])

    def test_group_roster_management_routes_move_copy_reorder_and_remove(self):
        source = self.app.database.add_group("Source Group")
        target = self.app.database.add_group("Target Group")
        first = self.app.database.add_group_athlete(source, "First Runner")
        second = self.app.database.add_group_athlete(source, "Second Runner")
        page = self.call("GET", f"/groups/{source}")["body"].decode()
        self.assertIn("Add to both", page)
        self.assertIn("Changes apply to future sessions", page)
        self.assertIn("Current groups:</strong> Source Group", page)
        self.assertIn("Choose another group", page)
        self.assertNotIn("value='2' selected", page)

        self.call("POST", f"/groups/{source}/roster/reorder", {"athlete_id": second, "direction": "up"}, form=True)
        self.call("POST", f"/groups/{source}/roster/transfer", {"athlete_id": first, "target_group_id": target, "action": "copy"}, form=True)
        self.call("POST", f"/groups/{source}/roster/transfer", {"athlete_id": second, "target_group_id": target, "action": "move"}, form=True)
        self.call("POST", f"/groups/{target}/roster/remove", {"athlete_id": first}, form=True)

        self.assertEqual([a["id"] for a in self.app.database.group_roster(source)], [first])
        self.assertEqual([a["id"] for a in self.app.database.group_roster(target)], [second])

    def test_group_page_searches_and_adds_existing_athlete_without_duplicate(self):
        source = self.app.database.add_group("Source Group")
        target = self.app.database.add_group("Target Group")
        athlete_id = self.app.database.add_group_athlete(source, "Jordan Lee")

        page = self.call("GET", f"/groups/{target}")["body"].decode()
        self.assertIn("Find an existing athlete", page)
        self.assertIn("Jordan Lee", page)
        self.assertIn("Source Group", page)
        self.assertIn("includes(query)", page)

        response = self.call(
            "POST", f"/groups/{target}/athletes/existing", {"athlete_id": athlete_id}, form=True
        )
        self.assertEqual(response["status"], "303 See Other")
        self.assertEqual([a["id"] for a in self.app.database.group_roster(target)], [athlete_id])
        self.assertEqual(len(self.app.database.all_athletes()), 2)

    def test_group_page_uses_collapsed_mobile_workflow_in_requested_order(self):
        group_id = self.app.database.add_group("Workflow Group")
        self.app.database.add_group_athlete(group_id, "Runner")

        page = self.call("GET", f"/groups/{group_id}")["body"].decode()

        create_at = page.index("Create a new athlete")
        find_at = page.index("<summary>Find an existing athlete</summary>")
        start_at = page.index("<summary>Start a session</summary>")
        athletes_at = page.index("<summary>All athletes (1)</summary>")
        self.assertLess(create_at, find_at)
        self.assertLess(find_at, start_at)
        self.assertLess(start_at, athletes_at)
        self.assertNotIn("<details class='roster-tool create-athlete'", page)

    def test_group_page_blocks_accidental_exact_name_duplicate(self):
        source = self.app.database.add_group("Source Group")
        target = self.app.database.add_group("Target Group")
        self.app.database.add_group_athlete(source, "Jordan Lee")

        response = self.call("POST", f"/groups/{target}/athletes", {"name": "jordan lee"}, form=True)

        self.assertEqual(response["status"], "400 Bad Request")
        self.assertIn(b"already exists", response["body"])
        self.assertEqual(len([a for a in self.app.database.all_athletes() if a["name"].lower() == "jordan lee"]), 1)

    def test_earlier_capture_page_keeps_its_roster_after_group_changes(self):
        group_id = self.app.database.add_group("Snapshot Team")
        original_id = self.app.database.add_group_athlete(group_id, "Original Runner")
        session_id = self.app.database.add_group_session(group_id, "10", "yards")
        later_id = self.app.database.add_group_athlete(group_id, "Later Runner")

        capture_page = self.call("GET", f"/sessions/{session_id}")
        self.assertIn(b"Original Runner", capture_page["body"])
        self.assertNotIn(b"Later Runner", capture_page["body"])
        rejected = self.call(
            "POST",
            f"/api/sessions/{session_id}/attempts",
            {"athlete_id": later_id, "elapsed_seconds": "1.75"},
        )
        accepted = self.call(
            "POST",
            f"/api/sessions/{session_id}/attempts",
            {"athlete_id": original_id, "elapsed_seconds": "1.80"},
        )
        self.assertEqual(rejected["status"], "400 Bad Request")
        self.assertEqual(accepted["status"], "201 Created")

    def test_active_session_can_add_late_athlete_to_session_and_group(self):
        group_id = self.app.database.add_group("Late Arrival Group")
        original_id = self.app.database.add_group_athlete(group_id, "Original Runner")
        earlier_session = self.app.database.add_group_session(group_id, "10", "yards")
        active_session = self.app.database.add_group_session(group_id, "10", "yards")

        response = self.call(
            "POST", f"/sessions/{active_session}/athletes", {"name": "Late Runner"}, form=True
        )

        self.assertEqual(response["status"], "303 See Other")
        self.assertEqual(response["header_map"]["Location"], f"/sessions/{active_session}")
        self.assertEqual([a["id"] for a in self.app.database.session_athletes(earlier_session)], [original_id])
        self.assertEqual(
            [a["name"] for a in self.app.database.session_athletes(active_session)],
            ["Original Runner", "Late Runner"],
        )
        self.assertEqual(
            [a["name"] for a in self.app.database.group_roster(group_id)],
            ["Original Runner", "Late Runner"],
        )

    def test_capture_page_shows_next_three_and_autosaves_without_save_button(self):
        group_id = self.app.database.add_group("Queue Group")
        for name in ("First", "Second", "Third", "Fourth"):
            self.app.database.add_group_athlete(group_id, name)
        session_id = self.app.database.add_group_session(group_id, "10", "yards")

        body = self.call("GET", f"/sessions/{session_id}")["body"].decode()

        self.assertIn("Next three", body)
        self.assertIn("id='up-next-list'", body)
        self.assertIn("setTimeout(saveAttempt,900)", body)
        self.assertIn("Times save automatically", body)
        self.assertNotIn("id='save'", body)

    def test_capture_time_input_automatically_places_decimal_after_first_digit(self):
        group_id = self.app.database.add_group("Decimal Input Group")
        self.app.database.add_group_athlete(group_id, "Runner")
        session_id = self.app.database.add_group_session(group_id, "10", "yards")

        body = self.call("GET", f"/sessions/{session_id}")["body"].decode()

        self.assertIn("inputmode='numeric'", body)
        self.assertIn("172 becomes 1.72", body)
        self.assertIn("function formatSprintTime(value)", body)
        self.assertIn("`${digits[0]}.${digits.slice(1)}`", body)
        self.assertIn("/^\\d\\.\\d{1,3}$/", body)

    def test_capture_page_prioritizes_live_controls_before_session_management(self):
        group_id = self.app.database.add_group("Mobile Priority Group")
        self.app.database.add_group_athlete(group_id, "Runner")
        session_id = self.app.database.add_group_session(group_id, "10", "yards")

        body = self.call("GET", f"/sessions/{session_id}")["body"].decode()

        self.assertLess(body.index("id='athlete-name'"), body.index("id='elapsed'"))
        self.assertLess(body.index("id='elapsed'"), body.index("Next three"))
        self.assertLess(body.index("Next three"), body.index("id='results'"))
        self.assertLess(body.index("id='results'"), body.index("Export Session CSV"))
        self.assertLess(body.index("Export Session CSV"), body.index("Delete session"))
        self.assertNotIn("Send Feedback", body)

    def test_athlete_summary_separates_current_attempts_from_comparable_history(self):
        group_id = self.app.database.add_group("History Group")
        athlete_id = self.app.database.add_group_athlete(group_id, "History Runner")
        oldest = self.app.database.add_group_session(group_id, "10", "yards")
        previous = self.app.database.add_group_session(group_id, "10", "yards")
        current = self.app.database.add_group_session(group_id, "10", "yards")
        other_unit = self.app.database.add_group_session(group_id, "10", "meters")
        with self.app.database.connect() as connection:
            connection.execute("UPDATE sprint_capture_sessions SET session_date='2026-07-20' WHERE id=?", (oldest,))
            connection.execute("UPDATE sprint_capture_sessions SET session_date='2026-08-03' WHERE id=?", (previous,))
            connection.execute("UPDATE sprint_capture_sessions SET session_date='2026-08-10' WHERE id=?", (current,))
            connection.execute("UPDATE sprint_capture_sessions SET session_date='2026-08-09' WHERE id=?", (other_unit,))
        self.app.database.add_attempt(oldest, athlete_id, 1650)
        self.app.database.add_attempt(previous, athlete_id, 1700)
        current_attempt = self.app.database.add_attempt(current, athlete_id, 1680)
        self.app.database.add_attempt(other_unit, athlete_id, 1500)

        data = self.body(self.call("GET", f"/api/sessions/{current}/athletes/{athlete_id}"))

        self.assertEqual(data["attempts"], [{"id": current_attempt, "time": "1.68", "status": "attempt", "just_saved": False}])
        self.assertEqual(data["best"], "1.68")
        self.assertEqual(data["all_time_best"], {"time": "1.65", "date": "2026-07-20"})
        self.assertEqual(data["previous_session"], {"best": "1.7", "date": "2026-08-03"})

    def test_history_reference_is_available_before_current_session_has_an_attempt(self):
        prior = self.app.database.add_session("10", "yards")
        current = self.app.database.add_session("10", "yards")
        with self.app.database.connect() as connection:
            connection.execute("UPDATE sprint_capture_sessions SET session_date='2026-08-01' WHERE id=?", (prior,))
            connection.execute("UPDATE sprint_capture_sessions SET session_date='2026-08-08' WHERE id=?", (current,))
        self.app.database.add_attempt(prior, self.athlete_id, 1720)

        data = self.body(self.call("GET", f"/api/sessions/{current}/athletes/{self.athlete_id}"))

        self.assertEqual(data["attempts"], [])
        self.assertIsNone(data["best"])
        self.assertEqual(data["all_time_best"], {"time": "1.72", "date": "2026-08-01"})
        self.assertEqual(data["previous_session"], {"best": "1.72", "date": "2026-08-01"})

    def test_complete_route_separates_active_and_completed_sessions(self):
        group_id = self.app.database.add_group("Lifecycle Group")
        athlete_id = self.app.database.add_group_athlete(group_id, "Runner")
        session_id = self.app.database.add_group_session(group_id, "10", "yards")

        completed = self.call("POST", f"/sessions/{session_id}/complete", {}, form=True)

        self.assertEqual(completed["status"], "303 See Other")
        self.assertEqual(completed["header_map"]["Location"], f"/groups/{group_id}")
        page = self.call("GET", f"/sessions/{session_id}")["body"]
        group_page = self.call("GET", f"/groups/{group_id}")["body"]
        self.assertIn(b"Completed session", page)
        self.assertIn(b"Capture is closed", page)
        self.assertNotIn(f"/sessions/{session_id}/athletes".encode(), page)
        self.assertIn(b"Completed session history", group_page)
        rejected = self.call(
            "POST",
            f"/api/sessions/{session_id}/attempts",
            {"athlete_id": athlete_id, "elapsed_seconds": "1.70"},
        )
        self.assertEqual(rejected["status"], "400 Bad Request")

    def test_session_labels_include_group_date_distance_and_unit(self):
        group_id = self.app.database.add_group("Clearly Labeled Group")
        self.app.database.add_group_athlete(group_id, "Runner")
        session_id = self.app.database.add_group_session(group_id, "10", "yards")
        session = self.app.database.session(session_id)

        group_page = self.call("GET", f"/groups/{group_id}")["body"].decode()
        session_page = self.call("GET", f"/sessions/{session_id}")["body"].decode()
        expected = f"Clearly Labeled Group · {session['session_date']} · 10 yards"
        self.assertIn(expected, group_page)
        self.assertIn(expected, session_page)

    def test_delete_session_route_permanently_removes_session_and_attempts(self):
        group_id = self.app.database.add_group("Delete Route Group")
        athlete_id = self.app.database.add_group_athlete(group_id, "Runner")
        session_id = self.app.database.add_group_session(group_id, "10", "yards")
        self.app.database.add_attempt(session_id, athlete_id, 1700)

        deleted = self.call("POST", f"/sessions/{session_id}/delete", {}, form=True)

        self.assertEqual(deleted["status"], "303 See Other")
        self.assertEqual(deleted["header_map"]["Location"], f"/groups/{group_id}")
        self.assertIsNone(self.app.database.session(session_id))
        self.assertEqual(self.app.database.all_attempts(), [])
        self.assertEqual(self.call("GET", f"/sessions/{session_id}")["status"], "404 Not Found")

    def test_export_actions_are_visible_on_session_and_group_pages(self):
        group_id = self.app.database.add_group("Export Group")
        self.app.database.add_group_athlete(group_id, "Runner")
        session_id = self.app.database.add_group_session(group_id, "10", "yards")

        group_page = self.call("GET", f"/groups/{group_id}")
        session_page = self.call("GET", f"/sessions/{session_id}")
        self.assertIn(b"Export Group CSV", group_page["body"])
        self.assertIn(f"/groups/{group_id}/export.csv".encode(), group_page["body"])
        self.assertIn(b"Export Session CSV", session_page["body"])
        self.assertIn(f"/sessions/{session_id}/export.csv".encode(), session_page["body"])

    def test_historical_import_upload_previews_without_writing_and_requires_resolutions(self):
        group_id = self.app.database.add_group("Historical Group")
        self.app.database.add_group_athlete(group_id, "Jordan Lee")
        sessions_before = len(self.app.database.all_sessions())
        attempts_before = len(self.app.database.all_attempts())
        csv_payload = b"Title\nFirst Name,Last Name,FASTEST,1/15\nJordan,Lee,1.60,fast\nNew,Runner,,1.90\n"
        upload_page = self.call("GET", f"/groups/{group_id}/imports/new")
        preview = self.upload_csv(
            f"/groups/{group_id}/imports/preview", csv_payload,
            distance="10", unit="yards", year="2024",
        )
        self.assertIn(b"Import historical sprint CSV", self.call("GET", f"/groups/{group_id}")["body"])
        self.assertIn(b"Nothing is saved until", upload_page["body"])
        self.assertIn(b"No-write preview", preview["body"])
        self.assertIn(b"FASTEST", preview["body"])
        self.assertIn(b"unmatched", preview["body"])
        self.assertIn(b"row 3 / column 4", preview["body"])
        self.assertEqual(len(self.app.database.all_sessions()), sessions_before)
        self.assertEqual(len(self.app.database.all_attempts()), attempts_before)

    def test_historical_import_web_confirmation_persists_reviewed_results(self):
        group_id = self.app.database.add_group("Historical Confirm Group")
        athlete_id = self.app.database.add_group_athlete(group_id, "Jordan Lee")
        csv_payload = b"First Name,Last Name,2024-01-15\nJordan,Lee,1.72\n"
        preview_response = self.upload_csv(
            f"/groups/{group_id}/imports/preview", csv_payload, distance="10", unit="yards",
        )
        self.assertEqual(preview_response["status"], "200 OK")
        token = next(iter(self.app.import_previews))
        confirmed = self.call(
            "POST", f"/groups/{group_id}/imports/confirm",
            {"preview_token": token, "resolution_2": f"existing:{athlete_id}"}, form=True,
        )
        self.assertEqual(confirmed["status"], "200 OK")
        self.assertIn(b"Historical sprint import confirmed", confirmed["body"])
        self.assertEqual(len(self.app.database.all_attempts()), 1)
        self.assertEqual(self.app.import_previews, {})

    def test_primary_mobile_controls_are_direct_semantic_destinations_without_nesting(self):
        group_id = self.app.database.add_group("Mobile Navigation Group")
        self.app.database.add_group_athlete(group_id, "Runner")
        session_id = self.app.database.add_group_session(group_id, "10", "yards")
        pages = [
            self.call("GET", "/")["body"].decode(),
            self.call("GET", f"/groups/{group_id}")["body"].decode(),
            self.call("GET", f"/sessions/{session_id}")["body"].decode(),
            self.call("GET", "/feedback")["body"].decode(),
        ]
        combined = "".join(pages)
        self.assertIn(f"href='/groups/{group_id}'", combined)
        self.assertIn(f"href='/sessions/{session_id}'", combined)
        self.assertIn("href='/feedback/new'", combined)
        self.assertIn(f"href='/sessions/{session_id}/export.csv'", combined)
        for markup in pages:
            parser = InteractiveNestingParser()
            parser.feed(markup)
            self.assertEqual(parser.nested, [])

    def test_initial_input_focus_is_limited_to_fine_pointer_devices(self):
        home = self.call("GET", "/")["body"].decode()
        session = self.call("GET", f"/sessions/{self.session_id}")["body"].decode()
        self.assertNotIn(" autofocus", home)
        self.assertIn("data-desktop-autofocus", home)
        self.assertIn("(hover: hover) and (pointer: fine)", home)
        self.assertIn("setAthlete(retainedIndex>=0?retainedIndex:0,finePointer)", session)
        self.assertIn("touch-action:manipulation", home)

    def test_feedback_button_and_form_are_visible(self):
        home = self.call("GET", "/")
        form = self.call("GET", "/feedback/new")
        self.assertIn(b"Send Feedback", home["body"])
        self.assertIn(b"What slowed you down?", form["body"])
        self.assertIn(b"What worked well?", form["body"])
        self.assertIn(b"What feature did you wish existed?", form["body"])

    def test_feedback_submission_without_context_is_listed(self):
        saved = self.call(
            "POST",
            "/feedback",
            {"slowed_down": "No context feedback", "worked_well": "", "wished_for": ""},
            form=True,
        )
        self.assertEqual(saved["status"], "303 See Other")
        self.assertEqual(saved["header_map"]["Location"], "/feedback")
        feedback = self.app.database.all_feedback()[0]
        self.assertIsNone(feedback["group_id"])
        self.assertIsNone(feedback["session_id"])
        self.assertTrue(feedback["created_at"])
        self.assertIn(b"No context feedback", self.call("GET", "/feedback")["body"])

    def test_feedback_route_saves_and_lists_group_and_session_context(self):
        group_id = self.app.database.add_group("Sprint Group Feedback")
        session_id = self.app.database.add_group_session(group_id, "10", "yards")
        saved = self.call(
            "POST",
            "/feedback",
            {
                "slowed_down": "  Finding the next athlete  ",
                "worked_well": "Enter to save",
                "wished_for": "A visible queue",
                "group_id": str(group_id),
                "session_id": str(session_id),
            },
            form=True,
        )
        self.assertEqual(saved["status"], "303 See Other")
        self.assertEqual(saved["header_map"]["Location"], "/feedback")
        listing = self.call("GET", "/feedback")
        self.assertIn(b"Finding the next athlete", listing["body"])
        self.assertIn(b"Sprint Group Feedback", listing["body"])
        self.assertIn(b"Session ", listing["body"])

    def test_feedback_listing_uses_controlled_chronological_order(self):
        oldest_id = self.app.database.add_feedback("Oldest feedback", "", "")
        newest_id = self.app.database.add_feedback("Newest feedback", "", "")
        middle_id = self.app.database.add_feedback("Middle feedback", "", "")
        with self.app.database.connect() as connection:
            connection.execute(
                "UPDATE prototype_feedback SET created_at=? WHERE id=?", ("2026-07-01 09:00:00", oldest_id)
            )
            connection.execute(
                "UPDATE prototype_feedback SET created_at=? WHERE id=?", ("2026-07-03 09:00:00", newest_id)
            )
            connection.execute(
                "UPDATE prototype_feedback SET created_at=? WHERE id=?", ("2026-07-02 09:00:00", middle_id)
            )

        body = self.call("GET", "/feedback")["body"].decode()
        self.assertLess(body.index("Newest feedback"), body.index("Middle feedback"))
        self.assertLess(body.index("Middle feedback"), body.index("Oldest feedback"))

    def test_feedback_rejects_empty_responses_and_invalid_context(self):
        blank = self.call("POST", "/feedback", {}, form=True)
        invalid = self.call("POST", "/feedback", {"slowed_down": "Slow", "group_id": "99999"}, form=True)
        self.assertEqual(blank["status"], "400 Bad Request")
        self.assertEqual(invalid["status"], "404 Not Found")

    def test_feedback_route_rejects_mismatched_group_and_session(self):
        selected_group = self.app.database.add_group("Selected Group")
        other_group = self.app.database.add_group("Other Group")
        other_session = self.app.database.add_group_session(other_group, "10", "yards")
        response = self.call(
            "POST",
            "/feedback",
            {"slowed_down": "Wrong context", "group_id": selected_group, "session_id": other_session},
            form=True,
        )
        self.assertEqual(response["status"], "400 Bad Request")
        self.assertEqual(self.app.database.all_feedback(), [])


if __name__ == "__main__":
    unittest.main()
