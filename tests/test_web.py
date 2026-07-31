import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode

from aip.web import create_app


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
            "wsgi.input": io.BytesIO(payload),
        }
        response = {}
        def start(status, headers):
            response["status"] = status
            response["headers"] = headers
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

    def test_nonexistent_resources_return_not_found(self):
        self.assertEqual(self.call("GET", "/sessions/99999")["status"], "404 Not Found")
        self.assertEqual(self.call("GET", f"/api/sessions/99999/athletes/{self.athlete_id}")["status"], "404 Not Found")
        self.assertEqual(self.call("GET", f"/api/sessions/{self.session_id}/athletes/99999")["status"], "404 Not Found")
        self.assertEqual(self.call("POST", "/api/attempts/99999/delete")["status"], "404 Not Found")


if __name__ == "__main__":
    unittest.main()
