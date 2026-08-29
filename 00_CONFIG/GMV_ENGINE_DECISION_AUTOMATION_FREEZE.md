# GMV Engine / Decision Engine — Unapproved Automation Freeze Record

## Status

- **FROZEN — UNAPPROVED AUTOMATION**
- Disposition: Post-REBASE 001 Task 4 verdict, `FREEZE_UNAPPROVED_AUTOMATION`
- Freeze date: 2026-07-13
- Current execution state: LaunchAgent unloaded and persistently disabled at both launchd layers; no scheduled or manual execution has occurred since the freeze.

## Components covered

- `com.gmv.engine` (LaunchAgent)
- `~/.gmv_core/scripts/gmv_engine.sh`
- `~/.gmv_core/scripts/gmv_decision_engine.sh`

**This freeze does not classify or freeze** `gmv_fenix_engine.sh`, `gmv_watchdog.sh`, `gmv_orchestrator.sh`, `gmv_snapshot.sh`, or `gmv_daily_boot.sh`. Those components remain exactly as they were before this task, in whatever loaded/unloaded and governance state they already had. No investigation of them was performed in this task.

## Historical role

- `com.gmv.engine` was a daily 21:30 scheduled wrapper (`RunAtLoad: true`, so it also ran once immediately on load).
- On each run it: checked a policy gate file's existence; ran a Core CLI status check; invoked the snapshot script; invoked the Watchdog script; invoked the Daily Boot script; invoked the Decision Engine script.
- The Decision Engine computed an advisory 0–15 score from three log signals (Engine/Watchdog/Fenix) and wrote a textual `MODE`/`ACTION` recommendation to `GMV_DECISION.md`, plus one line to a flat log file, every run.
- No confirmed consumer of `GMV_DECISION.md` or the flat logs was found.
- The computed score never caused any binding decision or autonomous execution — it was written and then read by nothing.

## Reason for freeze

- Both scripts are untracked (no git history).
- Neither has a Service OID.
- Neither is registered in the Service Registry or `SERVICE_SPECIFICATION.md`.
- Neither has a defined owner.
- Neither has test coverage.
- Neither has operative documentation.
- Two independent prior forensic archaeology documents (predating REBASE 001) identified this exact chain as contradicting an explicit architectural governance statement that no component may bypass Reasoning/Decision/autonomous-workflow gates.
- Six consecutive internal `[STATUS] FAIL` entries were recorded across the last six scheduled runs.
- These failures were masked from `launchd`'s own monitoring because the script always exited 0 regardless of the internal failure.
- The chain's snapshot and daily-boot invocations duplicated calls already made independently by `gmv_orchestrator.sh` (and, for daily-boot, by other scripts).
- The snapshot invocation is a real, state-changing Core operation (`gmv snapshot create`), and it was occurring daily under entirely unapproved, ungoverned automation.

## Current operational state

- Plist `Disabled` key: `true`, added to `~/Library/LaunchAgents/com.gmv.engine.plist`.
- launchd persistent-disable state: `com.gmv.engine` present in `launchctl print-disabled "gui/$(id -u)"`.
- Service loaded state: unloaded (`launchctl bootout` executed; `launchctl print` now reports "Could not find service").
- `gmv_engine.sh` and `gmv_decision_engine.sh`: preserved unchanged, hash-identical to their pre-freeze state.
- `04_LOGS/engine.log`, `04_LOGS/decision.log`, `03_STATE/GMV_DECISION.md`: preserved unchanged, hash-identical to their pre-freeze state.
- No code or output was deleted.
- No Service Registry entry or `GMV.db` row was created, modified, or deleted.

## Reactivation conditions

Reactivation requires, at minimum, all of the following:

1. Explicit Project Owner or approved Sprint authorization.
2. Git tracking of all runtime scripts involved.
3. Defined ownership.
4. Authority classification.
5. Service registration, or an explicit documented exception from registration.
6. Test coverage.
7. Diagnosis of the persistent internal `[STATUS] FAIL` condition.
8. Removal of the exit-code failure masking, or a documented, explicit exit-code policy in its place.
9. An audit of `gmv_snapshot.sh` and any other duplicate state-changing calls this chain makes.
10. A review of this chain's overlap with Fenix, Watchdog, and `gmv_orchestrator.sh`.
11. Successful isolated validation before the job is ever scheduled again.

## Manual reactivation principle

**Reactivation is not authorized by this document.** This record is a freeze, not a plan for resumption. A future, separately approved task would need to: fix the underlying defects identified above; clear the plist `Disabled` key; run `launchctl enable`; bootstrap the service; and verify an observed successful run before relying on it again. No single command or shortcut sequence is provided here to re-enable this automation.

## Preservation evidence

**Pre-freeze hashes (recorded before any modification):**

- `scripts/gmv_engine.sh`: `4f91fbbc71b5b04c0caab1c61130e9fe0274965e1afbbdb13e49ca96ad740dfa`
- `scripts/gmv_decision_engine.sh`: `34b0c73dae59bcd57d74079324b1c0f91214c16a1de9cb0edbb92b1862a3ac99`
- `com.gmv.engine.plist` (pre-freeze): `9a2f3cafeaf1537b784b615f923460925f70f7e030604a7dc29a032d2c1e51aa`
- `04_LOGS/engine.log`: `6be01df1443c2a244c2aedeba5e953e072c534a2416dc2e2a339376bca32e9d7`
- `04_LOGS/decision.log`: `d32b6cba99f5a7e61660cebc28b8919e04c19c4f5ea6c9b76f3b695803f8e98e`
- `03_STATE/GMV_DECISION.md`: `84f3d7c9b5d8a511ea4f447b4f811bbaa806bbfe6bd3b4828888d7c80e41c2d6`

**Post-freeze hashes:**

- `scripts/gmv_engine.sh`: `4f91fbbc71b5b04c0caab1c61130e9fe0274965e1afbbdb13e49ca96ad740dfa` (unchanged)
- `scripts/gmv_decision_engine.sh`: `34b0c73dae59bcd57d74079324b1c0f91214c16a1de9cb0edbb92b1862a3ac99` (unchanged)
- `04_LOGS/engine.log`: `6be01df1443c2a244c2aedeba5e953e072c534a2416dc2e2a339376bca32e9d7` (unchanged)
- `04_LOGS/decision.log`: `d32b6cba99f5a7e61660cebc28b8919e04c19c4f5ea6c9b76f3b695803f8e98e` (unchanged)
- `03_STATE/GMV_DECISION.md`: `84f3d7c9b5d8a511ea4f447b4f811bbaa806bbfe6bd3b4828888d7c80e41c2d6` (unchanged)
- `com.gmv.engine.plist` (post-freeze, with `Disabled` key added): recorded in this task's report; `plutil -lint` confirms validity before and after.
