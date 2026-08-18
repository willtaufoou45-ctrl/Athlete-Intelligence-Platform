"""SQLite persistence for the FEAT-001 prototype."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from .intelligence import (
    CONFIDENCE_LEVELS,
    EPISTEMIC_CLASSES,
    EVIDENCE_RELATIONSHIPS,
    EVIDENCE_TYPES,
    RECORD_STATUSES,
    RECORD_TYPES,
    SCHEMA as INTELLIGENCE_SCHEMA,
    STATE_TYPES,
    json_text,
    new_id,
    seed_rigby_case_study,
    seed_brody_case_study,
)
from .domain import FLYING_10_PROTOCOL
from .postgres import connect as postgres_connect, postgres_schema


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
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'completed')),
    session_date TEXT NOT NULL DEFAULT (date('now')),
    completed_at TEXT,
    protocol_key TEXT,
    protocol_name TEXT,
    protocol_alias TEXT,
    total_distance TEXT,
    timed_distance TEXT,
    run_in_distance TEXT,
    protocol_unit TEXT CHECK(protocol_unit IS NULL OR protocol_unit IN ('yards', 'meters')),
    timed_segment TEXT,
    start_type TEXT,
    purpose TEXT,
    target_attempts INTEGER CHECK(target_attempts IS NULL OR target_attempts > 0),
    surface_type TEXT,
    timing_method TEXT,
    environment TEXT,
    protocol_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sprint_attempts (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sprint_capture_sessions(id) ON DELETE CASCADE,
    athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE RESTRICT,
    elapsed_ms INTEGER NOT NULL CHECK(elapsed_ms > 0),
    request_key TEXT UNIQUE,
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

MIGRATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS data_migrations (
    id BIGSERIAL PRIMARY KEY,
    migration_key TEXT NOT NULL UNIQUE,
    source_sha256 TEXT NOT NULL,
    source_manifest TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running','complete','failed')),
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
"""

POSTGRES_SCHEMA_VERSION = 2


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.is_postgres = self.path.startswith(("postgres://", "postgresql://"))

    @contextmanager
    def connect(self):
        raw_connection = None
        if self.is_postgres:
            raw_connection, connection = postgres_connect(self.path)
        else:
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
        try:
            with (raw_connection or connection):
                yield connection
        finally:
            (raw_connection or connection).close()

    def initialize(self) -> None:
        if not self.is_postgres:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            if self.is_postgres:
                connection.execute("SELECT pg_advisory_xact_lock(hashtext(?))", ("aip-schema-migrations",))
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
                )
                applied = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=?", (POSTGRES_SCHEMA_VERSION,)
                ).fetchone()
                if not applied:
                    connection.executescript(postgres_schema(SCHEMA, INTELLIGENCE_SCHEMA, MIGRATION_SCHEMA))
                    connection.execute(
                        "INSERT INTO schema_migrations(version) VALUES (?)", (POSTGRES_SCHEMA_VERSION,)
                    )
            else:
                connection.executescript(SCHEMA)
                self._migrate_session_lifecycle(connection)
                self._migrate_attempt_request_keys(connection)
                self._migrate_sprint_protocols(connection)
                self._backfill_legacy_session_rosters(connection)
                connection.executescript(INTELLIGENCE_SCHEMA)
                self._migrate_intelligence_v02(connection)

    def seed_rigby_intelligence(self) -> str | None:
        with self.connect() as connection:
            return seed_rigby_case_study(connection)

    def seed_brody_intelligence(self) -> str | None:
        with self.connect() as connection:
            return seed_brody_case_study(connection)

    def add_canonical_athlete(self, display_name: str) -> str:
        display_name = normalized_name(display_name, "Canonical athlete")
        athlete_id = new_id()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO canonical_athletes(id,display_name) VALUES (?,?)", (athlete_id, display_name)
            )
        return athlete_id

    def canonical_athlete(self, athlete_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM canonical_athletes WHERE id=?", (athlete_id,)).fetchone()
            return dict(row) if row else None

    def canonical_athlete_by_external_identity(
        self, source_system: str, source_entity_type: str, source_record_id: str,
    ) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT athlete.* FROM athlete_external_identities identity
                   JOIN canonical_athletes athlete ON athlete.id=identity.athlete_id
                   WHERE identity.source_system=? AND identity.source_entity_type=?
                     AND identity.source_record_id=?""",
                (source_system, source_entity_type, str(source_record_id)),
            ).fetchone()
            return dict(row) if row else None

    def add_external_identity(
        self, athlete_id: str, source_system: str, source_entity_type: str,
        source_record_id: str, source_display_name: str | None = None, verified: bool = False,
    ) -> str:
        identity_id = new_id()
        with self.connect() as connection:
            if not connection.execute("SELECT 1 FROM canonical_athletes WHERE id=?", (athlete_id,)).fetchone():
                raise LookupError("Canonical athlete not found.")
            connection.execute(
                """INSERT INTO athlete_external_identities(
                       id,athlete_id,source_system,source_entity_type,source_record_id,
                       source_display_name,verified_at
                   ) VALUES (?,?,?,?,?,?,CASE WHEN ? THEN CURRENT_TIMESTAMP END)""",
                (identity_id, athlete_id, source_system, source_entity_type, str(source_record_id), source_display_name, verified),
            )
        return identity_id

    def add_athlete_state(
        self, athlete_id: str, state_type: str, *, label: str | None = None,
        effective_from: str | None = None, effective_to: str | None = None,
        attributes: dict | None = None,
    ) -> str:
        if state_type not in STATE_TYPES:
            raise ValueError("Choose a valid athlete state type.")
        state_id = new_id()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO athlete_states(
                       id,athlete_id,state_type,label,effective_from,effective_to,attributes
                   ) VALUES (?,?,?,?,?,?,?)""",
                (state_id, athlete_id, state_type, label, effective_from, effective_to, json_text(attributes)),
            )
        return state_id

    def add_intelligence_record(
        self, athlete_id: str, record_type: str, statement: str, status: str,
        *, confidence: str | None = None, created_by: str = "system",
        supersedes_record_id: str | None = None, epistemic_class: str | None = None,
        first_observed_at: str | None = None, last_confirmed_at: str | None = None,
        effective_from: str | None = None, effective_to: str | None = None,
        freshness_review_at: str | None = None,
    ) -> str:
        if record_type not in RECORD_TYPES or status not in RECORD_STATUSES:
            raise ValueError("Choose valid intelligence record type and status values.")
        if confidence is not None and confidence not in CONFIDENCE_LEVELS:
            raise ValueError("Choose a valid confidence level.")
        if epistemic_class is not None and epistemic_class not in EPISTEMIC_CLASSES:
            raise ValueError("Choose a valid epistemic class.")
        record_id = new_id()
        with self.connect() as connection:
            if supersedes_record_id:
                prior = connection.execute(
                    "SELECT athlete_id FROM intelligence_records WHERE id=?", (supersedes_record_id,)
                ).fetchone()
                if not prior or prior["athlete_id"] != athlete_id:
                    raise ValueError("A superseded record must belong to the same athlete.")
                connection.execute(
                    "UPDATE intelligence_records SET status='superseded',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (supersedes_record_id,),
                )
            connection.execute(
                """INSERT INTO intelligence_records(
                       id,athlete_id,type,epistemic_class,statement,status,confidence,
                       first_observed_at,last_confirmed_at,effective_from,effective_to,
                       freshness_review_at,supersedes_record_id,created_by
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (record_id, athlete_id, record_type, epistemic_class, statement, status, confidence,
                 first_observed_at, last_confirmed_at, effective_from, effective_to,
                 freshness_review_at, supersedes_record_id, created_by),
            )
        return record_id

    def add_evidence(
        self, athlete_id: str, evidence_type: str, source_system: str,
        source_entity_type: str, source_record_id: str, *, observed_date: str | None = None,
        observed_at: str | None = None, summary: str | None = None,
        source_version_or_digest: str | None = None, metadata: dict | None = None,
    ) -> str:
        if evidence_type not in EVIDENCE_TYPES:
            raise ValueError("Choose a valid evidence type.")
        evidence_id = new_id()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO evidence(
                       id,athlete_id,evidence_type,source_system,source_entity_type,source_record_id,
                       observed_at,observed_date,summary,source_version_or_digest,metadata
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (evidence_id, athlete_id, evidence_type, source_system, source_entity_type,
                 str(source_record_id), observed_at, observed_date, summary,
                 source_version_or_digest, json_text(metadata)),
            )
        return evidence_id

    def link_intelligence_evidence(
        self, intelligence_record_id: str, evidence_id: str,
        relationship_type: str, note: str | None = None,
    ) -> None:
        if relationship_type not in EVIDENCE_RELATIONSHIPS:
            raise ValueError("Choose a valid evidence relationship.")
        with self.connect() as connection:
            record = connection.execute(
                "SELECT athlete_id FROM intelligence_records WHERE id=?", (intelligence_record_id,)
            ).fetchone()
            evidence = connection.execute("SELECT athlete_id FROM evidence WHERE id=?", (evidence_id,)).fetchone()
            if not record or not evidence:
                raise LookupError("Intelligence record or evidence not found.")
            if record["athlete_id"] != evidence["athlete_id"]:
                raise ValueError("Intelligence and evidence must belong to the same athlete.")
            connection.execute(
                """INSERT INTO intelligence_evidence_links(
                       intelligence_record_id,evidence_id,relationship_type,note
                   ) VALUES (?,?,?,?)""",
                (intelligence_record_id, evidence_id, relationship_type, note),
            )

    def intelligence_snapshot(self, athlete_id: str) -> dict:
        with self.connect() as connection:
            athlete = connection.execute("SELECT * FROM canonical_athletes WHERE id=?", (athlete_id,)).fetchone()
            if not athlete:
                raise LookupError("Canonical athlete not found.")
            identities = [dict(row) for row in connection.execute(
                "SELECT * FROM athlete_external_identities WHERE athlete_id=? ORDER BY source_system", (athlete_id,)
            )]
            states = [dict(row) for row in connection.execute(
                """SELECT * FROM athlete_states WHERE athlete_id=?
                   ORDER BY CASE WHEN effective_from IS NULL THEN 1 ELSE 0 END,
                            effective_from,created_at,id""",
                (athlete_id,),
            )]
            records = [dict(row) for row in connection.execute(
                "SELECT * FROM intelligence_records WHERE athlete_id=? ORDER BY created_at,id", (athlete_id,)
            )]
            evidence = [dict(row) for row in connection.execute(
                "SELECT * FROM evidence WHERE athlete_id=? ORDER BY observed_date,id", (athlete_id,)
            )]
            links = [dict(row) for row in connection.execute(
                """SELECT link.* FROM intelligence_evidence_links link
                   JOIN intelligence_records record ON record.id=link.intelligence_record_id
                   WHERE record.athlete_id=? ORDER BY link.created_at,link.intelligence_record_id,link.evidence_id""",
                (athlete_id,),
            )]
        return {"athlete": dict(athlete), "external_identities": identities, "states": states,
                "records": records, "evidence": evidence, "links": links}

    @staticmethod
    def _migrate_intelligence_v02(connection: sqlite3.Connection) -> None:
        """Add v0.2 semantics while preserving every v0.1 record and link."""
        record_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(intelligence_records)")
        }
        if "epistemic_class" not in record_columns:
            connection.execute(
                """ALTER TABLE intelligence_records ADD COLUMN epistemic_class TEXT
                   CHECK(epistemic_class IS NULL OR epistemic_class IN
                   ('fact','coach_observation','athlete_report','hypothesis',
                    'interpretation','unknown','derived_analysis'))"""
            )

        evidence_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='evidence'"
        ).fetchone()["sql"]
        links_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='intelligence_evidence_links'"
        ).fetchone()["sql"]
        if "training_exposure" in evidence_sql and "contextualizes" in links_sql:
            return

        statements = (
            """CREATE TABLE evidence_v02 (
                id TEXT PRIMARY KEY,
                athlete_id TEXT NOT NULL REFERENCES canonical_athletes(id) ON DELETE RESTRICT,
                evidence_type TEXT NOT NULL CHECK(evidence_type IN
                    ('sprint_result','sprint_session','workout_session','exercise_performance',
                     'force_test','coach_observation','training_exposure')),
                source_system TEXT NOT NULL,
                source_entity_type TEXT NOT NULL,
                source_record_id TEXT NOT NULL,
                observed_at TEXT,
                observed_date TEXT,
                summary TEXT,
                source_version_or_digest TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_system, source_entity_type, source_record_id)
            )""",
            """INSERT INTO evidence_v02
            SELECT id,athlete_id,evidence_type,source_system,source_entity_type,source_record_id,
                   observed_at,observed_date,summary,source_version_or_digest,metadata,created_at
            FROM evidence""",
            """CREATE TABLE intelligence_evidence_links_v02 (
                intelligence_record_id TEXT NOT NULL REFERENCES intelligence_records(id) ON DELETE CASCADE,
                evidence_id TEXT NOT NULL REFERENCES evidence_v02(id) ON DELETE RESTRICT,
                relationship_type TEXT NOT NULL CHECK(relationship_type IN
                    ('supports','contradicts','motivated_by','response_to','resolved_by','contextualizes')),
                note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(intelligence_record_id, evidence_id)
            )""",
            """INSERT INTO intelligence_evidence_links_v02
            SELECT intelligence_record_id,evidence_id,relationship_type,note,created_at
            FROM intelligence_evidence_links""",
            "DROP TABLE intelligence_evidence_links",
            "DROP TABLE evidence",
            "ALTER TABLE evidence_v02 RENAME TO evidence",
            "ALTER TABLE intelligence_evidence_links_v02 RENAME TO intelligence_evidence_links",
            """CREATE INDEX IF NOT EXISTS idx_evidence_athlete
               ON evidence(athlete_id, observed_date, observed_at)""",
            """CREATE INDEX IF NOT EXISTS idx_intelligence_links_evidence
               ON intelligence_evidence_links(evidence_id)""",
        )
        for statement in statements:
            connection.execute(statement)

    @staticmethod
    def _migrate_session_lifecycle(connection: sqlite3.Connection) -> None:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(sprint_capture_sessions)")}
        if "status" not in columns:
            connection.execute(
                "ALTER TABLE sprint_capture_sessions ADD COLUMN status TEXT NOT NULL DEFAULT 'open'"
            )
        if "session_date" not in columns:
            connection.execute("ALTER TABLE sprint_capture_sessions ADD COLUMN session_date TEXT")
            connection.execute(
                """UPDATE sprint_capture_sessions
                   SET session_date=date(created_at, 'localtime') WHERE session_date IS NULL"""
            )
        if "completed_at" not in columns:
            connection.execute("ALTER TABLE sprint_capture_sessions ADD COLUMN completed_at TEXT")

    @staticmethod
    def _migrate_attempt_request_keys(connection: sqlite3.Connection) -> None:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(sprint_attempts)")}
        if "request_key" not in columns:
            connection.execute("ALTER TABLE sprint_attempts ADD COLUMN request_key TEXT")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_attempt_request_key ON sprint_attempts(request_key)"
        )

    @staticmethod
    def _migrate_sprint_protocols(connection: sqlite3.Connection) -> None:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(sprint_capture_sessions)")}
        definitions = {
            "protocol_key": "TEXT", "protocol_name": "TEXT", "protocol_alias": "TEXT",
            "total_distance": "TEXT", "timed_distance": "TEXT", "run_in_distance": "TEXT",
            "protocol_unit": "TEXT", "timed_segment": "TEXT", "start_type": "TEXT",
            "purpose": "TEXT", "target_attempts": "INTEGER", "surface_type": "TEXT",
            "timing_method": "TEXT", "environment": "TEXT", "protocol_notes": "TEXT",
        }
        for name, sql_type in definitions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE sprint_capture_sessions ADD COLUMN {name} {sql_type}")
        assignments = ", ".join(f"{name}=?" for name in FLYING_10_PROTOCOL)
        connection.execute(
            f"""UPDATE sprint_capture_sessions SET {assignments}
                WHERE distance='10' AND unit='yards' AND protocol_key IS NULL""",
            tuple(FLYING_10_PROTOCOL.values()),
        )

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

    def athlete_directory(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT a.id, a.name, g.id AS group_id, g.name AS group_name
                   FROM athletes a
                   LEFT JOIN training_group_members m ON m.athlete_id=a.id
                   LEFT JOIN training_groups g ON g.id=m.group_id
                   ORDER BY a.name COLLATE NOCASE, a.id, g.name COLLATE NOCASE, g.id"""
            )
            athletes: dict[int, dict] = {}
            for row in rows:
                athlete = athletes.setdefault(row["id"], {"id": row["id"], "name": row["name"], "groups": []})
                if row["group_id"] is not None:
                    athlete["groups"].append({"id": row["group_id"], "name": row["group_name"]})
            return list(athletes.values())

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
            query = """SELECT g.*,
                              (SELECT COUNT(*) FROM training_group_members m WHERE m.group_id=g.id) AS athlete_count,
                              (SELECT COUNT(*) FROM training_group_sessions gs WHERE gs.group_id=g.id) AS session_count
                       FROM training_groups g ORDER BY g.name COLLATE NOCASE, g.id"""
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

    def create_group_athlete(self, group_id: int, name: str) -> int:
        name = normalized_name(name, "Athlete")
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM athletes WHERE lower(name)=lower(?) ORDER BY id LIMIT 1", (name,)
            ).fetchone()
            if existing:
                raise ValueError("An athlete with this name already exists. Search for and add the existing athlete instead.")
        return self.add_group_athlete(group_id, name)

    def add_existing_group_athlete(self, group_id: int, athlete_id: int) -> None:
        with self.connect() as connection:
            if not connection.execute("SELECT 1 FROM training_groups WHERE id=?", (group_id,)).fetchone():
                raise LookupError("Training Group not found.")
            if not connection.execute("SELECT 1 FROM athletes WHERE id=?", (athlete_id,)).fetchone():
                raise LookupError("Athlete not found.")
            if connection.execute(
                "SELECT 1 FROM training_group_members WHERE group_id=? AND athlete_id=?",
                (group_id, athlete_id),
            ).fetchone():
                raise ValueError("This athlete is already in this Training Group.")
            position = connection.execute(
                "SELECT COALESCE(MAX(position),0)+1 FROM training_group_members WHERE group_id=?", (group_id,)
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO training_group_members(group_id,athlete_id,position) VALUES (?,?,?)",
                (group_id, athlete_id, position),
            )

    def reorder_group_athlete(self, group_id: int, athlete_id: int, direction: str) -> None:
        if direction not in {"up", "down"}:
            raise ValueError("Choose up or down.")
        with self.connect() as connection:
            athlete_ids = [row["athlete_id"] for row in connection.execute(
                "SELECT athlete_id FROM training_group_members WHERE group_id=? ORDER BY position",
                (group_id,),
            )]
            if athlete_id not in athlete_ids:
                raise LookupError("Athlete is not in this Training Group.")
            current = athlete_ids.index(athlete_id)
            target = current - 1 if direction == "up" else current + 1
            if target < 0 or target >= len(athlete_ids):
                return
            athlete_ids[current], athlete_ids[target] = athlete_ids[target], athlete_ids[current]
            self._set_group_order(connection, group_id, athlete_ids)

    def transfer_group_athlete(
        self, source_group_id: int, athlete_id: int, target_group_id: int, *, move: bool,
    ) -> None:
        if source_group_id == target_group_id:
            raise ValueError("Choose a different Training Group.")
        with self.connect() as connection:
            if not connection.execute(
                "SELECT 1 FROM training_group_members WHERE group_id=? AND athlete_id=?",
                (source_group_id, athlete_id),
            ).fetchone():
                raise LookupError("Athlete is not in this Training Group.")
            if not connection.execute("SELECT 1 FROM training_groups WHERE id=?", (target_group_id,)).fetchone():
                raise LookupError("Target Training Group not found.")
            if not connection.execute(
                "SELECT 1 FROM training_group_members WHERE group_id=? AND athlete_id=?",
                (target_group_id, athlete_id),
            ).fetchone():
                position = connection.execute(
                    "SELECT COALESCE(MAX(position),0)+1 FROM training_group_members WHERE group_id=?",
                    (target_group_id,),
                ).fetchone()[0]
                connection.execute(
                    "INSERT INTO training_group_members(group_id,athlete_id,position) VALUES (?,?,?)",
                    (target_group_id, athlete_id, position),
                )
            if move:
                self._remove_group_member(connection, source_group_id, athlete_id)

    def remove_group_athlete(self, group_id: int, athlete_id: int) -> None:
        with self.connect() as connection:
            if not connection.execute(
                "SELECT 1 FROM training_group_members WHERE group_id=? AND athlete_id=?",
                (group_id, athlete_id),
            ).fetchone():
                raise LookupError("Athlete is not in this Training Group.")
            self._remove_group_member(connection, group_id, athlete_id)

    @staticmethod
    def _remove_group_member(connection, group_id: int, athlete_id: int) -> None:
        connection.execute(
            "DELETE FROM training_group_members WHERE group_id=? AND athlete_id=?",
            (group_id, athlete_id),
        )
        remaining = [row["athlete_id"] for row in connection.execute(
            "SELECT athlete_id FROM training_group_members WHERE group_id=? ORDER BY position",
            (group_id,),
        )]
        Database._set_group_order(connection, group_id, remaining)

    @staticmethod
    def _set_group_order(connection, group_id: int, athlete_ids: list[int]) -> None:
        for temporary, athlete_id in enumerate(athlete_ids, 100001):
            connection.execute(
                "UPDATE training_group_members SET position=? WHERE group_id=? AND athlete_id=?",
                (temporary, group_id, athlete_id),
            )
        for position, athlete_id in enumerate(athlete_ids, 1):
            connection.execute(
                "UPDATE training_group_members SET position=? WHERE group_id=? AND athlete_id=?",
                (position, group_id, athlete_id),
            )

    def group_sessions(self, group_id: int) -> list[dict]:
        if not self.group(group_id):
            raise LookupError("Training Group not found.")
        with self.connect() as connection:
            query = """SELECT s.*,
                              (SELECT COUNT(*) FROM sprint_attempts a WHERE a.session_id=s.id) AS attempt_count
                       FROM training_group_sessions gs
                       JOIN sprint_capture_sessions s ON s.id=gs.session_id
                       WHERE gs.group_id=?
                       ORDER BY CASE s.status WHEN 'open' THEN 0 ELSE 1 END,
                                s.session_date DESC, s.id DESC"""
            return [dict(row) for row in connection.execute(query, (group_id,))]

    def all_sessions(self) -> list[dict]:
        with self.connect() as connection:
            query = """SELECT s.*, g.name AS group_name,
                              (SELECT COUNT(*) FROM sprint_attempts a WHERE a.session_id=s.id) AS attempt_count
                       FROM sprint_capture_sessions s
                       LEFT JOIN training_group_sessions gs ON gs.session_id=s.id
                       LEFT JOIN training_groups g ON g.id=gs.group_id
                       ORDER BY CASE s.status WHEN 'open' THEN 0 ELSE 1 END,
                                s.session_date DESC, s.id DESC"""
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

    def add_session(self, distance: str, unit: str, protocol_key: str | None = "__legacy__",
                    target_attempts: int | None = None, surface_type: str | None = None,
                    timing_method: str | None = None, environment: str | None = None,
                    protocol_notes: str | None = None) -> int:
        if unit not in {"yards", "meters"}:
            raise ValueError("Unit must be yards or meters.")
        with self.connect() as connection:
            return self._insert_session(connection, distance, unit, date.today().isoformat(), protocol_key,
                                        target_attempts, surface_type, timing_method, environment, protocol_notes)

    def add_group_session(self, group_id: int, distance: str, unit: str, protocol_key: str | None = "__legacy__",
                          target_attempts: int | None = None, surface_type: str | None = None,
                          timing_method: str | None = None, environment: str | None = None,
                          protocol_notes: str | None = None) -> int:
        if unit not in {"yards", "meters"}:
            raise ValueError("Unit must be yards or meters.")
        with self.connect() as connection:
            if not connection.execute("SELECT 1 FROM training_groups WHERE id=?", (group_id,)).fetchone():
                raise LookupError("Training Group not found.")
            session_id = self._insert_session(
                connection, distance, unit, date.today().isoformat(), protocol_key, target_attempts,
                surface_type, timing_method, environment, protocol_notes
            )
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

    @staticmethod
    def _insert_session(connection, distance, unit, session_date, protocol_key, target_attempts,
                        surface_type, timing_method, environment, protocol_notes):
        if target_attempts is not None and target_attempts not in {2, 4}:
            raise ValueError("Typical attempt count must be 2 or 4.")
        if protocol_key == "__legacy__":
            protocol_key = FLYING_10_PROTOCOL["protocol_key"] if (distance, unit) == ("10", "yards") else None
        metadata = FLYING_10_PROTOCOL if protocol_key == FLYING_10_PROTOCOL["protocol_key"] else None
        if protocol_key and metadata is None:
            raise ValueError("Choose a recognized sprint protocol.")
        if metadata and (distance != "10" or unit != "yards"):
            raise ValueError("The 10-yard fly protocol has a 10-yard timed distance.")
        surface_type = validated_choice(surface_type, "Surface type", {"turf", "track", "court", "grass", "other"})
        timing_method = validated_choice(timing_method, "Timing method", {"timing-gates", "laser", "video", "hand-timed", "other"})
        environment = validated_choice(environment, "Environment", {"indoor", "outdoor"})
        protocol_notes = (protocol_notes or "").strip() or None
        if protocol_notes and len(protocol_notes) > 1000:
            raise ValueError("Protocol notes must be 1,000 characters or fewer.")
        fields = tuple(metadata.values()) if metadata else (None,) * len(FLYING_10_PROTOCOL)
        cursor = connection.execute(
            """INSERT INTO sprint_capture_sessions(
                   distance,unit,session_date,protocol_key,protocol_name,protocol_alias,total_distance,
                   timed_distance,run_in_distance,protocol_unit,timed_segment,start_type,purpose,target_attempts,
                   surface_type,timing_method,environment,protocol_notes
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (distance, unit, session_date, *fields, target_attempts, surface_type, timing_method,
             environment, protocol_notes),
        )
        session_id = cursor.lastrowid
        if metadata is None:
            connection.execute(
                """UPDATE sprint_capture_sessions
                   SET protocol_key=?, protocol_name='Unspecified protocol'
                   WHERE id=?""",
                (f"unspecified-session:{session_id}", session_id),
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

    def add_session_athlete(self, session_id: int, name: str) -> int:
        """Add a new athlete to an open group session and its persistent roster."""
        name = normalized_name(name, "Athlete")
        with self.connect() as connection:
            session = connection.execute(
                "SELECT status FROM sprint_capture_sessions WHERE id=?", (session_id,)
            ).fetchone()
            if not session:
                raise LookupError("Session not found.")
            if session["status"] != "open":
                raise ValueError("Completed sessions cannot accept new athletes.")
            group = connection.execute(
                "SELECT group_id FROM training_group_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if not group:
                raise ValueError("Add athletes to standalone sessions from the home page.")
            athlete_id = connection.execute("INSERT INTO athletes(name) VALUES (?)", (name,)).lastrowid
            group_position = connection.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM training_group_members WHERE group_id=?",
                (group["group_id"],),
            ).fetchone()[0]
            session_position = connection.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM session_roster_members WHERE session_id=?",
                (session_id,),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO training_group_members(group_id, athlete_id, position) VALUES (?, ?, ?)",
                (group["group_id"], athlete_id, group_position),
            )
            connection.execute(
                "INSERT INTO session_roster_members(session_id, athlete_id, position) VALUES (?, ?, ?)",
                (session_id, athlete_id, session_position),
            )
            return athlete_id

    def complete_session(self, session_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                """UPDATE sprint_capture_sessions
                   SET status='completed', completed_at=COALESCE(completed_at, CURRENT_TIMESTAMP)
                   WHERE id=? AND status='open'""",
                (session_id,),
            )
            if cursor.rowcount:
                return
            session = connection.execute(
                "SELECT status FROM sprint_capture_sessions WHERE id=?", (session_id,)
            ).fetchone()
            if not session:
                raise LookupError("Session not found.")
            raise ValueError("Session is already completed.")

    def delete_session(self, session_id: int) -> int | None:
        """Permanently delete a session and its attempts, returning its group id."""
        with self.connect() as connection:
            session = connection.execute(
                "SELECT 1 FROM sprint_capture_sessions WHERE id=?", (session_id,)
            ).fetchone()
            if not session:
                raise LookupError("Session not found.")
            group = connection.execute(
                "SELECT group_id FROM training_group_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            connection.execute(
                """DELETE FROM imported_results
                   WHERE attempt_id IN (SELECT id FROM sprint_attempts WHERE session_id=?)""",
                (session_id,),
            )
            connection.execute("DELETE FROM sprint_capture_sessions WHERE id=?", (session_id,))
            return group["group_id"] if group else None

    def add_attempt(
        self, session_id: int, athlete_id: int, elapsed_ms: int, request_key: str | None = None,
    ) -> int:
        if request_key is not None and (not request_key.strip() or len(request_key) > 100):
            raise ValueError("Invalid attempt request identifier.")
        with self.connect() as connection:
            if request_key:
                existing = connection.execute(
                    "SELECT id,session_id,athlete_id,elapsed_ms FROM sprint_attempts WHERE request_key=?",
                    (request_key,),
                ).fetchone()
                if existing:
                    if (existing["session_id"], existing["athlete_id"], existing["elapsed_ms"]) != (
                        session_id, athlete_id, elapsed_ms,
                    ):
                        raise ValueError("Attempt request identifier conflicts with another save.")
                    return existing["id"]
            session = connection.execute(
                "SELECT status FROM sprint_capture_sessions WHERE id=?", (session_id,)
            ).fetchone()
            if not session:
                raise LookupError("Session not found.")
            if session["status"] != "open":
                raise ValueError("This session is completed and cannot accept new attempts.")
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
            if request_key:
                cursor = connection.execute(
                    "INSERT INTO sprint_attempts(session_id,athlete_id,elapsed_ms,request_key) VALUES (?,?,?,?) ON CONFLICT(request_key) DO NOTHING",
                    (session_id, athlete_id, elapsed_ms, request_key),
                )
                if cursor.rowcount:
                    return cursor.lastrowid
                existing = connection.execute(
                    "SELECT id,session_id,athlete_id,elapsed_ms FROM sprint_attempts WHERE request_key=?",
                    (request_key,),
                ).fetchone()
                if existing and (existing["session_id"], existing["athlete_id"], existing["elapsed_ms"]) == (
                    session_id, athlete_id, elapsed_ms,
                ):
                    return existing["id"]
                raise ValueError("Attempt request identifier conflicts with another save.")
            return connection.execute(
                "INSERT INTO sprint_attempts(session_id, athlete_id, elapsed_ms) VALUES (?, ?, ?)",
                (session_id, athlete_id, elapsed_ms),
            ).lastrowid

    def update_attempt(self, attempt_id: int, elapsed_ms: int) -> tuple[int, int]:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT attempts.session_id, attempts.athlete_id, sessions.status
                   FROM sprint_attempts attempts
                   JOIN sprint_capture_sessions sessions ON sessions.id=attempts.session_id
                   WHERE attempts.id=?""",
                (attempt_id,),
            ).fetchone()
            if not row:
                raise LookupError("Attempt not found.")
            if row["status"] != "open":
                raise ValueError("Attempts in a completed session cannot be edited.")
            connection.execute(
                "UPDATE sprint_attempts SET elapsed_ms=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (elapsed_ms, attempt_id),
            )
            return row["session_id"], row["athlete_id"]

    def delete_attempt(self, attempt_id: int) -> tuple[int, int]:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT attempts.session_id, attempts.athlete_id, sessions.status
                   FROM sprint_attempts attempts
                   JOIN sprint_capture_sessions sessions ON sessions.id=attempts.session_id
                   WHERE attempts.id=?""",
                (attempt_id,),
            ).fetchone()
            if not row:
                raise LookupError("Attempt not found.")
            if row["status"] != "open":
                raise ValueError("Attempts in a completed session cannot be deleted.")
            connection.execute("DELETE FROM sprint_attempts WHERE id=?", (attempt_id,))
            return row["session_id"], row["athlete_id"]

    def all_attempts(self) -> list[dict]:
        with self.connect() as connection:
            query = """SELECT a.*, s.distance, s.unit, s.session_date, s.protocol_key,
                              s.surface_type, s.timing_method, s.environment,
                              s.created_at AS session_created_at,
                              athletes.name AS athlete_name
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
                               s.protocol_key, s.protocol_name, s.protocol_alias, s.total_distance,
                               s.timed_distance, s.run_in_distance, s.protocol_unit, s.timed_segment,
                               s.start_type, s.purpose, s.target_attempts, s.surface_type,
                               s.timing_method, s.environment, s.protocol_notes,
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


def validated_choice(value: str | None, label: str, choices: set[str]) -> str | None:
    value = (value or "").strip() or None
    if value is not None and value not in choices:
        raise ValueError(f"Choose a valid {label.lower()}.")
    return value
