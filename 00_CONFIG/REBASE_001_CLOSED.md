# REBASE 001 — Closure Record

Status: CLOSED
Closed: 2026-07-12

## Objective

REBASE 001 was opened to complete the migration of runtime authority from
Dropbox (`GMV_MASTER_SYSTEM`) into GMV Core (`~/.gmv_core`), under the rule
that runtime code belongs to Core and Dropbox is canonical Repository only —
never a canonical source for an executable runtime component. It began as a
Core-migration effort (Task 1) and expanded, on discovery, to cover two
pre-existing uncommitted working-tree modifications found outside any
tracked task (`doctor_service.py`, `11_CLI/gmv`).

## Scope Completed

- **Task 1** — Complete Core migration: established the governing rules used
  by all subsequent work (runtime belongs to Core; Dropbox is canonical
  repository only; backwards compatibility preserved; no authority change
  without evidence).
- **Task 2** — Classify Dropbox executables: produced the AREA35/REPOSITORY/
  GMV_OS/BRIDGE/UNKNOWN classification and confidence table.
- **Task 3** — Resolve duplicate and divergent implementations: corrected
  Task 2's numerical inconsistency; confirmed the Apprentice and daily-log
  duplicate pairs were byte-identical (not divergent, as originally
  assumed); deferred `realestate_runner.py` pending a Project Owner
  decision.
- **Task 4** — Formalize Apprentice source/runtime authority: an initial
  Dropbox-as-canonical-source proposal was rejected by the Project Owner,
  who corrected the governing rule (runtime code belongs to Core/local
  runtime; Dropbox must not be declared canonical source for an executable
  runtime component); the task was revised to a read-only report under the
  corrected rule.
- **Task 5** — Migrate Apprentice runtime into git-tracked Core: copied
  `apprentice_runtime.py` into `01_RUNTIME/apprentice/`, verified
  byte-identical (SHA-256) to all prior copies, committed as `90d1942`.
- **Apprentice Complete Archaeology and Conditional Patching** (unnumbered):
  established, from git-tracked primary-source evidence, that Apprentice is
  superseded by the Knowledge Engine (`SRV-000001`); verdict
  `FREEZE_AS_LEGACY`; the LaunchAgent was disabled at two independent
  layers; committed as `113cd1f`/`fd1b851`.
- **Task 6** — Forensic archaeology of `doctor_service.py`: identified an
  unexplained, untraceable one-line `slots=True` removal; verdict
  `SAFE_TO_REVERT`.
- **Task 7** — Revert `doctor_service.py` to `HEAD`: file-scoped
  `git restore`; verified byte-identical to `HEAD`; no commit required.
- **Task 8** — Forensic archaeology of `11_CLI/gmv`: identified an
  unauthorized, never-committed `gmv constitution` CLI addition dispatching
  to an unregistered, undocumented, untested service reading Dropbox
  directly; verdict `FREEZE_UNAPPROVED_FEATURE`.
- **Task 9** — Freeze unapproved Constitution CLI feature: file-scoped
  `git restore` of `11_CLI/gmv` to `HEAD`; verified byte-identical; all
  historical files preserved; no commit required.
- **Task 10** — Document Constitution CLI feature freeze: created
  `00_CONFIG/CONSTITUTION_CLI_FEATURE_FREEZE.md`; committed as `e8e9459`.
- **Task 11** — Interim architectural report: created
  `00_CONFIG/REBASE_001_INTERIM_STATE.md` as the canonical restart point
  after Tasks 1–10; committed as `a2102a5`.
- **Task 12** — Forensic archaeology of `realestate_runner.py`: established
  the Real Estate Director/Recursion layer as a dormant, unregistered,
  unconsumed prototype orchestrator predating Core, with a confirmed
  Runtime/Repository boundary violation and a Market Engine dependency that
  has since diverged from an independently Core-governed copy
  (`SRV-000004`); verdict `FREEZE_AS_LEGACY`.
- **Task 13** — Document Real Estate legacy freeze: created
  `00_CONFIG/REALESTATE_LEGACY_FREEZE.md`; committed as `ac17e9b`.

## Major Architectural Decisions

Recorded only where evidence-backed within REBASE 001:

- **Runtime belongs to Core.** Established in Task 1; applied in Task 5
  (Apprentice runtime migrated into `01_RUNTIME/apprentice/`) and in the
  Task 4 correction.
- **Dropbox is Repository.** Established in Task 1; confirmed as the
  correct location for non-runtime material throughout Tasks 2–13.
- **Runtime ≠ Repository.** Confirmed directly by three separate,
  independent findings: the rejected Task 4 proposal, the Constitution CLI
  feature's direct Dropbox read (Task 8), and the Real Estate orchestration
  layer's Dropbox-resident execution and state-write behavior (Task 12).
- **Freeze before deletion.** Applied identically to all three frozen
  components (Apprentice, Constitution CLI, Real Estate orchestration): in
  every case, code and historical output were preserved, not removed.
- **Authority before execution.** Confirmed by Task 8's and Task 12's
  shared finding pattern: no Service OID, no registration, no test
  coverage — cited as the primary reasons for freezing rather than running
  or migrating either component.
- **Archaeology before implementation.** Applied identically in every
  action pair across REBASE 001: Task 6→7, Task 8→9, Task 12→13 — a
  report-only forensic task always preceded any file modification, and no
  modification occurred until a disposition was explicitly reported and
  separately authorized.

## Components Frozen

### Apprentice
- Disposition: `FREEZE_AS_LEGACY`.
- Freeze document: `00_CONFIG/APPRENTICE_LEGACY_FREEZE.md`.
- Reactivation conditions: diagnose and fix the `EXPERIENCE_LOG.md`
  `PermissionError`; re-enable at the launchd database level
  (`launchctl enable`); remove/clear the plist `Disabled` key; reload the
  LaunchAgent; confirm a successful run before relying on its output again.

### Constitution CLI
- Disposition: `FREEZE_UNAPPROVED_FEATURE`.
- Freeze document: `00_CONFIG/CONSTITUTION_CLI_FEATURE_FREEZE.md`.
- Reactivation conditions: explicit Project Owner approval; a documented
  architectural role; a resolved Runtime/Repository boundary; Service
  registration or an explicit documented exception; tests for
  `status`/`check`/`graph` and invalid inputs; explicit non-zero failure
  semantics for invalid subcommands; review of constitution source
  authority.

### Real Estate orchestration
- Disposition: `FREEZE_AS_LEGACY`.
- Freeze document: `00_CONFIG/REALESTATE_LEGACY_FREEZE.md`.
- Reactivation conditions: Project Owner approval; Runtime relocation into
  Core; Service registration; Runtime governance; Runtime/Repository
  boundary compliance; test coverage; review of Market Engine integration
  (given the confirmed divergence between the Dropbox copy and Core's
  hash-pinned `SRV-000004` copy).

## Repository State

- Tracked modifications resolved: `doctor_service.py` (Task 7) and
  `11_CLI/gmv` (Task 9) both restored to byte-identical match with `HEAD`;
  neither required a commit.
- Unexplained edits eliminated: both of the above were unexplained,
  untraceable working-tree modifications discovered outside any tracked
  task; both were forensically audited before any change was made, and
  both are now fully resolved.
- Repository consistency restored: as of this closure, `git status` shows
  no modified tracked file. Six commits were made during REBASE 001
  (`90d1942`, `113cd1f`, `fd1b851`, `e8e9459`, `a2102a5`, `ac17e9b`), each
  scoped to exactly one file or one coherent change, each preceded by a
  report-only investigation.

## Architectural Outcome

GMV Core now has one migrated, git-tracked runtime component
(`01_RUNTIME/apprentice/apprentice_runtime.py`) and three formally frozen,
evidence-documented legacy components, each with an explicit reactivation
path rather than an ambiguous or silently-abandoned state. The working
tree contains no unexplained tracked modifications. The Runtime/Repository
boundary principle has been applied consistently across three independent
cases (Apprentice, Constitution CLI, Real Estate orchestration), each
surfaced through the same archaeology-before-implementation discipline.
One classification item remains open: `realestate_runner.py`'s dependency,
`market_engine.py`, exists in two divergent forms — an ungoverned Dropbox
copy and an independently Core-governed, hash-pinned copy (`SRV-000004`) —
a fact discovered during Task 12 and not yet resolved.

## Lessons Learned

- Uncommitted working-tree modifications can persist silently outside any
  tracked task; both instances found during REBASE 001 (`doctor_service.py`,
  `11_CLI/gmv`) were discovered only because the working tree was
  inspected as a matter of course, not because either was reported.
- Apparent duplication is not always divergence: two file pairs assumed
  divergent in earlier archaeology phases (Apprentice, daily-log) were
  confirmed byte-identical by SHA-256 in Task 3 — hash verification, not
  visual or contextual inspection, was the deciding evidence in both cases.
- Partial migration can outpace its coordinating layer: Market Engine was
  independently migrated into Core governance (`SRV-000004`) without any
  corresponding update to the Real Estate Director/Runner that was built
  to coordinate it, producing two divergent copies of the same engine
  (Task 12).
- Freezing, not deleting, was sufficient in every case encountered: no
  component examined during REBASE 001 required decommissioning: all three
  frozen components retained plausible reference or reactivation value
  once their live/authoritative status was removed.

## Exit Criteria

REBASE 001 is considered complete because: every task opened was closed
with either a completed action or an explicit, evidence-backed
disposition; both unexplained tracked modifications were resolved; all
three components requiring a freeze decision were frozen and documented;
the working tree is clean of unexplained tracked changes; and the one
remaining open item (`realestate_runner.py`'s Market Engine divergence) is
explicitly captured as backlog rather than left implicit, per
`00_CONFIG/REALESTATE_LEGACY_FREEZE.md` §6.
