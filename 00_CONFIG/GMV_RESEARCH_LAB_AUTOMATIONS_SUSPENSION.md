# GMV Research Lab — Live Automations Suspension Record

## Status

**PROVISIONALLY SUSPENDED** (both automations).

- Root classification: `~/GMV_CORE` = `PROTOTYPE_ROOT`.
- Root disposition: `PRESERVE_PENDING_REVIEW`. This suspension does **not**
  freeze, decommission, migrate, repair, or classify the prototype root as
  legacy. It affects only the two live, scheduled LaunchAgents in scope.
- Suspension date: 2026-07-13.
- Authorized by: Project Owner decision, Stabilization — Final Blocker
  Resolution task.
- Basis: Stabilization — Final Blocker Task: Forensic Archaeology of
  `~/GMV_CORE` and its two live automations (report only; verdict
  `PROVISIONALLY_SUSPEND` for each runner, independently derived).

This suspension does **not** classify the Local Coding Engine
(`00_CONFIG/LOCAL_CODING_ENGINE.md`) or any other, unrelated component. The
prior conflation of `~/GMV_CORE` with the Local Coding Engine concept in
this project's ledger was found to be unevidenced and was corrected in the
preceding archaeology task.

## Components Covered

- `~/GMV_CORE/06_RUNNER/dropbox_daily_brief.py`
- `~/GMV_CORE/06_RUNNER/morning_os.py`
- `~/Library/LaunchAgents/com.gmv.dailybrief.plist`
- `~/Library/LaunchAgents/com.gmv.morningbrief.email.plist`
- launchd services `gui/$(id -u)/com.gmv.dailybrief` and
  `gui/$(id -u)/com.gmv.morningbrief.email`

## Distinct Failure Causes

The two automations were suspended for the same governance reason (live,
unregistered, ungoverned scheduled automation) but for two independently
diagnosed, distinct technical failure causes:

- **`com.gmv.dailybrief` / `dropbox_daily_brief.py`:** the LaunchAgent's
  plist contains a confirmed, genuine XML defect — an unescaped `&&`
  inside an XML `<string>` value (line 14) — making the file invalid XML.
  This was independently confirmed by `plutil -lint` in both the
  2026-07-10 archaeology pass and the preceding Stabilization archaeology
  task. All 6 recorded scheduled runs failed with `launchd` exit code 78
  (`EX_CONFIG`).
- **`com.gmv.morningbrief.email` / `morning_os.py`:** the LaunchAgent
  invokes the script directly with no `cd` step, while the script itself
  reads and writes relative paths (`04_RESULTS/dropbox_decisions.json`,
  `08_REPORTS/MORNING_OS_BRIEF.md`). This is consistent with a
  working-directory-dependent execution failure. All 7 recorded scheduled
  runs failed with exit code 1.

## Observed Failure History

**100% observed failure rate for both automations, across their entire
recorded operational history:**

- `com.gmv.dailybrief`: 6 of 6 recorded runs failed (`EX_CONFIG`, 78).
- `com.gmv.morningbrief.email`: 7 of 7 recorded runs failed (exit code 1).

Neither automation has produced fresh output via its LaunchAgent at any
point since its one manual test run on 2026-07-07 (the same day it was
authored).

## External-Email Capability

`morning_os.py` contains a conditional, exception-guarded email-dispatch
path (`MAIL/send_morning_brief.py`) targeting a local SMTP relay
(`127.0.0.1:1025` — the same relay documented for `SRV-000002` Morning
Brief in `LEGACY_ENGINE_INVENTORY.md`) with a real external recipient
address. This capability is **preserved but inactive**: the script code is
unchanged, and the automation that could reach this code path is now
suspended. No email was sent as part of this suspension task, and no
evidence was found that this capability was ever exercised through the
scheduled LaunchAgent (only the code path exists; every scheduled run
crashed before reaching it, per the failure cause above).

## No Final Decision

No final decision has been made to repair, migrate, merge, permanently
freeze, or decommission either automation, or the `~/GMV_CORE` root. This
is an operational suspension only, reducing live governance exposure while
preserving every option for the final disposition review listed below.

## Preservation

- Both Python runners (`dropbox_daily_brief.py`, `morning_os.py`) are
  confirmed hash-identical before and after this suspension.
- No file under `~/GMV_CORE` was modified, moved, renamed, or deleted.
- All existing logs and outputs (`MORNING_OS_BRIEF.md`,
  `DAILY_EXECUTION_BRIEF.md`, and the historically-absent
  `daily_brief.log`/`daily_brief_error.log`) remain exactly as found.
- No email was sent.
- No Dropbox access or write occurred.
- No workload was executed at any point during this suspension.

## Plist-Level Suspension — Recorded Limitation

`com.gmv.morningbrief.email.plist` was successfully edited: a `Disabled`
key (`true`) was added via `PlistBuddy`, validated with `plutil -lint`
both before and after (both `OK`), with every other existing key and value
unchanged.

`com.gmv.dailybrief.plist` **could not be edited at the plist level**.
`plutil -lint` and `PlistBuddy` both fail to parse the file (the same
unescaped-`&&` defect described above), and `PlistBuddy -c "Add :Disabled
bool true"` errored out without writing any change (confirmed: the file's
SHA-256 is unchanged from before the attempt). Per this task's explicit
instruction, the malformed XML was **not** rewritten or normalized to make
the edit possible. This job's suspension therefore relies solely on the
`launchd` persistent-disable database layer
(`launchctl disable "gui/$(id -u)/com.gmv.dailybrief"`), confirmed present
in `launchctl print-disabled`, without a corresponding in-plist `Disabled`
key.

## Current Operational State

- `com.gmv.morningbrief.email`: plist `Disabled: true` present; unloaded
  (`launchctl bootout` executed); persistently disabled
  (`launchctl print-disabled` confirms).
- `com.gmv.dailybrief`: plist unchanged (edit not possible, see above);
  unloaded (`launchctl bootout` executed); persistently disabled
  (`launchctl print-disabled` confirms) — this is the sole disable layer
  in effect for this job.
- No sibling LaunchAgent's state was changed by this action.

## Reactivation

Reactivation of either automation is not authorized by this document and
requires, at minimum, all of the following:

1. Explicit Project Owner approval.
2. Independent technical review.
3. Git tracking, or an explicit, documented prototype-governance exception.
4. Defined ownership.
5. Test coverage.
6. Repair and validation of each distinct failure cause identified above.
7. Review of overlap with `SRV-000002` Morning Brief and `SRV-000003`
   Daily Log.
8. Security review of the SMTP/email capability.
9. Explicit exit-code semantics.
10. An isolated, successful execution before either job is rescheduled.
11. A decision on whether this functionality belongs in `~/.gmv_core` or
    remains an approved, governed prototype within `~/GMV_CORE`.
