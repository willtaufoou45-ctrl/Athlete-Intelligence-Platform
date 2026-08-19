# WI-005 — Data Capture

## Observation

Coaches need to record current results quickly while retaining enough historical
context to interpret performance during the session.

## Evidence

Recording sprint data while coaching was identified as a workflow bottleneck.
Initial field testing showed that the active-session attempt list alone did not
visibly reference previous comparable performance, even though historical
attempts were used internally for PR classification. The live screen now keeps
those current attempts separate while showing the all-time comparable best and
the most recent earlier comparable session best and date.

Coaches also have substantial historical results in wide spreadsheets. The
validated Summit Football `10 yd` sheet organizes athletes in rows and testing
dates in columns. Without a safe import, coaches must re-enter those results or
accept incomplete personal-best and trend context.

Field capture also depends on delivery reliability. A phone-to-laptop local
network connection failed during use and prevented a second sprint session from
being recorded in AIP. Requiring the coach to run Terminal and keep a laptop
reachable is an operational dependency that competes with coaching attention.

## Why It Matters

Capturing a number is not sufficient if the coach cannot quickly understand
whether it reflects improvement, decline, consistency, or a new record.

## Product Implications

Keep active-session attempts separate from a compact historical reference.
Comparable results must match the athlete, exact distance, and exact unit.
On the live screen, prioritize the active athlete, time entry, next runners,
current attempts, and compact historical reference over session-management
actions.

Provide a preview-first historical import that converts populated athlete/date
cells into normal persisted sprint attempts. Exact identity resolution,
duplicate protection, source provenance, and atomic confirmation are required
because incorrect history would undermine trust in every derived insight.

Provide one permanent authenticated HTTPS address backed by hosted persistence
so the phone does not depend on the coach's laptop or local network. Hosted mode
still requires internet and must clearly distinguish a server-confirmed save
from an unconfirmed network failure. Offline capture and later synchronization
are separate future workflow intelligence and are not implied by hosted access.

## Related Product Decisions

- [PD-004 — Separate Current Results from Historical Context](../product/PRODUCT_DECISIONS.md#pd-004--separate-current-results-from-historical-context)
- [PD-006 — Historical imports require explicit identity resolution](../product/PRODUCT_DECISIONS.md#pd-006--historical-imports-require-explicit-identity-resolution)
- [PD-008 — Hosted capture preserves the validated workflow and requires internet](../product/PRODUCT_DECISIONS.md#pd-008--hosted-capture-preserves-the-validated-workflow-and-requires-internet)

## Related Features

- [FEAT-001 — Manual Sprint Capture](../product/FEATURES/feat-001-Manual%20Sprint%20Capture.md)
- [FEAT-001 V2 — Historical Performance Context](../product/FEATURE_BACKLOG.md#historical-performance-context)
- [FEAT-004 — Historical Sprint Import](../product/FEATURES/feat-004-Historical-Sprint-Import.md)
- [FEAT-005 — Hosted Mobile Sprint Capture](../product/FEATURES/feat-005-Hosted-Mobile-Sprint-Capture.md)
