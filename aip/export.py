"""CSV export for persisted sprint attempts."""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from datetime import date, datetime, timezone

from .domain import classify_attempts, format_seconds


CSV_HEADERS = [
    "Athlete ID",
    "Athlete name",
    "Training Group",
    "Session ID",
    "Session label",
    "Protocol",
    "Legacy protocol alias",
    "Total distance",
    "Timed distance",
    "Run-in distance",
    "Timed segment",
    "Start type",
    "Purpose",
    "Planned attempts",
    "Surface type",
    "Timing method",
    "Environment",
    "Protocol notes",
    "Session date/time",
    "Distance",
    "Unit",
    "Attempt number",
    "Attempt time in seconds",
    "Attempt time in milliseconds",
    "Session best",
    "Performance status",
    "Capture timestamp",
]


def parse_export_dates(start: str | None, end: str | None) -> tuple[str | None, str | None]:
    parsed = []
    for value, label in ((start, "start"), (end, "end")):
        value = (value or "").strip()
        if not value:
            parsed.append(None)
            continue
        try:
            parsed.append(date.fromisoformat(value).isoformat())
        except ValueError:
            raise ValueError(f"Enter a valid {label} date in YYYY-MM-DD format.") from None
    start_date, end_date = parsed
    if start_date and end_date and start_date > end_date:
        raise ValueError("Start date must be on or before end date.")
    return start_date, end_date


def sprint_export_csv(database, *, session_id: int | None = None, group_id: int | None = None,
                      start: str | None = None, end: str | None = None) -> bytes:
    """Return an Excel-compatible UTF-8 CSV for one validated export scope."""
    rows = database.export_attempts(session_id=session_id, group_id=group_id, start=start, end=end)
    all_attempts = database.all_attempts()
    statuses = {attempt["id"]: attempt["status"] for attempt in classify_attempts(all_attempts)}
    session_bests: dict[tuple[int, int], int] = {}
    attempt_numbers: dict[int, int] = {}
    attempts_by_runner: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for attempt in all_attempts:
        attempts_by_runner[(attempt["session_id"], attempt["athlete_id"])].append(attempt)
    for key, attempts in attempts_by_runner.items():
        ordered = sorted(attempts, key=lambda item: (item["captured_at"], item["id"]))
        session_bests[key] = min(item["elapsed_ms"] for item in ordered)
        attempt_numbers.update({item["id"]: number for number, item in enumerate(ordered, 1)})

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(CSV_HEADERS)
    for row in rows:
        status = {"attempt": "standard", "pr": "PR"}.get(statuses[row["id"]], statuses[row["id"]])
        best = session_bests[(row["session_id"], row["athlete_id"])]
        values = [
            row["athlete_id"],
            row["athlete_name"],
            row["group_name"] or "",
            row["session_id"],
            f"{row['distance']} {row['unit']}",
            row["protocol_name"] or "Unspecified protocol",
            row["protocol_alias"] or "",
            f"{row['total_distance']} {row['protocol_unit']}" if row["total_distance"] else "",
            f"{row['timed_distance']} {row['protocol_unit']}" if row["timed_distance"] else "",
            f"{row['run_in_distance']} {row['protocol_unit']}" if row["run_in_distance"] else "",
            row["timed_segment"] or "",
            row["start_type"] or "",
            row["purpose"] or "",
            row["target_attempts"] or "",
            row["surface_type"] or "",
            row["timing_method"] or "",
            row["environment"] or "",
            row["protocol_notes"] or "",
            row["session_created_at"],
            row["distance"],
            row["unit"],
            attempt_numbers[row["id"]],
            format_seconds(row["elapsed_ms"]),
            row["elapsed_ms"],
            format_seconds(best),
            status,
            row["captured_at"],
        ]
        writer.writerow([spreadsheet_safe(value) for value in values])
    return output.getvalue().encode("utf-8-sig")


def export_filename(scope: str, identifier: int, group_name: str | None = None, today: date | None = None) -> str:
    export_date = today or datetime.now(timezone.utc).date()
    if scope == "session":
        return f"aip-session-{identifier}-{export_date.isoformat()}.csv"
    if scope == "group" and group_name:
        safe_name = re.sub(r"[^a-z0-9]+", "-", group_name.casefold()).strip("-") or f"group-{identifier}"
        return f"aip-group-{safe_name}-{export_date.isoformat()}.csv"
    raise ValueError("Choose a valid export filename scope.")


def spreadsheet_safe(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
