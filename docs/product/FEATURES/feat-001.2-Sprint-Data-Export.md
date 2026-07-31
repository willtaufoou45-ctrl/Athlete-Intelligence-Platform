# FEAT-001.2 — Sprint Data Export

## Status

Implemented locally. Awaiting field validation.

## Purpose

Prevent coaches from recording sprint data twice. AIP remains the source of
truth, with simple CSV export for Google Sheets, Excel, reporting, or sharing.

## V1 Scope

### Export options

- Current `SprintCaptureSession`
- Selected Training Group
- Optional inclusive start and end dates for Training Group exports, applied to
  the session creation date

### CSV columns

1. Athlete ID
2. Athlete name
3. Training Group
4. Session ID
5. Session label
6. Session date/time
7. Distance
8. Unit
9. Attempt number
10. Attempt time in seconds
11. Attempt time in milliseconds
12. Session best
13. Performance status
14. Capture timestamp

The session label is derived from the persisted distance and unit because the
prototype does not yet store a separate session name. Session best is the
athlete's fastest valid attempt in that session, expressed in seconds. Attempt
number is the athlete's chronological attempt number within that session. The
exported performance status uses `baseline`, `PR`, or `standard` and maps the
application's internal `attempt` classification to `standard` without changing
the underlying semantics.

## Requirements

- Export one row per valid persisted sprint attempt.
- Preserve the exact athlete, session, distance, and unit.
- Use existing persisted data; require no manual re-entry.
- Produce UTF-8 CSV that opens cleanly in Google Sheets and Excel.
- Respect historical session roster snapshots for Training Group exports.
- Derive baseline, PR, and standard status using existing sprint calculation
  semantics and the athlete's complete comparable history.
- Order rows deterministically by session date/time, session ID, session roster
  position when available, athlete name, capture timestamp, and attempt ID.
- Prefix text whose first non-whitespace character is `=`, `+`, `-`, or `@` to
  prevent spreadsheet formula execution. Numeric fields remain numeric.
- Use `aip-session-<session-id>-<YYYY-MM-DD>.csv` for session exports and
  `aip-group-<sanitized-group-name>-<YYYY-MM-DD>.csv` for group exports.
- Return a header-only CSV when the selected scope has no attempts.

## Explicit Exclusions

- Direct Google Sheets sync
- Excel-specific formatting
- PDF reports
- Automatic email
- Cloud storage integrations
- Scheduled exports
- Authentication or reporting dashboards

## Related

- [FEAT-001 — Manual Sprint Capture](feat-001-Manual%20Sprint%20Capture.md)
- [FEAT-001.1 — Workflow Friction Improvements](feat-001.1-Workflow-Friction-Improvements.md)
- [FEAT-001 field review](../FEATURE_REVIEWS/FEAT-001-Review.md)
- [PD-005 — AIP Is the Sprint Data Source of Truth](../PRODUCT_DECISIONS.md#pd-005--aip-is-the-sprint-data-source-of-truth)
