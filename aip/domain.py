"""Measurement parsing and derived sprint results."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


FLYING_10_PROTOCOL = {
    "protocol_key": "flying_10_acceleration_5yd_run_in",
    "protocol_name": "Flying 10-yard acceleration test with a 5-yard run-in",
    "protocol_alias": "10-yard sprint",
    "total_distance": "15",
    "timed_distance": "10",
    "run_in_distance": "5",
    "protocol_unit": "yards",
    "timed_segment": "5–15 yards",
    "start_type": "two-point",
    "purpose": "acceleration",
}


def seconds_to_milliseconds(value: str) -> int:
    try:
        seconds = Decimal(value.strip())
    except (AttributeError, InvalidOperation):
        raise ValueError("Enter a valid time in seconds, such as 1.72.") from None
    if not seconds.is_finite() or seconds < Decimal("0.1") or seconds > Decimal("120"):
        raise ValueError("Time must be between 0.10 and 120 seconds.")
    return int((seconds * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def normalize_distance(value: str) -> str:
    try:
        distance = Decimal(value.strip())
    except (AttributeError, InvalidOperation):
        raise ValueError("Enter a valid distance.") from None
    if not distance.is_finite() or distance <= 0 or distance > 1000:
        raise ValueError("Distance must be greater than 0 and no more than 1000.")
    return format(distance.normalize(), "f")


def format_seconds(milliseconds: int) -> str:
    return f"{milliseconds / 1000:.3f}".rstrip("0").rstrip(".")


def classify_attempts(attempts: list[dict]) -> list[dict]:
    """Classify attempts in chronological order, deriving rather than storing status."""
    historical_best: dict[tuple, int] = {}
    classified = []
    for attempt in sorted(attempts, key=lambda item: (item["captured_at"], item["id"])):
        # Protocol identity is part of comparability. Unknown protocols remain
        # isolated by session so they can never be silently mixed.
        if attempt.get("protocol_key"):
            protocol_identity = attempt["protocol_key"]
        elif "session_id" in attempt:
            protocol_identity = f"unknown-session:{attempt['session_id']}"
        else:
            # Compatibility for callers using the pre-session domain shape.
            protocol_identity = "legacy-unspecified"
        # Surface and timing method can materially change a short sprint time.
        # Environment is retained as context but does not split comparison sets.
        key = (attempt["athlete_id"], attempt["distance"], attempt["unit"], protocol_identity,
               attempt.get("surface_type"), attempt.get("timing_method"))
        previous = historical_best.get(key)
        status = "baseline" if previous is None else ("pr" if attempt["elapsed_ms"] < previous else "attempt")
        item = dict(attempt)
        item["status"] = status
        classified.append(item)
        historical_best[key] = min(previous, attempt["elapsed_ms"]) if previous is not None else attempt["elapsed_ms"]
    return classified
