"""Small server-rendered WSGI application for live sprint capture."""

from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import parse_qs

from .database import Database
from .domain import classify_attempts, format_seconds, normalize_distance, seconds_to_milliseconds
from .export import export_filename, parse_export_dates, sprint_export_csv


def create_app(database_path: str | Path = "data/aip.sqlite3"):
    database = Database(database_path)
    database.initialize()

    def app(environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/").rstrip("/") or "/"
        parts = [part for part in path.split("/") if part]
        try:
            if method == "GET" and path == "/":
                return respond(start_response, home_page(database))
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
                session_id = database.add_session(normalize_distance(data.get("distance", "")), data.get("unit", ""))
                return redirect(start_response, f"/sessions/{session_id}")
            if method == "POST" and path == "/groups":
                group_id = database.add_group(form_data(environ).get("name", ""))
                return redirect(start_response, f"/groups/{group_id}")
            if method == "GET" and len(parts) == 2 and parts[0] == "groups":
                return respond(start_response, group_page(database, resource_id(parts[1], "Training Group")))
            if method == "POST" and len(parts) == 3 and parts[0] == "groups" and parts[2] == "athletes":
                group_id = resource_id(parts[1], "Training Group")
                database.add_group_athlete(group_id, form_data(environ).get("name", ""))
                return redirect(start_response, f"/groups/{group_id}")
            if method == "POST" and len(parts) == 3 and parts[0] == "groups" and parts[2] == "sessions":
                group_id = resource_id(parts[1], "Training Group")
                data = form_data(environ)
                session_id = database.add_group_session(
                    group_id, normalize_distance(data.get("distance", "")), data.get("unit", "")
                )
                return redirect(start_response, f"/sessions/{session_id}")
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
                attempt_id = database.add_attempt(session_id, athlete_id, seconds_to_milliseconds(data.get("elapsed_seconds", "")))
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

    app.database = database
    return app


def home_page(db: Database) -> str:
    athlete_items = "".join(f"<li>{html.escape(a['name'])}</li>" for a in db.all_athletes()) or "<li class='muted'>No athletes yet</li>"
    session_items = "".join(
        f"<a class='session-link' href='/sessions/{s['id']}'><strong>{html.escape(s['distance'])} {s['unit']}</strong>"
        f"<span>{s['attempt_count']} attempts · {s['created_at']}</span></a>" for s in db.all_sessions()
    ) or "<p class='muted'>No capture sessions yet.</p>"
    group_items = "".join(
        f"<a class='session-link' href='/groups/{g['id']}'><strong>{html.escape(g['name'])}</strong>"
        f"<span>{g['athlete_count']} athletes · {g['session_count']} sessions</span></a>" for g in db.all_groups()
    ) or "<p class='muted'>Create your first recurring Training Group.</p>"
    body = f"""
    <header><p class='eyebrow'>Athlete Intelligence Platform</p><h1>Manual sprint capture</h1><p>Reuse a Training Group roster, then start or resume a measurement session.</p></header>
    <main class='home-grid'>
      <section class='card groups'><h2>Training Groups</h2><form method='post' action='/groups' class='inline-form'><label>Group name<input name='name' maxlength='100' required autofocus placeholder='Park City Football'></label><button>Create group</button></form>{group_items}</section>
      <section class='card sessions'><h2>Resume a session</h2>{session_items}</section>
      <details class='card legacy'><summary>Standalone capture tools</summary><p class='muted'>Existing FEAT-001 workflows remain available for sessions without a Training Group.</p><h3>Athletes</h3><form method='post' action='/athletes' class='inline-form'><label>Name<input name='name' maxlength='100' required placeholder='Athlete name'></label><button>Add athlete</button></form><ul>{athlete_items}</ul><h3>New standalone session</h3><form method='post' action='/sessions' class='session-form'><label>Distance<input name='distance' inputmode='decimal' required value='10'></label><label>Unit<select name='unit'><option value='yards'>yards</option><option value='meters'>meters</option></select></label><button>Start capture</button></form></details>
    </main>"""
    return page("Sprint capture", body)


def group_page(db: Database, group_id: int) -> str:
    group = db.group(group_id)
    if not group:
        raise LookupError("Training Group not found.")
    roster = db.group_roster(group_id)
    roster_items = "".join(
        f"<li><span class='position'>{athlete['position']}</span>{html.escape(athlete['name'])}</li>" for athlete in roster
    ) or "<li class='muted'>No athletes yet.</li>"
    sessions = "".join(
        f"<a class='session-link' href='/sessions/{session['id']}'><strong>{html.escape(session['distance'])} {session['unit']}</strong>"
        f"<span>{session['attempt_count']} attempts · {session['created_at']}</span></a>" for session in db.group_sessions(group_id)
    ) or "<p class='muted'>No sessions yet.</p>"
    disabled = "disabled" if not roster else ""
    body = f"""
    <header><a href='/'>← Training Groups</a><p class='eyebrow'>Recurring Training Group</p><h1>{html.escape(group['name'])}</h1><p>{len(roster)} athletes in persistent training order.</p></header>
    <main class='home-grid'>
      <section class='card'><h2>Persistent roster</h2><form method='post' action='/groups/{group_id}/athletes' class='inline-form'><label>Athlete name<input name='name' maxlength='100' required autofocus placeholder='Athlete name'></label><button>Add athlete</button></form><ol class='roster'>{roster_items}</ol></section>
      <section class='card'><h2>Start a session</h2><form method='post' action='/groups/{group_id}/sessions' class='session-form'><label>Distance<input name='distance' inputmode='decimal' required value='10'></label><label>Unit<select name='unit'><option value='yards'>yards</option><option value='meters'>meters</option></select></label><button {disabled}>Start with this roster</button></form>{'<p class="notice">Add an athlete before starting a session.</p>' if not roster else ''}</section>
      <section class='card sessions'><h2>Session history</h2>{sessions}<h3>Export sprint data</h3><form method='get' action='/groups/{group_id}/export.csv' class='export-form'><label>Start date (optional)<input type='date' name='start'></label><label>End date (optional)<input type='date' name='end'></label><button>Export Group CSV</button></form></section>
    </main>"""
    return page(group["name"], body)


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
    group_label = f"<p class='group-label'>{html.escape(group['name'])}</p>" if group else ""
    back_link = f"/groups/{group['id']}" if group else "/"
    body = f"""
    <header class='capture-header'><a href='{back_link}'>← Sessions</a><p class='eyebrow'>Sprint capture session</p><h1>{html.escape(session['distance'])} {session['unit']}</h1>{group_label}<p>Move through the training order or jump to any athlete.</p><a class='button-link' href='/sessions/{session_id}/export.csv'>Export Session CSV</a></header>
    <main class='capture-layout'>
      <section class='capture-card'>
        {empty}<form id='capture-form' data-session='{session_id}'>
          <div class='athlete-flow'><button type='button' id='previous-athlete' class='flow-button' aria-label='Previous athlete'>←</button><div class='active-athlete'><span id='athlete-position'>Athlete</span><strong id='athlete-name'>Choose athlete</strong></div><button type='button' id='next-athlete' class='flow-button' aria-label='Next athlete'>→</button></div>
          <input type='hidden' id='athlete' required>
          <label class='jump-label'>Jump to athlete<input id='athlete-search' list='athlete-options' autocomplete='off' placeholder='Type a name or number' {'disabled' if not athletes else ''}></label><datalist id='athlete-options'>{options}</datalist>
          <label>Time (seconds)<div class='time-row'><input id='elapsed' inputmode='decimal' autocomplete='off' placeholder='1.72' required {'disabled' if not athletes else ''}><button id='save' {'disabled' if not athletes else ''}>Save</button></div></label>
        </form><p id='feedback' role='status' aria-live='polite'></p>
        <p class='shortcut'><kbd>Alt</kbd> + <kbd>→</kbd> next · <kbd>Alt</kbd> + <kbd>←</kbd> previous · <kbd>Alt</kbd> + <kbd>A</kbd> jump</p>
      </section>
      <section class='results-card'><div id='results'><p class='muted'>Select an athlete to see their results.</p></div></section>
    </main>
    <script>const athletes={athlete_json};{CAPTURE_SCRIPT}</script>"""
    return page(f"{session['distance']} {session['unit']} capture", body)


def athlete_summary(db: Database, session_id: int, athlete_id: int, saved_attempt_id: int | None = None) -> dict:
    if not db.session(session_id):
        raise LookupError("Session not found.")
    athlete = db.athlete(athlete_id)
    if not athlete:
        raise LookupError("Athlete not found.")
    all_attempts = classify_attempts(db.all_attempts())
    session_attempts = [a for a in all_attempts if a["session_id"] == session_id and a["athlete_id"] == athlete_id]
    if not session_attempts:
        return {"athlete_name": athlete["name"], "best": None, "attempts": []}
    attempts = []
    for attempt in reversed(session_attempts):
        attempts.append({
            "id": attempt["id"], "time": format_seconds(attempt["elapsed_ms"]), "status": attempt["status"],
            "just_saved": attempt["id"] == saved_attempt_id,
        })
    return {
        "athlete_name": session_attempts[0]["athlete_name"],
        "best": format_seconds(min(a["elapsed_ms"] for a in session_attempts)),
        "attempts": attempts,
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


def page(title: str, body: str) -> str:
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)} · AIP</title><style>{STYLES}</style></head><body><nav class='prototype-nav'><a class='button-link' href='/feedback/new'>Send Feedback</a></nav>{body}</body></html>"


def form_data(environ) -> dict[str, str]:
    length = int(environ.get("CONTENT_LENGTH") or 0)
    parsed = parse_qs(environ["wsgi.input"].read(length).decode())
    return {key: values[0] for key, values in parsed.items()}


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


def redirect(start_response, location: str):
    start_response("303 See Other", [("Location", location), ("Content-Length", "0")])
    return [b""]


CAPTURE_SCRIPT = r"""
const form=document.querySelector('#capture-form'), athlete=document.querySelector('#athlete'), athleteName=document.querySelector('#athlete-name'), athletePosition=document.querySelector('#athlete-position'), athleteSearch=document.querySelector('#athlete-search'), previousAthlete=document.querySelector('#previous-athlete'), nextAthlete=document.querySelector('#next-athlete'), elapsed=document.querySelector('#elapsed'), feedback=document.querySelector('#feedback'), results=document.querySelector('#results'), save=document.querySelector('#save');
const sessionId=form.dataset.session;
let activeIndex=-1;
const escapeHtml=s=>String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
function render(data){
  if(!data.attempts.length){results.innerHTML=`<h2>${escapeHtml(data.athlete_name)}</h2><p class="muted">No attempts in this session.</p>`;return;}
  const rows=data.attempts.map(a=>`<li class="attempt ${a.just_saved?'saved':''}"><div><strong>${escapeHtml(a.time)}s</strong> ${a.status==='baseline'?'<span class="badge baseline">Baseline</span>':a.status==='pr'?'<span class="badge pr">PR</span>':''}</div><div class="actions"><button type="button" onclick="editAttempt(${a.id}, '${escapeHtml(a.time)}')">Edit</button><button type="button" class="danger" onclick="deleteAttempt(${a.id})">Delete</button></div></li>`).join('');
  results.innerHTML=`<div class="result-heading"><div><p class="eyebrow">Selected athlete</p><h2>${escapeHtml(data.athlete_name)}</h2></div><div class="best"><span>Session best</span><strong>${escapeHtml(data.best)}s</strong></div></div><ol class="attempts">${rows}</ol>`;
}
async function request(url, body={}){const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw new Error(data.error||'Could not save.');return data;}
async function loadAthlete(){if(!athlete.value){results.innerHTML='<p class="muted">Select an athlete to see their results.</p>';return;}const response=await fetch(`/api/sessions/${sessionId}/athletes/${athlete.value}`);const data=await response.json();if(response.ok)render(data);else feedback.textContent=data.error||'Could not load results.';}
async function setAthlete(index){if(!athletes.length)return;activeIndex=(index+athletes.length)%athletes.length;const selected=athletes[activeIndex];athlete.value=selected.id;athleteName.textContent=selected.name;athletePosition.textContent=`Athlete ${activeIndex+1} of ${athletes.length}`;athleteSearch.value='';localStorage.setItem(`aip-session-${sessionId}-athlete`,selected.id);await loadAthlete();elapsed.focus();}
previousAthlete.addEventListener('click',()=>setAthlete(activeIndex-1));
nextAthlete.addEventListener('click',()=>setAthlete(activeIndex+1));
athleteSearch.addEventListener('change',()=>{const typed=athleteSearch.value.trim().toLowerCase();const index=athletes.findIndex((item,i)=>`${i+1} · ${item.name}`.toLowerCase()===typed||item.name.toLowerCase()===typed);if(index>=0)setAthlete(index);else feedback.textContent='Choose an athlete from the roster.';});
form.addEventListener('submit',async event=>{event.preventDefault();feedback.textContent='';save.disabled=true;try{const data=await request(`/api/sessions/${sessionId}/attempts`,{athlete_id:athlete.value,elapsed_seconds:elapsed.value});render(data);elapsed.value='';feedback.textContent='Saved.';}catch(error){feedback.textContent=error.message;}finally{save.disabled=false;elapsed.focus();}});
window.editAttempt=async(id,current)=>{const value=prompt('Correct time in seconds:',current);if(value===null)return;try{render(await request(`/api/attempts/${id}/edit`,{elapsed_seconds:value}));feedback.textContent='Attempt updated.';}catch(error){feedback.textContent=error.message;}elapsed.focus();};
window.deleteAttempt=async id=>{if(!confirm('Delete this attempt?'))return;try{render(await request(`/api/attempts/${id}/delete`));feedback.textContent='Attempt deleted.';}catch(error){feedback.textContent=error.message;}elapsed.focus();};
document.addEventListener('keydown',event=>{if(!event.altKey)return;if(event.key==='ArrowRight'){event.preventDefault();setAthlete(activeIndex+1);}else if(event.key==='ArrowLeft'){event.preventDefault();setAthlete(activeIndex-1);}else if(event.key.toLowerCase()==='a'){event.preventDefault();athleteSearch.focus();}});
const retained=Number(localStorage.getItem(`aip-session-${sessionId}-athlete`));const retainedIndex=athletes.findIndex(item=>item.id===retained);if(athletes.length)setAthlete(retainedIndex>=0?retainedIndex:0);
"""


STYLES = """
:root{font-family:Inter,ui-sans-serif,system-ui,sans-serif;color:#17211b;background:#f3f5ef;line-height:1.5}*{box-sizing:border-box}body{margin:0;padding:32px;max-width:1100px;margin-inline:auto}header{margin:20px 0 32px}h1,h2,p{margin-top:0}h1{font-size:clamp(2rem,6vw,4.4rem);line-height:1;letter-spacing:-.05em;max-width:780px}h2{letter-spacing:-.025em}.eyebrow{text-transform:uppercase;letter-spacing:.13em;font-weight:800;font-size:.75rem;color:#647267}.home-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.card,.capture-card,.results-card{background:#fff;border:1px solid #dce2d8;border-radius:18px;padding:24px;box-shadow:0 10px 30px #17211b0a}.sessions{grid-column:1/-1}label{display:grid;gap:7px;font-weight:700}input,select,button{font:inherit;border-radius:10px;border:1px solid #b9c3b8;padding:12px}input:focus,select:focus,button:focus{outline:3px solid #ffc857;outline-offset:2px}button{background:#173c2c;color:#fff;border-color:#173c2c;font-weight:800;cursor:pointer}button:disabled{opacity:.5}.inline-form,.session-form,.time-row{display:flex;align-items:end;gap:10px}.inline-form label,.session-form label{flex:1}ul{padding-left:20px}.session-link{display:flex;justify-content:space-between;color:inherit;text-decoration:none;border-top:1px solid #e6eae3;padding:14px 0}.session-link span,.muted,.shortcut{color:#6d776e}.capture-header h1{margin-bottom:8px}.capture-layout{display:grid;grid-template-columns:minmax(300px,.8fr) minmax(360px,1.2fr);gap:18px}.capture-card form{display:grid;gap:22px}.time-row input{font-size:2rem;width:100%;font-variant-numeric:tabular-nums}.time-row button{min-width:100px}.shortcut{font-size:.85rem;margin-top:30px}kbd{border:1px solid #c7cec5;border-bottom-width:2px;border-radius:5px;background:#f5f6f3;padding:2px 6px}.result-heading,.attempt{display:flex;justify-content:space-between;align-items:center;gap:12px}.best{text-align:right}.best span{display:block;color:#6d776e;font-size:.8rem}.best strong{font-size:1.8rem}.attempts{list-style:none;padding:0;margin:22px 0 0}.attempt{border-top:1px solid #e6eae3;padding:14px 0}.attempt strong{font-size:1.25rem;font-variant-numeric:tabular-nums}.badge{font-size:.7rem;text-transform:uppercase;font-weight:900;letter-spacing:.08em;padding:4px 7px;border-radius:999px;margin-left:6px}.baseline{background:#e7e9f8;color:#333b7a}.pr{background:#d7f4df;color:#155d2d}.actions{display:flex;gap:7px}.actions button{padding:7px 10px;background:#fff;color:#173c2c}.actions .danger{color:#8c2c24;border-color:#d7aaa6}.saved{animation:flash 1.2s}@keyframes flash{from{background:#d7f4df}to{background:transparent}}#feedback{min-height:24px;color:#155d2d;font-weight:800;margin:12px 0 0}.notice{background:#fff3cf;padding:12px;border-radius:10px}@media(max-width:720px){body{padding:18px}.home-grid,.capture-layout{grid-template-columns:1fr}.sessions{grid-column:auto}.inline-form,.session-form{align-items:stretch;flex-direction:column}.session-link{align-items:flex-start;flex-direction:column}}
.groups,.legacy{grid-column:1/-1}.legacy summary{font-weight:800;cursor:pointer}.roster{list-style:none;padding:0}.roster li{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #e6eae3}.position{display:inline-grid;place-items:center;width:28px;height:28px;border-radius:50%;background:#e8eee7;font-weight:800}.group-label{font-weight:800;color:#47725d}.capture-card form{gap:18px}.athlete-flow{display:grid;grid-template-columns:52px 1fr 52px;gap:10px;align-items:stretch}.flow-button{font-size:1.5rem;padding:8px}.active-athlete{display:flex;min-height:82px;flex-direction:column;align-items:center;justify-content:center;border:1px solid #b9c3b8;border-radius:12px;background:#f7f8f5}.active-athlete span{font-size:.75rem;text-transform:uppercase;letter-spacing:.08em;color:#6d776e}.active-athlete strong{font-size:1.35rem;text-align:center}.jump-label{font-size:.85rem}@media(max-width:720px){.groups,.legacy{grid-column:auto}}
.prototype-nav{display:flex;justify-content:flex-end}.button-link{display:inline-block;background:#173c2c;color:#fff;text-decoration:none;border-radius:10px;padding:10px 14px;font-weight:800}.feedback-layout{max-width:760px}.feedback-form{display:grid;gap:20px}.feedback-form textarea{font:inherit;resize:vertical;border-radius:10px;border:1px solid #b9c3b8;padding:12px}.feedback-form textarea:focus{outline:3px solid #ffc857;outline-offset:2px}.feedback-context{display:grid;grid-template-columns:1fr 1fr;gap:12px}.feedback-list{display:grid;gap:14px}.feedback-entry h3{margin-bottom:4px;font-size:1rem}.feedback-entry p{white-space:pre-wrap}@media(max-width:720px){.feedback-context{grid-template-columns:1fr}}
.export-form{display:flex;align-items:end;gap:10px;margin-top:14px}.export-form label{flex:1}@media(max-width:720px){.export-form{align-items:stretch;flex-direction:column}}
"""
