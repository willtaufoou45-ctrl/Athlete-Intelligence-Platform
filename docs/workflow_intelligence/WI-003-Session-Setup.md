# WI-003 — Session Setup

## Observation

Coaches usually train recurring teams or groups rather than creating a new
athlete list for every practice.

## Evidence

Recreating athlete lists before every session adds unnecessary setup time.
Coaches repeatedly work with the same athletes and reuse recurring training
groups.

## Why It Matters

Repeated setup work delays training and asks the coach to recreate information
the system could retain.

## Product Implications

A coach should create a Training Group once. Each new session should reuse its
roster, athlete order, and relevant session history.

An active session must support an explicit late-athlete addition without
altering earlier sessions. Completing the session establishes the point after
which its roster and attempts are closed. Active sessions should be separated
from clearly labeled completed history.

## Related Product Decisions

- [PD-002 — Training Groups are Persistent](../product/PRODUCT_DECISIONS.md#pd-002--training-groups-are-persistent)
- [PD-003 — Large Rosters Require Persistent Import and Grouping](../product/PRODUCT_DECISIONS.md#pd-003--large-rosters-require-persistent-import-and-grouping)
- [PD-007 — Active sessions may accept explicit roster changes](../product/PRODUCT_DECISIONS.md#pd-007--active-sessions-may-accept-explicit-roster-changes)

## Related Features

- [FEAT-002 — Training Groups & Persistent Rosters](../product/FEATURE_BACKLOG.md#feat-002--training-groups--persistent-rosters)
- [FEAT-001.1 — Workflow Friction Improvements](../product/FEATURES/feat-001.1-Workflow-Friction-Improvements.md)
- [FEAT-003 — Roster Import & Group Management](../product/FEATURE_BACKLOG.md#feat-003--roster-import--group-management)
