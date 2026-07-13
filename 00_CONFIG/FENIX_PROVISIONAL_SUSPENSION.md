# Fenix — Provisional Suspension Record

## Status

**PROVISIONALLY SUSPENDED — PENDING TECHNICAL REVIEW**

This is an operational suspension only. It is explicitly **not** a
classification of Fenix as legacy, obsolete, deprecated, rejected, or
decommissioned. Fenix's final architectural disposition remains pending
technical review.

- Basis: Post-REBASE 001 Task 6 archaeology (verdict recommendation
  `FREEZE_UNAPPROVED_AUTOMATION`, report only, not itself authorized as a
  final disposition).
- Suspension date: 2026-07-13.
- Authorized by: Project Owner decision, Post-REBASE 001 Task 7.

## Operational Reason for Suspension

`com.gmv.fenix` was a live, loaded, daily-scheduled (03:30) LaunchAgent
running `~/.gmv_core/scripts/gmv_fenix_engine.sh`, an untracked script with
no Service OID, no registration, no documentation, no owner, and no tests.
Every one of its 7 recorded runs logged an internal `[FENIX] CLI FAIL` and
`[FENIX] STATE DEGRADED - RECONCILIATION REQUIRED` condition, none of which
was ever surfaced to `launchd` (the job's own exit code was always 0).
Continuing to run this automation unmonitored, while its own development
and technical review were never completed, was assessed as an unnecessary
operational exposure. Suspending it removes that exposure without
prejudging its eventual architectural fate.

## Fenix Is a Partial Implementation

Fenix is a partial implementation whose development and technical review
were not completed. It was created in the same untracked authoring batch
as `gmv_engine.sh`, `gmv_decision_engine.sh`, and `gmv_watchdog.sh`
(2026-07-07), and its own plist carries a comment describing its schedule
as a *"fallback"* mechanism — direct evidence it was not built or reviewed
as a finished, primary system.

## No Final Architectural Rejection

No final architectural rejection has been made. This suspension does not
determine whether Fenix should eventually be kept, governed, merged into
another component, or decommissioned — that determination requires the
technical review listed below and remains explicitly open.

## Preservation

- `~/.gmv_core/scripts/gmv_fenix_engine.sh` — unmodified.
- `~/.gmv_core/04_LOGS/fenix.log` — unmodified; all 7 historical run
  entries preserved exactly as recorded.
- `~/.gmv_core/03_STATE/GMV_DAILY_BOOT.md`, `~/.gmv_core/05_OUTPUT/snapshots/`
  — unmodified.
- No code, log, or historical evidence was deleted.
- No Service Registry entry or `GMV.db` row was created, modified, or
  deleted.

## No Current Consumer

No current consumer of Fenix's output exists. Its sole prior consumer,
`gmv_decision_engine.sh`, was itself frozen in Post-REBASE 001 Task 5
(`GMV_ENGINE_DECISION_AUTOMATION_FREEZE.md`). Suspending Fenix removes no
functioning downstream dependency.

## Observed Behavior Pattern

All observed executions (7 of 7 recorded runs, from creation on 2026-07-07
through 2026-07-13) reported internal degradation
(`[FENIX] CLI FAIL`, `[FENIX] STATE DEGRADED - RECONCILIATION REQUIRED`)
while the job itself always returned exit code 0 to `launchd`. Fenix
performs observation and reporting only — it checks CLI status, lists the
most recent snapshot filename, and writes log/report text. It does not
itself perform any recovery, repair, restart, or state-mutating action.

## Current Operational State

- Plist `Disabled` key: `true`, added to
  `~/Library/LaunchAgents/com.gmv.fenix.plist`. `plutil -lint` confirmed
  valid both before and after the edit.
- launchd persistent-disable state: `com.gmv.fenix` present in
  `launchctl print-disabled "gui/$(id -u)"`.
- Service loaded state: unloaded (`launchctl bootout` executed;
  `launchctl print` now reports "Could not find service").
- No sibling LaunchAgent's state was changed by this action.
- No workload was executed at any point during this suspension.

## Final Disposition — Minimum Requirements

Final disposition of Fenix requires, at minimum, all of the following:

1. Project Owner approval.
2. Codex or an equivalent independent technical review.
3. Forensic archaeology of `gmv_watchdog.sh`.
4. An audit of `gmv_snapshot.sh` and the snapshot mechanism.
5. A comparison of Fenix's function against Core `status` and `doctor`.
6. Clarification of the intended Orchestrator architecture.
7. Diagnosis of the persistent CLI failure Fenix has reported in every
   recorded run.
8. Test coverage.
9. Explicit exit-code semantics (Fenix's own exit code currently does not
   reflect the internal condition it detects).
10. Defined ownership and authority.

## Preservation Hashes

- `scripts/gmv_fenix_engine.sh`: `c80c5d369fa3fc2c5d8f925f5b44442f2d748d7e53fb3d246aac1aabcdeec01a` (unchanged before and after suspension)
- `04_LOGS/fenix.log`: unchanged mtime and content (last entry: 2026-07-13 03:30:00, `[FENIX] STATE DEGRADED - RECONCILIATION REQUIRED`)
- `com.gmv.fenix.plist` pre-suspension: `22164b546815d963eeffe599151da05a2b86b6cd988bb8322698ea77a004a40f`
- `com.gmv.fenix.plist` post-suspension: includes the added `Disabled: true` key; all other keys/values unchanged. (Note: the plist's descriptive XML comment — *"fallback: 1 volta al giorno alle 03:30"* — was not preserved by the `PlistBuddy` rewrite used to add the `Disabled` key; this is a formatting side effect of the edit tool, not a semantic change, and the comment's content is preserved verbatim in this document and in the Post-REBASE 001 Task 6 archaeology report.)

## Reactivation

Reactivation is not authorized by this document and is not the subject of
this suspension. Any future reactivation or final disposition requires a
separately approved task addressing the minimum requirements listed above.
