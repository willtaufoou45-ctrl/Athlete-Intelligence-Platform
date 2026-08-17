# Product Decisions

## PD-001 — Organize live capture around athlete flow

### Decision

Live capture should be organized around a predefined athlete order or queue
rather than requiring the coach to search and scroll for each athlete.

### Evidence

With 20 or more athletes completing multiple trials, the athlete list becomes
long and difficult to navigate. Scrolling to find the next athlete creates the
same friction as using Google Sheets and pulls attention away from coaching.

### Related Workflow Intelligence

- [WI-001 — Athlete Flow](../workflow_intelligence/WI-001-Athlete-Flow.md)
- [WI-004 — Coach Attention](../workflow_intelligence/WI-004-Coach-Attention.md)
- [FEAT-001.1 — Workflow Friction Improvements](FEATURES/feat-001.1-Workflow-Friction-Improvements.md)

## PD-002 — Training Groups are Persistent

### Decision

The primary organizational object should be a recurring Training Group (team,
class, private group, etc.), not an individual sprint session.

### Evidence

Coaches repeatedly work with the same athletes. Recreating athlete lists for
every practice creates unnecessary friction and slows session setup.

### Reasoning

The coach should create a Training Group once and reuse it indefinitely.

Each training day should simply create a new Session attached to that Training
Group.

### Proposed workflow

```text
Training Group
    ↓
Park City Football

Roster
    ↓
Hudson
James
Peter
...

Session History
    ↓
July 31
August 2
August 5
```

Each new session automatically loads:

- roster
- athlete order
- previous coaching data
- previous sprint history

### Product Implications

Future implementation should introduce:

- Training Groups
- Persistent Rosters
- Session History
- Copy Previous Session
- Default Athlete Order

### Status

Validated workflow observation.  
Initial implementation completed in FEAT-001.1; field validation pending.

### Related

- PD-001 — Organize live capture around athlete flow
- FEAT-001 — Manual Sprint Capture
- [WI-003 — Session Setup](../workflow_intelligence/WI-003-Session-Setup.md)
- [FEAT-001.1 — Workflow Friction Improvements](FEATURES/feat-001.1-Workflow-Friction-Improvements.md)

## PD-003 — Large Rosters Require Persistent Import and Grouping

### Decision

Training Groups should support persistent rosters and recurring subgroups.
Coaches should be able to import large rosters once and reuse them across future
sessions.

### Evidence

Teams with 70+ athletes are routinely divided into smaller recurring training
groups. Manual athlete entry or repeated roster creation is not scalable.

### Reasoning

The software should minimize setup time so coaches can begin training
immediately.

### Future capabilities

- Paste roster from spreadsheet
- CSV import
- Duplicate an existing roster
- Persistent subgroups within a training group
- Drag-and-drop athlete assignment between subgroups
- Reuse subgroup assignments across sessions

### Status

Validated workflow observation.  
Not yet implemented.

### Related

- PD-001 — Organize live capture around athlete flow
- PD-002 — Training Groups are Persistent
- FEAT-001 — Manual Sprint Capture
- [WI-002 — Large Group Workflows](../workflow_intelligence/WI-002-Large-Group-Workflows.md)
- [WI-003 — Session Setup](../workflow_intelligence/WI-003-Session-Setup.md)

## PD-004 — Separate Current Results from Historical Context

### Decision

During live capture, the interface should display current-session attempts
separately from historical performance context.

### Evidence

When an athlete is recorded in multiple sessions, the current session does not
visibly reference previous comparable times. This makes it difficult for the
coach to interpret whether today's result represents improvement, decline,
consistency, or a new personal record.

### Reasoning

Historical context is valuable during coaching, but mixing prior attempts into
today's attempt list would create clutter and make the active session harder to
understand.

### Product Implication

Future FEAT-001 iterations should display a compact historical-reference panel
containing:

- Previous personal best before the current session
- Date of that result
- Most recent comparable session best
- Today's best
- Difference in seconds
- Percentage difference

Comparable results must match the athlete, exact distance, and exact unit.
Historical attempts must remain separate from the active-session attempt list.

### Status

Validated workflow gap; not yet implemented.

### Related

- FEAT-001 — Manual Sprint Capture
- FEAT-001 field review
- PD-001 — Organize live capture around athlete flow
- [WI-005 — Data Capture](../workflow_intelligence/WI-005-Data-Capture.md)

## PD-005 — AIP Is the Sprint Data Source of Truth

### Decision

Sprint times should be recorded once in AIP and exported when needed. Coaches
should not manually duplicate data in another system.

### Reasoning

Duplicate entry wastes time, increases error risk, creates conflicting records,
and weakens trust in the data.

### Product Implication

Provide a simple CSV export before adding direct integrations.

### Status

Validated workflow improvement.

### Related

- [FEAT-001 — Manual Sprint Capture](FEATURES/feat-001-Manual%20Sprint%20Capture.md)
- [FEAT-001.1 — Workflow Friction Improvements](FEATURES/feat-001.1-Workflow-Friction-Improvements.md)
- [FEAT-001.2 — Sprint Data Export](FEATURES/feat-001.2-Sprint-Data-Export.md)

## PD-006 — Historical imports require explicit identity resolution

### Decision

AIP may normalize surrounding, repeated whitespace and case for athlete
matching, but it must never silently merge, create, or fuzzily match an athlete
when importing historical results.

### Evidence

The validated Summit Football `10 yd` spreadsheet contains extra whitespace,
incomplete names, inconsistent capitalization, grade labels in name fields, and
similar athlete names. Assigning a result to the wrong athlete would corrupt
personal records and every future individual or team insight.

### Reasoning

Historical import creates durable coaching evidence. A slower explicit review
is preferable to an invisible identity error that produces a false personal
best. One exact normalized match within the selected Training Group may be
accepted automatically; unmatched or ambiguous names require coach resolution.

### Product Implication

Historical import must provide a no-write preview, explicit athlete resolution,
invalid-value and duplicate reporting, and atomic confirmation. It must retain
source provenance so a repeated import can be detected and audited.

### Status

Implemented locally in FEAT-004. Awaiting field validation.

### Related

- [FEAT-004 — Historical Sprint Import](FEATURES/feat-004-Historical-Sprint-Import.md)
- [PD-004 — Separate Current Results from Historical Context](#pd-004--separate-current-results-from-historical-context)
- [PD-005 — AIP Is the Sprint Data Source of Truth](#pd-005--aip-is-the-sprint-data-source-of-truth)
- [WI-005 — Data Capture](../workflow_intelligence/WI-005-Data-Capture.md)

## PD-007 — Active sessions may accept explicit roster changes

### Decision

An active group session may accept an explicit late-athlete addition. The
athlete is appended to that session's roster snapshot and the persistent
Training Group roster. Completed and earlier sessions remain unchanged.

### Evidence

Unexpected athletes can arrive after sprint timing has started. Requiring the
coach to abandon the active workflow or create another session prevents timely
capture and risks losing the athlete's first result.

### Reasoning

The roster snapshot protects historical truth, but an active session is still
in progress. A deliberate addition accurately records who participated without
retroactively changing prior sessions. Completion is the boundary after which
the roster and results are closed.

### Status

Implemented locally in FEAT-001.3. Awaiting field validation.

### Related

- [FEAT-001.3 — Live Session Workflow](FEATURES/feat-001.3-Live-Session-Workflow.md)
- [PD-001 — Organize live capture around athlete flow](#pd-001--organize-live-capture-around-athlete-flow)
- [PD-002 — Training Groups are Persistent](#pd-002--training-groups-are-persistent)
- [WI-001 — Athlete Flow](../workflow_intelligence/WI-001-Athlete-Flow.md)
- [WI-003 — Session Setup](../workflow_intelligence/WI-003-Session-Setup.md)
