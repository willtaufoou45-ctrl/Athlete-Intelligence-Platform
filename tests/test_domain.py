import unittest

from aip.domain import classify_attempts, normalize_distance, seconds_to_milliseconds


class MeasurementTests(unittest.TestCase):
    def test_seconds_convert_without_float_error(self):
        self.assertEqual(seconds_to_milliseconds("1.72"), 1720)
        self.assertEqual(seconds_to_milliseconds("1.2345"), 1235)

    def test_invalid_measurements_are_rejected(self):
        for value in ("", "fast", "0", "-1", "121", "NaN", "Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                seconds_to_milliseconds(value)

    def test_distance_is_normalized(self):
        self.assertEqual(normalize_distance("10.00"), "10")

    def test_baseline_strict_pr_and_unit_isolation(self):
        rows = [
            attempt(1, 1, 1800, "10", "yards"),
            attempt(2, 1, 1800, "10", "yards"),
            attempt(3, 1, 1750, "10", "yards"),
            attempt(4, 1, 1740, "10", "meters"),
            attempt(5, 1, 1700, "20", "yards"),
        ]
        self.assertEqual([a["status"] for a in classify_attempts(rows)], ["baseline", "attempt", "pr", "baseline", "baseline"])


def attempt(identifier, athlete_id, elapsed_ms, distance, unit):
    return {"id": identifier, "athlete_id": athlete_id, "elapsed_ms": elapsed_ms, "distance": distance, "unit": unit, "captured_at": "2026-01-01 00:00:00"}


if __name__ == "__main__":
    unittest.main()
