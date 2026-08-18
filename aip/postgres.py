"""Minimal Psycopg compatibility boundary for the existing repository queries."""

from __future__ import annotations

import re


ID_TABLES = {
    "athletes", "sprint_capture_sessions", "sprint_attempts", "training_groups",
    "prototype_feedback", "import_batches", "imported_results",
}


class Cursor:
    def __init__(self, cursor, *, returning_id: bool = False):
        self._cursor = cursor
        self.lastrowid = None
        if returning_id:
            row = cursor.fetchone()
            self.lastrowid = row["id"] if row else None

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)


class Connection:
    def __init__(self, connection):
        self._connection = connection

    def execute(self, query: str, parameters=()):
        query = postgres_query(query)
        returning = False
        match = re.match(r"\s*INSERT\s+INTO\s+([a-z_]+)", query, re.I)
        if match and match.group(1).lower() in ID_TABLES and " RETURNING " not in query.upper():
            query = query.rstrip().rstrip(";") + " RETURNING id"
            returning = True
        cursor = self._connection.execute(query, parameters)
        return Cursor(cursor, returning_id=returning)

    def executescript(self, script: str):
        for statement in (part.strip() for part in script.split(";")):
            if statement:
                self._connection.execute(postgres_query(statement))


def connect(database_url: str):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise RuntimeError("PostgreSQL requires the psycopg dependency from pyproject.toml.") from error
    raw = psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10)
    return raw, Connection(raw)


def postgres_query(query: str) -> str:
    query = query.replace("?", "%s").replace(" COLLATE NOCASE", "")
    query = re.sub(r"\bdate\(([^(),]+)\)", r"CAST(\1 AS DATE)", query, flags=re.I)
    query = query.replace(
        "CURRENT_TIMESTAMP",
        "to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')",
    )
    return query


def postgres_schema(*schemas: str) -> str:
    value = "\n".join(schemas)
    value = re.sub(r"^PRAGMA .*?;\s*", "", value, flags=re.M)
    value = re.sub(r"(?m)^(\s*)id INTEGER PRIMARY KEY", r"\1id BIGSERIAL PRIMARY KEY", value)
    value = re.sub(r"\b([a-z_]+_id) INTEGER\b", r"\1 BIGINT", value)
    value = value.replace("DEFAULT (date('now'))", "DEFAULT (CURRENT_DATE::text)")
    return postgres_query(value)
