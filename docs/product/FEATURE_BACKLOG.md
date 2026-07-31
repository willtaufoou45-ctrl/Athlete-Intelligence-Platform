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

# FEAT-002 — Athlete Check-In

## Problem

Coaches do not know exactly which athletes are present until practice begins. Attendance is tracked informally, making it difficult to manage testing, organize groups, identify missing athletes, and prepare the session efficiently. If were expecting 60 kids and only have forty, we have to scroll through google sheet to find each kid.

As practice grows larger, coaches spend valuable time determining who is present instead of coaching.

---

## Why This Matters

The beginning of practice sets the tone for the entire session.

If attendance is unclear, every workflow that follows becomes more difficult, including:

- Sprint testing
- Force plate testing
- Weight room organization
- Athlete grouping
- Parent communication
- Practice review

Knowing who is present should require little to no effort from the coach.

---

## Evidence

### Workflow

- Before Practice
- Athlete Arrival

### Practice OS

- Coach reviews roster before practice.
- Coach prepares testing based on expected attendance.
- Coach needs to know who is available before training begins.

### Field Notes

- Attendance is currently determined by observation.
- Coaches often adjust groups after practice has already started.
- Injured and late athletes require additional attention and disrupt the normal workflow.

---

## Current Process

1. Coach arrives before practice.
2. Coach estimates who will attend.
3. Athletes gradually arrive.
4. Coach mentally tracks attendance.
5. Coach adjusts testing groups based on who is present.
6. Coach determines who is missing after practice has already started.

This process relies heavily on memory and observation.

---

## Desired Outcome

- Athletes check into practice with minimal effort.
- Coaches immediately know who is present, absent, late, or limited.
- Attendance automatically updates throughout practice.
- Testing groups are created from the current roster.
- Coaches begin practice fully organized.

---

## Possible Solutions

- Athlete self check-in.
- Coach check-in.
- QR code check-in.
- Team attendance dashboard.
- Injury or limitation status during check-in.
- Automatic testing group assignments based on attendance.

---

## Primary User

Coach

---

## Success Metrics

- Coach no longer tracks attendance manually.
- Attendance is complete before training begins.
- Testing groups are organized automatically.
- Time spent organizing athletes before practice is reduced.
- Coaches begin practice focused on coaching rather than administration.

---

## Target Release

**MVP**

---

## Notes

Attendance is the starting point for every practice workflow. Accurate athlete check-in allows testing, grouping, programming, reporting, and communication to operate from a single source of truth. Attendance would also be a metric to show why an athlete imporoved or did not.

# FEAT-003 — Athlete Focus Memory

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

# FEAT-004 — Athlete Queue

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
