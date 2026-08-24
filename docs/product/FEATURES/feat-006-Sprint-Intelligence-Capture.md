# FEAT-006 — Sprint Intelligence Capture v0.1

## Status

Implemented locally. Awaiting field validation.

## Purpose

Turn sprint results into reusable coaching history without treating a time as a complete diagnosis. Sprint Capture preserves what was intended, what happened, what the coach and athlete observed, and what should return at the next session.

## Validated Case

The first workflow was derived from Brody's acceleration session:

- flying 10-yard acceleration protocol with a 5-yard run-in;
- four timed repetitions: 1.35, 1.26, 1.35, and 1.37 seconds;
- Rep 2 was selected as the visual and performance reference;
- the coach observed effortless execution, lower projection, big arms, and stable head, neck, and shoulders;
- the athlete described the rep as “low and shot out”;
- later reps became tense when the athlete tried to beat the result;
- the confirmed carry-forward was “Run every sprint the same. Do not think about beating your time.”

This is session evidence and a working hypothesis, not a permanent diagnosis.

## Implemented Workflow

### Sprint Brief

The capture page stores the session's shared emphasis, work leading into timed sprints, and conditioning performed after quality work.

### Rep Context

Each timed attempt may store:

- effort instruction;
- coach observation;
- athlete feedback in the athlete's own language;
- a video reference.

One attempt may be selected as the athlete's reference repetition for the session.

### Coach Review

For each athlete and session, the coach may confirm:

- primary intention;
- performance target;
- athlete feedback;
- coach observation;
- interpretation;
- working hypothesis;
- unknowns;
- next-session carry-forward.

These fields remain separate so observed evidence is not silently converted into a conclusion.

### Next Session

The most recent confirmed carry-forward is returned when the athlete is opened in a later session. Full session and rep history remains stored, while the live workflow surfaces the actionable reminder.

## Product Boundaries

- The coach confirms or changes all interpretations and carry-forward language.
- A sprint time remains performance evidence, not a complete diagnosis.
- Video is linked to the attempt; automated mechanics or angle analysis is excluded.
- The feature does not recommend drills or replace medical or practitioner judgment.
- Conditioning is recorded separately from quality timed work.

## Field Validation

Validate across multiple athletes and at least two later sessions. Confirm that:

- updating an athlete takes less than one minute;
- recording context does not interrupt timing or athlete flow;
- the returned carry-forward changes or improves next-session coaching;
- coaches can distinguish facts, observations, interpretations, hypotheses, and unknowns;
- reference video links remain usable on the coach's phone.
