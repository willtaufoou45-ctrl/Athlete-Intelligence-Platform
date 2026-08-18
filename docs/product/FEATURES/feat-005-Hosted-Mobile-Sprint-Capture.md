# FEAT-005 — Hosted Mobile Sprint Capture

## Status

Architecture implementation started locally. PostgreSQL compatibility, hosted
configuration, single-coach authentication, CSRF/security controls, duplicate-
safe attempt retries, migration/reconciliation tooling, and free-pilot
deployment scaffolding are implemented but not deployed. Vendor-account,
real-data migration, backup-retention, and cutover approvals remain open.

## Validated Problem

AIP currently depends on `python3 main.py` running on the coach's laptop and on
the phone remaining connected to the laptop over a stable local network. During
field use, that connection was lost and the second sprint session could not be
captured in AIP.

## Goal

Provide one permanent HTTPS address that a coach can open directly on a phone,
without Terminal or the coach's laptop, while preserving the current mobile
capture workflow and all persisted sprint-history semantics.

## Mode Boundary

### Hosted mode — FEAT-005 V1

- Works without the laptop or Terminal.
- Uses a permanent HTTPS URL.
- Requires the phone to have internet access.
- Persists confirmed writes in a hosted database.

### Future offline mode — explicitly excluded from V1

- Captures attempts while the phone has no internet access.
- Queues and synchronizes those writes later.
- Requires conflict, identity, ordering, duplicate, deletion, and reconciliation
  rules that do not exist today.

V1 may improve ordinary network-failure handling by keeping an entered value on
screen, showing an explicit unsaved/error state, and allowing a deliberate retry.
It must not claim that an attempt is saved before the server confirms it. This is
not offline capture or synchronization.

## Current-System Assessment

### Application architecture

- `main.py` starts a threaded development WSGI server on `0.0.0.0:8000`.
- `aip/web.py` is a dependency-light, server-rendered WSGI application. Small
  JSON endpoints support attempt capture/edit/delete; HTML, CSS, and JavaScript
  are otherwise emitted by the same module.
- `aip/database.py` contains persistence and schema initialization.
- `aip/domain.py` owns time/distance normalization and chronological
  baseline/PR classification.
- `aip/importer.py` owns no-write CSV preview, revalidation, identity resolution,
  duplicate detection, and atomic confirmation.
- `aip/export.py` generates Excel-compatible UTF-8 CSV downloads and neutralizes
  spreadsheet-formula text.
- Historical import previews currently live only in one Python process's memory
  and are limited to 20 entries. A restart expires them; multiple web workers
  would not share them.
- There is no authentication, authorization, CSRF protection, production WSGI
  server, dependency manifest, deployment configuration, or schema-version
  migration framework.

### Local data location and inspected source

The default database is `data/aip.sqlite3`; `--database` can override it. The
entire `data/` directory is excluded from Git. Manual backup currently means
stopping the process and copying the SQLite file.

The inspected local database is approximately 264 KiB and contains both sprint
capture and Athlete Intelligence tables. At assessment time its sprint-domain
counts were:

| Entity | Count |
| --- | ---: |
| Athletes | 88 |
| Training Groups | 5 |
| Training Group memberships | 82 |
| Sprint sessions | 8 |
| Session roster snapshots | 8 |
| Session roster members | 196 |
| Sprint attempts | 167 |
| Prototype feedback | 0 |
| Import batches | 2 |
| Imported-result provenance rows | 0 |

These counts are assessment evidence, not hard-coded migration expectations.
The migration tool must calculate and save a fresh manifest from the exact
source backup selected for migration.

### SQLite schema and relationships

The sprint domain uses integer primary keys and foreign keys across athletes,
Training Groups, ordered memberships, sessions, group-session links, roster
snapshots, attempts, feedback, import batches, and imported-result provenance.
Deletion behaviors include cascade, restrict, and set-null relationships. The
same file also contains canonical-athlete, external-identity, state,
intelligence-record, evidence, and evidence-link tables; migration must preserve
these records too, even though FEAT-005 does not expand their UI.

Initialization executes idempotent `CREATE TABLE IF NOT EXISTS` statements,
adds lifecycle/intelligence columns when absent, and backfills a snapshot for
legacy group sessions once. PostgreSQL requires explicit versioned migrations;
SQLite startup mutation must not remain the production migration mechanism.

### Session and roster lifecycle

- A session has one distance, one unit, a session date, and `open` or
  `completed` status.
- Starting a group session atomically links it to the Training Group, creates a
  roster snapshot, and copies the persistent ordered roster into that snapshot.
- Later group changes do not alter an earlier snapshot.
- An explicit late-athlete addition to an open group session appends a newly
  created athlete to both the persistent roster and that active snapshot.
- Completed sessions reject roster additions and attempt creation/edit/delete.
- Confirmed session deletion removes the session, attempts, group link, and
  snapshot while preserving the Training Group roster. Imported-result links
  for its attempts are explicitly removed first.
- Standalone legacy sessions use the global athlete list and do not have a
  session roster snapshot; hosted migration must preserve that distinction.

### Attempts and existing PR semantics

- Times are stored as positive integer milliseconds.
- Baseline and PR are derived, never stored.
- History is comparable only for the same athlete, normalized distance, and
  exact unit.
- The first chronologically valid comparable attempt is `baseline`; a later
  attempt is a PR only when strictly faster than every earlier comparable
  attempt; an equal time is not a PR.
- Ordering uses `captured_at` and then attempt ID, so both values and their
  relative order must survive migration.
- Editing or deleting an open-session attempt recalculates derived status and
  session best.

### Historical imports, exports, feedback, and tests

- Historical CSV preview performs no sprint-data writes. Confirmation rebuilds
  the preview, requires explicit identity/conflict resolution, blocks identical
  batch scope by file digest, skips record duplicates by fingerprint, and writes
  the batch, athletes, memberships, sessions, snapshots, attempts, and provenance
  in one transaction.
- Preview payloads include uploaded athlete data and currently remain in process
  memory until confirmation, eviction, or restart. Hosted V1 should retain this
  short-lived behavior only with one web process, or move previews to protected,
  expiring server-side storage before multiple workers are allowed. They must
  never be logged.
- Session and Training Group CSV exports are read-only, preserve snapshot order,
  derive statuses, include a UTF-8 BOM, and neutralize formula-like text.
- Prototype feedback is stored in the same database with optional group/session
  context.
- Tests cover persistence, foreign-key behavior, roster snapshots, lifecycle,
  PR recalculation, import atomicity/idempotency/conflicts, export content and
  safety, mobile markup/workflow, validation, diagnostics, and request logging.
  They are SQLite-only and have no authentication or hosted-migration coverage.

## V1 Functional Scope

V1 must support:

- a stable provider URL and optional owned custom domain, both HTTPS-only;
- phone-first sign-in and the current phone-first capture page;
- one coach account with secure credential storage and logout;
- hosted PostgreSQL persistence;
- Training Groups and ordered persistent rosters;
- immutable session roster snapshots with current late-athlete semantics;
- open/completed sessions and current attempt edit/delete rules;
- existing baseline, PR, comparable-history, and session-best semantics;
- historical CSV preview and atomic import;
- session and Training Group sprint CSV export;
- prototype feedback capture and review behind authentication;
- automated database backups plus a documented, tested restore procedure;
- a one-time, idempotent migration of the complete selected `aip.sqlite3` file;
- a reconciliation report proving counts, keys, references, order, timestamps,
  nulls, and representative derived PR results survived migration.

## Quality and Security Requirements

- Enforce authentication on every application and JSON route except a minimal
  liveness endpoint that reveals no data.
- Use a slow password hash (scrypt, Argon2id, or the framework's current equivalent), a
  random secret supplied only through hosted secrets, `Secure`, `HttpOnly`, and
  `SameSite=Lax` session cookies, login throttling, and generic login errors.
- Protect every state-changing form and JSON request against CSRF.
- Redirect HTTP to HTTPS and set HSTS, a restrictive Content Security Policy,
  `X-Content-Type-Options: nosniff`, and a conservative referrer policy.
- Do not put athlete names, uploaded CSV content, database URLs, credentials, or
  form bodies in application logs. Retain useful request IDs, routes, status,
  duration, and response size.
- Limit upload size and accepted content as today; keep previews private and
  short-lived. One process is the safe initial constraint while previews are
  in memory.
- Run schema migration as an explicit release/pre-deploy step, not concurrently
  in every web worker.
- Use least-privilege database credentials and a private database connection
  where the selected provider supports it.
- The production server must have bounded request/body/time settings and a
  graceful restart path. The standard-library development server is excluded.
- A successful attempt response is the commit acknowledgement. On timeout or
  disconnect, show “not confirmed” and support safe coach reconciliation/retry;
  do not silently create a second write. Attempt creation uses a client-generated
  idempotency key so the same unconfirmed save can be retried safely.

## Deployment Approaches

Cost estimates are planning ranges as of 2026-08-17, excluding domain
registration, taxes, unusual egress, and staff time. Vendor pricing must be
rechecked at approval.

### Approach A — Preserve server-rendered Python; managed web service + PostgreSQL

Representative deployment: Render paid web service plus paid Render Postgres,
or an equivalent managed Python host and PostgreSQL service in one region.

**Required code changes**

- Keep routes, HTML/CSS/JavaScript, domain rules, imports, and exports.
- Introduce a small database adapter/repository boundary and port SQLite SQL to
  PostgreSQL: connection handling, `%s` parameters, returned IDs, date functions,
  transaction boundaries, schema DDL/checks, and metadata queries.
- Add versioned schema migrations and a production WSGI server such as Gunicorn.
- Add simple session authentication, CSRF protection, security headers, trusted
  proxy/HTTPS handling, secret configuration, login throttling, and auth tests.
- Make request logging privacy-safe. Retain a single web worker while import
  previews remain in memory, or persist expiring previews before scaling out.
- Add an idempotent SQLite-to-PostgreSQL migration/reconciliation command and
  deployment/operations documentation.

**Hosting and database services**

- One always-on managed Python web service with managed TLS and permanent
  provider hostname; optional custom domain.
- One paid managed PostgreSQL instance in the same region/private network.
- Provider PITR plus separately retained logical `pg_dump` backups.

**Authentication**

One provisioned coach username and scrypt password hash stored in the hosting
secret configuration, with signed, expiring application session cookies. No public signup,
password reset email, OAuth, roles, organizations, or athlete accounts in V1.
Credential provisioning/reset is an explicit operator command.

**Estimated recurring cost**

Approximately **$15–$30/month** at prototype traffic for the smallest paid web
and PostgreSQL resources with backups. Render's exact current flexible database
storage/compute price must be confirmed in its calculator; free instances are
not acceptable because of sleep/data-loss/backup limitations. A split option
such as a paid web host plus Neon Launch is commonly around **$20–$30/month**
at light intermittent load.

Render documents managed HTTPS for web services, paid PostgreSQL point-in-time
recovery, and the free-tier filesystem/backup limitations. See
[Render web services](https://render.com/docs/web-services),
[Render PostgreSQL backups](https://render.com/docs/postgresql-backups), and
[Render free-tier limitations](https://render.com/docs/free).

**Deployment complexity**

Moderate: one application service, one database, environment secrets, a release
migration, health check, DNS if a custom domain is chosen, and a restore drill.
The PostgreSQL port and safe data migration are the main engineering work.

**Data migration process**

Use the one-time process defined below. Never upload the live SQLite file to a
web endpoint or include it in the repository/container image.

**Backup and recovery**

Require paid PITR (minimum seven-day target if the selected plan permits), plus
encrypted logical backups exported to a second failure domain on a documented
schedule. Perform and record a restore drill before field cutover and at least
quarterly thereafter. Define recovery point and recovery time objectives.

**Security risks**

Public exposure introduces credential attacks, CSRF, session theft, uploaded
CSV privacy, secret leakage, vulnerable dependencies, and sensitive logs.
Single-factor shared credentials reduce attribution. Mitigate with the V1
security requirements, provider alerts, dependency patching, and short access
to the deployment/database consoles.

**Operational limitations**

Internet loss still stops capture. One process limits scale while previews are
in memory. A small non-HA database can experience maintenance downtime. There
is no self-service recovery or multi-coach permission model.

**Vendor lock-in**

Low to moderate. The app remains standard WSGI and data remains standard
PostgreSQL; provider configuration, private networking, TLS, and PITR are
provider-specific. `pg_dump` and documented environment variables preserve an
exit path.

**Current mobile workflow intact?**

Yes. Add a sign-in screen and explicit network/save status; otherwise preserve
the existing URLs and phone-first capture interaction.

### Approach B — Preserve the app and SQLite on a managed VM/container volume

Representative deployment: one Fly Machine or comparable service, one attached
persistent volume holding `aip.sqlite3`, managed HTTPS, and automated volume
snapshots.

**Why assess it**

This materially reduces the initial database-port and data-transform work. It
is a viable narrow pilot alternative, but it does not reduce long-term
operational risk enough to recommend for the durable V1.

**Required code changes**

- Keep the SQLite persistence layer and mount a fixed database path.
- Add the same production WSGI server, authentication, CSRF/security controls,
  privacy-safe logging, secrets, health checks, deployment configuration, and
  operator docs as Approach A.
- Add SQLite online-backup/integrity tooling and prevent more than one writer
  process/Machine from serving the database.

**Hosting and database services**

One always-on application Machine and one provider-local persistent volume;
there is no independent managed database service.

**Authentication**

The same single-coach application-owned password/session model as Approach A.

**Estimated recurring cost**

Approximately **$5–$12/month** for a small always-on Machine, volume, snapshots,
TLS, and light traffic; actual Machine size and regional pricing control the
total. Fly currently lists volumes at $0.15/GB-month, snapshot storage at
$0.08/GB-month with the first 10 GB free, and the first ten single-host TLS
certificates free. See [Fly resource pricing](https://fly.io/docs/about/pricing/).

**Deployment complexity**

Low-to-moderate for initial deployment, but higher operational responsibility:
volume placement, single-instance enforcement, SQLite backup consistency,
restore commands, integrity checks, and Machine/volume recovery remain ours.

**Data migration process**

After a verified local backup and maintenance window, copy the exact SQLite
file over an authenticated operator channel to a new empty volume, verify its
SHA-256 digest and `PRAGMA integrity_check`, then start the one production
instance. Record a migration ledger outside and inside the database. Do not use
an application upload route.

**Backup and recovery**

Use provider volume snapshots plus scheduled SQLite online backups copied to a
second failure domain. A volume snapshot alone is not a complete recovery plan.
Test restoration onto a new volume/Machine.

**Security risks**

The public-app risks match Approach A. In addition, anyone with Machine or
volume access can copy the whole database; backup copies multiply athlete-data
exposure. Encrypt transport and backup storage and minimize operator access.

**Operational limitations**

Single writer, single region, no horizontal scaling, a local volume tied to
placement, restore-oriented failover, and more manual recovery. A mistaken
multi-instance rollout can corrupt expectations or create split data. These
limitations conflict with “smallest safe permanent hosted version.”

**Vendor lock-in**

Low at the data/app layer because the artifact is a normal SQLite file; moderate
in deployment, volume, snapshot, and recovery automation.

**Current mobile workflow intact?**

Yes, with the same login and network-status additions.

## Recommendation

Choose **Approach A: preserve the current server-rendered Python application,
run one paid managed web service, and use paid managed PostgreSQL in the same
region**. Prefer a single provider initially (Render is the reference option)
to minimize networking, credentials, billing, and incident surfaces. Keep one
web process until import previews are moved from memory.

This is the smallest safe option because it changes the persistence and
security edges without rewriting the proven phone workflow or domain logic. A
frontend/API rewrite would duplicate behavior and introduce migration risk.
Hosted SQLite saves porting work but transfers database durability, failover,
and single-writer responsibility to the project, which is the wrong trade for a
permanent field-capture endpoint.

## Migration and Duplicate-Protection Plan

### Prepare

1. Select a short maintenance window; stop local AIP writes.
2. Create two offline copies using SQLite's backup API or CLI `.backup`, not a
   live filesystem copy. Record source absolute path, size, SHA-256, UTC time,
   SQLite version, schema SQL hash, `PRAGMA user_version`, and
   `PRAGMA integrity_check` result in a migration manifest.
3. Inventory every application table, row count, primary-key range, null count,
   foreign-key violations, ordered-membership count, and relationship count.
   Save representative derived PR/export fixtures without exposing athlete data
   in logs or documentation.

### Load

4. Apply reviewed PostgreSQL migrations to an empty database.
5. Acquire a PostgreSQL advisory lock. Insert a `data_migrations` row with a
   unique key such as `sqlite:<source_sha256>:full-v1`. A unique constraint makes
   a repeated execution stop before domain rows are inserted.
6. In one transaction, copy all tables in foreign-key order while preserving
   primary keys, timestamps, text, nulls, and explicit relationships. Include
   Athlete Intelligence tables. Reset every PostgreSQL identity sequence above
   the imported maximum.
7. Mark the ledger row complete only after reconciliation. Any exception rolls
   back the transaction; a failed ledger record may be kept separately from the
   domain transaction for diagnosis, but must not permit partial data.

### Verify

8. Compare source and target counts per table; primary-key sets or deterministic
   row digests; orphan queries for every foreign key; group and snapshot position
   uniqueness/order; group-session links; attempt athlete/session links; import
   batch/result links; feedback context; timestamps; statuses; and open/completed
   lifecycle fields.
9. Recompute baseline/PR and session-best classifications for every comparable
   attempt history on both databases and compare ordered results. Compare CSV
   export output from selected session/group fixtures after normalizing only
   database-specific timestamp formatting if necessary.
10. Exercise authenticated read-only smoke tests against the target. Produce a
    signed reconciliation report containing no athlete names.

### Cut over and roll back

11. Keep the local app read-only/off during cutover. Point the hosted service to
    the verified target, run a small scripted smoke test, then complete one
    explicit non-athlete test write/delete if approved.
12. Retain the immutable source backups and manifest. If reconciliation or
    smoke testing fails before hosted field writes, disable the hosted service,
    discard/recreate the target, and continue locally from the unchanged source.
13. After hosted field writes begin, do not copy the old SQLite file over the
    hosted database. Roll back application code while retaining PostgreSQL, or
    restore PostgreSQL to a verified point. Returning to SQLite would require a
    separately built and verified PostgreSQL-to-SQLite export and a new downtime
    window.

## Focused Test Plan

### Existing regression suite

- Run all current domain, database, import, export, intelligence, main, and web
  tests against SQLite throughout the port.
- Parameterize persistence contract tests and run the applicable suite against
  ephemeral PostgreSQL in CI.

### Authentication and web security

- Unauthenticated HTML/API/export/import/feedback requests redirect or return
  `401`; liveness remains data-free.
- Correct login/logout, slow hash verification, cookie flags, session expiry,
  secret rotation behavior, generic failures, and throttling.
- CSRF rejection for forms and JSON mutations; security headers and HTTPS proxy
  behavior; no secrets/athlete/form/upload data in logs.

### PostgreSQL behavior

- Transaction rollback, concurrent attempt creation, returned IDs, exact
  timestamp ordering, foreign-key actions, sequence reset, roster-position
  uniqueness, lifecycle closure, and snapshot immutability.
- Existing PR semantics across sessions, same timestamps, equal times, edits,
  deletes, imported history, distances, and units.

### Import/export and phone workflow

- Preview expiry/restart behavior under the one-process constraint; identical
  batch and fingerprint protection; stale preview revalidation; atomic failure.
- CSV headers, ordering, BOM, date ranges, formula neutralization, and read-only
  behavior.
- Real-phone checks for sign-in, group/session resume, athlete navigation,
  auto-save acknowledgement, retry after a simulated timeout, completion, and
  export over cellular and Wi-Fi.

### Migration and recovery

- Migrate a production-shaped redacted copy twice: first succeeds, second is
  blocked before writes.
- Inject a mid-load failure and prove zero partial domain rows.
- Compare all counts, key sets/digests, foreign keys, ordered rosters, derived
  PR classifications, and selected exports.
- Restore a backup into an isolated database and run reconciliation plus smoke
  tests; record measured recovery time and recovery point.

## Exact Files Expected to Change During Implementation

Existing files:

- `aip/database.py` — PostgreSQL-capable persistence and explicit transaction
  behavior, or a split repository extracted from it.
- `aip/web.py` — authentication, authorization boundary, CSRF, secure cookies,
  headers, proxy handling, privacy-safe logging, and network-save feedback.
- `aip/importer.py` — PostgreSQL SQL/transaction compatibility and preview
  storage boundary if more than one worker is required.
- `aip/intelligence.py` — PostgreSQL-compatible schema/query handling for the
  intelligence tables included in migration.
- `main.py` — environment-driven local/hosted configuration and removal of
  hard-coded network output from the production path.
- `README.md` — local development, configuration, deployment, backup, migration,
  recovery, and hosted-mode limitations.
- `tests/test_database.py`, `tests/test_web.py`, `tests/test_importer.py`,
  `tests/test_export.py`, `tests/test_intelligence.py`, and `tests/test_main.py` —
  PostgreSQL contracts, security, migration, and regression adjustments.

Expected new files (names may change only with an approved implementation
tooling decision):

- `pyproject.toml` — pinned runtime/test dependencies and Python requirement.
- `aip/config.py` — validated environment configuration.
- `aip/auth.py` — coach credential and session helpers.
- `aip/migrations/` — ordered PostgreSQL schema migrations.
- `scripts/migrate_sqlite_to_postgres.py` — locked, idempotent migration and
  reconciliation command.
- `tests/test_auth.py` and `tests/test_migration.py` — focused security and data
  migration coverage.
- `render.yaml` — reference single-provider infrastructure configuration if
  Render is approved.
- `.env.example` — names and safe examples only; never credentials.
- `docs/operations/HOSTED_OPERATIONS.md` — deploy, credential reset, backup,
  restore, monitoring, incident, migration, rollback, and data-handling runbook.

No feature implementation is expected in `aip/domain.py` or `aip/export.py`
unless tests expose a database/timestamp portability issue. This specification
and its linked decision/backlog/index records should be updated when approvals
or implementation facts change.

## Decisions Requiring Owner Approval

1. Approve PostgreSQL over hosted SQLite and approve the selected hosting and
   database vendor/region.
2. Approve a monthly budget ceiling and whether a provider hostname is adequate
   or an owned custom domain is required for V1.
3. Approve the single-coach password model, who receives the credential, and
   the operator-only reset process; decide whether individual coach accounts and
   audit attribution are required before field use.
4. Approve the backup policy, proposed RPO/RTO, retention outside the provider,
   and who performs quarterly restore drills.
5. Approve the migration source backup, maintenance window, reconciliation
   report, and irreversible hosted cutover point.
6. Confirm whether Athlete Intelligence tables in the current SQLite file may be
   hosted now. The safe default is to migrate them for completeness but keep
   their current internal routes authenticated and otherwise unchanged.
7. Accept that FEAT-005 V1 requires internet and does not guarantee capture
   during a cellular/Wi-Fi outage; decide whether field validation can proceed
   under that constraint.

## Recommended Implementation Sequence

1. Record the approvals above and set measurable RPO/RTO and cost ceilings.
2. Add dependency/configuration management and a production server while keeping
   local SQLite development working.
3. Add authentication, CSRF, security headers, privacy-safe logging, and their
   tests before exposing any hosted endpoint.
4. Introduce versioned PostgreSQL migrations and port the persistence contracts;
   run SQLite and PostgreSQL regression suites.
5. Build and dry-run the idempotent full-database migration/reconciliation tool
   against a redacted production-shaped copy.
6. Add deployment configuration and the operations runbook; provision only
   after a separate explicit approval.
7. Prove backup restore in isolation, then run authenticated phone workflow and
   network-failure tests with synthetic data.
8. Schedule the local write freeze, create immutable backups, migrate, reconcile,
   and request cutover approval.
9. Cut over, monitor the first field session, verify counts/backups immediately
   afterward, and keep the source backups unchanged.
10. Evaluate offline capture as a separate feature only after hosted V1 field
    reliability is measured.

## Success Criteria

- A coach can sign in at the same HTTPS URL from a phone and complete the current
  sprint workflow with no coach laptop or Terminal process running.
- Every confirmed write survives application restart and deployment.
- Existing rosters, snapshots, attempts, imports, exports, feedback, and derived
  PR results behave as before.
- Migration is duplicate-safe and its reconciliation report proves all selected
  records and relationships survived.
- A backup has been restored and verified before athlete data is cut over.
- Loss of internet is reported honestly as an unconfirmed save; no offline sync
  is implied or implemented.

## Related

- [FEAT-001 — Manual Sprint Capture](feat-001-Manual%20Sprint%20Capture.md)
- [FEAT-001.3 — Live Session Workflow](feat-001.3-Live-Session-Workflow.md)
- [FEAT-004 — Historical Sprint Import](feat-004-Historical-Sprint-Import.md)
- [FEAT-001 field review](../FEATURE_REVIEWS/FEAT-001-Review.md)
- [PD-008 — Hosted capture preserves the validated workflow and requires
  internet](../PRODUCT_DECISIONS.md#pd-008--hosted-capture-preserves-the-validated-workflow-and-requires-internet)
- [WI-005 — Data Capture](../../workflow_intelligence/WI-005-Data-Capture.md)
