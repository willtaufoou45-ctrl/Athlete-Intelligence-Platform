# FEAT-001 Review

## Hypothesis

What did we expect?

## What actually happened?

## Workflow friction

Immediately before a live session, an unexpected athlete may need to be added
after the session roster snapshot has already been created. Returning to group
setup and creating another session is too disruptive onsite.

During timing, the coach needs to see the next three sprinters so athletes can
be called forward. A separate Save tap for every time is also unnecessary
friction when the entered value can be validated and saved automatically.

The growing list of resumable sessions became difficult to understand without
an explicit completion state. Sessions need clear Training Group and date labels,
separate active/completed lists, and a confirmed deletion path.

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

Implementation status: the compact live screen now shows current-session
attempts separately from the athlete's all-time comparable best and most recent
earlier comparable session best. Comparable means the exact athlete, distance,
and unit. The actual prior session date is shown rather than assuming practices
occur exactly seven days apart.

### Data Portability

Sprint results currently remain inside AIP. Coaches may still need the same
data in Google Sheets, Excel, reports, or other workflows. Re-entering results
manually would duplicate work and create errors.

Historical sprint results also remain in wide Google Sheets workbooks. The
validated Summit Football `10 yd` sheet stores athletes in rows and testing
dates in columns. Coaches need to bring those results into AIP once so previous
best and future performance context are based on the complete comparable
history.

Historical import must not silently merge uncertain athlete identities. The
reference data includes inconsistent whitespace, incomplete names, and similar
names that require an explicit preview and resolution step.

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

Partial implementation status: all-time comparable best and the most recent
earlier comparable session best/date are now visible during capture. Difference
in seconds, percentage difference, and the distinct previous-PR-before-current-
session calculation remain deferred.

Lifetime Record should show the fastest valid attempt for the same athlete,
distance, and unit.

Comparable results must match the athlete, exact distance, and exact unit.
Historical attempts must not be added to the current-session attempt list.

### Required Improvements

Allow coaches to export persisted sprint results from the current session or a
selected Training Group as CSV. AIP should remain the source of truth so the
same sprint data does not need to be recorded manually in another system.

Add a safe wide-format historical sprint import with preview, exact athlete
matching, invalid-time reporting, duplicate protection, and atomic confirmation.
Imported history must use the existing athlete/distance/unit PR semantics.

Allow explicit late-athlete additions while a group session is active, show the
next three runners, auto-save valid decimal times, and add clear session
completion, labeling, and deletion controls.

## New feature ideas created

## Related Workflow Intelligence

- [WI-001 — Athlete Flow](../../workflow_intelligence/WI-001-Athlete-Flow.md)
- [WI-002 — Large Group Workflows](../../workflow_intelligence/WI-002-Large-Group-Workflows.md)
- [WI-003 — Session Setup](../../workflow_intelligence/WI-003-Session-Setup.md)
- [WI-004 — Coach Attention](../../workflow_intelligence/WI-004-Coach-Attention.md)
- [WI-005 — Data Capture](../../workflow_intelligence/WI-005-Data-Capture.md)
- [FEAT-004 — Historical Sprint Import](../FEATURES/feat-004-Historical-Sprint-Import.md)
