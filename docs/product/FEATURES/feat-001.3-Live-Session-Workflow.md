# FEAT-001.3 — Live Session Workflow

## Status

Implemented locally. Awaiting field validation.

## Purpose

Reduce the remaining interruptions observed immediately before and during live
sprint timing.

## Validated Problems

- An unexpected athlete may arrive after a group session has started.
- The coach needs to see who is approaching the timing line, not only the
  currently selected athlete.
- Requiring a separate Save tap adds work to every recorded attempt.
- An undifferentiated list of resumable sessions becomes difficult to navigate.
- Sessions need an explicit end state and a deliberate removal path.

## Implemented Behavior

### Add a late athlete

- An athlete can be created from an active Training Group session.
- The athlete is appended to the active session roster snapshot.
- The athlete is also appended to the persistent Training Group roster for
  future sessions.
- Earlier sessions are not changed.
- Completed sessions cannot accept roster changes.

### Upcoming runners

- The capture screen shows the next three athletes in training order.
- The queue wraps through the roster for repeated trials.
- The coach can still move backward, forward, or jump out of order.

### Compact mobile capture

- The active athlete and time field appear at the top of the capture workflow.
- The next three athletes, current-session attempts, all-time comparable best,
  and most recent prior comparable session best remain together in the primary
  capture card.
- Historical reference values match the exact athlete, distance, and unit and
  do not mix historical attempts into the current-session attempt list.
- Jump-to-athlete and late-athlete controls remain available as collapsed
  secondary actions.
- Export, completion, and permanent deletion appear after the live capture
  workflow at the bottom of the page.

### Automatic save

- A complete decimal time saves after a short typing pause.
- Pressing Enter saves immediately as a fallback.
- The field clears only after the server confirms the attempt.
- Validation errors remain visible and do not create an attempt.

### Session lifecycle

- New sessions start with `open` status.
- Completing a session records completion and closes roster and attempt
  mutation.
- Open sessions appear separately from completed session history.
- Session labels contain Training Group, session date, distance, and unit.
- A session may be permanently deleted after a confirmation warning. Deletion
  removes its attempts and snapshot but preserves the Training Group roster.

## Data Integrity

An active session snapshot is stable except for explicit late-athlete additions.
Once completed, the snapshot and attempts are closed. Adding an athlete to an
active session never changes earlier session snapshots.

## Explicit Exclusions

- Removing or reordering athletes inside an active session
- Reopening completed sessions
- Soft deletion or undo
- User permissions or approval roles
- Automated lane assignment
- Voice or timing-gate capture
- Calendar-week aggregation; "previous" means the most recent earlier
  comparable session and its actual date is displayed

## Related

- [FEAT-001 — Manual Sprint Capture](feat-001-Manual%20Sprint%20Capture.md)
- [FEAT-001.1 — Workflow Friction Improvements](feat-001.1-Workflow-Friction-Improvements.md)
- [FEAT-001 field review](../FEATURE_REVIEWS/FEAT-001-Review.md)
- [PD-007 — Active sessions may accept explicit roster changes](../PRODUCT_DECISIONS.md#pd-007--active-sessions-may-accept-explicit-roster-changes)
