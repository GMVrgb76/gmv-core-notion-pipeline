# REBASE 001 — Interim Architectural State

Status: Interim report after Tasks 1–10
Recorded: 2026-07-12
Purpose: Canonical restart point for all future REBASE 001 work.

## 1. Executive Summary

REBASE 001 was opened to complete the migration of runtime authority from
Dropbox (`GMV_MASTER_SYSTEM`) into GMV Core (`~/.gmv_core`), under the rule
that runtime code belongs to Core and Dropbox is canonical Repository only —
never a canonical source for an executable runtime component. The work
proceeded as a sequence of strictly evidence-first tasks: classify Dropbox
executables, resolve duplicate/divergent implementations, formalize and
migrate the Apprentice runtime, and forensically audit two pre-existing
uncommitted working-tree modifications (`doctor_service.py`,
`11_CLI/gmv`) discovered outside any tracked task.

Work completed to date: the Apprentice runtime is migrated into git-tracked
Core and its scheduled execution is frozen (not decommissioned) with full
rollback documentation; an unexplained one-line regression in
`doctor_service.py` was identified and reverted; an unauthorized `gmv
constitution` CLI feature was identified, forensically audited, removed from
the live CLI, and formally frozen with a dedicated record.

Current architectural state: the working tree contains no unexplained
tracked modifications. Two components are formally frozen with rollback
paths (Apprentice runtime execution, Constitution CLI feature). One
previously-identified boundary-violation candidate (`realestate_runner.py`)
remains unresolved and is the recommended next task (§10).

## 2. Completed Tasks

### Task 1 — Complete Core migration
- Objective: begin Core migration under the rules that runtime belongs to
  Core, Dropbox is canonical repository only, backwards compatibility is
  preserved, and no authority change is made without evidence.
- Result: produced the initial migration report establishing the governing
  rules used by all subsequent REBASE 001 tasks.
- Disposition: complete; superseded operationally by Tasks 2–10, which
  carried out the migration work under these rules.
- Commit: none (report-only task).

### Task 2 — Classify Dropbox executables
- Objective: classify Dropbox executable components as AREA35, REPOSITORY,
  GMV_OS, BRIDGE, or UNKNOWN.
- Result: produced a classification report and confidence table.
- Disposition: complete. A numerical inconsistency between the Executive
  Summary ("6 files") and Section 4 (4 files) was identified and corrected
  in Task 3.
- Commit: none (report-only task).

### Task 3 — Resolve duplicate and divergent implementations
- Objective: resolve four groups (A–D) of duplicate/divergent
  implementations identified in Task 2.
- Result: corrected Task 2's numerical inconsistency (5 HIGH-confidence
  entries total; 4 both HIGH-confidence and not requiring PO decision,
  matching Section 4). Two pairs originally assumed divergent (Apprentice
  Core/Dropbox copy, daily-log Dropbox/`.gmv_scripts` copy) were confirmed
  byte-identical via SHA-256, correcting an earlier archaeology-phase
  mischaracterization. `realestate_runner.py` was identified as requiring a
  Project Owner decision due to a boundary violation, and left unresolved.
- Disposition: complete for the groups resolved; `realestate_runner.py`
  explicitly deferred, not resolved (see §6, §10).
- Commit: none (report-only task).

### Task 4 — Formalize Apprentice source/runtime authority
- Objective: formalize Apprentice source/runtime authority per an initial
  Project Owner decision (Dropbox canonical source, Core execution copy,
  fail-closed hash verification).
- Result: an edit implementing Dropbox-as-canonical-source hash-pinning in
  `~/.gmv_scripts/run_apprentice_local.sh` was proposed and rejected. The
  Project Owner corrected the governing rule: runtime code belongs to
  Core/local runtime; Dropbox must not be declared the canonical source of
  an executable runtime component. The task was revised to a read-only
  analysis under the corrected rule.
- Disposition: complete as a corrected, read-only report. No file was
  modified under the original (rejected) framing.
- Commit: none.

### Task 5 — Migrate Apprentice runtime into git-tracked Core
- Objective: copy the Apprentice runtime into `01_RUNTIME/apprentice/` under
  git-tracked Core, without registration, OID assignment, behavior change,
  path/schedule change, or deletion of any existing copy.
- Result: `01_RUNTIME/apprentice/apprentice_runtime.py` created, verified
  byte-identical (SHA-256) to the pre-existing `.gmv_runtime` and Dropbox
  copies both before and after the copy.
  `~/.gmv_scripts/run_apprentice_local.sh` updated to execute the new
  Core-tracked path.
- Disposition: complete.
- Commit: `90d1942` — "feat: migrate Apprentice runtime under git-tracked
  Core".

### Unnumbered — Apprentice Complete Archaeology and Conditional Patching
- Objective: full archaeology of the Apprentice runtime's operational
  history and failure state, followed by a conditional, verdict-driven
  patching phase.
- Result: established, from git-tracked primary-source evidence — Root 1's
  `13_HISTORY.md` and `01_RUNTIME/knowledge_engine.py`'s own
  `"former_codename": "apprentice"` field and Timeline entry — that
  Apprentice is a superseded predecessor of the Knowledge Engine (`SRV-000001`).
  Confirmed Apprentice has not completed a successful scheduled run since
  2026-07-01T14:30:50 (`PermissionError` on `EXPERIENCE_LOG.md`), and that no
  consumer of any Apprentice output exists anywhere in Core, `.gmv_scripts`,
  or Dropbox. Verdict: **FREEZE_AS_LEGACY**.
  `~/Library/LaunchAgents/com.gmv.apprentice.plist` was marked `Disabled:
  true`; `com.gmv.apprentice` was additionally disabled at the launchd
  per-user database level (`launchctl disable`), confirmed via
  `launchctl print-disabled`. No code, configuration content, or historical
  output was deleted.
- Disposition: complete. Recorded in `00_CONFIG/APPRENTICE_LEGACY_FREEZE.md`
  (§4).
- Commits: `113cd1f`, then `fd1b851` (same message, updated to document the
  persistent launchd disable state and full rollback procedure) — both
  "docs: freeze Apprentice as legacy predecessor of Knowledge Engine".

### Task 6 — Forensic archaeology of `doctor_service.py`
- Objective: strictly read-only investigation of an uncommitted one-line
  diff removing `slots=True` from the `CheckResult` dataclass.
- Result: the diff had no commit, blame, or reflog trace; the file's sole
  commit (`dc39670`) introduced `slots=True` and it was never removed by any
  recorded change. No functional justification, documentation, or test
  dependency was found for the removal.
- Disposition: **SAFE_TO_REVERT**.
- Commit: none (report-only task).

### Task 7 — Revert `doctor_service.py` to HEAD
- Objective: file-scoped revert of `doctor_service.py` to `HEAD` per Task
  6's disposition.
- Result: `git restore --source=HEAD -- 10_API/doctor_service.py` executed.
  Working-tree SHA-256 verified identical to `HEAD`'s blob hash after
  restore; `slots=True` confirmed present at line 29; file no longer
  appears in `git status`.
- Disposition: complete.
- Commit: none required — file returned to byte-identical match with `HEAD`.

### Task 8 — Forensic archaeology of `11_CLI/gmv`
- Objective: strictly read-only investigation of a 22-insertion,
  0-deletion uncommitted diff adding a `gmv constitution
  [status|check|graph]` command dispatching to the untracked
  `10_API/constitution_service.py`.
- Result: confirmed no commit exists for this feature anywhere in
  `11_CLI/gmv`'s otherwise one-subcommand-per-commit history; the feature
  is undocumented anywhere in the project; `constitution_service.py` is
  untracked, unregistered (no Service OID), untested, and reads Dropbox
  directly from a Core CLI path; `GMV_HANDOFF_S002_FINAL.md` independently
  lists `constitution_service.py` as a "Legacy component" excluded from
  Sprint 002 closure; a confirmed defect was found where invalid
  subcommands exit `0` instead of failing non-zero.
- Disposition: **FREEZE_UNAPPROVED_FEATURE**.
- Commit: none (report-only task).

### Task 9 — Freeze unapproved Constitution CLI feature
- Objective: file-scoped restore of `11_CLI/gmv` to `HEAD`, removing the
  unauthorized `constitution` CLI wiring while preserving
  `constitution_service.py` and both backup files unchanged.
- Result: `git restore --source=HEAD -- 11_CLI/gmv` executed. Working-tree
  SHA-256 verified identical to `HEAD`'s blob hash after restore. `gmv
  constitution` no longer exposed by the live CLI. All three historical
  files (`constitution_service.py`,
  `constitution_service.py.bak_20260709_220335`,
  `gmv.bak_20260709_220211`) confirmed hash-identical before and after.
- Disposition: complete.
- Commit: none required — file returned to byte-identical match with
  `HEAD`.

### Task 10 — Document Constitution CLI feature freeze
- Objective: create a minimal factual freeze record for the unapproved
  Constitution CLI feature, since no existing document was suitable.
- Result: `00_CONFIG/CONSTITUTION_CLI_FEATURE_FREEZE.md` created, recording
  status, historical implementation, reason for freeze, current operational
  state, reactivation conditions, preservation hashes, and a rollback note
  stating reactivation requires a new approved implementation task.
- Disposition: complete.
- Commit: `e8e9459` — "docs: freeze unapproved Constitution CLI feature".

## 3. Architectural Decisions Confirmed

Decisions below are supported by evidence gathered across Tasks 1–10 and the
unnumbered Apprentice archaeology task. No new principle is introduced here.

- **Runtime belongs to Core.** Established in Task 1; applied concretely in
  Task 5 (Apprentice runtime migrated into `01_RUNTIME/apprentice/` under
  git-tracked Core) and in the Task 4 correction (Dropbox rejected as
  canonical source for an executable runtime component).
- **Dropbox is the canonical Repository.** Established in Task 1; Dropbox
  remains the source for constitution documents, historical
  Apprentice/Knowledge Engine records, and other non-runtime material
  throughout Tasks 2–10.
- **Repository is not Runtime.** Confirmed by the Task 4 correction and by
  Task 8's finding that `constitution_service.py` reading Dropbox directly
  from a Core CLI path is a boundary violation and a stated reason for its
  freeze (Task 8 §3, Task 10 §3).
- **Freeze is preferred over deletion.** Applied in the Apprentice
  disposition (FREEZE_AS_LEGACY, not decommission — all code, configuration,
  and historical output preserved) and in the Constitution CLI feature
  disposition (FREEZE_UNAPPROVED_FEATURE — `constitution_service.py` and
  both backup files preserved untouched rather than deleted).
- **Every runtime requires authority.** Confirmed by Task 8's finding that
  `constitution_service.py` has no Service OID, no registration in
  `SERVICE_SPECIFICATION.md`, and no test coverage, contributing directly to
  its freeze.
- **Working-tree archaeology precedes implementation.** Applied identically
  in Task 6→7 (`doctor_service.py`) and Task 8→9 (`11_CLI/gmv`): in both
  cases, a report-only forensic task preceded any file modification, and no
  modification occurred until a disposition was explicitly reported and
  authorized in a separate turn.
- **Runtime/Repository boundary is enforced.** Confirmed by the removal of
  the `constitution` CLI wiring (Task 9), which was the only command in
  `11_CLI/gmv` found to read Dropbox directly (Task 8 §4).

## 4. Frozen Components

### Apprentice (`com.gmv.apprentice` LaunchAgent and runtime)
- Reason: superseded by Knowledge Engine (`SRV-000001`), which self-declares
  `"former_codename": "apprentice"`; no successful scheduled run since
  2026-07-01T14:30:50 (`PermissionError` on `EXPERIENCE_LOG.md`); no
  consumer of any Apprentice output found.
- Current state: LaunchAgent disabled at two independent layers (plist
  `Disabled: true`, and `launchctl disable` at the launchd per-user
  database level); not loaded. Runtime code preserved unchanged in Core
  (`01_RUNTIME/apprentice/apprentice_runtime.py`, commit `90d1942`),
  `.gmv_scripts`, `.gmv_runtime`, and Dropbox.
- Reactivation conditions: diagnose and fix the `EXPERIENCE_LOG.md`
  `PermissionError`; re-enable at the launchd database level
  (`launchctl enable`); remove/clear the plist `Disabled` key; reload the
  LaunchAgent; confirm a successful run before relying on its output again.
- Document recording the freeze: `00_CONFIG/APPRENTICE_LEGACY_FREEZE.md`.

### Constitution CLI feature (`gmv constitution [status|check|graph]`)
- Reason: undocumented anywhere in the project; unregistered (no Service
  OID); untested; reads Dropbox directly from a Core CLI path (Runtime/
  Repository boundary violation); confirmed invalid-subcommand exit-code
  defect; explicitly named as a "Legacy component" excluded from Sprint 002
  closure in `GMV_HANDOFF_S002_FINAL.md`.
- Current state: `11_CLI/gmv` restored to byte-identical match with `HEAD`;
  `gmv constitution` not exposed by the live CLI.
  `10_API/constitution_service.py` and its `.bak` file, and
  `11_CLI/gmv.bak_20260709_220211`, preserved untouched and untracked.
- Reactivation conditions: explicit Project Owner approval; a documented
  architectural role; a resolved Runtime/Repository boundary decision;
  Service registration or an explicit documented exception; tests for
  `status`/`check`/`graph` and invalid inputs; explicit non-zero failure
  semantics for invalid subcommands; review of constitution source
  authority.
- Document recording the freeze: `00_CONFIG/CONSTITUTION_CLI_FEATURE_FREEZE.md`.

## 5. Repository Cleanup Achieved

- Unexplained tracked modifications removed: `doctor_service.py`'s
  unexplained `slots=True` removal (Task 7); `11_CLI/gmv`'s unauthorized
  `constitution` CLI wiring (Task 9).
- Reverted files: `10_API/doctor_service.py`, `11_CLI/gmv` — both confirmed
  byte-identical to `HEAD` after restore; neither required a commit.
- Documented freezes: `00_CONFIG/APPRENTICE_LEGACY_FREEZE.md`,
  `00_CONFIG/CONSTITUTION_CLI_FEATURE_FREEZE.md`.
- Remaining tracked modifications: none. `git status` shows no modified
  tracked file as of this report. Untracked files present in the working
  tree (e.g. `10_API/constitution_service.py` and its `.bak`,
  `11_CLI/gmv.bak_20260709_220211`, and other pre-existing untracked
  material such as `00_CONFIG/GMV_POLICY.md`, `99_SYSTEM/`, `archive/`,
  `scripts/*.sh`) are outside this report's scope and were not created,
  altered, or evaluated by Tasks 1–10 beyond the specific files named above.

## 6. Remaining REBASE Backlog

### Priority: High
- **`realestate_runner.py`** (Dropbox:
  `99_SYSTEM/03_DIRECTORS/realestate_runner.py`).
  - Current evidence: identified in Task 3 as requiring a Project Owner
    decision due to a boundary violation (the specific nature of the
    violation was noted but not resolved in Task 3).
  - Next required investigation: forensic archaeology of
    `realestate_runner.py` (see §10).
  - Implementation: blocked pending that archaeology and a Project Owner
    decision.

### Priority: Unranked / not yet scoped
- No other unresolved REBASE 001 items have been identified through Task
  10. Task 2's classification report and Task 3's resolution report may
  contain additional lower-confidence entries not yet re-examined under
  REBASE 001; this report does not restate them, as doing so would exceed
  what Tasks 1–10 established as resolved or explicitly deferred.

## 7. Runtime Classification Status

- Already classified: Dropbox executables classified in Task 2
  (AREA35/REPOSITORY/GMV_OS/BRIDGE/UNKNOWN); duplicate/divergent groups
  resolved in Task 3, except `realestate_runner.py`.
- Frozen: Apprentice runtime (execution); Constitution CLI feature
  (CLI wiring only — underlying service preserved, not executed).
- Migrated: Apprentice runtime, copied into git-tracked Core
  (`01_RUNTIME/apprentice/`, commit `90d1942`).
- Pending: `realestate_runner.py` (boundary-violation decision deferred
  from Task 3).
- Unresolved: none additional identified within the scope of Tasks 1–10.

## 8. Authority Map

- **Core:** `01_RUNTIME/apprentice/apprentice_runtime.py` (git-tracked,
  commit `90d1942`); `10_API/doctor_service.py`; `11_CLI/gmv` — all
  byte-identical to `HEAD`, under Core authority.
- **Repository:** Dropbox `GMV_MASTER_SYSTEM` — canonical for
  non-runtime material (constitution documents, historical Apprentice
  state/reports, Knowledge Engine source records).
- **Legacy:** Apprentice runtime and LaunchAgent (superseded by Knowledge
  Engine, `SRV-000001`).
- **Frozen:** Apprentice scheduled execution (two-layer launchd disable);
  Constitution CLI feature (CLI wiring removed from `11_CLI/gmv`).
- **Historical:** `10_API/constitution_service.py`,
  `10_API/constitution_service.py.bak_20260709_220335`,
  `11_CLI/gmv.bak_20260709_220211` — preserved, untracked, no Service
  authority.
- **Pending:** `realestate_runner.py` — classification and boundary
  decision not yet resolved.

## 9. Risks Remaining

- `realestate_runner.py`'s boundary violation is unresolved; its nature and
  severity have not been forensically established beyond Task 3's
  identification that a Project Owner decision is required.
- The Apprentice reactivation path depends on diagnosing a live
  `PermissionError` (`EXPERIENCE_LOG.md`) that has not been investigated
  beyond confirming its persistence since 2026-07-01.
- Untracked material outside the scope of Tasks 1–10 (e.g. `99_SYSTEM/`,
  `archive/`, various root-level `.md` files, `scripts/*.sh`) remains
  present in the working tree; its classification status has not been
  established or re-established under REBASE 001.

## 10. Recommended Next Task

**Forensic archaeology of `realestate_runner.py`**
(`Library/CloudStorage/Dropbox/GMV_MASTER_SYSTEM/99_SYSTEM/03_DIRECTORS/realestate_runner.py`),
following the same strictly evidence-first, report-only pattern used for
Apprentice (Task 4→5) and the Constitution CLI feature (Task 8→9): gather
git/documentary/functional evidence, determine the specific nature of the
boundary violation identified in Task 3, and report a disposition — without
implementing any change in that same task.

No implementation is begun here.
