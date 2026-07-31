"""Measurement parsing and derived sprint results."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


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
    historical_best: dict[tuple[int, str, str], int] = {}
    classified = []
    for attempt in sorted(attempts, key=lambda item: (item["captured_at"], item["id"])):
        key = (attempt["athlete_id"], attempt["distance"], attempt["unit"])
        previous = historical_best.get(key)
        status = "baseline" if previous is None else ("pr" if attempt["elapsed_ms"] < previous else "attempt")
        item = dict(attempt)
        item["status"] = status
        classified.append(item)
        historical_best[key] = min(previous, attempt["elapsed_ms"]) if previous is not None else attempt["elapsed_ms"]
    return classified
