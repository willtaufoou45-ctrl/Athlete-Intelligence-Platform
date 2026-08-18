"""Small server-rendered WSGI application for live sprint capture."""

from __future__ import annotations

import html
import io
import json
import re
import secrets
from email import policy
from email.parser import BytesParser
from pathlib import Path
from time import perf_counter, time
from urllib.parse import parse_qs

from .auth import csrf_valid, expired_cookie, issue_session, read_session, session_cookie, verify_password
from .config import Config
from .database import Database
from .domain import classify_attempts, format_seconds, normalize_distance, seconds_to_milliseconds
from .export import export_filename, parse_export_dates, sprint_export_csv
from .importer import build_preview, confirm_import


def create_app(database_path: str | Path = "data/aip.sqlite3", *, config: Config | None = None):
    config = config or Config.from_env(str(database_path))
    database = Database(config.database_url)
    database.initialize()
    import_previews: dict[str, dict] = {}
    login_failures: dict[str, list[float]] = {}

    def handle_request(environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/").rstrip("/") or "/"
        parts = [part for part in path.split("/") if part]
        try:
            if method == "GET" and path == "/diagnostics/ping":
                return plain_text_response(start_response, "pong\n")
            if config.auth_enabled and method == "GET" and path == "/login":
                if environ.get("aip.session"):
                    return redirect(start_response, "/")
                return respond(start_response, login_page())
            if config.auth_enabled and method == "POST" and path == "/login":
                login_key = environ.get("REMOTE_ADDR") or "unknown"
                cutoff = time() - 300
                login_failures[login_key] = [item for item in login_failures.get(login_key, []) if item >= cutoff]
                if len(login_failures[login_key]) >= 5:
                    return respond(start_response, login_page("Try again in a few minutes."), "429 Too Many Requests")
                data = form_data(environ)
                valid = secrets.compare_digest(data.get("username", ""), config.coach_username or "")
                valid = verify_password(data.get("password", ""), config.coach_password_hash or "") and valid
                if not valid:
                    login_failures[login_key].append(time())
                    return respond(start_response, login_page("Invalid username or password."), "401 Unauthorized")
                login_failures.pop(login_key, None)
                token, _ = issue_session(config.coach_username or "coach", config.session_secret or "")
                return redirect_with_cookie(
                    start_response, "/", session_cookie(token, secure=request_is_secure(environ, config))
                )
            if config.auth_enabled and not environ.get("aip.session"):
                if path.startswith("/api/"):
                    return json_response(start_response, {"error": "Authentication required."}, "401 Unauthorized")
                return redirect(start_response, "/login")
            if config.auth_enabled and method == "POST" and path == "/logout":
                return redirect_with_cookie(
                    start_response, "/login", expired_cookie(secure=request_is_secure(environ, config))
                )
            if config.auth_enabled and method in {"POST", "PUT", "PATCH", "DELETE"}:
                submitted = csrf_from_request(environ)
                if not csrf_valid(environ, environ["aip.session"], submitted):
                    if path.startswith("/api/"):
                        return json_response(start_response, {"error": "Request verification failed."}, "403 Forbidden")
                    return respond(start_response, page("Request expired", "<h1>Request expired</h1><p>Reload the page and try again.</p>"), "403 Forbidden")
            if method == "GET" and path == "/":
                return respond(start_response, home_page(database))
            if method == "GET" and len(parts) == 3 and parts[:2] == ["internal", "intelligence"]:
                case_studies = {
                    "rigby": ("9", "Case Study 001"),
                    "brody": ("7", "Case Study 002"),
                }
                if parts[2] not in case_studies:
                    raise LookupError("Athlete Intelligence case study not found.")
                sprint_id, case_study = case_studies[parts[2]]
                athlete = database.canonical_athlete_by_external_identity(
                    "sprint_capture", "athlete", sprint_id
                )
                if not athlete:
                    raise LookupError("Verified Athlete Intelligence identity not found.")
                return respond(
                    start_response, intelligence_page(database, athlete["id"], case_study)
                )
            if method == "GET" and path == "/feedback/new":
                return respond(start_response, feedback_form_page(database))
            if method == "GET" and path == "/feedback":
                return respond(start_response, feedback_list_page(database))
            if method == "GET" and len(parts) == 3 and parts[0] == "sessions" and parts[2] == "export.csv":
                session_id = resource_id(parts[1], "session")
                payload = sprint_export_csv(database, session_id=session_id)
                return csv_response(start_response, payload, export_filename("session", session_id))
            if method == "GET" and len(parts) == 3 and parts[0] == "groups" and parts[2] == "export.csv":
                group_id = resource_id(parts[1], "Training Group")
                group = database.group(group_id)
                if not group:
                    raise LookupError("Training Group not found.")
                query = parse_qs(environ.get("QUERY_STRING", ""))
                start, end = parse_export_dates(first_value(query, "start"), first_value(query, "end"))
                payload = sprint_export_csv(database, group_id=group_id, start=start, end=end)
                return csv_response(start_response, payload, export_filename("group", group_id, group["name"]))
            if method == "POST" and path == "/feedback":
                data = form_data(environ)
                database.add_feedback(
                    data.get("slowed_down", ""),
                    data.get("worked_well", ""),
                    data.get("wished_for", ""),
                    optional_resource_id(data.get("group_id"), "Training Group"),
                    optional_resource_id(data.get("session_id"), "session"),
                )
                return redirect(start_response, "/feedback")
            if method == "POST" and path == "/athletes":
                data = form_data(environ)
                database.add_athlete(data.get("name", ""))
                return redirect(start_response, "/")
            if method == "POST" and path == "/sessions":
                data = form_data(environ)
                session_id = database.add_session(
                    normalize_distance(data.get("distance", "")), data.get("unit", ""),
                    selected_protocol(data.get("protocol_key")), optional_attempt_count(data.get("target_attempts")),
                    data.get("surface_type"), data.get("timing_method"), data.get("environment"),
                    data.get("protocol_notes"),
                )
                return redirect(start_response, f"/sessions/{session_id}")
            if method == "POST" and path == "/groups":
                group_id = database.add_group(form_data(environ).get("name", ""))
                return redirect(start_response, f"/groups/{group_id}")
            if method == "GET" and len(parts) == 4 and parts[0] == "groups" and parts[2:] == ["imports", "new"]:
                return respond(start_response, import_upload_page(database, resource_id(parts[1], "Training Group")))
            if method == "POST" and len(parts) == 4 and parts[0] == "groups" and parts[2:] == ["imports", "preview"]:
                group_id = resource_id(parts[1], "Training Group")
                fields, files = multipart_form(environ)
                upload = files.get("csv_file")
                if not upload or not upload["payload"]:
                    raise ValueError("Choose a CSV file to preview.")
                year_text = fields.get("year", "").strip()
                preview = build_preview(
                    database, upload["payload"], upload["filename"], group_id,
                    fields.get("distance", ""), fields.get("unit", ""), int(year_text) if year_text else None,
                    fields.get("surface_type"), fields.get("timing_method"), fields.get("environment"),
                    fields.get("protocol_notes"),
                )
                if len(import_previews) >= 20:
                    import_previews.pop(next(iter(import_previews)))
                token = secrets.token_urlsafe(24)
                import_previews[token] = preview
                return respond(start_response, import_preview_page(database, token, preview))
            if method == "POST" and len(parts) == 4 and parts[0] == "groups" and parts[2:] == ["imports", "confirm"]:
                group_id = resource_id(parts[1], "Training Group")
                data = form_data(environ)
                token = data.get("preview_token", "")
                preview = import_previews.get(token)
                if not preview or preview["group_id"] != group_id:
                    raise ValueError("This import preview expired. Upload the CSV again.")
                resolutions = {
                    athlete["source_row"]: data.get(f"resolution_{athlete['source_row']}", "")
                    for athlete in preview["athletes"]
                }
                conflicts = {
                    conflict["date"]: data.get(f"conflict_{conflict['date']}", "")
                    for conflict in preview["conflicts"]
                }
                summary = confirm_import(
                    database, preview, resolutions, conflicts,
                    acknowledge_issues=data.get("acknowledge_issues") == "yes",
                )
                import_previews.pop(token, None)
                return respond(start_response, import_summary_page(database, group_id, summary))
            if method == "GET" and len(parts) == 2 and parts[0] == "groups":
                return respond(start_response, group_page(database, resource_id(parts[1], "Training Group")))
            if method == "POST" and len(parts) == 3 and parts[0] == "groups" and parts[2] == "athletes":
                group_id = resource_id(parts[1], "Training Group")
                database.create_group_athlete(group_id, form_data(environ).get("name", ""))
                return redirect(start_response, f"/groups/{group_id}")
            if method == "POST" and len(parts) == 4 and parts[0] == "groups" and parts[2:] == ["athletes", "existing"]:
                group_id = resource_id(parts[1], "Training Group")
                database.add_existing_group_athlete(
                    group_id, resource_id(form_data(environ).get("athlete_id"), "athlete")
                )
                return redirect(start_response, f"/groups/{group_id}")
            if method == "POST" and len(parts) == 4 and parts[0] == "groups" and parts[2:] == ["roster", "reorder"]:
                group_id = resource_id(parts[1], "Training Group")
                data = form_data(environ)
                database.reorder_group_athlete(
                    group_id, resource_id(data.get("athlete_id"), "athlete"), data.get("direction", ""),
                )
                return redirect(start_response, f"/groups/{group_id}")
            if method == "POST" and len(parts) == 4 and parts[0] == "groups" and parts[2:] == ["roster", "transfer"]:
                group_id = resource_id(parts[1], "Training Group")
                data = form_data(environ)
                action = data.get("action", "")
                if action not in {"copy", "move"}:
                    raise ValueError("Choose copy or move.")
                database.transfer_group_athlete(
                    group_id, resource_id(data.get("athlete_id"), "athlete"),
                    resource_id(data.get("target_group_id"), "Training Group"), move=action == "move",
                )
                return redirect(start_response, f"/groups/{group_id}")
            if method == "POST" and len(parts) == 4 and parts[0] == "groups" and parts[2:] == ["roster", "remove"]:
                group_id = resource_id(parts[1], "Training Group")
                database.remove_group_athlete(
                    group_id, resource_id(form_data(environ).get("athlete_id"), "athlete"),
                )
                return redirect(start_response, f"/groups/{group_id}")
            if method == "POST" and len(parts) == 3 and parts[0] == "groups" and parts[2] == "sessions":
                group_id = resource_id(parts[1], "Training Group")
                data = form_data(environ)
                session_id = database.add_group_session(
                    group_id, normalize_distance(data.get("distance", "")), data.get("unit", ""),
                    selected_protocol(data.get("protocol_key")), optional_attempt_count(data.get("target_attempts")),
                    data.get("surface_type"), data.get("timing_method"), data.get("environment"),
                    data.get("protocol_notes"),
                )
                return redirect(start_response, f"/sessions/{session_id}")
            if method == "POST" and len(parts) == 3 and parts[0] == "sessions" and parts[2] == "athletes":
                session_id = resource_id(parts[1], "session")
                database.add_session_athlete(session_id, form_data(environ).get("name", ""))
                return redirect(start_response, f"/sessions/{session_id}")
            if method == "POST" and len(parts) == 3 and parts[0] == "sessions" and parts[2] == "complete":
                session_id = resource_id(parts[1], "session")
                database.complete_session(session_id)
                group = database.session_group(session_id)
                return redirect(start_response, f"/groups/{group['id']}" if group else "/")
            if method == "POST" and len(parts) == 3 and parts[0] == "sessions" and parts[2] == "delete":
                session_id = resource_id(parts[1], "session")
                group_id = database.delete_session(session_id)
                return redirect(start_response, f"/groups/{group_id}" if group_id else "/")
            if method == "GET" and len(parts) == 2 and parts[0] == "sessions":
                session_id = resource_id(parts[1], "session")
                return respond(start_response, session_page(database, session_id))
            if method == "GET" and len(parts) == 5 and parts[0:2] == ["api", "sessions"] and parts[3] == "athletes":
                session_id = resource_id(parts[2], "session")
                athlete_id = resource_id(parts[4], "athlete")
                return json_response(start_response, athlete_summary(database, session_id, athlete_id))
            if method == "POST" and len(parts) == 4 and parts[0:2] == ["api", "sessions"] and parts[3] == "attempts":
                session_id = resource_id(parts[2], "session")
                data = json_data(environ)
                athlete_id = resource_id(data.get("athlete_id", ""), "athlete")
                attempt_id = database.add_attempt(
                    session_id, athlete_id, seconds_to_milliseconds(data.get("elapsed_seconds", "")),
                    data.get("request_id"),
                )
                return json_response(start_response, athlete_summary(database, session_id, athlete_id, attempt_id), "201 Created")
            if method == "POST" and len(parts) == 4 and parts[0:2] == ["api", "attempts"] and parts[3] == "edit":
                attempt_id = resource_id(parts[2], "attempt")
                session_id, athlete_id = database.update_attempt(attempt_id, seconds_to_milliseconds(json_data(environ).get("elapsed_seconds", "")))
                return json_response(start_response, athlete_summary(database, session_id, athlete_id))
            if method == "POST" and len(parts) == 4 and parts[0:2] == ["api", "attempts"] and parts[3] == "delete":
                attempt_id = resource_id(parts[2], "attempt")
                session_id, athlete_id = database.delete_attempt(attempt_id)
                return json_response(start_response, athlete_summary(database, session_id, athlete_id))
            return respond(start_response, page("Not found", "<h1>Page not found</h1>"), "404 Not Found")
        except LookupError as error:
            if path.startswith("/api/"):
                return json_response(start_response, {"error": str(error)}, "404 Not Found")
            return respond(start_response, page("Not found", f"<h1>Not found</h1><p>{html.escape(str(error))}</p><p><a href='/'>Go back</a></p>"), "404 Not Found")
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
            if path.startswith("/api/"):
                return json_response(start_response, {"error": str(error)}, "400 Bad Request")
            return respond(start_response, page("Check your entry", f"<h1>Check your entry</h1><p>{html.escape(str(error))}</p><p><a href='/'>Go back</a></p>"), "400 Bad Request")

    def app(environ, start_response):
        started = perf_counter()
        captured: dict = {}

        def capture_response(status, headers, exc_info=None):
            captured["status"] = status
            captured["headers"] = list(headers)
            captured["exc_info"] = exc_info

        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/") or "/"
        client_ip = environ.get("REMOTE_ADDR") or "-"
        if config.auth_enabled:
            environ["aip.session"] = read_session(environ, config.session_secret or "")
        try:
            response = handle_request(environ, capture_response)
        except Exception:
            elapsed_ms = (perf_counter() - started) * 1000
            print(f"{client_ip} {method} {path} 500 app={elapsed_ms:.1f}ms bytes=0", flush=True)
            raise

        elapsed_ms = (perf_counter() - started) * 1000
        status = captured.get("status", "500 Internal Server Error")
        headers = [
            (name, value) for name, value in captured.get("headers", [])
            if name.lower() != "server-timing"
        ]
        headers.append(("Server-Timing", f"app;dur={elapsed_ms:.3f}"))
        headers.extend(security_headers(request_is_secure(environ, config)))
        if path == "/diagnostics/ping":
            headers.append(("Cache-Control", "no-store"))
        if (config.auth_enabled and environ.get("aip.session") and isinstance(response, (list, tuple))
                and any(name.lower() == "content-type" and value.startswith("text/html") for name, value in headers)):
            response = [inject_csrf(b"".join(response), environ["aip.session"]["csrf"])]
            headers = [(name, value) for name, value in headers if name.lower() != "content-length"]
        body_size = sum(len(chunk) for chunk in response) if isinstance(response, (list, tuple)) else 0
        if not any(name.lower() == "content-length" for name, _ in headers) and isinstance(response, (list, tuple)):
            headers.append(("Content-Length", str(body_size)))
        if captured.get("exc_info") is None:
            start_response(status, headers)
        else:
            start_response(status, headers, captured["exc_info"])
        status_code = status.split(" ", 1)[0]
        print(f"{client_ip} {method} {path} {status_code} app={elapsed_ms:.1f}ms bytes={body_size}", flush=True)
        return response

    app.database = database
    app.import_previews = import_previews
    app.config = config
    app.login_failures = login_failures
    return app


def login_page(error: str = "") -> str:
    message = f"<p class='error'>{html.escape(error)}</p>" if error else ""
    body = f"""
    <header><p class='eyebrow'>Athlete Intelligence Platform</p><h1>Coach sign in</h1></header>
    <main class='capture-layout'><section class='card'>{message}<form method='post' action='/login'>
      <label>Username<input name='username' autocomplete='username' required></label>
      <label>Password<input type='password' name='password' autocomplete='current-password' required></label>
      <button>Sign in</button>
    </form></section></main>"""
    return page("Coach sign in", body, show_nav=False)


def home_page(db: Database) -> str:
    athlete_items = "".join(f"<li>{html.escape(a['name'])}</li>" for a in db.all_athletes()) or "<li class='muted'>No athletes yet</li>"
    all_sessions = db.all_sessions()
    active_sessions = [session for session in all_sessions if session["status"] == "open"]
    completed_sessions = [session for session in all_sessions if session["status"] == "completed"]
    session_items = "".join(
        session_link(s) for s in active_sessions
    ) or "<p class='muted'>No active sessions.</p>"
    completed_items = "".join(session_link(s) for s in completed_sessions[:10]) or "<p class='muted'>No completed sessions yet.</p>"
    group_items = "".join(
        f"<a class='session-link' href='/groups/{g['id']}'><strong>{html.escape(g['name'])}</strong>"
        f"<span>{g['athlete_count']} athletes · {g['session_count']} sessions</span></a>" for g in db.all_groups()
    ) or "<p class='muted'>Create your first recurring Training Group.</p>"
    body = f"""
    <header><p class='eyebrow'>Athlete Intelligence Platform</p><h1>Manual sprint capture</h1><p>Reuse a Training Group roster, then start or continue an active measurement session.</p></header>
    <main class='home-grid'>
      <section class='card groups'><h2>Training Groups</h2><form method='post' action='/groups' class='inline-form'><label>Group name<input name='name' maxlength='100' required data-desktop-autofocus placeholder='Park City Football'></label><button>Create group</button></form>{group_items}</section>
      <section class='card sessions'><h2>Active sessions</h2>{session_items}<details class='completed-sessions'><summary>Completed session history</summary>{completed_items}</details></section>
      <details class='card legacy'><summary>Standalone capture tools</summary><p class='muted'>Existing FEAT-001 workflows remain available for sessions without a Training Group.</p><h3>Athletes</h3><form method='post' action='/athletes' class='inline-form'><label>Name<input name='name' maxlength='100' required placeholder='Athlete name'></label><button>Add athlete</button></form><ul>{athlete_items}</ul><h3>New standalone session</h3>{session_form('/sessions')} </details>
    </main>"""
    return page("Sprint capture", body)


def intelligence_page(db: Database, athlete_id: str, case_study: str) -> str:
    """Minimal internal inspection view for verified Athlete Intelligence cases."""
    snapshot = db.intelligence_snapshot(athlete_id)
    athlete = snapshot["athlete"]
    identities = "".join(
        f"<li><strong>{html.escape(item['source_system'])}</strong> · "
        f"{html.escape(item['source_entity_type'])} {html.escape(item['source_record_id'])} · "
        f"{html.escape(item['source_display_name'] or '')} · {'verified' if item['verified_at'] else 'unverified'}</li>"
        for item in snapshot["external_identities"]
    )
    states = "".join(
        f"<li><strong>{html.escape(item['state_type'])}</strong> · {html.escape(item['label'] or '')} · "
        f"{html.escape(item['effective_from'] or 'unknown')} → {html.escape(item['effective_to'] or 'current')}"
        f"<pre>{html.escape(item['attributes'] or '{}')}</pre></li>" for item in snapshot["states"]
    )
    evidence_by_id = {item["id"]: item for item in snapshot["evidence"]}
    links_by_record: dict[str, list[dict]] = {}
    for link in snapshot["links"]:
        links_by_record.setdefault(link["intelligence_record_id"], []).append(link)
    records = []
    for record in snapshot["records"]:
        links = "".join(
            f"<li>{html.escape(link['relationship_type'])}: "
            f"{html.escape(evidence_by_id[link['evidence_id']]['source_system'])}/"
            f"{html.escape(evidence_by_id[link['evidence_id']]['source_entity_type'])}/"
            f"{html.escape(evidence_by_id[link['evidence_id']]['source_record_id'])}</li>"
            for link in links_by_record.get(record["id"], [])
        )
        records.append(
            f"<article class='card'><p class='eyebrow'>{html.escape(record['type'])} · "
            f"{html.escape(record['epistemic_class'] or 'unclassified')} · "
            f"{html.escape(record['status'])} · {html.escape(record['confidence'] or 'unrated')}</p>"
            f"<p>{html.escape(record['statement'])}</p>{f'<ul>{links}</ul>' if links else ''}</article>"
        )
    evidence_items = []
    for item in snapshot["evidence"]:
        metadata = f"<pre>{html.escape(item['metadata'])}</pre>" if item["metadata"] else ""
        evidence_items.append(
            f"<li><strong>{html.escape(item['evidence_type'])}</strong> · "
            f"{html.escape(item['source_system'])}/{html.escape(item['source_entity_type'])}/"
            f"{html.escape(item['source_record_id'])} · {html.escape(item['summary'] or '')}"
            f"{metadata}</li>"
        )
    evidence = "".join(evidence_items)
    open_questions = "".join(
        f"<li>{html.escape(record['statement'])}</li>" for record in snapshot["records"]
        if record["type"] == "open_question" and record["status"] == "active"
    ) or "<li>None.</li>"
    body = f"""
    <header><a href='/'>← Sprint capture</a><p class='eyebrow'>Internal inspection · {html.escape(case_study)}</p>
      <h1>{html.escape(athlete['display_name'])}</h1><p>Canonical UUID: <code>{html.escape(athlete['id'])}</code></p></header>
    <main class='feedback-list'><section class='card'><h2>External identities</h2><ul>{identities}</ul>
      <h2>Athlete state</h2><ul>{states}</ul><h2>Active open questions</h2><ul>{open_questions}</ul>
      <h2>Evidence references</h2><ul>{evidence}</ul></section>
      <section><h2>Intelligence records</h2>{''.join(records)}</section></main>"""
    return page("Athlete Intelligence", body)


def group_page(db: Database, group_id: int) -> str:
    group = db.group(group_id)
    if not group:
        raise LookupError("Training Group not found.")
    roster = db.group_roster(group_id)
    roster_ids = {athlete["id"] for athlete in roster}
    available_athletes = [athlete for athlete in db.athlete_directory() if athlete["id"] not in roster_ids]
    directory_json = json.dumps(available_athletes).replace("<", "\\u003c")
    target_groups = [item for item in db.all_groups() if item["id"] != group_id]
    target_options = "".join(
        f"<option value='{item['id']}'>{html.escape(item['name'])}</option>" for item in target_groups
    )
    roster_items = "".join(
        roster_member_controls(group_id, athlete, target_options, bool(target_groups)) for athlete in roster
    ) or "<li class='muted'>No athletes yet.</li>"
    all_sessions = db.group_sessions(group_id)
    active_sessions = [session for session in all_sessions if session["status"] == "open"]
    completed_sessions = [session for session in all_sessions if session["status"] == "completed"]
    active = "".join(session_entry(session, group["name"]) for session in active_sessions) or "<p class='muted'>No active sessions.</p>"
    completed = "".join(session_entry(session, group["name"]) for session in completed_sessions) or "<p class='muted'>No completed sessions yet.</p>"
    disabled = "disabled" if not roster else ""
    body = f"""
    <header><a href='/'>← Training Groups</a><p class='eyebrow'>Recurring Training Group</p><h1>{html.escape(group['name'])}</h1><p>{len(roster)} athletes in persistent training order.</p></header>
    <main class='home-grid'>
      <section class='card roster-card'><h2>Persistent roster</h2><p class='muted'>Changes apply to future sessions. Existing session rosters stay unchanged.</p>
        <div class='athlete-picker'><label>Find an existing athlete<input id='existing-athlete-search' maxlength='100' autocomplete='off' data-desktop-autofocus placeholder='Type part of a name'></label><p class='muted'>Matching athletes will appear as you type.</p><div id='existing-athlete-results' class='athlete-search-results' aria-live='polite'></div></div>
        <details class='create-athlete'><summary>Create a new athlete</summary><form method='post' action='/groups/{group_id}/athletes' class='inline-form'><label>New athlete name<input name='name' maxlength='100' required placeholder='Full athlete name'></label><button>Create and add</button></form><p class='muted'>Use this only when the athlete does not already exist.</p></details>
        <ol class='roster'>{roster_items}</ol></section>
      <section class='card'><h2>Start a session</h2>{session_form(f'/groups/{group_id}/sessions', disabled)}{'<p class="notice">Add an athlete before starting a session.</p>' if not roster else ''}</section>
      <section class='card sessions'><h2>Active sessions</h2>{active}<details class='completed-sessions'><summary>Completed session history</summary>{completed}</details><h3>Historical data</h3><p><a class='button-link' href='/groups/{group_id}/imports/new'>Import historical sprint CSV</a></p><h3>Export sprint data</h3><form method='get' action='/groups/{group_id}/export.csv' class='export-form'><label>Start date (optional)<input type='date' name='start'></label><label>End date (optional)<input type='date' name='end'></label><button>Export Group CSV</button></form></section>
    </main><script>const athleteDirectory={directory_json};const athleteSearch=document.querySelector('#existing-athlete-search'),athleteResults=document.querySelector('#existing-athlete-results');
      const escapeAthleteText=value=>String(value).replace(/[&<>'"]/g,character=>({{'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}}[character]));
      function showAthleteMatches(){{const query=athleteSearch.value.trim().toLowerCase();if(!query){{athleteResults.innerHTML='';return;}}const matches=athleteDirectory.filter(item=>item.name.toLowerCase().includes(query)).slice(0,10);athleteResults.innerHTML=matches.map(item=>`<form method="post" action="/groups/{group_id}/athletes/existing" class="athlete-search-result"><input type="hidden" name="athlete_id" value="${{item.id}}"><span><strong>${{escapeAthleteText(item.name)}}</strong><small>${{item.groups.length?escapeAthleteText(item.groups.map(group=>group.name).join(' · ')):'Not currently in a group'}}</small></span><button>Add</button></form>`).join('')||(query.length<2?'<p class="muted">Type another letter to narrow the list.</p>':'<p class="muted">No existing athletes match. Create a new athlete below if needed.</p>');}}
      athleteSearch.addEventListener('input',showAthleteMatches);</script>"""
    return page(group["name"], body)


def roster_member_controls(group_id: int, athlete: dict, target_options: str, has_targets: bool) -> str:
    athlete_id = athlete["id"]
    transfer = f"""<form method='post' action='/groups/{group_id}/roster/transfer' class='roster-transfer'>
      <input type='hidden' name='athlete_id' value='{athlete_id}'>
      <label>Group<select name='target_group_id' required>{target_options}</select></label>
      <button name='action' value='move'>Move</button><button name='action' value='copy'>Add to both</button>
    </form>""" if has_targets else "<span class='muted'>Create another group to move this athlete.</span>"
    return f"""<li class='roster-member'><div class='roster-person'><span class='position'>{athlete['position']}</span><strong>{html.escape(athlete['name'])}</strong></div>
      <div class='roster-actions'><form method='post' action='/groups/{group_id}/roster/reorder'>
        <input type='hidden' name='athlete_id' value='{athlete_id}'><button name='direction' value='up' aria-label='Move {html.escape(athlete['name'])} up'>↑</button><button name='direction' value='down' aria-label='Move {html.escape(athlete['name'])} down'>↓</button>
      </form>{transfer}<form method='post' action='/groups/{group_id}/roster/remove' onsubmit="return confirm('Remove this athlete from future sessions in this group?')">
        <input type='hidden' name='athlete_id' value='{athlete_id}'><button class='text-danger'>Remove</button>
      </form></div></li>"""


def session_label(session: dict, group_name: str | None = None) -> str:
    owner = group_name or session.get("group_name") or "Standalone"
    test = (f"{session['distance']} {session['unit']} · 10-yard fly"
            if session.get("protocol_key") == "flying_10_acceleration_5yd_run_in"
            else f"{session['distance']} {session['unit']} · protocol unspecified")
    return f"{owner} · {session['session_date']} · {test}"


def session_form(action: str, disabled: str = "") -> str:
    return f"""<form method='post' action='{action}' class='session-form'>
      <label>Test protocol<select name='protocol_key' required>
        <option value='flying_10_acceleration_5yd_run_in'>10-yard fly</option>
        <option value='unspecified'>Other / protocol not yet documented</option>
      </select></label>
      <label>Timed distance<input name='distance' inputmode='decimal' required value='10'></label>
      <label>Unit<select name='unit'><option value='yards'>yards</option><option value='meters'>meters</option></select></label>
      <label>Planned attempts<select name='target_attempts'><option value='4'>4 (ideal)</option><option value='2'>2</option></select></label>
      <label>Surface<select name='surface_type' required><option value='turf'>Turf</option><option value='track'>Track</option><option value='court'>Court</option><option value='grass'>Grass</option><option value='other'>Other</option></select></label>
      <label>Timing method<select name='timing_method' required><option value='timing-gates'>Timing gates</option><option value='laser'>Laser</option><option value='video'>Video</option><option value='hand-timed'>Hand-timed</option><option value='other'>Other</option></select></label>
      <label>Environment<select name='environment' required><option value='indoor'>Indoor</option><option value='outdoor'>Outdoor</option></select></label>
      <label>Notes (optional)<input name='protocol_notes' maxlength='1000' placeholder='Footwear, weather, setup differences'></label>
      <button {disabled}>Start capture</button>
      <p class='muted'>10-yard fly: two-point set, 5-yard untimed run-in, timed from 5–15 yards; acceleration test. Legacy name: 10-yard sprint.</p>
    </form>"""


def session_link(session: dict, group_name: str | None = None) -> str:
    label = html.escape(session_label(session, group_name))
    return (
        f"<a class='session-link' href='/sessions/{session['id']}'><strong>{label}</strong>"
        f"<span>{session['attempt_count']} attempts · {session['status']}</span></a>"
    )


def session_entry(session: dict, group_name: str) -> str:
    return f"""<article class='session-entry'>{session_link(session, group_name)}
      <form method='post' action='/sessions/{session['id']}/delete' onsubmit=\"return confirm('Permanently delete this session and all of its sprint attempts?')\">
        <button class='text-danger'>Delete</button>
      </form>
    </article>"""


def import_upload_page(db: Database, group_id: int) -> str:
    group = db.group(group_id)
    if not group:
        raise LookupError("Training Group not found.")
    body = f"""
    <header><a href='/groups/{group_id}'>← {html.escape(group['name'])}</a><p class='eyebrow'>FEAT-004</p><h1>Import historical sprint results</h1><p>Upload a wide CSV to preview it. Nothing is saved until you review and confirm.</p></header>
    <main><section class='card import-card'><form method='post' action='/groups/{group_id}/imports/preview' enctype='multipart/form-data' class='import-form'>
      <label>CSV file<input type='file' name='csv_file' accept='.csv,text/csv' required></label>
      <label>Distance<input name='distance' inputmode='decimal' required></label>
      <label>Unit<select name='unit' required><option value='yards'>yards</option><option value='meters'>meters</option></select></label>
      <label>Surface<select name='surface_type' required><option value='turf'>Turf</option><option value='track'>Track</option><option value='court'>Court</option><option value='grass'>Grass</option><option value='other'>Other</option></select></label>
      <label>Timing method<select name='timing_method' required><option value='timing-gates'>Timing gates</option><option value='laser'>Laser</option><option value='video'>Video</option><option value='hand-timed'>Hand-timed</option><option value='other'>Other</option></select></label>
      <label>Environment<select name='environment' required><option value='indoor'>Indoor</option><option value='outdoor'>Outdoor</option></select></label>
      <label>Notes (optional)<input name='protocol_notes' maxlength='1000'></label>
      <label>Year for month/day headers (optional)<input name='year' inputmode='numeric' pattern='[0-9]{{4}}'></label>
      <button>Preview import</button>
    </form></section></main>"""
    return page("Historical sprint import", body)


def import_preview_page(db: Database, token: str, preview: dict) -> str:
    all_athletes = db.all_athletes()
    roster_ids = {athlete["id"] for athlete in db.group_roster(preview["group_id"])}
    detected = "".join(f"<li>Column {item['column']}: {html.escape(item['label'])} → {item['date']}</li>" for item in preview["date_columns"])
    skipped = "".join(f"<li>Column {item['column']}: {html.escape(item['label'] or '(blank)')} — {html.escape(item['reason'])}</li>" for item in preview["skipped_columns"]) or "<li>None</li>"
    issue_items = "".join(
        f"<li>{html.escape(issue_location(item))}{html.escape(item['message'])}</li>"
        for item in preview["issues"]
    ) or "<li>None</li>"
    possible_duplicates = sum(1 for item in preview["results"] if item.get("possible_duplicate"))
    unresolved_athletes = sum(1 for item in preview["athletes"] if item["status"] != "matched")
    candidate_sessions = len({item["source_date"] for item in preview["results"]})
    athlete_controls = []
    for athlete in preview["athletes"]:
        options = []
        selected_id = athlete["athlete_id"]
        if athlete["status"] != "matched":
            options.append("<option value=''>Choose a resolution</option>")
        for existing in all_athletes:
            selected = " selected" if existing["id"] == selected_id else ""
            roster_note = "" if existing["id"] in roster_ids else " (adds to group if outside roster)"
            options.append(f"<option value='existing:{existing['id']}'{selected}>Use {html.escape(existing['name'])}{roster_note}</option>")
        options.extend(["<option value='create'>Create athlete and add to group</option>", "<option value='exclude'>Exclude this row</option>"])
        athlete_controls.append(
            f"<tr><td>{athlete['source_row']}</td><td>{html.escape(athlete['name'])}</td><td>{athlete['status']}</td>"
            f"<td><select name='resolution_{athlete['source_row']}' required>{''.join(options)}</select></td></tr>"
        )
    conflict_controls = []
    for conflict in preview["conflicts"]:
        options = ["<option value=''>Choose a resolution</option>", "<option value='separate'>Create a separate historical session</option>"]
        options.extend(f"<option value='reuse:{session['id']}'>Reuse session {session['id']} ({session['attempt_count']} attempts)</option>" for session in conflict["sessions"])
        conflict_controls.append(f"<label>{conflict['date']} existing-session conflict<select name='conflict_{conflict['date']}' required>{''.join(options)}</select></label>")
    duplicate_warning = f"<p class='notice'>Identical upload already confirmed as batch {preview['identical_batch_id']}. Confirmation is blocked.</p>" if preview["identical_batch_id"] else ""
    duplicate_dates = any(item["kind"] == "duplicate_date" for item in preview["issues"])
    blocker = preview["identical_batch_id"] or duplicate_dates
    acknowledgement = ""
    if preview["issues"]:
        acknowledgement = "<label><input type='checkbox' name='acknowledge_issues' value='yes' required> Exclude and acknowledge the listed invalid cells/columns.</label>"
    body = f"""
    <header><a href='/groups/{preview['group_id']}/imports/new'>← Start over</a><p class='eyebrow'>No-write preview</p><h1>Review {html.escape(preview['filename'])}</h1><p>{html.escape(preview['group_name'])} · {preview['distance']} {preview['unit']}</p></header>
    <main class='import-review'><section class='card'><h2>Detected structure</h2><p>Header row {preview['header_row']}; first-name column {preview['first_column']}; last-name column {preview['last_column']}.</p><h3>Confirmed testing dates</h3><ul>{detected}</ul><h3>Skipped columns</h3><ul>{skipped}</ul><p class='muted'>{preview['ordering_note']}</p></section>
      <section class='card'><h2>Proposed import</h2><ul><li>Up to {candidate_sessions} historical sessions</li><li>{len(preview['athletes'])} source athletes ({unresolved_athletes} require explicit resolution)</li><li>{len(preview['results'])} valid attempts before exclusions</li><li>{possible_duplicates} possible provenance duplicates to skip</li></ul><h2>Issues and exclusions</h2><ul>{issue_items}</ul>{duplicate_warning}</section>
      <form method='post' action='/groups/{preview['group_id']}/imports/confirm' class='card import-form'>
        <input type='hidden' name='preview_token' value='{html.escape(token)}'>
        <h2>Athlete resolutions</h2><table><thead><tr><th>Row</th><th>Source name</th><th>Match</th><th>Resolution</th></tr></thead><tbody>{''.join(athlete_controls)}</tbody></table>
        {''.join(conflict_controls)}{acknowledgement}
        <p>Confirmation would process {len(preview['results'])} valid results across {len(preview['date_columns'])} date columns.</p>
        <button{' disabled' if blocker else ''}>Confirm atomic import</button>
      </form></main>"""
    return page("Review historical import", body)


def import_summary_page(db: Database, group_id: int, summary: dict) -> str:
    body = f"""
    <header><a href='/groups/{group_id}'>← Training Group</a><p class='eyebrow'>Import complete</p><h1>Historical sprint import confirmed</h1></header>
    <main><section class='card'><h2>Batch {summary['batch_id']}</h2><ul>
      <li>{summary['sessions_created']} historical sessions created</li><li>{summary['sessions_reused']} sessions reused</li>
      <li>{summary['created_athletes']} athletes intentionally created</li><li>{summary['attempts_created']} attempts created</li>
      <li>{summary['duplicates_skipped']} duplicate results skipped</li><li>{summary['excluded_rows']} rows excluded</li>
      <li>{summary['excluded_issues']} warnings retained for audit</li></ul></section></main>"""
    return page("Historical import complete", body)


def issue_location(issue: dict) -> str:
    parts = []
    if issue.get("row"):
        parts.append(f"row {issue['row']}")
    if issue.get("column"):
        parts.append(f"column {issue['column']}")
    return f"{' / '.join(parts)}: " if parts else ""


def session_page(db: Database, session_id: int) -> str:
    session = db.session(session_id)
    if not session:
        raise LookupError("Session not found.")
    athletes = db.session_athletes(session_id)
    group = db.session_group(session_id)
    athlete_data = [{"id": athlete["id"], "name": athlete["name"]} for athlete in athletes]
    athlete_json = json.dumps(athlete_data).replace("<", "\\u003c")
    options = "".join(
        f"<option value='{index} · {html.escape(athlete['name'])}'></option>" for index, athlete in enumerate(athletes, 1)
    )
    empty = "" if athletes else "<p class='notice'>Add an athlete from the home page before recording an attempt.</p>"
    back_link = f"/groups/{group['id']}" if group else "/"
    completed = session["status"] == "completed"
    disabled = "disabled" if completed or not athletes else ""
    status_notice = (
        "<p class='notice'>This session is complete. Results are preserved and capture is closed.</p>"
        if completed else ""
    )
    add_athlete = ""
    if group and not completed:
        add_athlete = f"""<details class='add-session-athlete'><summary>Add a late athlete</summary>
          <form method='post' action='/sessions/{session_id}/athletes' class='inline-form'>
            <label>Athlete name<input name='name' maxlength='100' required placeholder='Athlete name'></label>
            <button>Add to session and group</button>
          </form><p class='muted'>Adds the athlete to this active session and future {html.escape(group['name'])} sessions.</p>
        </details>"""
    lifecycle_actions = f"""<div class='session-actions'>
      <a class='button-link' href='/sessions/{session_id}/export.csv'>Export Session CSV</a>
      {'' if completed else f'''<form method='post' action='/sessions/{session_id}/complete' onsubmit=\"return confirm('Complete this session? New attempts will be closed.')\"><button>Complete session</button></form>'''}
      <form method='post' action='/sessions/{session_id}/delete' onsubmit=\"return confirm('Permanently delete this session and all of its sprint attempts?')\"><button class='danger-button'>Delete session</button></form>
    </div>"""
    body = f"""
    <header class='capture-header'><a href='{back_link}'>← Sessions</a><p class='capture-context'>{html.escape(session_label(session, group['name'] if group else None))} · {'Completed session' if completed else 'Live'}</p><p class='muted'>{html.escape(session_conditions(session))}</p></header>
    <main class='capture-layout'>
      <section class='capture-card'>
        {status_notice}{empty}<form id='capture-form' data-session='{session_id}' data-completed='{'true' if completed else 'false'}'>
          <div class='athlete-flow'><button type='button' id='previous-athlete' class='flow-button' aria-label='Previous athlete'>←</button><div class='active-athlete'><span id='athlete-position'>Athlete</span><strong id='athlete-name'>Choose athlete</strong></div><button type='button' id='next-athlete' class='flow-button' aria-label='Next athlete'>→</button></div>
          <input type='hidden' id='athlete' required>
          <label>Time (seconds)<div class='time-row'><input id='elapsed' inputmode='decimal' autocomplete='off' placeholder='1.72' required {disabled}></div></label>
          <p class='autosave-note'>{'Capture is closed.' if completed else 'Times save automatically after you finish typing. Press Enter to save immediately.'}</p>
          <div class='up-next'><p class='eyebrow'>Next three</p><ol id='up-next-list'></ol></div>
        </form><p id='feedback' role='status' aria-live='polite'></p>
        <div id='results'><p class='muted'>Select an athlete to see their results.</p></div>
        <details class='secondary-controls'><summary>Jump to another athlete</summary><label class='jump-label'>Athlete name or number<input id='athlete-search' list='athlete-options' autocomplete='off' placeholder='Type a name or number' {disabled}></label><datalist id='athlete-options'>{options}</datalist></details>
        {add_athlete}
        <p class='shortcut'><kbd>Alt</kbd> + <kbd>→</kbd> next · <kbd>Alt</kbd> + <kbd>←</kbd> previous · <kbd>Alt</kbd> + <kbd>A</kbd> jump</p>
      </section>
    </main>
    <footer class='session-management card'><p class='eyebrow'>Session management</p>{lifecycle_actions}</footer>
    <script>const athletes={athlete_json};{CAPTURE_SCRIPT}</script>"""
    return page(f"{session['distance']} {session['unit']} capture", body, show_nav=False)


def session_conditions(session: dict) -> str:
    values = [session.get("surface_type") or "surface unspecified",
              session.get("timing_method") or "timing unspecified",
              session.get("environment") or "environment unspecified"]
    if session.get("protocol_notes"):
        values.append(session["protocol_notes"])
    return " · ".join(values)


def athlete_summary(db: Database, session_id: int, athlete_id: int, saved_attempt_id: int | None = None) -> dict:
    session = db.session(session_id)
    if not session:
        raise LookupError("Session not found.")
    athlete = db.athlete(athlete_id)
    if not athlete:
        raise LookupError("Athlete not found.")
    all_attempts = classify_attempts(db.all_attempts())
    comparable = [
        a for a in all_attempts
        if a["athlete_id"] == athlete_id and a["distance"] == session["distance"] and a["unit"] == session["unit"]
        and a.get("protocol_key") == session.get("protocol_key")
        and a.get("surface_type") == session.get("surface_type")
        and a.get("timing_method") == session.get("timing_method")
    ]
    session_attempts = [a for a in comparable if a["session_id"] == session_id]
    prior_sessions = {}
    current_key = (session["session_date"], session_id)
    for attempt in comparable:
        attempt_key = (attempt["session_date"], attempt["session_id"])
        if attempt["session_id"] != session_id and attempt_key < current_key:
            prior_sessions.setdefault(attempt_key, []).append(attempt)
    previous_session = None
    if prior_sessions:
        previous_key = max(prior_sessions)
        previous_attempts = prior_sessions[previous_key]
        previous_session = {
            "date": previous_key[0],
            "best": format_seconds(min(a["elapsed_ms"] for a in previous_attempts)),
        }
    all_time_best = None
    if comparable:
        fastest = min(comparable, key=lambda a: (a["elapsed_ms"], a["captured_at"], a["id"]))
        all_time_best = {"time": format_seconds(fastest["elapsed_ms"]), "date": fastest["session_date"]}
    attempts = []
    for attempt in reversed(session_attempts):
        attempts.append({
            "id": attempt["id"], "time": format_seconds(attempt["elapsed_ms"]), "status": attempt["status"],
            "just_saved": attempt["id"] == saved_attempt_id,
        })
    return {
        "athlete_name": athlete["name"],
        "best": format_seconds(min(a["elapsed_ms"] for a in session_attempts)) if session_attempts else None,
        "attempts": attempts,
        "all_time_best": all_time_best,
        "previous_session": previous_session,
        "editable": session["status"] == "open",
    }


def feedback_form_page(db: Database) -> str:
    group_options = "".join(
        f"<option value='{group['id']}'>{html.escape(group['name'])}</option>" for group in db.all_groups()
    )
    session_options = "".join(
        f"<option value='{session['id']}'>Session {session['id']} · {html.escape(session['distance'])} {session['unit']} · {session['created_at']}</option>"
        for session in db.all_sessions()
    )
    body = f"""
    <header><a href='/'>← Sprint capture</a><p class='eyebrow'>Local prototype feedback</p><h1>Send feedback</h1><p>Capture what happened while it is still fresh. Responses stay in this local prototype.</p></header>
    <main class='feedback-layout'><form method='post' action='/feedback' class='card feedback-form'>
      <label>What slowed you down?<textarea name='slowed_down' maxlength='5000' rows='4'></textarea></label>
      <label>What worked well?<textarea name='worked_well' maxlength='5000' rows='4'></textarea></label>
      <label>What feature did you wish existed?<textarea name='wished_for' maxlength='5000' rows='4'></textarea></label>
      <div class='feedback-context'><label>Training Group (optional)<select name='group_id'><option value=''>None</option>{group_options}</select></label><label>Session (optional)<select name='session_id'><option value=''>None</option>{session_options}</select></label></div>
      <button>Save feedback</button><p class='muted'>At least one response is required.</p>
    </form><p><a href='/feedback'>View saved feedback</a></p></main>"""
    return page("Send feedback", body)


def feedback_list_page(db: Database) -> str:
    items = []
    for entry in db.all_feedback():
        context = []
        if entry["group_name"]:
            context.append(html.escape(entry["group_name"]))
        if entry["session_id"]:
            context.append(
                f"Session {entry['session_id']} · {html.escape(entry['session_distance'])} {entry['session_unit']}"
            )
        answers = "".join(
            f"<div><h3>{label}</h3><p>{html.escape(entry[field])}</p></div>"
            for field, label in (
                ("slowed_down", "What slowed you down?"),
                ("worked_well", "What worked well?"),
                ("wished_for", "What feature did you wish existed?"),
            )
            if entry[field]
        )
        context_text = " · ".join(context) if context else "No group or session attached"
        items.append(
            f"<article class='card feedback-entry'><p class='eyebrow'>{entry['created_at']} · {context_text}</p>{answers}</article>"
        )
    entries = "".join(items) or "<section class='card'><p class='muted'>No feedback has been saved yet.</p></section>"
    body = f"""<header><a href='/'>← Sprint capture</a><p class='eyebrow'>Local prototype feedback</p><h1>Feedback</h1><p>Newest feedback appears first.</p><a class='button-link' href='/feedback/new'>Send feedback</a></header><main class='feedback-list'>{entries}</main>"""
    return page("Feedback", body)


def page(title: str, body: str, *, show_nav: bool = True) -> str:
    nav = "<nav class='prototype-nav'><a class='button-link' href='/feedback/new'>Send Feedback</a></nav>" if show_nav else ""
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)} · AIP</title><style>{STYLES}</style></head><body>{nav}{body}<script>{DESKTOP_FOCUS_SCRIPT}</script></body></html>"


def form_data(environ) -> dict[str, str]:
    length = int(environ.get("CONTENT_LENGTH") or 0)
    parsed = parse_qs(environ["wsgi.input"].read(length).decode())
    return {key: values[0] for key, values in parsed.items()}


def multipart_form(environ) -> tuple[dict[str, str], dict[str, dict]]:
    content_type = environ.get("CONTENT_TYPE", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise ValueError("Upload the CSV using the import form.")
    try:
        length = int(environ.get("CONTENT_LENGTH") or "0")
    except ValueError:
        raise ValueError("The upload length is invalid.") from None
    if length <= 0 or length > 5_500_000:
        raise ValueError("CSV uploads must be 5 MB or smaller.")
    payload = environ["wsgi.input"].read(length)
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + payload
    )
    if not message.is_multipart():
        raise ValueError("The upload form is malformed.")
    fields, files = {}, {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        content = part.get_payload(decode=True) or b""
        if filename is not None:
            files[name] = {"filename": Path(filename).name or "upload.csv", "payload": content}
        else:
            fields[name] = content.decode(part.get_content_charset() or "utf-8")
    return fields, files


def json_data(environ) -> dict:
    length = int(environ.get("CONTENT_LENGTH") or 0)
    return json.loads(environ["wsgi.input"].read(length).decode() or "{}")


def resource_id(value, resource: str) -> int:
    try:
        identifier = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {resource} identifier.") from None
    if identifier <= 0:
        raise ValueError(f"Invalid {resource} identifier.")
    return identifier


def optional_resource_id(value, resource: str) -> int | None:
    return None if value is None or str(value).strip() == "" else resource_id(value, resource)


def selected_protocol(value: str | None) -> str | None:
    return None if value in (None, "", "unspecified") else value


def optional_attempt_count(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        count = int(value)
    except (TypeError, ValueError):
        raise ValueError("Typical attempt count must be 2 or 4.") from None
    if count not in {2, 4}:
        raise ValueError("Typical attempt count must be 2 or 4.")
    return count


def first_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def respond(start_response, content: str, status: str = "200 OK"):
    payload = content.encode()
    start_response(status, [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(payload)))])
    return [payload]


def json_response(start_response, value: dict, status: str = "200 OK"):
    payload = json.dumps(value).encode()
    start_response(status, [("Content-Type", "application/json"), ("Content-Length", str(len(payload)))])
    return [payload]


def csv_response(start_response, payload: bytes, filename: str):
    start_response(
        "200 OK",
        [
            ("Content-Type", "text/csv; charset=utf-8"),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
            ("Content-Length", str(len(payload))),
        ],
    )
    return [payload]


def plain_text_response(start_response, content: str, status: str = "200 OK"):
    payload = content.encode()
    start_response(status, [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(payload)))])
    return [payload]


def redirect(start_response, location: str):
    start_response("303 See Other", [("Location", location), ("Content-Length", "0")])
    return [b""]


def redirect_with_cookie(start_response, location: str, cookie: str):
    start_response("303 See Other", [("Location", location), ("Set-Cookie", cookie), ("Content-Length", "0")])
    return [b""]


def request_is_secure(environ: dict, config: Config) -> bool:
    if environ.get("wsgi.url_scheme") == "https":
        return True
    forwarded = environ.get("HTTP_X_FORWARDED_PROTO", "").split(",")[0].strip()
    return bool(config.trusted_proxy and forwarded == "https")


def security_headers(secure: bool) -> list[tuple[str, str]]:
    headers = [
        ("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "no-referrer"),
        ("X-Frame-Options", "DENY"),
    ]
    if secure:
        headers.append(("Strict-Transport-Security", "max-age=31536000; includeSubDomains"))
    return headers


def csrf_from_request(environ: dict) -> str | None:
    header = environ.get("HTTP_X_CSRF_TOKEN")
    if header:
        return header
    content_type = environ.get("CONTENT_TYPE", "")
    length = int(environ.get("CONTENT_LENGTH") or 0)
    payload = environ["wsgi.input"].read(length)
    environ["wsgi.input"] = io.BytesIO(payload)
    if content_type.startswith("application/x-www-form-urlencoded"):
        return parse_qs(payload.decode()).get("csrf_token", [None])[0]
    if content_type.startswith("multipart/form-data"):
        try:
            fields, _ = multipart_form(environ)
            return fields.get("csrf_token")
        finally:
            environ["wsgi.input"] = io.BytesIO(payload)
    return None


def inject_csrf(payload: bytes, token: str) -> bytes:
    content = payload.decode()
    escaped = html.escape(token, quote=True)
    content = content.replace("</head>", f"<meta name='csrf-token' content='{escaped}'></head>")
    hidden = f"<input type='hidden' name='csrf_token' value='{escaped}'>"
    content = re.sub(r"(<form\b[^>]*\bmethod=['\"]post['\"][^>]*>)", r"\1" + hidden, content, flags=re.I)
    logout = f"<form method='post' action='/logout'>{hidden}<button>Sign out</button></form>"
    content = content.replace("</nav>", logout + "</nav>", 1)
    return content.encode()


CAPTURE_SCRIPT = r"""
const form=document.querySelector('#capture-form'), athlete=document.querySelector('#athlete'), athleteName=document.querySelector('#athlete-name'), athletePosition=document.querySelector('#athlete-position'), athleteSearch=document.querySelector('#athlete-search'), previousAthlete=document.querySelector('#previous-athlete'), nextAthlete=document.querySelector('#next-athlete'), upNextList=document.querySelector('#up-next-list'), elapsed=document.querySelector('#elapsed'), feedback=document.querySelector('#feedback'), results=document.querySelector('#results');
const sessionId=form.dataset.session;
const completed=form.dataset.completed==='true';
const finePointer=window.matchMedia('(hover: hover) and (pointer: fine)').matches;
let activeIndex=-1,saveTimer=null,saving=false,pendingRequestId=null;
const escapeHtml=s=>String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
function render(data){
  const allTime=data.all_time_best?`<strong>${escapeHtml(data.all_time_best.time)}s</strong><span>${escapeHtml(data.all_time_best.date)}</span>`:'<strong>—</strong><span>No comparable result</span>';
  const previous=data.previous_session?`<strong>${escapeHtml(data.previous_session.best)}s</strong><span>${escapeHtml(data.previous_session.date)}</span>`:'<strong>—</strong><span>No previous session</span>';
  const rows=data.attempts.map(a=>`<li class="attempt ${a.just_saved?'saved':''}"><div><strong>${escapeHtml(a.time)}s</strong> ${a.status==='baseline'?'<span class="badge baseline">Baseline</span>':a.status==='pr'?'<span class="badge pr">PR</span>':''}</div>${data.editable?`<div class="actions"><button type="button" onclick="editAttempt(${a.id}, '${escapeHtml(a.time)}')">Edit</button><button type="button" class="danger" onclick="deleteAttempt(${a.id})">Delete</button></div>`:''}</li>`).join('');
  results.innerHTML=`<div class="reference-grid"><div><p>All-time best</p>${allTime}</div><div><p>Previous session</p>${previous}</div></div><div class="current-results"><div class="result-heading"><p class="eyebrow">This session</p><div class="best"><span>Best</span><strong>${data.best?escapeHtml(data.best)+'s':'—'}</strong></div></div>${rows?`<ol class="attempts">${rows}</ol>`:'<p class="muted">No attempts yet.</p>'}</div>`;
}
async function request(url, body={}){const csrf=document.querySelector("meta[name='csrf-token']")?.content||'';const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw new Error(data.error||'Could not save.');return data;}
async function loadAthlete(){if(!athlete.value){results.innerHTML='<p class="muted">Select an athlete to see their results.</p>';return;}const response=await fetch(`/api/sessions/${sessionId}/athletes/${athlete.value}`);const data=await response.json();if(response.ok)render(data);else feedback.textContent=data.error||'Could not load results.';}
function renderUpNext(){const count=Math.min(3,Math.max(0,athletes.length-1));upNextList.innerHTML=Array.from({length:count},(_,offset)=>{const index=(activeIndex+offset+1)%athletes.length;return `<li><span>${index+1}</span><strong>${escapeHtml(athletes[index].name)}</strong></li>`;}).join('')||'<li class="muted">No other athletes queued.</li>';}
async function setAthlete(index,focusTime=true){if(!athletes.length)return;activeIndex=(index+athletes.length)%athletes.length;const selected=athletes[activeIndex];athlete.value=selected.id;athleteName.textContent=selected.name;athletePosition.textContent=`Athlete ${activeIndex+1} of ${athletes.length}`;athleteSearch.value='';localStorage.setItem(`aip-session-${sessionId}-athlete`,selected.id);renderUpNext();await loadAthlete();if(focusTime&&!completed)elapsed.focus();}
async function saveAttempt(){if(completed||saving||!elapsed.value.trim())return;clearTimeout(saveTimer);saving=true;pendingRequestId=pendingRequestId||(crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random()}`);feedback.textContent='Saving…';try{const data=await request(`/api/sessions/${sessionId}/attempts`,{athlete_id:athlete.value,elapsed_seconds:elapsed.value,request_id:pendingRequestId});render(data);elapsed.value='';pendingRequestId=null;feedback.textContent='Saved.';}catch(error){feedback.textContent=`Not confirmed — ${error.message} Retry with the time still entered.`;}finally{saving=false;if(!completed)elapsed.focus();}}
previousAthlete.addEventListener('click',()=>setAthlete(activeIndex-1));
nextAthlete.addEventListener('click',()=>setAthlete(activeIndex+1));
athleteSearch.addEventListener('change',()=>{const typed=athleteSearch.value.trim().toLowerCase();const index=athletes.findIndex((item,i)=>`${i+1} · ${item.name}`.toLowerCase()===typed||item.name.toLowerCase()===typed);if(index>=0)setAthlete(index);else feedback.textContent='Choose an athlete from the roster.';});
elapsed.addEventListener('input',()=>{clearTimeout(saveTimer);feedback.textContent='';if(/^\d+\.\d{1,3}$/.test(elapsed.value.trim()))saveTimer=setTimeout(saveAttempt,900);});
form.addEventListener('submit',async event=>{event.preventDefault();await saveAttempt();});
window.editAttempt=async(id,current)=>{const value=prompt('Correct time in seconds:',current);if(value===null)return;try{render(await request(`/api/attempts/${id}/edit`,{elapsed_seconds:value}));feedback.textContent='Attempt updated.';}catch(error){feedback.textContent=error.message;}elapsed.focus();};
window.deleteAttempt=async id=>{if(!confirm('Delete this attempt?'))return;try{render(await request(`/api/attempts/${id}/delete`));feedback.textContent='Attempt deleted.';}catch(error){feedback.textContent=error.message;}elapsed.focus();};
document.addEventListener('keydown',event=>{if(!event.altKey)return;if(event.key==='ArrowRight'){event.preventDefault();setAthlete(activeIndex+1);}else if(event.key==='ArrowLeft'){event.preventDefault();setAthlete(activeIndex-1);}else if(event.key.toLowerCase()==='a'){event.preventDefault();athleteSearch.focus();}});
const retained=Number(localStorage.getItem(`aip-session-${sessionId}-athlete`));const retainedIndex=athletes.findIndex(item=>item.id===retained);if(athletes.length)setAthlete(retainedIndex>=0?retainedIndex:0,finePointer);
"""


DESKTOP_FOCUS_SCRIPT = r"""
if(window.matchMedia('(hover: hover) and (pointer: fine)').matches){
  const target=document.querySelector('[data-desktop-autofocus]');
  if(target)target.focus();
}
"""


STYLES = """
:root{font-family:Inter,ui-sans-serif,system-ui,sans-serif;color:#17211b;background:#f3f5ef;line-height:1.5}*{box-sizing:border-box}body{margin:0;padding:32px;max-width:1100px;margin-inline:auto}header{margin:20px 0 32px}h1,h2,p{margin-top:0}h1{font-size:clamp(2rem,6vw,4.4rem);line-height:1;letter-spacing:-.05em;max-width:780px}h2{letter-spacing:-.025em}.eyebrow{text-transform:uppercase;letter-spacing:.13em;font-weight:800;font-size:.75rem;color:#647267}.home-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.card,.capture-card,.results-card{background:#fff;border:1px solid #dce2d8;border-radius:18px;padding:24px;box-shadow:0 10px 30px #17211b0a}.sessions{grid-column:1/-1}label{display:grid;gap:7px;font-weight:700}input,select,button{font:inherit;border-radius:10px;border:1px solid #b9c3b8;padding:12px}input:focus,select:focus,button:focus{outline:3px solid #ffc857;outline-offset:2px}button{background:#173c2c;color:#fff;border-color:#173c2c;font-weight:800;cursor:pointer}button:disabled{opacity:.5}.inline-form,.session-form,.time-row{display:flex;align-items:end;gap:10px}.inline-form label,.session-form label{flex:1}ul{padding-left:20px}.session-link{display:flex;justify-content:space-between;color:inherit;text-decoration:none;border-top:1px solid #e6eae3;padding:14px 0}.session-link span,.muted,.shortcut{color:#6d776e}.capture-header h1{margin-bottom:8px}.capture-layout{display:grid;grid-template-columns:minmax(300px,.8fr) minmax(360px,1.2fr);gap:18px}.capture-card form{display:grid;gap:22px}.time-row input{font-size:2rem;width:100%;font-variant-numeric:tabular-nums}.time-row button{min-width:100px}.shortcut{font-size:.85rem;margin-top:30px}kbd{border:1px solid #c7cec5;border-bottom-width:2px;border-radius:5px;background:#f5f6f3;padding:2px 6px}.result-heading,.attempt{display:flex;justify-content:space-between;align-items:center;gap:12px}.best{text-align:right}.best span{display:block;color:#6d776e;font-size:.8rem}.best strong{font-size:1.8rem}.attempts{list-style:none;padding:0;margin:22px 0 0}.attempt{border-top:1px solid #e6eae3;padding:14px 0}.attempt strong{font-size:1.25rem;font-variant-numeric:tabular-nums}.badge{font-size:.7rem;text-transform:uppercase;font-weight:900;letter-spacing:.08em;padding:4px 7px;border-radius:999px;margin-left:6px}.baseline{background:#e7e9f8;color:#333b7a}.pr{background:#d7f4df;color:#155d2d}.actions{display:flex;gap:7px}.actions button{padding:7px 10px;background:#fff;color:#173c2c}.actions .danger{color:#8c2c24;border-color:#d7aaa6}.saved{animation:flash 1.2s}@keyframes flash{from{background:#d7f4df}to{background:transparent}}#feedback{min-height:24px;color:#155d2d;font-weight:800;margin:12px 0 0}.notice{background:#fff3cf;padding:12px;border-radius:10px}@media(max-width:720px){body{padding:18px}.home-grid,.capture-layout{grid-template-columns:1fr}.sessions{grid-column:auto}.inline-form,.session-form{align-items:stretch;flex-direction:column}.session-link{align-items:flex-start;flex-direction:column}}
.groups,.legacy{grid-column:1/-1}.legacy summary{font-weight:800;cursor:pointer}.roster{list-style:none;padding:0}.roster li{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #e6eae3}.position{display:inline-grid;place-items:center;width:28px;height:28px;border-radius:50%;background:#e8eee7;font-weight:800}.group-label{font-weight:800;color:#47725d}.capture-header{margin-bottom:12px}.capture-context{font-weight:800;margin:10px 0 0}.capture-layout{display:block;max-width:760px}.capture-card form{gap:14px}.athlete-flow{display:grid;grid-template-columns:52px 1fr 52px;gap:10px;align-items:stretch}.flow-button{font-size:1.5rem;padding:8px}.active-athlete{display:flex;min-height:72px;flex-direction:column;align-items:center;justify-content:center;border:1px solid #b9c3b8;border-radius:12px;background:#f7f8f5}.active-athlete span{font-size:.75rem;text-transform:uppercase;letter-spacing:.08em;color:#6d776e}.active-athlete strong{font-size:1.35rem;text-align:center}.jump-label{font-size:.85rem}.reference-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:18px}.reference-grid>div{background:#f3f5ef;border-radius:12px;padding:12px}.reference-grid p{font-size:.75rem;font-weight:800;text-transform:uppercase;letter-spacing:.06em;color:#647267;margin-bottom:2px}.reference-grid strong,.reference-grid span{display:block}.reference-grid strong{font-size:1.4rem}.reference-grid span{font-size:.75rem;color:#6d776e}.current-results{margin-top:18px}.current-results .result-heading{border-bottom:1px solid #e6eae3}.secondary-controls{border-top:1px solid #e6eae3;margin-top:16px;padding-top:14px}.secondary-controls summary{font-weight:800;cursor:pointer}.secondary-controls label{margin-top:12px}.session-management{max-width:760px;margin-top:18px}.session-management .session-actions{align-items:stretch}.session-management .session-actions>a,.session-management .session-actions form,.session-management .session-actions button{flex:1;text-align:center}@media(max-width:720px){.groups,.legacy{grid-column:auto}.capture-header{margin-top:8px}.capture-card{padding:14px}.time-row input{font-size:2.35rem;padding:10px}.up-next{padding:9px 12px}.up-next ol{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}.up-next li{display:block;padding:2px 0;font-size:.78rem;overflow-wrap:anywhere}.up-next li span{display:grid;margin-bottom:3px}.attempts{display:flex;gap:8px;margin-top:6px;overflow-x:auto;padding-bottom:4px}.attempt{align-items:flex-start;flex:0 0 auto;min-width:112px;padding:8px}.attempt .actions{margin-top:6px}.shortcut{display:none}.session-management{padding:16px}}
.prototype-nav{display:flex;justify-content:flex-end}.button-link{display:inline-block;background:#173c2c;color:#fff;text-decoration:none;border-radius:10px;padding:10px 14px;font-weight:800}.feedback-layout{max-width:760px}.feedback-form{display:grid;gap:20px}.feedback-form textarea{font:inherit;resize:vertical;border-radius:10px;border:1px solid #b9c3b8;padding:12px}.feedback-form textarea:focus{outline:3px solid #ffc857;outline-offset:2px}.feedback-context{display:grid;grid-template-columns:1fr 1fr;gap:12px}.feedback-list{display:grid;gap:14px}.feedback-entry h3{margin-bottom:4px;font-size:1rem}.feedback-entry p{white-space:pre-wrap}@media(max-width:720px){.feedback-context{grid-template-columns:1fr}}
.export-form{display:flex;align-items:end;gap:10px;margin-top:14px}.export-form label{flex:1}@media(max-width:720px){.export-form{align-items:stretch;flex-direction:column}}
.completed-sessions{margin-top:20px;border-top:1px solid #e6eae3;padding-top:16px}.completed-sessions summary,.add-session-athlete summary{font-weight:800;cursor:pointer}.session-entry{display:grid;grid-template-columns:1fr auto;align-items:center;border-top:1px solid #e6eae3}.session-entry .session-link{border:0}.session-entry form{margin:0}.text-danger{background:transparent;color:#8c2c24;border-color:#d7aaa6;padding:7px 10px}.header-actions,.session-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.session-actions form{margin:0}.danger-button{background:#fff;color:#8c2c24;border-color:#d7aaa6}.up-next{background:#eef3ec;border-radius:12px;padding:12px 16px}.up-next p{margin-bottom:5px}.up-next ol{list-style:none;margin:0;padding:0}.up-next li{display:flex;gap:10px;align-items:center;padding:5px 0}.up-next li span{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:50%;background:#fff;font-size:.75rem}.autosave-note{font-size:.85rem;color:#6d776e;margin:-8px 0 0}.add-session-athlete{border-top:1px solid #e6eae3;margin-top:18px;padding-top:16px}.add-session-athlete form{margin-top:12px}.add-session-athlete p{margin:8px 0 0;font-size:.85rem}@media(max-width:720px){.session-entry{grid-template-columns:1fr}.session-entry form{padding-bottom:12px}.header-actions{align-items:stretch;flex-direction:column}.header-actions>a,.header-actions form,.header-actions button{width:100%;text-align:center}.session-management .session-actions{flex-direction:column}.session-management .session-actions>a,.session-management .session-actions form,.session-management .session-actions button{width:100%}}
a,button,summary{touch-action:manipulation}a:active,button:active,summary:active{opacity:.72}
.roster-member{display:block!important;padding:14px 0!important}.roster-person{display:flex;align-items:center;gap:10px}.roster-actions{display:flex;align-items:end;gap:8px;flex-wrap:wrap;margin:10px 0 0 38px}.roster-actions form{display:flex;align-items:end;gap:6px;margin:0}.roster-actions button{padding:8px 10px}.roster-transfer label{font-size:.8rem}.roster-transfer select{padding:8px}@media(max-width:720px){.roster-actions{align-items:stretch;flex-direction:column;margin-left:0}.roster-actions form,.roster-transfer{display:flex;flex-wrap:wrap}.roster-transfer label{flex:1 1 100%}.roster-transfer select{width:100%}.roster-actions button{min-height:44px}}
.athlete-picker{margin:18px 0}.athlete-picker>label{max-width:520px}.athlete-picker>p{font-size:.85rem;margin:6px 0}.athlete-search-results{display:grid;gap:7px;margin-top:10px}.athlete-search-result{display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid #dce2d8;border-radius:10px;padding:9px;background:#f7f8f5}.athlete-search-result span,.athlete-search-result small{display:block}.athlete-search-result small{color:#6d776e}.athlete-search-result button{padding:8px 14px}.create-athlete{border-top:1px solid #e6eae3;border-bottom:1px solid #e6eae3;padding:14px 0;margin-bottom:12px}.create-athlete summary{font-weight:800;cursor:pointer}.create-athlete form{margin-top:12px}.create-athlete p{font-size:.85rem;margin:7px 0 0}@media(max-width:720px){.athlete-search-result button{min-height:44px}.create-athlete .inline-form{align-items:stretch}}
"""
