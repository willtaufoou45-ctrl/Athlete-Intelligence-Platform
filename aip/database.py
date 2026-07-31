"""SQLite persistence for the FEAT-001 prototype."""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS athletes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sprint_capture_sessions (
    id INTEGER PRIMARY KEY,
    distance TEXT NOT NULL,
    unit TEXT NOT NULL CHECK(unit IN ('yards', 'meters')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sprint_attempts (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sprint_capture_sessions(id) ON DELETE CASCADE,
    athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE RESTRICT,
    elapsed_ms INTEGER NOT NULL CHECK(elapsed_ms > 0),
    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_attempt_session_athlete ON sprint_attempts(session_id, athlete_id);
CREATE INDEX IF NOT EXISTS idx_attempt_athlete_history ON sprint_attempts(athlete_id, captured_at, id);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def all_athletes(self) -> list[dict]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM athletes ORDER BY name COLLATE NOCASE, id")]

    def athlete(self, athlete_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM athletes WHERE id=?", (athlete_id,)).fetchone()
            return dict(row) if row else None

    def add_athlete(self, name: str) -> int:
        name = " ".join(name.split())
        if not name or len(name) > 100:
            raise ValueError("Athlete name must be between 1 and 100 characters.")
        with self.connect() as connection:
            return connection.execute("INSERT INTO athletes(name) VALUES (?)", (name,)).lastrowid

    def all_sessions(self) -> list[dict]:
        with self.connect() as connection:
            query = """SELECT s.*, COUNT(a.id) AS attempt_count
                       FROM sprint_capture_sessions s LEFT JOIN sprint_attempts a ON a.session_id=s.id
                       GROUP BY s.id ORDER BY s.id DESC"""
            return [dict(row) for row in connection.execute(query)]

    def add_session(self, distance: str, unit: str) -> int:
        if unit not in {"yards", "meters"}:
            raise ValueError("Unit must be yards or meters.")
        with self.connect() as connection:
            return connection.execute(
                "INSERT INTO sprint_capture_sessions(distance, unit) VALUES (?, ?)", (distance, unit)
            ).lastrowid

    def session(self, session_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM sprint_capture_sessions WHERE id=?", (session_id,)).fetchone()
            return dict(row) if row else None

    def add_attempt(self, session_id: int, athlete_id: int, elapsed_ms: int) -> int:
        with self.connect() as connection:
            if not connection.execute("SELECT 1 FROM sprint_capture_sessions WHERE id=?", (session_id,)).fetchone():
                raise LookupError("Session not found.")
            if not connection.execute("SELECT 1 FROM athletes WHERE id=?", (athlete_id,)).fetchone():
                raise ValueError("Choose a valid athlete.")
            return connection.execute(
                "INSERT INTO sprint_attempts(session_id, athlete_id, elapsed_ms) VALUES (?, ?, ?)",
                (session_id, athlete_id, elapsed_ms),
            ).lastrowid

    def update_attempt(self, attempt_id: int, elapsed_ms: int) -> tuple[int, int]:
        with self.connect() as connection:
            row = connection.execute("SELECT session_id, athlete_id FROM sprint_attempts WHERE id=?", (attempt_id,)).fetchone()
            if not row:
                raise LookupError("Attempt not found.")
            connection.execute(
                "UPDATE sprint_attempts SET elapsed_ms=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (elapsed_ms, attempt_id),
            )
            return row["session_id"], row["athlete_id"]

    def delete_attempt(self, attempt_id: int) -> tuple[int, int]:
        with self.connect() as connection:
            row = connection.execute("SELECT session_id, athlete_id FROM sprint_attempts WHERE id=?", (attempt_id,)).fetchone()
            if not row:
                raise LookupError("Attempt not found.")
            connection.execute("DELETE FROM sprint_attempts WHERE id=?", (attempt_id,))
            return row["session_id"], row["athlete_id"]

    def all_attempts(self) -> list[dict]:
        with self.connect() as connection:
            query = """SELECT a.*, s.distance, s.unit, athletes.name AS athlete_name
                       FROM sprint_attempts a
                       JOIN sprint_capture_sessions s ON s.id=a.session_id
                       JOIN athletes ON athletes.id=a.athlete_id
                       ORDER BY a.captured_at, a.id"""
            return [dict(row) for row in connection.execute(query)]
