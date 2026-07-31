# Athlete Intelligence Platform

Athlete Intelligence Platform (AIP) is an early-stage coaching product focused
on turning objective athlete measurements into clear coaching decisions.

The repository contains product discovery and design documentation alongside
FEAT-001, a functional local prototype for manual sprint capture. Its canonical
specification is
[FEAT-001 — Manual Sprint Capture](docs/product/FEATURES/feat-001-Manual%20Sprint%20Capture.md).

See the [Documentation Index](docs/INDEX.md) for the canonical repository map
and current documentation gaps.

## Repository structure

- `docs/philosophy/` — product vision and principles.
- `docs/product/` — product workflows, backlog, and feature specifications.
- `docs/intelligence/` — decision and assessment concepts.
- `docs/research/` — field notes and product research.
- `docs/workflows/` — workflow placeholders as they are developed.
- `docs/case_studies/` — athlete case-study material.
- `aip/` — FEAT-001 application, measurement logic, and SQLite persistence.
- `tests/` — automated tests for measurement, persistence, and web behavior.
- `main.py` — local FEAT-001 application launcher.

## Current status

FEAT-001 is implemented as a single-coach local prototype. It is intended for
workflow validation, not production deployment.

FEAT-001.1 adds recurring Training Groups, persistent ordered rosters, automatic
roster reuse with an immutable roster snapshot for each new group session, and
previous/next athlete navigation with a searchable out-of-order fallback. These
improvements are implemented locally and awaiting field validation.

FEAT-001.2 adds CSV downloads for an individual sprint session or a Training
Group, with optional session-date filtering for group exports. Exported files
use the existing persisted sprint records and derived baseline/PR semantics.

The prototype also includes a local feedback form for recording workflow
friction, successful interactions, and desired features. Feedback is stored in
the same local SQLite database as athletes, Training Groups, sessions, and
sprint attempts, and can be reviewed chronologically from the app.

## Run the application

From the repository root:

```bash
python3 main.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser. Stop the
application by pressing `Control-C` in the terminal.

## Run the tests

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v
```

## Local data and backups

When the application is started from the repository root, SQLite data is stored
at:

```text
data/aip.sqlite3
```

The entire `data/` directory is excluded from Git. Local athlete, session, and
attempt records are therefore not included in commits or pushed to GitHub.

To create a manual backup, stop the application and copy the database file to a
safe location. This copy includes feedback records along with all other local
prototype data. For example:

```bash
cp data/aip.sqlite3 aip-backup.sqlite3
```

To reset all local prototype data, stop the application and delete
`data/aip.sqlite3`. A new empty database will be created the next time the
application starts.

**Warning:** Deleting `data/aip.sqlite3` permanently removes feedback records,
athletes, Training Groups, sessions, sprint attempts, and all other local
prototype data unless you previously copied the file to a backup location.
