#!/usr/bin/env python3
"""Idempotently migrate one verified AIP SQLite backup to PostgreSQL."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from aip.database import Database
from aip.domain import classify_attempts


TABLES = (
    "athletes", "training_groups", "training_group_members",
    "sprint_capture_sessions", "training_group_sessions",
    "session_roster_snapshots", "session_roster_members", "sprint_attempts",
    "prototype_feedback", "import_batches", "imported_results",
    "canonical_athletes", "athlete_external_identities", "athlete_states",
    "intelligence_records", "evidence", "intelligence_evidence_links",
)
SERIAL_TABLES = {
    "athletes", "training_groups", "sprint_capture_sessions", "sprint_attempts",
    "prototype_feedback", "import_batches", "imported_results",
}
ORDER_BY = {
    "training_group_members": "group_id,position,athlete_id",
    "training_group_sessions": "group_id,session_id",
    "session_roster_snapshots": "session_id",
    "session_roster_members": "session_id,position,athlete_id",
    "athlete_external_identities": "id",
    "athlete_states": "id",
    "intelligence_records": "id",
    "evidence": "id",
    "intelligence_evidence_links": "intelligence_record_id,evidence_id",
}


def source_manifest(path: Path) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
        if integrity != "ok" or foreign_keys:
            raise ValueError("Source SQLite backup failed integrity or foreign-key checks.")
        tables = {}
        existing = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        for table in TABLES:
            if table not in existing:
                raise ValueError(f"Source backup is missing required table {table}.")
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
            rows = [dict(row) for row in connection.execute(
                f'SELECT * FROM "{table}" ORDER BY {ORDER_BY.get(table, "id")}'
            )]
            tables[table] = {"count": len(rows), "columns": columns, "sha256": rows_digest(rows)}
        return {
            "source_sha256": digest, "size_bytes": path.stat().st_size, "tables": tables,
            "derived": pr_manifest(connection),
        }
    finally:
        connection.close()


def migrate(source_path: Path, target_url: str) -> dict:
    manifest = source_manifest(source_path)
    migration_key = f"sqlite:{manifest['source_sha256']}:full-v1"
    source = sqlite3.connect(f"file:{source_path}?mode=ro&immutable=1", uri=True)
    source.row_factory = sqlite3.Row
    target = Database(target_url)
    if not target.is_postgres:
        raise ValueError("Target must be a PostgreSQL URL.")
    target.initialize()
    try:
        with target.connect() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(?))", ("aip-full-migration-v1",))
            existing = connection.execute(
                "SELECT status FROM data_migrations WHERE migration_key=?", (migration_key,)
            ).fetchone()
            if existing:
                raise ValueError(f"Migration {migration_key} is already {existing['status']}.")
            occupied = {
                table: connection.execute(f'SELECT COUNT(*) AS count FROM "{table}"').fetchone()["count"]
                for table in TABLES
            }
            if any(occupied.values()):
                raise ValueError("Target contains domain records; migration requires an empty target.")
            connection.execute(
                """INSERT INTO data_migrations(migration_key,source_sha256,source_manifest,status)
                   VALUES (?,?,?,'running')""",
                (migration_key, manifest["source_sha256"], json.dumps(manifest, sort_keys=True)),
            )
            for table in TABLES:
                columns = [row[1] for row in source.execute(f'PRAGMA table_info("{table}")')]
                names = ",".join(f'"{name}"' for name in columns)
                placeholders = ",".join("?" for _ in columns)
                for row in source.execute(f'SELECT {names} FROM "{table}" ORDER BY rowid'):
                    connection.execute(
                        f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})', tuple(row)
                    )
            for table in SERIAL_TABLES:
                maximum = connection.execute(f'SELECT MAX(id) AS maximum FROM "{table}"').fetchone()["maximum"]
                if maximum is not None:
                    connection.execute(
                        "SELECT setval(pg_get_serial_sequence(?, 'id'), ?, true)", (table, maximum)
                    )
            verify_target(connection, manifest)
            connection.execute(
                """UPDATE data_migrations SET status='complete',completed_at=CURRENT_TIMESTAMP
                   WHERE migration_key=?""", (migration_key,)
            )
        return {"migration_key": migration_key, "manifest": manifest}
    finally:
        source.close()


def verify_target(connection, manifest: dict) -> None:
    for table, expected in manifest["tables"].items():
        names = ",".join(f'"{name}"' for name in expected["columns"])
        rows = [dict(row) for row in connection.execute(
            f'SELECT {names} FROM "{table}" ORDER BY {ORDER_BY.get(table, "id")}'
        )]
        if len(rows) != expected["count"] or rows_digest(rows) != expected["sha256"]:
            raise ValueError(f"Row reconciliation failed for {table}.")
    if pr_manifest(connection) != manifest["derived"]:
        raise ValueError("Derived baseline/PR reconciliation failed.")


def rows_digest(rows: list[dict]) -> str:
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def pr_manifest(connection) -> dict:
    attempts = [dict(row) for row in connection.execute(
        """SELECT a.*,s.distance,s.unit,s.protocol_key,s.surface_type,s.timing_method
           FROM sprint_attempts a
           JOIN sprint_capture_sessions s ON s.id=a.session_id
           ORDER BY a.captured_at,a.id"""
    )]
    classified = [
        {"id": item["id"], "status": item["status"]}
        for item in classify_attempts(attempts)
    ]
    return {"count": len(classified), "sha256": rows_digest(classified)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Verified, stopped SQLite backup")
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()
    if not args.source.is_file():
        raise SystemExit("Source backup does not exist.")
    if args.manifest_only:
        print(json.dumps(source_manifest(args.source), indent=2, sort_keys=True))
        return
    target_url = os.environ.get("MIGRATION_DATABASE_URL")
    if not target_url:
        raise SystemExit("Set MIGRATION_DATABASE_URL to a direct PostgreSQL connection URL.")
    result = migrate(args.source, target_url)
    counts = {table: item["count"] for table, item in result["manifest"]["tables"].items()}
    print(json.dumps({"migration_key": result["migration_key"], "counts": counts}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
