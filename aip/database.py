"""SQLite persistence for the FEAT-001 prototype."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
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
CREATE TABLE IF NOT EXISTS training_groups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS training_group_members (
    group_id INTEGER NOT NULL REFERENCES training_groups(id) ON DELETE CASCADE,
    athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK(position > 0),
    PRIMARY KEY (group_id, athlete_id),
    UNIQUE (group_id, position)
);
CREATE TABLE IF NOT EXISTS training_group_sessions (
    group_id INTEGER NOT NULL REFERENCES training_groups(id) ON DELETE CASCADE,
    session_id INTEGER NOT NULL REFERENCES sprint_capture_sessions(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, session_id),
    UNIQUE (session_id)
);
CREATE TABLE IF NOT EXISTS session_roster_snapshots (
    session_id INTEGER PRIMARY KEY REFERENCES sprint_capture_sessions(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS session_roster_members (
    session_id INTEGER NOT NULL REFERENCES session_roster_snapshots(session_id) ON DELETE CASCADE,
    athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL CHECK(position > 0),
    PRIMARY KEY (session_id, athlete_id),
    UNIQUE (session_id, position)
);
CREATE TABLE IF NOT EXISTS prototype_feedback (
    id INTEGER PRIMARY KEY,
    group_id INTEGER REFERENCES training_groups(id) ON DELETE SET NULL,
    session_id INTEGER REFERENCES sprint_capture_sessions(id) ON DELETE SET NULL,
    slowed_down TEXT NOT NULL DEFAULT '',
    worked_well TEXT NOT NULL DEFAULT '',
    wished_for TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK(length(trim(slowed_down)) > 0 OR length(trim(worked_well)) > 0 OR length(trim(wished_for)) > 0)
);
CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY,
    file_digest TEXT NOT NULL,
    group_id INTEGER NOT NULL REFERENCES training_groups(id) ON DELETE RESTRICT,
    distance TEXT NOT NULL,
    unit TEXT NOT NULL CHECK(unit IN ('yards', 'meters')),
    original_filename TEXT NOT NULL,
    confirmed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    summary TEXT NOT NULL,
    warnings TEXT NOT NULL DEFAULT '[]',
    UNIQUE(file_digest, group_id, distance, unit)
);
CREATE TABLE IF NOT EXISTS imported_results (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE RESTRICT,
    attempt_id INTEGER UNIQUE REFERENCES sprint_attempts(id) ON DELETE SET NULL,
    source_row INTEGER NOT NULL CHECK(source_row > 0),
    source_column INTEGER NOT NULL CHECK(source_column > 0),
    source_date TEXT NOT NULL,
    source_elapsed_ms INTEGER NOT NULL CHECK(source_elapsed_ms > 0),
    fingerprint TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_attempt_session_athlete ON sprint_attempts(session_id, athlete_id);
CREATE INDEX IF NOT EXISTS idx_attempt_athlete_history ON sprint_attempts(athlete_id, captured_at, id);
CREATE INDEX IF NOT EXISTS idx_group_members_order ON training_group_members(group_id, position);
CREATE INDEX IF NOT EXISTS idx_session_roster_order ON session_roster_members(session_id, position);
CREATE INDEX IF NOT EXISTS idx_prototype_feedback_created ON prototype_feedback(created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_import_batches_scope ON import_batches(group_id, distance, unit);
CREATE INDEX IF NOT EXISTS idx_imported_results_batch ON imported_results(batch_id, source_row, source_column);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._backfill_legacy_session_rosters(connection)

    @staticmethod
    def _backfill_legacy_session_rosters(connection: sqlite3.Connection) -> None:
        legacy_sessions = connection.execute(
            """SELECT gs.session_id, gs.group_id FROM training_group_sessions gs
               LEFT JOIN session_roster_snapshots snapshot ON snapshot.session_id=gs.session_id
               WHERE snapshot.session_id IS NULL ORDER BY gs.session_id"""
        ).fetchall()
        for session in legacy_sessions:
            connection.execute(
                "INSERT INTO session_roster_snapshots(session_id) VALUES (?)", (session["session_id"],)
            )
            connection.execute(
                """INSERT INTO session_roster_members(session_id, athlete_id, position)
                   SELECT ?, athlete_id, position FROM training_group_members
                   WHERE group_id=? ORDER BY position""",
                (session["session_id"], session["group_id"]),
            )

    def all_athletes(self) -> list[dict]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM athletes ORDER BY name COLLATE NOCASE, id")]

    def athlete(self, athlete_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM athletes WHERE id=?", (athlete_id,)).fetchone()
            return dict(row) if row else None

    def add_athlete(self, name: str) -> int:
        name = normalized_name(name, "Athlete")
        with self.connect() as connection:
            return connection.execute("INSERT INTO athletes(name) VALUES (?)", (name,)).lastrowid

    def all_groups(self) -> list[dict]:
        with self.connect() as connection:
            query = """SELECT g.*, COUNT(DISTINCT m.athlete_id) AS athlete_count,
                              COUNT(DISTINCT gs.session_id) AS session_count
                       FROM training_groups g
                       LEFT JOIN training_group_members m ON m.group_id=g.id
                       LEFT JOIN training_group_sessions gs ON gs.group_id=g.id
                       GROUP BY g.id ORDER BY g.name COLLATE NOCASE, g.id"""
            return [dict(row) for row in connection.execute(query)]

    def group(self, group_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM training_groups WHERE id=?", (group_id,)).fetchone()
            return dict(row) if row else None

    def add_group(self, name: str) -> int:
        name = normalized_name(name, "Training Group")
        with self.connect() as connection:
            return connection.execute("INSERT INTO training_groups(name) VALUES (?)", (name,)).lastrowid

    def group_roster(self, group_id: int) -> list[dict]:
        if not self.group(group_id):
            raise LookupError("Training Group not found.")
        with self.connect() as connection:
            query = """SELECT a.*, m.position FROM training_group_members m
                       JOIN athletes a ON a.id=m.athlete_id
                       WHERE m.group_id=? ORDER BY m.position"""
            return [dict(row) for row in connection.execute(query, (group_id,))]

    def add_group_athlete(self, group_id: int, name: str) -> int:
        name = normalized_name(name, "Athlete")
        with self.connect() as connection:
            if not connection.execute("SELECT 1 FROM training_groups WHERE id=?", (group_id,)).fetchone():
                raise LookupError("Training Group not found.")
            athlete_id = connection.execute("INSERT INTO athletes(name) VALUES (?)", (name,)).lastrowid
            position = connection.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM training_group_members WHERE group_id=?", (group_id,)
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO training_group_members(group_id, athlete_id, position) VALUES (?, ?, ?)",
                (group_id, athlete_id, position),
            )
            return athlete_id

    def group_sessions(self, group_id: int) -> list[dict]:
        if not self.group(group_id):
            raise LookupError("Training Group not found.")
        with self.connect() as connection:
            query = """SELECT s.*, COUNT(a.id) AS attempt_count
                       FROM training_group_sessions gs
                       JOIN sprint_capture_sessions s ON s.id=gs.session_id
                       LEFT JOIN sprint_attempts a ON a.session_id=s.id
                       WHERE gs.group_id=? GROUP BY s.id ORDER BY s.id DESC"""
            return [dict(row) for row in connection.execute(query, (group_id,))]

    def all_sessions(self) -> list[dict]:
        with self.connect() as connection:
            query = """SELECT s.*, COUNT(a.id) AS attempt_count
                       FROM sprint_capture_sessions s LEFT JOIN sprint_attempts a ON a.session_id=s.id
                       GROUP BY s.id ORDER BY s.id DESC"""
            return [dict(row) for row in connection.execute(query)]

    def add_feedback(
        self,
        slowed_down: str,
        worked_well: str,
        wished_for: str,
        group_id: int | None = None,
        session_id: int | None = None,
    ) -> int:
        responses = tuple((value or "").strip() for value in (slowed_down, worked_well, wished_for))
        if not any(responses):
            raise ValueError("Enter at least one feedback response.")
        if any(len(value) > 5000 for value in responses):
            raise ValueError("Each feedback response must be 5,000 characters or fewer.")
        with self.connect() as connection:
            if group_id is not None and not connection.execute(
                "SELECT 1 FROM training_groups WHERE id=?", (group_id,)
            ).fetchone():
                raise LookupError("Training Group not found.")
            if session_id is not None and not connection.execute(
                "SELECT 1 FROM sprint_capture_sessions WHERE id=?", (session_id,)
            ).fetchone():
                raise LookupError("Session not found.")
            if group_id is not None and session_id is not None and not connection.execute(
                "SELECT 1 FROM training_group_sessions WHERE group_id=? AND session_id=?",
                (group_id, session_id),
            ).fetchone():
                raise ValueError("The selected session does not belong to the selected Training Group.")
            return connection.execute(
                """INSERT INTO prototype_feedback(
                       group_id, session_id, slowed_down, worked_well, wished_for
                   ) VALUES (?, ?, ?, ?, ?)""",
                (group_id, session_id, *responses),
            ).lastrowid

    def all_feedback(self) -> list[dict]:
        with self.connect() as connection:
            query = """SELECT f.*, g.name AS group_name,
                              s.distance AS session_distance, s.unit AS session_unit,
                              s.created_at AS session_created_at
                       FROM prototype_feedback f
                       LEFT JOIN training_groups g ON g.id=f.group_id
                       LEFT JOIN sprint_capture_sessions s ON s.id=f.session_id
                       ORDER BY f.created_at DESC, f.id DESC"""
            return [dict(row) for row in connection.execute(query)]

    def import_batch(self, batch_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM import_batches WHERE id=?", (batch_id,)).fetchone()
            return dict(row) if row else None

    def import_results(self, batch_id: int) -> list[dict]:
        with self.connect() as connection:
            query = """SELECT provenance.*, attempts.session_id, attempts.athlete_id, attempts.elapsed_ms,
                              attempts.captured_at
                       FROM imported_results provenance
                       LEFT JOIN sprint_attempts attempts ON attempts.id=provenance.attempt_id
                       WHERE provenance.batch_id=? ORDER BY provenance.source_row, provenance.source_column"""
            return [dict(row) for row in connection.execute(query, (batch_id,))]

    def add_session(self, distance: str, unit: str) -> int:
        if unit not in {"yards", "meters"}:
            raise ValueError("Unit must be yards or meters.")
        with self.connect() as connection:
            return connection.execute(
                "INSERT INTO sprint_capture_sessions(distance, unit) VALUES (?, ?)", (distance, unit)
            ).lastrowid

    def add_group_session(self, group_id: int, distance: str, unit: str) -> int:
        if unit not in {"yards", "meters"}:
            raise ValueError("Unit must be yards or meters.")
        with self.connect() as connection:
            if not connection.execute("SELECT 1 FROM training_groups WHERE id=?", (group_id,)).fetchone():
                raise LookupError("Training Group not found.")
            session_id = connection.execute(
                "INSERT INTO sprint_capture_sessions(distance, unit) VALUES (?, ?)", (distance, unit)
            ).lastrowid
            connection.execute(
                "INSERT INTO training_group_sessions(group_id, session_id) VALUES (?, ?)", (group_id, session_id)
            )
            connection.execute(
                "INSERT INTO session_roster_snapshots(session_id) VALUES (?)", (session_id,)
            )
            connection.execute(
                """INSERT INTO session_roster_members(session_id, athlete_id, position)
                   SELECT ?, athlete_id, position FROM training_group_members
                   WHERE group_id=? ORDER BY position""",
                (session_id, group_id),
            )
            return session_id

    def session(self, session_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM sprint_capture_sessions WHERE id=?", (session_id,)).fetchone()
            return dict(row) if row else None

    def session_group(self, session_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT g.* FROM training_group_sessions gs
                   JOIN training_groups g ON g.id=gs.group_id WHERE gs.session_id=?""", (session_id,)
            ).fetchone()
            return dict(row) if row else None

    def session_athletes(self, session_id: int) -> list[dict]:
        if not self.session(session_id):
            raise LookupError("Session not found.")
        group = self.session_group(session_id)
        return self.session_roster(session_id) if group else self.all_athletes()

    def session_roster(self, session_id: int) -> list[dict]:
        with self.connect() as connection:
            if not connection.execute(
                "SELECT 1 FROM session_roster_snapshots WHERE session_id=?", (session_id,)
            ).fetchone():
                raise LookupError("Session roster snapshot not found.")
            query = """SELECT a.*, member.position FROM session_roster_members member
                       JOIN athletes a ON a.id=member.athlete_id
                       WHERE member.session_id=? ORDER BY member.position"""
            return [dict(row) for row in connection.execute(query, (session_id,))]

    def add_attempt(self, session_id: int, athlete_id: int, elapsed_ms: int) -> int:
        with self.connect() as connection:
            if not connection.execute("SELECT 1 FROM sprint_capture_sessions WHERE id=?", (session_id,)).fetchone():
                raise LookupError("Session not found.")
            if not connection.execute("SELECT 1 FROM athletes WHERE id=?", (athlete_id,)).fetchone():
                raise ValueError("Choose a valid athlete.")
            group_row = connection.execute(
                "SELECT group_id FROM training_group_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if group_row and not connection.execute(
                "SELECT 1 FROM session_roster_members WHERE session_id=? AND athlete_id=?",
                (session_id, athlete_id),
            ).fetchone():
                raise ValueError("Choose an athlete from this session roster.")
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

    def export_attempts(
        self,
        *,
        session_id: int | None = None,
        group_id: int | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict]:
        if (session_id is None) == (group_id is None):
            raise ValueError("Choose exactly one export scope.")
        with self.connect() as connection:
            if session_id is not None and not connection.execute(
                "SELECT 1 FROM sprint_capture_sessions WHERE id=?", (session_id,)
            ).fetchone():
                raise LookupError("Session not found.")
            if group_id is not None and not connection.execute(
                "SELECT 1 FROM training_groups WHERE id=?", (group_id,)
            ).fetchone():
                raise LookupError("Training Group not found.")
            conditions = ["a.session_id=?" if session_id is not None else "gs.group_id=?"]
            parameters: list[object] = [session_id if session_id is not None else group_id]
            if start:
                conditions.append("date(s.created_at) >= ?")
                parameters.append(start)
            if end:
                conditions.append("date(s.created_at) <= ?")
                parameters.append(end)
            query = f"""SELECT a.*, athletes.name AS athlete_name,
                               s.distance, s.unit, s.created_at AS session_created_at,
                               gs.group_id, groups.name AS group_name,
                               roster.position AS roster_position
                        FROM sprint_attempts a
                        JOIN sprint_capture_sessions s ON s.id=a.session_id
                        JOIN athletes ON athletes.id=a.athlete_id
                        LEFT JOIN training_group_sessions gs ON gs.session_id=s.id
                        LEFT JOIN training_groups groups ON groups.id=gs.group_id
                        LEFT JOIN session_roster_members roster
                          ON roster.session_id=s.id AND roster.athlete_id=a.athlete_id
                        WHERE {' AND '.join(conditions)}
                        ORDER BY s.created_at, s.id,
                                 CASE WHEN roster.position IS NULL THEN 1 ELSE 0 END,
                                 roster.position, athletes.name COLLATE NOCASE,
                                 a.athlete_id, a.captured_at, a.id"""
            return [dict(row) for row in connection.execute(query, parameters)]


def normalized_name(value: str, label: str) -> str:
    name = " ".join(value.split())
    if not name or len(name) > 100:
        raise ValueError(f"{label} name must be between 1 and 100 characters.")
    return name
