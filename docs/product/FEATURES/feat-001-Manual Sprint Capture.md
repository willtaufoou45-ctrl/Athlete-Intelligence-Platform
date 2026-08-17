# FEAT-001 — Manual Sprint Capture

## Status

Implemented as a functional local prototype. FEAT-001.1 workflow improvements
are implemented locally and awaiting field validation.

## Problem

Coaches must record sprint times and organize athlete data while simultaneously
coaching. Finding an athlete in a spreadsheet and entering each result divides
the coach's attention, interrupts immediate feedback, and slows the flow of
practice.

Sprint testing field notes reinforce this problem: a parent volunteered to
record times so the coach could focus on coaching, feedback was sometimes
skipped because the next athlete was ready, and manual entry was the primary
bottleneck.

## Goal

Validate that a coach can reliably capture and correct sprint measurements
during a live group session without a spreadsheet. A trained user should be able
to record a normal attempt in fewer than 10 seconds.

The prototype is successful when the coach can spend more attention on athlete
feedback while every valid attempt remains organized and available after an
application restart.

## Prototype boundaries

- Single coach.
- Local use only.
- Smallest maintainable server-rendered Python web stack.
- SQLite persistence.
- Keyboard-first interaction.
- No production-platform architecture is required.

A `SprintCaptureSession` is a measurement context. It is not a complete training
session or training block and must not displace the product's training-block
model.

### Sprint protocol identity

The coach-facing name for the established test is **10-yard fly**. Its full
protocol name is **Flying 10-yard acceleration test with a 5-yard run-in**:
a two-point set start, 5-yard untimed run-in, and a timed 5–15-yard segment.
It measures acceleration over that segment, not stationary-start 0–10-yard
performance or pure maximal velocity. **10-yard sprint** remains a legacy alias.

The session retains protocol identity with every result: 15-yard total distance,
10-yard timed distance, 5-yard run-in, 5–15-yard timed segment, two-point start,
and acceleration purpose. Unknown protocols remain explicitly unspecified and
are not silently compared with the 10-yard fly. A three-point start used for
40-yard preparation is a separate protocol. Sessions also retain the planned
attempt count (typically four, or two when group size requires it); recorded
attempts and their elapsed times are unchanged.

Each session also records surface type, timing method, indoor/outdoor
environment, and optional setup notes. Baseline and PR comparisons require the
same protocol, surface type, and timing method. Environment and notes remain
visible comparison context without changing the recorded elapsed time.

## Measurement rules

- Each `SprintCaptureSession` has exactly one fixed distance and unit.
- Supported units are yards and meters.
- The prototype does not convert between units.
- A time is entered as decimal seconds and stored as integer milliseconds.
- Comparisons only include valid attempts for the same athlete, exact distance,
  and exact unit.
- An athlete's first valid attempt at a distance and unit establishes a baseline.
- A personal record (PR) is strictly faster than every earlier valid attempt for
  that athlete at the same distance and unit.
- An equal time is not a PR.
- Session best is the fastest valid attempt for the selected athlete in the
  current capture session.
- Baseline, PR, and session-best status are derived from persisted attempts and
  recalculated after an attempt is edited or deleted.

## Required workflow

1. Add an athlete using name only.
2. Create a `SprintCaptureSession` by choosing a distance and unit, or resume an
   existing session.
3. Select an athlete.
4. Enter a sprint time in decimal seconds.
5. Press Enter to save.
6. Keep the athlete selected, clear the saved time, and return focus to the time
   field.
7. Immediately show the athlete's attempts, session best, and baseline/PR status.
8. Repeat entry for multiple attempts or switch athletes with a short keyboard
   path.
9. Edit or delete an incorrect attempt.
10. Retain all athlete, session, and attempt data after restarting the
    application.

## Interaction requirements

- Optimize the active capture view for one-handed, keyboard-first use.
- Make athlete selection and the time field the primary controls.
- Allow Enter to submit a valid time without page navigation.
- Preserve the selected athlete after a successful save.
- Clear only the time field after a successful save and focus it again.
- Show save success, validation errors, session best, and baseline/PR feedback
  immediately.
- Keep invalid input available for correction and retain focus and athlete
  selection.
- Prevent accidental duplicate submission while a save is in progress, without
  rejecting legitimate identical attempts.
- Keep edit and delete controls compact but clear enough for live correction.

## Acceptance criteria

- A coach can add a named athlete and select that athlete for capture.
- A coach can create and later resume a capture session with its distance and
  unit unchanged.
- Both yards and meters are accepted and remain distinct for record comparison.
- Decimal seconds are converted to and persisted as integer milliseconds without
  binary floating-point comparison errors.
- Pressing Enter saves an attempt, retains the athlete, clears the time field,
  and returns focus to it.
- Multiple attempts can be saved for the same athlete and session.
- The selected athlete's attempts and current session best update immediately.
- The first historical valid result is labeled as a baseline, not a broken PR.
- A later attempt is labeled PR only when strictly faster than all earlier valid
  attempts for the same athlete, distance, and unit.
- Editing or deleting an attempt immediately produces correct recalculated
  baseline, PR, and session-best status.
- Saved data remains available after stopping and restarting the application.
- A trained coach can complete the normal attempt-entry path in under 10 seconds.

## Explicit exclusions

- Authentication.
- Multiple coaches or organizations.
- Training programming.
- Timing-gate integrations or automatic capture.
- Athlete queues or automatic athlete association.
- Voice input.
- AI recommendations.
- Dashboards, reporting, or complex analytics.
- Cloud deployment.
- External services.
- Complex frontend frameworks.
- Infrastructure unrelated to this vertical slice.

## Evidence and related documents

- [FEAT-001 field review](../FEATURE_REVIEWS/FEAT-001-Review.md)
- `docs/product/COACH_JOURNEY.md`, Sprint Testing section.
- `docs/product/PRACTICE_OS.md`, Sprint Testing section.
- `docs/research/FIELD_NOTES/2026-06-30.md`, Sprint Testing observations.
- `docs/philosophy/PRODUCT_PRINCIPLES.md`, especially Coaching Comes First,
  Simple Wins, Training Blocks Drive Development, and Technology Should Be
  Invisible.

## Assumptions to validate in field testing

- Name-only athlete creation is sufficient for identifying athletes in the first
  prototype.
- Fixing distance and unit at session creation reduces entry time and errors.
- Retaining the selected athlete is the fastest default for repeated attempts;
  switching athletes must remain easy for group rotation.
- Local SQLite storage is sufficient for workflow validation and recovery after
  application restarts.
