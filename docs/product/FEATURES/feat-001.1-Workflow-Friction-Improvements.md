# FEAT-001.1 — Workflow Friction Improvements

## Status

Implemented locally. Awaiting field validation.

## Purpose

Reduce the major workflow interruptions discovered during initial FEAT-001
field testing so future testing can focus on deeper coaching insights.

## Implemented scope

### Persistent Training Groups

- A coach can create and reopen a recurring Training Group.
- A Training Group retains its roster and session history after restart.
- New sprint sessions can be started directly from the Training Group.

### Persistent Rosters

- Athletes added to a Training Group remain attached to that group.
- Roster order is persistent and follows athlete-entry order.
- Every new group session loads the existing ordered roster automatically.
- Creating a group session stores an immutable snapshot of its athlete IDs and
  order.
- Later group additions, removals, or reordering do not change earlier session
  rosters.
- Attempts in a group session are accepted only for athletes in that session's
  roster snapshot.

### Improved Athlete Flow

- The capture screen presents one active athlete at a time in training order.
- Previous and next controls move through the roster without scrolling.
- Keyboard shortcuts move forward or backward through the roster.
- A searchable name-or-number field allows out-of-order capture.
- Saving an attempt retains the active athlete, preserving FEAT-001 behavior.

## Data-model boundary

The existing `athletes`, `sprint_capture_sessions`, and `sprint_attempts` tables
and their measurement semantics are unchanged. FEAT-001.1 adds Training Group,
roster-membership, group-session association, and session-roster snapshot tables
around the existing sprint records.

Existing standalone FEAT-001 sessions remain supported.

## Legacy snapshot backfill

When an existing local database contains a Training Group session created before
session-roster snapshots were introduced, application initialization creates a
snapshot from that group's current roster and order.

- Backfill runs only when the session has no snapshot marker.
- An existing snapshot is never overwritten.
- The backfill preserves the current roster available at migration time; it
  cannot reconstruct historical membership or order that was never stored.
- New group sessions create the session, group association, snapshot marker,
  and ordered roster members in one transaction.

## Explicit exclusions

- Historical performance comparison
- Voice capture
- AI recommendations
- Roster import
- Persistent subgroups
- Multi-user or production infrastructure

## Deferred athlete identity handling

Adding an athlete through a Training Group currently creates a new `Athlete`
record. The prototype does not yet provide a way to attach an existing
standalone athlete record to a Training Group.

Re-entering the same person creates a distinct athlete ID and does not merge
their previous sprint history or PR calculations. Connecting existing athletes
to groups without duplicating identity is explicitly deferred from FEAT-001.1
and must be resolved before existing-data continuity becomes a requirement.

## Validation required

- Confirm previous/next navigation matches real running order.
- Confirm out-of-order capture is fast enough when athletes switch unexpectedly.
- Confirm persistent rosters materially reduce session setup time.
- Confirm the workflow remains usable with 20+ athletes and multiple trials.

## Related

- [FEAT-001 — Manual Sprint Capture](feat-001-Manual%20Sprint%20Capture.md)
- [FEAT-001 field review](../FEATURE_REVIEWS/FEAT-001-Review.md)
- [PD-001 — Organize live capture around athlete flow](../PRODUCT_DECISIONS.md#pd-001--organize-live-capture-around-athlete-flow)
- [PD-002 — Training Groups are Persistent](../PRODUCT_DECISIONS.md#pd-002--training-groups-are-persistent)
- [WI-001 — Athlete Flow](../../workflow_intelligence/WI-001-Athlete-Flow.md)
- [WI-003 — Session Setup](../../workflow_intelligence/WI-003-Session-Setup.md)
