"""Validated wide-CSV preview and atomic historical sprint import."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import date, datetime, timedelta

from .database import Database, normalized_name
from .domain import normalize_distance, seconds_to_milliseconds


NAME_HEADERS = {
    "first": {"first", "first name", "firstname", "given name"},
    "last": {"last", "last name", "lastname", "surname", "family name"},
}
SKIPPED_LABELS = {"fastest", "initial 10", "qtr rev"}
MAX_HEADER_SCAN = 20


def identity_name(first: str, last: str) -> str:
    """Return the V1 exact-match identity key without rewriting stored names."""
    return " ".join(part for part in (" ".join(first.split()), " ".join(last.split())) if part).casefold()


def display_name(first: str, last: str) -> str:
    return " ".join(part for part in (" ".join(first.split()), " ".join(last.split())) if part)


def _date_header(value: str, supplied_year: int | None) -> tuple[str | None, str | None]:
    value = value.strip()
    if not value:
        return None, None
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat(), None
        except ValueError:
            pass
    numeric = re.fullmatch(r"(\d{1,2})/(\d{1,2})", value)
    if numeric:
        month, day = map(int, numeric.groups())
        if supplied_year is None:
            return None, "year_required"
        try:
            return date(supplied_year, month, day).isoformat(), None
        except ValueError:
            return None, "invalid_date"
    for pattern in ("%b %d %Y", "%B %d %Y"):
        try:
            parsed = datetime.strptime(f"{value} 2000", pattern)
        except ValueError:
            continue
        if supplied_year is None:
            return None, "year_required"
        try:
            return date(supplied_year, parsed.month, parsed.day).isoformat(), None
        except ValueError:
            return None, "invalid_date"
    if re.fullmatch(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}", value):
        return None, "invalid_date"
    return None, None


def _csv_rows(payload: bytes) -> list[list[str]]:
    if len(payload) > 5_000_000:
        raise ValueError("CSV files must be 5 MB or smaller.")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Upload a UTF-8 CSV file.") from None
    try:
        return list(csv.reader(io.StringIO(text)))
    except csv.Error as error:
        raise ValueError(f"The CSV could not be parsed: {error}.") from None


def _header(rows: list[list[str]]) -> tuple[int, int, int]:
    for row_index, row in enumerate(rows[:MAX_HEADER_SCAN]):
        lowered = [" ".join(cell.split()).casefold() for cell in row]
        first = [index for index, value in enumerate(lowered) if value in NAME_HEADERS["first"]]
        last = [index for index, value in enumerate(lowered) if value in NAME_HEADERS["last"]]
        if first and last:
            return row_index, first[0], last[0]
    raise ValueError("Could not detect a header row with First Name and Last Name columns.")


def build_preview(
    database: Database,
    payload: bytes,
    filename: str,
    group_id: int,
    distance: str,
    unit: str,
    year: int | None = None,
) -> dict:
    """Parse and validate an import without writing persisted sprint data."""
    group = database.group(group_id)
    if not group:
        raise LookupError("Training Group not found.")
    distance = normalize_distance(distance)
    if unit not in {"yards", "meters"}:
        raise ValueError("Unit must be yards or meters.")
    if year is not None and not 1900 <= year <= 2100:
        raise ValueError("Year must be between 1900 and 2100.")
    rows = _csv_rows(payload)
    if not rows:
        raise ValueError("The CSV is empty.")
    header_row, first_column, last_column = _header(rows)
    headers = rows[header_row]
    date_columns, skipped_columns, issues = [], [], []
    seen_dates: dict[str, int] = {}
    for column, label in enumerate(headers):
        if column in {first_column, last_column}:
            continue
        source_date, problem = _date_header(label, year)
        if source_date:
            if source_date in seen_dates:
                issues.append({"kind": "duplicate_date", "column": column + 1, "label": label,
                               "message": f"Date {source_date} appears in more than one column."})
            else:
                seen_dates[source_date] = column
                date_columns.append({"column": column + 1, "index": column, "label": label, "date": source_date})
        elif problem:
            message = (f"Column {column + 1} ({label or 'blank'}) requires an explicit year."
                       if problem == "year_required"
                       else f"Column {column + 1} ({label or 'blank'}) is not a valid date.")
            issues.append({"kind": problem, "column": column + 1, "label": label,
                           "message": message})
        else:
            skipped_columns.append({"column": column + 1, "label": label,
                                    "reason": "summary/non-date" if label.strip().casefold() in SKIPPED_LABELS else "not a confirmed date"})
    if not date_columns:
        raise ValueError("No usable testing-date columns were detected.")

    roster = database.group_roster(group_id)
    matches: dict[str, list[dict]] = {}
    for athlete in roster:
        matches.setdefault(identity_name(athlete["name"], ""), []).append(athlete)
    athletes, results = [], []
    for row_index, row in enumerate(rows[header_row + 1:], header_row + 2):
        first = row[first_column] if first_column < len(row) else ""
        last = row[last_column] if last_column < len(row) else ""
        name = display_name(first, last)
        populated = any(column["index"] < len(row) and row[column["index"]].strip() for column in date_columns)
        if not name:
            if populated:
                issues.append({"kind": "missing_name", "row": row_index,
                               "message": f"Row {row_index} has results but no usable athlete name."})
            continue
        exact = matches.get(identity_name(first, last), [])
        match_status = "matched" if len(exact) == 1 else ("ambiguous" if len(exact) > 1 else "unmatched")
        athlete_entry = {"source_row": row_index, "name": name, "status": match_status,
                         "matches": [{"id": item["id"], "name": item["name"]} for item in exact],
                         "athlete_id": exact[0]["id"] if len(exact) == 1 else None}
        athletes.append(athlete_entry)
        for column in date_columns:
            raw = row[column["index"]].strip() if column["index"] < len(row) else ""
            if not raw:
                continue
            try:
                elapsed_ms = seconds_to_milliseconds(raw)
            except ValueError as error:
                issues.append({"kind": "invalid_time", "row": row_index, "column": column["column"],
                               "value": raw, "message": str(error)})
                continue
            results.append({"source_row": row_index, "source_column": column["column"], "athlete_name": name,
                            "source_date": column["date"], "raw": raw, "elapsed_ms": elapsed_ms})

    conflicts = []
    with database.connect() as connection:
        for source_date in sorted({item["source_date"] for item in results}):
            existing = connection.execute(
                """SELECT s.id, COUNT(a.id) AS attempt_count
                   FROM training_group_sessions gs JOIN sprint_capture_sessions s ON s.id=gs.session_id
                   LEFT JOIN sprint_attempts a ON a.session_id=s.id
                   WHERE gs.group_id=? AND s.distance=? AND s.unit=? AND date(s.created_at)=?
                   GROUP BY s.id ORDER BY s.id""",
                (group_id, distance, unit, source_date),
            ).fetchall()
            non_imported = []
            for item in existing:
                imported_count = connection.execute(
                    """SELECT COUNT(*) FROM imported_results provenance
                       JOIN sprint_attempts attempt ON attempt.id=provenance.attempt_id
                       WHERE attempt.session_id=?""",
                    (item["id"],),
                ).fetchone()[0]
                if item["attempt_count"] == 0 or imported_count != item["attempt_count"]:
                    non_imported.append(dict(item))
            if non_imported:
                conflicts.append({"date": source_date, "sessions": non_imported})
        identical = connection.execute(
            "SELECT id FROM import_batches WHERE file_digest=? AND group_id=? AND distance=? AND unit=?",
            (hashlib.sha256(payload).hexdigest(), group_id, distance, unit),
        ).fetchone()
        athlete_by_row = {item["source_row"]: item for item in athletes}
        for result in results:
            athlete = athlete_by_row[result["source_row"]]
            if athlete["athlete_id"] is None:
                result["possible_duplicate"] = False
                continue
            fingerprint = _fingerprint(group_id, athlete["athlete_id"], result, distance, unit)
            result["possible_duplicate"] = bool(connection.execute(
                "SELECT 1 FROM imported_results WHERE fingerprint=?", (fingerprint,)
            ).fetchone())

    return {
        "payload": payload, "filename": filename, "digest": hashlib.sha256(payload).hexdigest(),
        "group_id": group_id, "group_name": group["name"], "distance": distance, "unit": unit, "year": year,
        "header_row": header_row + 1, "first_column": first_column + 1, "last_column": last_column + 1,
        "date_columns": date_columns, "skipped_columns": skipped_columns, "athletes": athletes,
        "results": results, "issues": issues, "conflicts": conflicts, "identical_batch_id": identical["id"] if identical else None,
        "ordering_note": "Date-only results use noon local time; source row order breaks same-day ties.",
    }


def _fingerprint(group_id: int, athlete_id: int, result: dict, distance: str, unit: str) -> str:
    stable = [group_id, athlete_id, result["source_date"], distance, unit,
              result["source_row"], result["source_column"], result["elapsed_ms"]]
    return hashlib.sha256(json.dumps(stable, separators=(",", ":")).encode()).hexdigest()


def _review_state(preview: dict) -> str:
    state = {
        "athletes": [
            [item["source_row"], item["status"], item["athlete_id"], [match["id"] for match in item["matches"]]]
            for item in preview["athletes"]
        ],
        "conflicts": preview["conflicts"],
        "issues": preview["issues"],
        "duplicates": [
            [item["source_row"], item["source_column"], item.get("possible_duplicate", False)]
            for item in preview["results"]
        ],
        "identical_batch_id": preview["identical_batch_id"],
    }
    return json.dumps(state, sort_keys=True, separators=(",", ":"))


def confirm_import(database: Database, preview: dict, resolutions: dict[int, str],
                   conflict_resolutions: dict[str, str], *, acknowledge_issues: bool = False,
                   fail_after_attempts: int | None = None) -> dict:
    """Revalidate and persist one reviewed preview in a single transaction."""
    current = build_preview(database, preview["payload"], preview["filename"], preview["group_id"],
                            preview["distance"], preview["unit"], preview["year"])
    if current["identical_batch_id"]:
        raise ValueError(f"This identical file was already imported as batch {current['identical_batch_id']}.")
    if _review_state(current) != _review_state(preview):
        raise ValueError("The roster or sprint data changed after preview. Review a fresh preview before confirming.")
    if current["issues"] and not acknowledge_issues:
        raise ValueError("Acknowledge the excluded invalid cells and columns before confirmation.")
    if any(issue["kind"] == "duplicate_date" for issue in current["issues"]):
        raise ValueError("Duplicate date columns must be removed from the CSV before confirmation.")

    athlete_rows = {item["source_row"]: item for item in current["athletes"]}
    resolved: dict[int, tuple[str, int | None]] = {}
    for source_row, athlete in athlete_rows.items():
        choice = resolutions.get(source_row) or (f"existing:{athlete['athlete_id']}" if athlete["status"] == "matched" else "")
        if choice == "exclude" or choice == "create":
            resolved[source_row] = (choice, None)
        elif choice.startswith("existing:"):
            resolved[source_row] = ("existing", int(choice.split(":", 1)[1]))
        else:
            raise ValueError(f"Resolve athlete row {source_row} before confirmation.")
    for conflict in current["conflicts"]:
        if conflict["date"] not in conflict_resolutions:
            raise ValueError(f"Resolve the existing-session conflict for {conflict['date']}.")

    created_athletes, sessions_created, sessions_reused, attempts_created, duplicates = [], [], [], 0, 0
    excluded_rows = sum(1 for choice, _ in resolved.values() if choice == "exclude")
    with database.connect() as connection:
        if connection.execute("SELECT 1 FROM import_batches WHERE file_digest=? AND group_id=? AND distance=? AND unit=?",
                              (current["digest"], current["group_id"], current["distance"], current["unit"])).fetchone():
            raise ValueError("This identical file has already been imported.")
        for source_row, (choice, athlete_id) in list(resolved.items()):
            athlete = athlete_rows[source_row]
            if choice == "create":
                name = normalized_name(athlete["name"], "Athlete")
                athlete_id = connection.execute("INSERT INTO athletes(name) VALUES (?)", (name,)).lastrowid
                position = connection.execute("SELECT COALESCE(MAX(position),0)+1 FROM training_group_members WHERE group_id=?",
                                              (current["group_id"],)).fetchone()[0]
                connection.execute("INSERT INTO training_group_members(group_id,athlete_id,position) VALUES (?,?,?)",
                                   (current["group_id"], athlete_id, position))
                created_athletes.append(athlete_id)
            elif choice == "existing":
                if not connection.execute("SELECT 1 FROM athletes WHERE id=?", (athlete_id,)).fetchone():
                    raise ValueError(f"Athlete resolution for row {source_row} no longer exists.")
                if not connection.execute("SELECT 1 FROM training_group_members WHERE group_id=? AND athlete_id=?",
                                          (current["group_id"], athlete_id)).fetchone():
                    position = connection.execute("SELECT COALESCE(MAX(position),0)+1 FROM training_group_members WHERE group_id=?",
                                                  (current["group_id"],)).fetchone()[0]
                    connection.execute("INSERT INTO training_group_members(group_id,athlete_id,position) VALUES (?,?,?)",
                                       (current["group_id"], athlete_id, position))
            resolved[source_row] = (choice, athlete_id)

        active_results = [item for item in current["results"] if resolved[item["source_row"]][0] != "exclude"]
        duplicate_flags = {}
        for result in active_results:
            athlete_id = resolved[result["source_row"]][1]
            fingerprint = _fingerprint(current["group_id"], athlete_id, result, current["distance"], current["unit"])
            duplicate_flags[(result["source_row"], result["source_column"])] = fingerprint
        novel_results = [item for item in active_results if not connection.execute(
            "SELECT 1 FROM imported_results WHERE fingerprint=?",
            (duplicate_flags[(item["source_row"], item["source_column"])],),
        ).fetchone()]
        duplicates = len(active_results) - len(novel_results)

        summary = {"created_athletes": len(created_athletes), "sessions_created": 0, "sessions_reused": 0,
                   "attempts_created": len(novel_results), "duplicates_skipped": duplicates,
                   "excluded_rows": excluded_rows, "excluded_issues": len(current["issues"])}
        batch_id = connection.execute(
            """INSERT INTO import_batches(file_digest,group_id,distance,unit,original_filename,summary,warnings)
               VALUES (?,?,?,?,?,?,?)""",
            (current["digest"], current["group_id"], current["distance"], current["unit"],
             current["filename"], json.dumps(summary, sort_keys=True), json.dumps(current["issues"], sort_keys=True)),
        ).lastrowid
        session_by_date = {}
        for source_date in sorted({item["source_date"] for item in novel_results}):
            resolution = conflict_resolutions.get(source_date, "separate")
            if resolution.startswith("reuse:"):
                session_id = int(resolution.split(":", 1)[1])
                valid = connection.execute(
                    """SELECT 1 FROM training_group_sessions gs JOIN sprint_capture_sessions s ON s.id=gs.session_id
                       WHERE gs.group_id=? AND s.id=? AND s.distance=? AND s.unit=? AND date(s.created_at)=?""",
                    (current["group_id"], session_id, current["distance"], current["unit"], source_date),
                ).fetchone()
                if not valid:
                    raise ValueError(f"The selected session for {source_date} is no longer valid.")
                missing = [
                    resolved[item["source_row"]][1] for item in novel_results
                    if item["source_date"] == source_date and not connection.execute(
                        "SELECT 1 FROM session_roster_members WHERE session_id=? AND athlete_id=?",
                        (session_id, resolved[item["source_row"]][1]),
                    ).fetchone()
                ]
                if missing:
                    raise ValueError(
                        f"Session {session_id} cannot be reused because its immutable roster lacks a resolved athlete. "
                        "Create a separate historical session instead."
                    )
                sessions_reused.append(session_id)
            elif resolution == "separate":
                session_id = connection.execute(
                    """INSERT INTO sprint_capture_sessions(distance,unit,session_date,created_at)
                       VALUES (?,?,?,?)""",
                    (current["distance"], current["unit"], source_date, f"{source_date} 12:00:00"),
                ).lastrowid
                connection.execute("INSERT INTO training_group_sessions(group_id,session_id) VALUES (?,?)",
                                   (current["group_id"], session_id))
                connection.execute("INSERT INTO session_roster_snapshots(session_id,created_at) VALUES (?,?)",
                                   (session_id, f"{source_date} 12:00:00"))
                ordered_ids = []
                for result in novel_results:
                    if result["source_date"] == source_date:
                        athlete_id = resolved[result["source_row"]][1]
                        if athlete_id not in ordered_ids:
                            ordered_ids.append(athlete_id)
                for position, athlete_id in enumerate(ordered_ids, 1):
                    connection.execute("INSERT INTO session_roster_members(session_id,athlete_id,position) VALUES (?,?,?)",
                                       (session_id, athlete_id, position))
                sessions_created.append(session_id)
            else:
                raise ValueError(f"Choose separate or reuse for {source_date}.")
            session_by_date[source_date] = session_id

        for sequence, result in enumerate(novel_results):
            athlete_id = resolved[result["source_row"]][1]
            captured_at = datetime.fromisoformat(f"{result['source_date']}T12:00:00") + timedelta(microseconds=result["source_row"])
            attempt_id = connection.execute(
                "INSERT INTO sprint_attempts(session_id,athlete_id,elapsed_ms,captured_at,updated_at) VALUES (?,?,?,?,?)",
                (session_by_date[result["source_date"]], athlete_id, result["elapsed_ms"],
                 captured_at.isoformat(sep=" "), captured_at.isoformat(sep=" ")),
            ).lastrowid
            connection.execute(
                """INSERT INTO imported_results(
                       batch_id,attempt_id,source_row,source_column,source_date,source_elapsed_ms,fingerprint
                   ) VALUES (?,?,?,?,?,?,?)""",
                (batch_id, attempt_id, result["source_row"], result["source_column"], result["source_date"],
                 result["elapsed_ms"], duplicate_flags[(result["source_row"], result["source_column"])]),
            )
            attempts_created += 1
            if fail_after_attempts is not None and attempts_created >= fail_after_attempts:
                raise RuntimeError("Injected import failure.")
        summary.update({"sessions_created": len(sessions_created), "sessions_reused": len(sessions_reused)})
        connection.execute("UPDATE import_batches SET summary=? WHERE id=?", (json.dumps(summary, sort_keys=True), batch_id))
    return {"batch_id": batch_id, **summary, "session_ids_created": sessions_created,
            "session_ids_reused": sessions_reused, "created_athlete_ids": created_athletes}
