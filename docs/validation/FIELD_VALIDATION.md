# AIP Field Validation Protocol

## Purpose

Validate that AIP improves live coaching workflow and preserves coaching
understanding over time. Field validation should produce evidence for product
decisions, not a list of requested features.

## Validation window

Use at least three real sprint sessions and at least two prospective updates
for each case-study athlete before changing the underlying model, unless a
data-loss or session-blocking defect is found.

# Loop 1 — Sprint Workflow

## Before the session

- Use a real recurring Training Group and its saved roster.
- Create the session before athletes begin running.
- Record the distance and unit actually used.
- Note whether setup required a workaround outside AIP.

## During the session

Use AIP as the source of truth. Do not also enter times in a spreadsheet unless
AIP fails or the backup is operationally necessary.

Observe these five questions without interrupting coaching to write long notes:

1. **Coaching interruption:** What caused the coach to stop watching or coaching?
2. **Autosave trust:** Did the coach wait for, recheck, or doubt a saved time?
3. **Athlete flow:** Did the next-three queue match the actual running order?
4. **Historical context:** Did prior results change an interpretation, cue, or conversation?
5. **Completion:** Was it clear when and how to finish the session?

For each meaningful event, record the approximate moment, what happened, and
the workaround. A repeated minor interruption is more important than a single
preference.

## Immediately after the session

Complete the existing AIP feedback form while the experience is fresh:

- **What slowed coaching down?** Record interruptions and workarounds.
- **What worked well?** Record interactions that supported coaching.
- **What should improve?** Record the desired outcome, not a proposed interface.

Also record:

- Training Group and session date
- Approximate athlete count and attempts per athlete
- Device used
- Whether every valid time was preserved
- Whether another system was used as a backup
- Whether the session was completed successfully

## Sprint-loop success criteria

After three sessions, the workflow is ready to retain when:

- No valid sprint result is lost.
- Normal entry does not require duplicate recording.
- Autosave is trusted without repeated checking.
- The queue is correct for most trials and out-of-order changes are recoverable.
- Historical context is understandable and does not contaminate today's results.
- Session completion is clear and does not close a session accidentally.
- The coach spends more attention on athletes than on finding athletes or saving data.

Any data-loss event, incorrect athlete assignment, false personal record, or
unrecoverable session closure is a stop-the-line defect and should be reviewed
before the next field session.

# Loop 2 — Athlete Intelligence

## Scope

Run the prospective loop independently for Rigby Young and Brody Bradford. Do
not rewrite their histories to fit new evidence. New evidence should update,
support, contradict, supersede, or leave prior thinking unresolved.

## Trigger

Run the loop when meaningful new evidence arrives, including:

- a comparable sprint session,
- a force test,
- a completed training block or material workout response,
- a coach observation that changes the current understanding,
- an athlete report about fatigue, readiness, pain, confidence, or training exposure,
- a change in season, sport demand, schedule, or total training load.

## Prospective update sequence

1. **New evidence** — What happened, when, and where is the source record?
2. **Current state** — Has the athlete's season, role, exposure, or training context changed?
3. **Prior thinking** — Which existing fact, observation, interpretation, hypothesis,
   focus, or open question does this evidence relate to?
4. **Uncertainty** — Does confidence increase, decrease, or remain unchanged? What is
   still unknown?
5. **Decision** — What will the coach continue, change, stop, or investigate?
6. **Expected response** — What observable result would support or challenge the decision?
7. **Follow-up** — When or under what condition will the decision be reviewed?
8. **Actual response** — At follow-up, what changed and what did AIP learn?

## Athlete-loop success criteria

After two prospective updates per athlete, the model succeeds when:

- New evidence can be attached without duplicating source-owned raw data.
- Historical statements remain visible after thinking changes.
- Facts, observations, interpretations, hypotheses, and unknowns remain distinct.
- Contradictory evidence can be preserved rather than explained away.
- A coaching decision and its expected response can be traced to evidence.
- The follow-up response can confirm, weaken, reject, or supersede prior thinking.
- Reviewing AIP reduces the need to reconstruct the athlete's story from memory.

# Decision rule

Do not build a requested feature from one isolated preference. Prioritize a
change when it prevents data loss, repeatedly interrupts coaching, corrupts
athlete understanding, or appears across multiple sessions or athletes.

At the end of the validation window, classify each finding as:

- **Retain** — works as intended.
- **Adjust** — valuable but creates repeatable friction or misunderstanding.
- **Remove** — adds work without improving coaching.
- **Investigate** — evidence is insufficient or contradictory.

