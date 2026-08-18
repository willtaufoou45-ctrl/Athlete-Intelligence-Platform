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

FEAT-001.3 improves the live workflow with late-athlete entry for active group
sessions, a visible next-three runner queue, automatic time saving, explicit
session completion, group/date session labels, and confirmed session deletion.
Completed sessions are read-only; deletion permanently removes that session and
its attempts while preserving the Training Group roster. The compact mobile
capture view prioritizes the athlete, time entry, next runners, current-session
attempts, all-time comparable best, and most recent prior comparable session;
export and lifecycle controls remain at the bottom of the page.

FEAT-004 adds reviewed historical sprint import for Summit-style wide CSV files.
Coaches choose an exact Training Group, distance, and unit; preview detected
dates, skipped columns, identity resolutions, invalid values, duplicates, and
session conflicts without database writes; then explicitly confirm one atomic
import. Imported attempts retain source provenance and continue to use the
existing chronological baseline/PR calculation semantics.

FEAT-005 defines and begins the hosted-mobile architecture. Local development
continues to use SQLite by default. Hosted mode accepts a PostgreSQL
`DATABASE_URL`, requires a coach credential and signed session secret, runs
behind HTTPS, and protects state-changing requests against CSRF. Deployment and
real-data migration remain explicit operator actions; see the
[Hosted Sprint Capture Operations](docs/operations/HOSTED_OPERATIONS.md) runbook.

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

## Hosted configuration

The dependency and Render pilot definitions are in `pyproject.toml` and
`render.yaml`. Copy variable names from `.env.example`, but keep all real values
in untracked local configuration or the hosting provider's secret store.

Generate the coach password hash interactively:

```bash
python3 -m scripts.hash_coach_password
```

Do not deploy or migrate athlete data until the approvals and verification
gates in the FEAT-005 specification and hosted operations runbook are complete.

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
