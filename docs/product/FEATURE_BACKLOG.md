# Feature Backlog

Every feature in ACE must solve a documented coaching problem.

Features should always trace back to:

- Philosophy
- Workflow
- Practice OS
- Field Notes

---

# Feature ID

# FEAT-001 — Manual Sprint Capture

A single-coach local prototype for recording sprint attempts quickly during live
practice. It provides persistent manual entry, session bests, and baseline/PR
feedback while keeping the normal entry path under 10 seconds.

Status: **MVP candidate**

Canonical specification:
[FEAT-001 — Manual Sprint Capture](FEATURES/feat-001-Manual%20Sprint%20Capture.md)

### FEAT-001.1 — Workflow Friction Improvements

Status: **Implemented locally; awaiting field validation**

Adds persistent Training Groups, persistent ordered rosters, automatic roster
reuse for new sessions, previous/next athlete navigation, and searchable
out-of-order athlete selection.

Canonical specification:
[FEAT-001.1 — Workflow Friction Improvements](FEATURES/feat-001.1-Workflow-Friction-Improvements.md)

### FEAT-001.3 — Live Session Workflow

Status: **Implemented locally; awaiting field validation**

Adds explicit late-athlete entry for active group sessions, a next-three runner
queue, automatic attempt saving, open/completed session states, clear
group/date session labels, and permanent session deletion with confirmation.

Canonical specification:
[FEAT-001.3 — Live Session Workflow](FEATURES/feat-001.3-Live-Session-Workflow.md)

## V2 Improvements

### Historical Performance Context

The active capture screen should show a compact comparison between today's
performance and the athlete's previous comparable results without adding
historical attempts to the active-session list.

Comparable results must match the athlete, exact distance, and exact unit.

# FEAT-002 — Training Groups & Persistent Rosters

## Status

Discovery

The initial persistent-group and roster workflow is implemented in FEAT-001.1.
Further changes remain discovery work until field validation is complete.

## Problem

Creating athlete lists before every session creates unnecessary setup work.

## Goal

Allow coaches to create recurring training groups once and automatically reuse
their roster, athlete order, and session history every time they train.

# FEAT-003 — Roster Import & Group Management

## Status

Discovery

## Problem

Large teams cannot be efficiently created or managed through manual athlete
entry.

## Goal

Allow coaches to import large rosters once, organize athletes into recurring
subgroups, and reuse those groups across every training session.

## Potential future capabilities

- Paste from Excel or Google Sheets
- CSV import
- Bulk athlete creation
- Persistent subgroup management
- Move athletes between groups
- Copy previous season roster

# FEAT-004 — Historical Sprint Import

## Status

Implemented locally. Awaiting field validation.

## Problem

Historical sprint results remain in wide spreadsheets, so AIP cannot answer
"What was my best?" from the athlete's complete history without manual
re-entry.

## Goal

Safely transform athlete-row/date-column CSV data into persisted historical
sessions and attempts through a no-write preview, explicit athlete resolution,
duplicate protection, and atomic confirmation.

Canonical specification:
[FEAT-004 — Historical Sprint Import](FEATURES/feat-004-Historical-Sprint-Import.md)

# FEAT-005 — Hosted Mobile Sprint Capture

## Status

Architecture implementation started locally; not deployed. Vendor-account,
real-data migration, backup, and cutover approvals remain open.

## Problem

The phone currently depends on Terminal running on the coach's laptop and a
stable local network connection. That connection failed during field use and a
second sprint session could not be captured in AIP.

## Goal

Provide a permanent authenticated HTTPS address backed by hosted persistent
storage while preserving the current phone-first capture workflow, Training
Groups, roster snapshots, attempt/PR semantics, historical CSV import, sprint
CSV export, and prototype feedback.

Hosted V1 requires internet. Offline capture and later synchronization are a
separate future feature and are explicitly excluded.

Canonical specification:
[FEAT-005 — Hosted Mobile Sprint Capture](FEATURES/feat-005-Hosted-Mobile-Sprint-Capture.md)

# FEAT-006 — Athlete Focus Memory

## Category

Core Value

---

## Problem

Coaches rely heavily on memory to remember what each athlete is working on throughout the training cycle.

Whether coaching six athletes or sixty, it becomes difficult to remember an athlete's current focus, why that focus was chosen, what changes have been made over the past several weeks, and whether those changes have been successful.

The athlete's focus drives coaching cues, exercise intent, progression, and communication throughout the session.

As the number of athletes grows, the coach's mental bandwidth becomes the limiting factor rather than coaching ability.

---

## Why This Matters

Elite coaching is built on continuity.

Every session should build upon the previous one.

If coaches cannot quickly remember an athlete's history, valuable coaching time is spent rediscovering information instead of progressing the athlete.

The platform should become the coach's memory, allowing coaches to spend less time recalling information and more time coaching.

This increases coaching confidence, improves decision making, and allows the business to scale without sacrificing coaching quality.

---

## Evidence

### Workflow

- Before Practice
- Speed Training
- Sprint Testing
- Weight Room
- Post Practice Review

### Practice OS

- Coach reviews team focus before practice.
- Coach reviews individual athlete focus.
- Coach references coaching reminders throughout the session.
- Athlete receives consistent coaching cues throughout the training cycle.

### Field Notes

- Coach relies on memory for most coaching decisions.
- Coach often asks athletes what they have been working on.
- Coach searches Google Sheets for previous sprint results.
- Coach searches Sparta for previous force plate data.
- Coach forgets small adjustments made during previous sessions.
- Valuable coaching time is spent recalling information.

### Coach Observations

- Coaching quality improves when historical context is immediately available.
- Small coaching adjustments are often forgotten over time.
- Athletes rarely remember their own long-term focus without reinforcement.

---

## Current Process

1. Review roster and team focus before practice.
2. Review athletes requiring additional attention.
3. Coach from memory throughout practice.
4. Search historical sprint or force plate data when needed.
5. Review notes after practice to prepare for the next session.

This process relies heavily on memory and multiple disconnected systems.

---

## Desired Outcome

The coach immediately understands every athlete's current training focus without relying on memory.

The platform reminds the coach:

- What the athlete is currently working on.
- Why that focus was selected.
- Previous coaching adjustments.
- What has worked.
- What should be reinforced during today's session.

Athletes also understand their current focus and become active participants in their own development.

---

## Possible Solutions

- Individual coaching reminders before practice.
- Athlete focus displayed on the coach's dashboard.
- Athlete focus displayed on the athlete's device.
- Daily coaching reminders.
- Historical coaching timeline.
- Session notes attached to each athlete.
- One-click coaching summary before practice.

---

## Primary User

Coach

### Secondary Users

- Athlete

---

## Success Metrics

- Coaches no longer rely primarily on memory.
- Coaches no longer search multiple systems for historical context.
- Coaching interruptions decrease.
- Athletes can explain their current training focus.
- Coaching cues remain consistent across multiple weeks.
- Coaches feel more confident making day-to-day decisions.

---

## Target Release

MVP

---

## Dependencies

- Athlete Profile
- Team Roster
- Historical Sprint Data
- Historical Force Plate Data
- Coach Notes
- Training History

---

## Notes

This feature is more than a note-taking system.

It preserves coaching continuity.

The goal is not simply to remember information.

The goal is to preserve the reasoning behind coaching decisions so every session builds on the previous one.

The platform becomes an extension of the coach's memory rather than another database to manage.

# Future Idea — Athlete Queue

## Category

Core Value | Foundation | Workflow | Intelligence

---

## Problem
Athletes don’t know where to go, when it’s their turn, or what they’re doing next.

What coaching problem exists?

Describe the problem from the coach's perspective.

What is happening today?

Why is it difficult?

How does it affect coaching?

---

## Why This Matters

Why is solving this problem important?

How does it improve coaching?

What is the impact on the athlete?

What is the impact on the coach?

---

## Evidence

### Workflow

-

### Practice OS

-

### Field Notes

-

### Coach Observations

-

---

## Current Process

Describe exactly how this is done today.

1.
2.
3.
4.
5.

Where does coaching stop?

Where does administration begin?

---

## Desired Outcome

If this problem disappeared tomorrow...

What would the coach experience?

-

-

-

-

---

## Possible Solutions

Don't worry about implementation.

Simply list ideas.

-

-

-

-

---

## Primary User

Coach

### Secondary Users

-

---

## Success Metrics

How will we know this feature solved the problem?

-

-

-

-

---

## Target Release

MVP | Version 2 | Future

---

## Dependencies

What information or features must exist before this one can work?

-

-

-

---

## Notes

Anything important that doesn't fit above.

Ideas.

Questions.

Future thoughts.

Connections to other features.

This placeholder previously used FEAT-005. That identifier is now assigned to
the validated Hosted Mobile Sprint Capture feature. Athlete Queue remains an
unnumbered future idea until it is defined and assigned a new feature ID.
