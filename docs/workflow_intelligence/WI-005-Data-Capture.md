# WI-005 — Data Capture

## Observation

Coaches need to record current results quickly while retaining enough historical
context to interpret performance during the session.

## Evidence

Recording sprint data while coaching was identified as a workflow bottleneck.
The current FEAT-001 screen shows active-session attempts but does not visibly
reference previous comparable performance, even though historical attempts are
used internally for PR classification.

## Why It Matters

Capturing a number is not sufficient if the coach cannot quickly understand
whether it reflects improvement, decline, consistency, or a new record.

## Product Implications

Keep active-session attempts separate from a compact historical reference.
Comparable results must match the athlete, exact distance, and exact unit.

## Related Product Decisions

- [PD-004 — Separate Current Results from Historical Context](../product/PRODUCT_DECISIONS.md#pd-004--separate-current-results-from-historical-context)

## Related Features

- [FEAT-001 — Manual Sprint Capture](../product/FEATURES/feat-001-Manual%20Sprint%20Capture.md)
- [FEAT-001 V2 — Historical Performance Context](../product/FEATURE_BACKLOG.md#historical-performance-context)
