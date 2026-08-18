# Hosted Sprint Capture Operations

## Scope

This runbook covers the FEAT-005 free pilot architecture: one Render web
service, one Neon PostgreSQL database, and one coach credential. It does not
authorize account creation, deployment, athlete-data upload, or cutover.

## Architecture

- Render terminates HTTPS and runs one Gunicorn worker with four threads.
- The single worker is required while historical-import previews remain in
  process memory.
- `DATABASE_URL` is the Neon pooled TLS URL used by normal web requests.
- `MIGRATION_DATABASE_URL` is a Neon direct TLS URL used only by the one-time
  migration command.
- SQLite remains the default for local development and automated tests.
- Hosted mode requires authentication and refuses to start if its username,
  password hash, or session secret is missing.

Neon free compute suspends when idle. AIP opens a new database transaction for
each repository operation rather than retaining an idle global connection. The
first request after suspension can be slower and should be tested before a
field session.

## Local hosted-mode verification

Install dependencies in an isolated environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Generate secrets without placing the plaintext password in shell history:

```bash
.venv/bin/python -m scripts.hash_coach_password
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Store the outputs in an untracked local environment file or export them through
the shell's secure secret mechanism. Do not commit `.env`, a database URL, a
password hash, or a session secret.

Required hosted variables:

- `DATABASE_URL`
- `AIP_HOSTED=true`
- `AIP_AUTH_ENABLED=true`
- `AIP_TRUST_PROXY=true`
- `AIP_COACH_USERNAME`
- `AIP_COACH_PASSWORD_HASH`
- `AIP_SESSION_SECRET` (at least 32 characters)

Start the production entrypoint locally with Gunicorn after configuration:

```bash
.venv/bin/gunicorn --workers 1 --threads 4 --bind 127.0.0.1:8000 aip.production:application
```

## Free-pilot provisioning checklist

Do not use identifiable athlete data during provisioning or initial network
tests.

1. Obtain owner and school/data-handling approval.
2. Create a Neon free project in the approved region.
3. Copy both pooled and direct TLS URLs into the appropriate secret stores.
4. Create the Render service from `render.yaml`.
5. Enter the pooled URL and coach credential values as Render secrets.
6. Confirm `/diagnostics/ping` returns only `pong` over HTTPS.
7. Sign in and complete the synthetic-data smoke test over a hotspot.
8. Repeat over school Wi-Fi. If filtered, request an allowlist for the exact
   Render/custom hostname on HTTPS port 443.
9. Confirm cold-start behavior after both services have been idle.

## Pre-session checklist for the free tier

1. Open the HTTPS URL at least two minutes before timing starts.
2. Sign in and load the intended Training Group.
3. Confirm the roster and last session are present.
4. Record and delete one approved synthetic test attempt, or use a dedicated
   synthetic Training Group.
5. Keep the entered time visible until the UI reports `Saved.`
6. If a save is not confirmed, do not assume it exists. Reload the athlete
   history before retrying to avoid a duplicate.

## SQLite migration preparation

Stop the local application before making the source backup:

```bash
sqlite3 data/aip.sqlite3 ".backup 'aip-migration-source.sqlite3'"
python3 -m scripts.migrate_sqlite_to_postgres --source aip-migration-source.sqlite3 --manifest-only
```

Store the backup and manifest securely. The manifest contains counts and
digests, not athlete names.

Run a real migration only against an empty target and only after explicit
cutover approval:

```bash
MIGRATION_DATABASE_URL='postgresql://direct-connection' \
  python3 -m scripts.migrate_sqlite_to_postgres --source aip-migration-source.sqlite3
```

The command:

- verifies SQLite integrity and foreign keys;
- hashes the complete source file;
- acquires a PostgreSQL transaction advisory lock;
- blocks a repeated source digest through `data_migrations.migration_key`;
- refuses a non-empty target;
- copies every sprint and Athlete Intelligence table in one transaction;
- preserves primary keys and resets PostgreSQL sequences;
- compares every table count and deterministic full-row digest before commit;
- recomputes and compares every attempt's baseline/PR classification digest.

Current implementation reconciliation proves counts, complete row content,
database constraints, and derived PR classifications. A selected cross-database
CSV export comparison and an isolated restore drill remain required before
real-data cutover.

## Backup and recovery limits

Neon Free provides only a short restore window. Before real data is approved:

- schedule encrypted logical backups to a separate approved location;
- document who can access those backups;
- restore one backup into an isolated database;
- run counts, relationships, PR, import, and export verification;
- record recovery time and the latest recoverable write.

Free Render and Neon are validation services, not an availability guarantee.
If either service is unavailable during a session, AIP V1 cannot capture
offline.

## Rollback

Before hosted field writes, disable the hosted service and return to the
unchanged local SQLite source if migration or verification fails.

After hosted field writes begin, never overwrite PostgreSQL with the old SQLite
file. Roll back application code while retaining PostgreSQL, or restore
PostgreSQL to a verified recovery point. Returning to SQLite requires a separate
export, reconciliation, and maintenance window.

## Incident evidence

Record timestamp, network, page/route, HTTP status, whether the UI displayed
`Saved.`, provider status, and a request/log correlation identifier when
available. Never copy athlete names, CSV contents, passwords, cookies, database
URLs, or form bodies into incident tickets.
