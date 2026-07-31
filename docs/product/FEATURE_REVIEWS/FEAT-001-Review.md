# FEAT-001 Review

## Hypothesis

What did we expect?

## What actually happened?

## Workflow friction

During sprint capture with 20+ athletes and multiple trials, the athlete list
becomes too long. Scrolling to find the next athlete creates the same friction
as using Google Sheets and pulls attention away from coaching.

### Athlete Switching

The live capture workflow should be organized around athlete flow and running
order, not repeated athlete search.

### Setup Friction

Coaches rarely create a brand-new athlete list for each practice. Most training
groups are recurring teams or groups that train together repeatedly. Recreating
athlete lists before every session adds unnecessary setup time.

#### Large Group Workflows

Large recurring teams (e.g., Summit Football with 70+ athletes) make manual
roster creation impractical. Coaches frequently split one team into recurring
training groups (Sprint Group A, Sprint Group B, etc.). Recreating or manually
entering large rosters creates significant setup friction.

### Data Visibility

When the same athlete records sprint times across multiple
`SprintCaptureSession` records, the current session screen only displays
attempts from the active session. Although historical data may be used
internally for PR classification, the coach cannot see the athlete's relevant
historical performance while recording the current session.

A coach needs immediate context to interpret today's performance. Showing only
current-session attempts makes it difficult to compare today's times with the
athlete's previous best or recent sessions.

## Unexpected behavior

## What coaches liked

## What slowed coaching down

## V2 Changes

### Changes Required Before Commit or V2 Changes

Organize live capture around a predefined athlete order or queue rather than
requiring the coach to search and scroll for each athlete.

Implementation status: addressed in FEAT-001.1 with persistent roster order,
previous/next navigation, and searchable out-of-order selection. Field
validation is still required.

### V2 Ideas

Reuse persistent Training Groups, including their rosters and athlete order,
when creating a new session.

Implementation status: addressed in FEAT-001.1. Field validation is still
required.

Each new group session now preserves a session-specific roster and order
snapshot. Later Training Group changes do not alter earlier sessions.

Support importing large rosters once, organizing athletes into recurring
subgroups, and reusing those subgroup assignments across sessions.

### Required V2 Changes

Keep current-session results and historical performance context visibly
separate.

Current Session should contain only:

- Attempts recorded in the active `SprintCaptureSession`
- Current-session best

Historical Reference should contain:

- Previous personal best before the active session
- Date of the previous personal best
- Most recent comparable session result
- Comparison between today's best and the previous personal best

Lifetime Record should show the fastest valid attempt for the same athlete,
distance, and unit.

Comparable results must match the athlete, exact distance, and exact unit.
Historical attempts must not be added to the current-session attempt list.

## New feature ideas created

## Related Workflow Intelligence

- [WI-001 — Athlete Flow](../../workflow_intelligence/WI-001-Athlete-Flow.md)
- [WI-002 — Large Group Workflows](../../workflow_intelligence/WI-002-Large-Group-Workflows.md)
- [WI-003 — Session Setup](../../workflow_intelligence/WI-003-Session-Setup.md)
- [WI-004 — Coach Attention](../../workflow_intelligence/WI-004-Coach-Attention.md)
- [WI-005 — Data Capture](../../workflow_intelligence/WI-005-Data-Capture.md)
