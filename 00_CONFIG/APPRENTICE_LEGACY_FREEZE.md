# Apprentice — Legacy Freeze Record

Status: Frozen legacy (REBASE 001)
Recorded: 2026-07-12
Scope: `com.gmv.apprentice` LaunchAgent and its runtime, `apprentice_runtime.py`

## What this is

A factual record of a REBASE 001 disposition decision, not an architecture
document. It exists because no existing inventory, REBASE, or service
specification document was found suitable to hold this record (checked:
`SERVICE_SPECIFICATION.md`, `LEGACY_ENGINE_INVENTORY.md` — both scoped to
different, already-approved content).

## Disposition

**FREEZE_AS_LEGACY**, decided by evidence-based archaeology (REBASE 001,
Apprentice task). Full reasoning, timeline, and evidence index are recorded in
that task's report; this file states only the operative facts.

## Why

- Root 1's own `13_HISTORY.md` narrates Apprentice as a superseded predecessor
  whose functions were absorbed into a more general level of the system, from
  which the Knowledge Engine was born.
- `01_RUNTIME/knowledge_engine.py` (git-tracked, `SRV-000001`) independently
  and directly confirms this: every report it generates carries
  `"former_codename": "apprentice"`, and its Timeline records *"Knowledge
  Engine V0 initialized from former Apprentice concept."*
- Apprentice has not completed a successful run since **2026-07-01T14:30:50**
  (`APPRENTICE_STATE.json`, Dropbox). Every scheduled run since — including
  2026-07-12 02:15, the morning this record was written — failed with an
  identical, uncaught `PermissionError` reading `EXPERIENCE_LOG.md`.
- No consumer of any Apprentice output (state file, dated reports, experience
  log) was found anywhere in Core, `.gmv_scripts`, or Dropbox.
- Apprentice's own domain-scan/change-detection logic has not yet been
  reimplemented by its successor (Knowledge Engine V0's own `next_step` field
  states the real importer is not yet built) — this is why the disposition is
  a reversible freeze, not a decommission: the algorithm may still have
  reference value even though the running component currently does not.

## What was changed

- `~/Library/LaunchAgents/com.gmv.apprentice.plist`: unloaded from `launchd`
  and marked `Disabled: true` (a standard, documented launchd mechanism).
  `ProgramArguments`, `StartCalendarInterval`, and every other key are
  unchanged.
- `launchd`'s own per-user service database (`gui/<uid>`, not a file):
  `com.gmv.apprentice` was additionally disabled via
  `launchctl disable gui/$(id -u)/com.gmv.apprentice`. Confirmed via
  `launchctl print-disabled gui/$(id -u)` (`"com.gmv.apprentice" => disabled`)
  and `launchctl print gui/$(id -u)/com.gmv.apprentice` ("Could not find
  service... in domain" — not loaded). This is a second, independent,
  persistent disable layer, separate from the plist's own `Disabled` key, and
  is the more authoritative of the two on macOS: it survives reboots and any
  future plist edit that does not also re-enable the service at this layer.

## What was not changed

- `~/.gmv_core/01_RUNTIME/apprentice/apprentice_runtime.py` (git-tracked,
  commit `90d1942`) — untouched.
- `~/.gmv_scripts/run_apprentice_local.sh` — untouched (still resolves to the
  Core path from the prior REBASE 001 task).
- `~/.gmv_runtime/apprentice/apprentice_runtime.py` (rollback copy from the
  prior task) — untouched.
- Dropbox `99_SYSTEM/02_SERVICES/Apprentice/` (runtime + wrapper) — untouched.
- Dropbox `99_SYSTEM/10_APPRENTICE/` (state, reports, experience log) —
  untouched; all historical output preserved exactly as it was left on
  2026-07-01.
- The three previously-identified dormant wrappers
  (`~/.gmv_scripts/run_apprentice.sh`, `run_apprentice_launcher.sh`, Dropbox
  `Apprentice/run_apprentice.sh`) — untouched.

## Manual reactivation path

Two independent disable layers exist; both must be reversed — either one
alone is sufficient to keep the job from running.

1. Diagnose and fix the `PermissionError` on
   `.../99_SYSTEM/10_APPRENTICE/EXPERIENCE_LOG.md` (not investigated here —
   see the Apprentice archaeology report's evidence gaps).
2. Re-enable at the launchd database level:
   `launchctl enable gui/$(id -u)/com.gmv.apprentice`.
3. Remove the `Disabled` key (or set it `false`) in
   `~/Library/LaunchAgents/com.gmv.apprentice.plist`.
4. `launchctl load ~/Library/LaunchAgents/com.gmv.apprentice.plist`.
5. Confirm a successful, loaded run (e.g. via
   `launchctl print gui/$(id -u)/com.gmv.apprentice`) before relying on its
   output again.

No code, configuration content, or historical output was deleted to reach
this freeze.
