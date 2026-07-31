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
        self.assertIn(b"Move through the training order", capture_page["body"])
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
