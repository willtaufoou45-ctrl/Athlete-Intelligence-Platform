# FEAT-004 — Historical Sprint Import

## Status

Implemented locally. Awaiting review; not yet committed.

## Purpose

Bring validated historical sprint results into AIP safely so coaches can answer
questions such as "What was my best?" without re-entering years of existing
data or compromising athlete identity and PR history.

The validated reference is the Summit Football `10 yd` spreadsheet. In that
wide format, athletes occupy rows, testing dates occupy columns, and populated
intersections contain sprint times.

## Validated Reference Shape

- Row 2 contains `First Name`, `Last Name`, summary/non-session columns, and
  testing dates.
- Athlete data begins below the header.
- First and last names are stored separately and may contain extra whitespace.
- The `FASTEST` column is calculated and must not be imported as an attempt.
- Non-session columns such as `initial 10` or `Qtr Rev` are not attempts unless
  the coach explicitly maps them to a dated session.
- Blank athlete/date intersections contain no result.
- A populated date cell represents one historical result for that athlete on
  that date.

## V1 Workflow

1. Coach chooses a Training Group, exact distance, and exact unit.
2. Coach uploads a CSV exported from the historical spreadsheet.
3. AIP detects the header row, athlete-name columns, and candidate date columns.
4. If date headers omit a year, the coach supplies the year; AIP does not infer
   it silently.
5. AIP parses the file without changing persisted sprint data.
6. AIP shows a preview containing:
   - detected and skipped columns;
   - exact athlete matches;
   - unmatched and ambiguous names;
   - invalid dates and times;
   - possible duplicate results and existing-session conflicts;
   - sessions, athletes, and attempts that confirmation would create.
7. The coach explicitly resolves every unmatched or ambiguous athlete by
   selecting an existing athlete, intentionally creating a new athlete, or
   excluding the row.
8. The coach confirms the reviewed import.
9. AIP persists the entire confirmed import atomically and reports created,
   skipped, and rejected records.

## Data Mapping

| Source | AIP value |
|---|---|
| First Name + Last Name | Candidate athlete display name |
| Date-column header | Historical session date |
| Selected import distance | `SprintCaptureSession.distance` |
| Selected import unit | `SprintCaptureSession.unit` |
| Populated athlete/date cell | `SprintAttempt.elapsed_ms` |
| Selected Training Group | Group/session association |
| Athlete order in the file | Preview order and imported session-roster order |

Times use the existing decimal-seconds parser and are stored as integer
milliseconds. Distance and unit use the existing normalization and exact
comparison semantics.

## Header and Date Detection

- Scan a bounded preview for a row containing recognizable first-name and
  last-name headers.
- Require the coach to confirm the detected header row and name columns.
- Treat only parseable, coach-confirmed columns as testing dates.
- Support dates with an explicit year.
- Support month/day headers only after the coach explicitly supplies a year.
- Never interpret summary labels, formulas, or calculated best values as dates.
- Report duplicate date columns rather than silently combining them.

## Athlete Identity Rules

For matching only, normalize a candidate name by:

1. trimming leading and trailing whitespace from each name part;
2. collapsing internal whitespace;
3. joining non-empty first and last name parts with one space; and
4. applying Unicode case-insensitive comparison.

The stored display name is not automatically rewritten beyond the repository's
existing whitespace normalization.

- Search for exact normalized matches within the selected Training Group.
- One exact match is matched automatically.
- No exact matches is unmatched and requires explicit review.
- More than one exact match is ambiguous and requires explicit review.
- Do not use fuzzy, nickname, phonetic, or edit-distance matching in V1.
- Do not silently create or merge athletes.
- Creating a new athlete or choosing an athlete outside the current group must
  be an explicit confirmation action that also states the roster effect.

## Validation

- A row without a usable athlete name is invalid.
- A populated result must pass the existing seconds-to-milliseconds rules.
- Blank cells are skipped, not rejected.
- Formulas, summary values, text notes, and non-finite or out-of-range times are
  reported and excluded from confirmation.
- Distance and unit are required import-level inputs and are not inferred from
  a filename or tab name.
- Every unresolved identity, date, invalid value, or existing-session conflict
  must be resolved or explicitly excluded before confirmation.

## Duplicate Protection

V1 uses two layers:

1. Record a SHA-256 digest of the uploaded bytes to detect an identical file
   submitted again for the same Training Group, distance, and unit.
2. Record provenance for every imported result and compare the normalized
   athlete resolution, exact date, distance, unit, source position, and elapsed
   milliseconds before confirmation.

An identical upload is blocked. A changed upload receives a new preview but
results matching existing import provenance are marked as duplicates and are
not inserted again. Existing non-imported sessions or attempts on the same date
are conflicts requiring explicit review; AIP must not silently append to them
or assume that an equal time is a duplicate.

## Persistence Approach

The implementation should add minimal import provenance rather than changing
the sprint-calculation model:

- An import-batch record stores the file digest, selected Training Group,
  distance, unit, original filename, confirmation timestamp, and summary.
- An imported-result provenance record links each created attempt to its batch,
  source row/column, source date, and stable duplicate fingerprint.
- One historical group session is created per confirmed testing date unless the
  preview explicitly resolves an existing-session conflict.
- Each created group session receives an immutable roster snapshot in the
  confirmed file order.
- Imported attempt `captured_at` values and session timestamps preserve
  chronological ordering for existing PR classification.
- Batch metadata, explicitly created athletes/group memberships, sessions,
  snapshots, attempts, and provenance are written in one SQLite transaction.
- Any failure rolls back the entire confirmed import.

Preview state may be held temporarily and must be revalidated against the
database at confirmation so roster or data changes cannot invalidate a prior
preview silently.

## Compatibility With Existing PR Semantics

Imported results become normal persisted sprint attempts. The existing
`classify_attempts` logic continues to derive `baseline`, `pr`, and standard
attempt status chronologically for the same athlete, exact distance, and exact
unit. Import must not store a mutable PR flag or import the spreadsheet's
calculated `FASTEST` value.

When results share a date and the source has no time of day, the importer must
apply one documented deterministic timestamp/order. The preview must disclose
that the source cannot establish intra-day ordering.

## Import Summary

After confirmation, show:

- import batch identifier;
- historical sessions created or explicitly reused;
- athletes matched and intentionally created;
- attempts created;
- duplicates skipped;
- rows/cells excluded by the coach; and
- warnings retained for audit.

## Implemented V1 Notes

- The import entry point is available from each Training Group page.
- Uploaded CSV bytes and preview state remain in process memory until confirmation;
  preview does not write athletes, memberships, sessions, attempts, batches, or
  provenance.
- Confirming the review reparses and revalidates the original uploaded bytes
  against current database state before opening one SQLite transaction.
- Date-only sessions and attempts use `12:00:00` local time on the source date.
  Source-row order is represented with deterministic microsecond offsets for
  same-day attempt ordering; the review page discloses that the CSV contains no
  actual time of day.
- Reusing an existing session is allowed only after an explicit conflict choice
  and only when its immutable roster already contains every resolved athlete.
- Invalid cells and non-date columns require an acknowledgement before
  confirmation. Duplicate date columns block confirmation and must be corrected
  in the source CSV.
- Import-batch warnings and per-attempt source provenance are retained for audit.

## Acceptance Criteria

- A Summit Football-style wide CSV can be uploaded and previewed without a
  database write.
- Calculated and non-date columns are not imported as attempts.
- Every result retains its athlete, exact session date, distance, unit, time,
  and source provenance.
- Unmatched and ambiguous athletes cannot be confirmed silently.
- Invalid values are reported with source row and column.
- Re-uploading an identical file cannot duplicate attempts.
- Confirmation is atomic and a failed import leaves no partial athletes,
  sessions, snapshots, attempts, or provenance.
- Imported attempts participate correctly in existing baseline and PR
  classification.
- Historical session roster snapshots remain stable after later group changes.

## Explicit Exclusions

- Dashboards, charts, rankings, or team analytics
- AI recommendations or fuzzy identity matching
- Direct Google Sheets synchronization
- Background or scheduled imports
- Importing strength, force-plate, payment, attendance, or other spreadsheet
  tabs
- Editing source spreadsheets
- Authentication, organizations, or production infrastructure

## Risks and Open Questions

- Month/day-only CSV headers lose the year displayed by the source workbook;
  explicit year selection is required.
- The reference sheet contains incomplete names, grade labels in name fields,
  inconsistent capitalization, and likely spelling variations. These must
  remain review items rather than automatic matches.
- The source records one value per athlete/date, so it cannot reconstruct
  multiple trials or their order within a session.
- A date may overlap an existing live AIP session. V1 needs an explicit
  conflict choice before reuse or separate-session creation.
- The product must choose a deterministic local timestamp for date-only results
  without implying that the source recorded a time of day.

## Focused Test Plan

- Detect the Summit-style two-row header and date columns.
- Skip `FASTEST`, `Qtr Rev`, formulas, and blank cells.
- Require a year for month/day-only headers.
- Normalize whitespace and case for matching without fuzzy matching.
- Exercise exact, unmatched, and duplicate-name ambiguity paths.
- Reject invalid dates and existing time values outside current bounds.
- Preview without writes and revalidate before confirmation.
- Block identical-file re-import and skip record-level import duplicates.
- Surface conflicts with existing non-imported sessions/attempts.
- Confirm multiple athletes and dates in one transaction.
- Roll back athletes, memberships, sessions, snapshots, attempts, and provenance
  after an injected failure.
- Preserve file order in historical session snapshots.
- Verify imported attempts affect baseline/PR results by athlete, exact
  distance, and exact unit only.
- Verify yards/meters and different distances remain isolated.

## Related

- [FEAT-001 — Manual Sprint Capture](feat-001-Manual%20Sprint%20Capture.md)
- [FEAT-001.2 — Sprint Data Export](feat-001.2-Sprint-Data-Export.md)
- [FEAT-003 — Roster Import & Group Management](../FEATURE_BACKLOG.md#feat-003--roster-import--group-management)
- [PD-006 — Historical imports require explicit identity resolution](../PRODUCT_DECISIONS.md#pd-006--historical-imports-require-explicit-identity-resolution)
- [WI-005 — Data Capture](../../workflow_intelligence/WI-005-Data-Capture.md)
