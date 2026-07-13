# GMV Project Status — Operational Ledger

## Operational Rules

1. `PROJECT_STATUS.md` is the single operational ledger for this project.
2. Every completed task updates `PROJECT_STATUS.md`.
3. No task is considered complete until `PROJECT_STATUS.md` has been updated.
4. `PROJECT_STATUS.md` records facts only. No speculation. No architectural
   opinions. No implementation proposals.
5. Historical records remain append-only. Corrections are added as new
   entries. Previous history is never silently rewritten.
6. Every future task, without exception, must end by updating
   `PROJECT_STATUS.md`, appending the fixed "PROJECT STATUS UPDATE" block
   defined in the Task Completion Protocol below.
7. `PROJECT_STATUS.md` is the unique operational source of truth for
   current project state. ADRs remain the authoritative architectural
   decision records; freeze documents remain the authoritative component
   lifecycle records. This document indexes and summarizes them — it never
   replaces or restates their content.
8. Historical reports (archaeology reports, task outputs) are immutable
   once completed and are never edited after completion. Corrections take
   the form of new entries, per Rule 5.
9. Every future task must verify that `PROJECT_STATUS.md` has been updated
   before declaring the task complete.

This document is not an ADR, not an archaeology report, and not a handoff.
It is a living ledger. ADRs, freeze records, and archaeology reports remain
the source of full reasoning; this document only tracks current state,
active decisions, and the chronological record of what happened.

---

## Task Completion Protocol

Every future task must end its own output with a fixed "PROJECT STATUS
UPDATE" block, and must reflect that same information here (§1 Dashboard,
and §4 Timeline for the completed entry) before the task is declared
complete.

Required block, verbatim field set:

```
## PROJECT STATUS UPDATE

- Current Phase: <...>
- Current Approved Task: <...>
- Tasks Completed: <...>
- Architecture Changed (YES/NO): <...>
- ADR Created: <...>
- Freeze Created: <...>
- Documents Updated: <...>
- Next Approved Task: <...>
- Known Risks: <...>
- Working Tree Status: <...>
- Commit: <...>
```

A task is not complete until this block has been produced in the task's
own report and `PROJECT_STATUS.md` has been updated to match it.

---

## 1. Project Dashboard

*Current state only. For history, see §4. For architectural reasoning, see §2 and the referenced documents.*

- **Current Phase:** Stabilization — exit criteria operationally satisfied; Stabilization not yet formally closed.
- **Current Objective:** Formal closure of Stabilization and opening of GMV Core Development.
- **Last Completed Task:** Stabilization — Final Blocker Resolution: Provisional Suspension of `~/GMV_CORE` Live Automations (`00_CONFIG/GMV_RESEARCH_LAB_AUTOMATIONS_SUSPENSION.md`). Both `com.gmv.dailybrief` and `com.gmv.morningbrief.email` disabled and unloaded; `~/GMV_CORE` preserved as `PROTOTYPE_ROOT`, disposition `PRESERVE_PENDING_REVIEW`.
- **Next Approved Task:** Formal closure of Stabilization and opening of GMV Core Development.
- **Last Commit:** this task's commit (see `git log`) — "docs: suspend GMV Research Lab automations".
- **Repository Status:** Clean — no unexplained tracked modifications as of the last System Authority Audit (Post-REBASE 001 Task 3, 2026-07-13). Untracked material remains present (see §7, Automation Review) but is inventoried, not unexplained.
- **Runtime Status:** One native Core service (`SRV-000001` Knowledge Engine) and three compatibility services (`SRV-000002` Morning Brief, `SRV-000003` Daily Log, `SRV-000004` Market Engine) are registered and active. Four components are formally frozen (Apprentice, Constitution CLI feature, Real Estate orchestration, GMV Engine/Decision Engine automation). Fenix, `com.gmv.dailybrief`, and `com.gmv.morningbrief.email` are provisionally suspended pending technical review (operational suspension only — none classified as legacy/frozen/rejected). No live, ungoverned, scheduled automation remains loaded.
- **Current Risks:** See §6, Open Questions and §7, Project Health.
- **Current Blockers:** None. The sole remaining Stabilization BLOCKER (live ungoverned automation) is resolved — live ungoverned automation blocker count is now zero. Stabilization exit criteria are operationally satisfied; formal closure has not yet been performed and requires a dedicated closure task.
- **Development Readiness:** Ready for controlled, evidence-first work (see §7).
- **Last Updated:** 2026-07-13.

---

## 2. Permanent Architectural Decisions

*Only active decisions. Full reasoning lives in the referenced ADRs/freeze records — never duplicated here.*

| Category | Decision | Reference |
|---|---|---|
| **Repository** | Dropbox (`GMV_MASTER_SYSTEM`) is the canonical Repository for non-runtime material; it is never the canonical source for executable runtime code. | `00_CONFIG/REBASE_001_CLOSED.md` §"Major Architectural Decisions" |
| **Runtime** | Runtime code belongs to GMV Core (`~/.gmv_core`, git-tracked). | `00_CONFIG/REBASE_001_CLOSED.md` §"Major Architectural Decisions" |
| **Compatibility** | Legacy engines execute through a hash-pinned Compatibility Layer (`10_API/gmv_compatibility.py`) with fail-closed release verification. Registered services: `SRV-000002` Morning Brief, `SRV-000003` Daily Log, `SRV-000004` Market Engine. | `00_CONFIG/SERVICE_SPECIFICATION.md`, `00_CONFIG/LEGACY_ENGINE_INVENTORY.md` |
| **Legacy** | Frozen, preserved, not deleted: Apprentice; Constitution CLI feature; Real Estate orchestration (`realestate_runner.py` family); Dropbox `market_engine.py` (reclassified `HISTORICAL_BEHAVIOUR_ONLY`); GMV Engine/Decision Engine automation. | `00_CONFIG/APPRENTICE_LEGACY_FREEZE.md`, `00_CONFIG/CONSTITUTION_CLI_FEATURE_FREEZE.md`, `00_CONFIG/REALESTATE_LEGACY_FREEZE.md`, `00_CONFIG/ADR_MARKET_ENGINE_RENDERING_DIVERGENCE.md`, `00_CONFIG/GMV_ENGINE_DECISION_AUTOMATION_FREEZE.md` |
| **Experimental** | A Local Coding Engine (v0, Draft status) exists as a separate, explicitly-scoped, read-only-first initiative. | `00_CONFIG/LOCAL_CODING_ENGINE.md` |
| **Primary Engineering** | Knowledge Engine (`SRV-000001`, `01_RUNTIME/knowledge_engine.py`) is the native Core runtime and the successor to the frozen Apprentice concept. | `00_CONFIG/APPRENTICE_LEGACY_FREEZE.md` |
| **Independent Validation** | Divergent implementations are validated via isolated, `mktemp`-based fixture execution — never against production data — before any output-contract decision is made. | Post-REBASE 001 Task 2 (methodology; report only, no standalone document) |

---

## 3. Active Work

*Current work queue. Status reflects actual authorization state, not aspiration.*

| Item | Status | Owner | Priority | Dependencies |
|---|---|---|---|---|
| Formal closure of Stabilization | APPROVED — sole remaining action; exit criteria operationally satisfied | Unassigned | High | None |
| Fenix final disposition (`com.gmv.fenix` / `gmv_fenix_engine.sh`) | PROVISIONALLY SUSPENDED — PENDING TECHNICAL REVIEW (Post-REBASE 001 Task 7; see `00_CONFIG/FENIX_PROVISIONAL_SUSPENSION.md` for minimum requirements) | Unassigned | Medium (operational exposure removed; final disposition not urgent) | None |
| `com.gmv.dailybrief` / `com.gmv.morningbrief.email` final disposition | PROVISIONALLY SUSPENDED — PENDING TECHNICAL REVIEW (this task; see `00_CONFIG/GMV_RESEARCH_LAB_AUTOMATIONS_SUSPENSION.md` for minimum requirements) | Unassigned | Medium (operational exposure removed; final disposition not urgent) | None |
| `~/GMV_CORE` root — broader classification beyond its two (now suspended) live LaunchAgents | IDENTIFIED, unscheduled; root verdict `PRESERVE_PENDING_REVIEW`; ~40 further scripts and the `GMV_REDUCED` subsystem not yet audited | Unassigned | Low | None |
| Classify Dropbox `property_engine.py` | IDENTIFIED, unscheduled (open since REBASE 001 Task 3) | Unassigned | Medium | None |
| Archaeology of `gmv_watchdog.sh` and `gmv_orchestrator.sh` | IDENTIFIED, unscheduled (flagged by System Authority Audit and GMV Engine/Fenix archaeology as sharing the same governance gap) | Unassigned | Medium | None |
| Diagnose persistent `gmv status` CLI failure under `launchd` | IDENTIFIED, unscheduled (evidence gap in Post-REBASE 001 Tasks 4 and 6) | Unassigned | Medium | None |

---

## 4. Timeline

*Append-only. Never rewritten. Corrections are added as new entries below, not edits to existing ones.*

| Date | Task | Decision | Documents | Commit | Next task |
|---|---|---|---|---|---|
| 2026-07-12 | REBASE 001 Tasks 1–4 (Core migration scope; Dropbox executable classification; duplicate/divergent resolution; Apprentice authority formalization, revised) | Governing principles established: Runtime belongs to Core, Dropbox is Repository | Report-only | none | Migrate Apprentice runtime |
| 2026-07-12 | REBASE 001 Task 5 — Migrate Apprentice runtime into git-tracked Core | Complete | `01_RUNTIME/apprentice/apprentice_runtime.py` | `90d1942` | Apprentice complete archaeology |
| 2026-07-12 | Apprentice Complete Archaeology and Conditional Patching (unnumbered) | `FREEZE_AS_LEGACY` | `00_CONFIG/APPRENTICE_LEGACY_FREEZE.md` | `113cd1f` | Update freeze doc with launchd disable detail |
| 2026-07-12 | Apprentice freeze record update (launchd persistent-disable documentation) | `FREEZE_AS_LEGACY` (unchanged, documented more fully) | `00_CONFIG/APPRENTICE_LEGACY_FREEZE.md` | `fd1b851` | doctor_service.py archaeology |
| 2026-07-12 | REBASE 001 Tasks 6–7 — Forensic archaeology and revert of `doctor_service.py` | `SAFE_TO_REVERT`; reverted to `HEAD` | Report-only; no commit (file returned byte-identical to `HEAD`) | none | `11_CLI/gmv` archaeology |
| 2026-07-12 | REBASE 001 Tasks 8–9 — Forensic archaeology and revert of `11_CLI/gmv` (Constitution CLI feature) | `FREEZE_UNAPPROVED_FEATURE`; CLI wiring reverted to `HEAD` | Report-only; no commit (file returned byte-identical to `HEAD`) | none | Document Constitution CLI freeze |
| 2026-07-12 | REBASE 001 Task 10 — Document Constitution CLI feature freeze | Complete | `00_CONFIG/CONSTITUTION_CLI_FEATURE_FREEZE.md` | `e8e9459` | Interim architectural report |
| 2026-07-12 | REBASE 001 Task 11 — Interim architectural report | Complete | `00_CONFIG/REBASE_001_INTERIM_STATE.md` | `a2102a5` | `realestate_runner.py` archaeology |
| 2026-07-12 | REBASE 001 Task 12 — Forensic archaeology of `realestate_runner.py` | `FREEZE_AS_LEGACY` | Report-only | none | Document Real Estate legacy freeze |
| 2026-07-12 | REBASE 001 Task 13 — Document Real Estate legacy freeze | Complete | `00_CONFIG/REALESTATE_LEGACY_FREEZE.md` | `ac17e9b` | Close REBASE 001 |
| 2026-07-12 | REBASE 001 Closure | Complete | `00_CONFIG/REBASE_001_CLOSED.md`, `00_CONFIG/WHAT_TO_DO_NEXT.md` | `2d13567` | Market Engine divergence archaeology |
| 2026-07-13 | Post-REBASE 001 Task 1 — Forensic archaeology of `market_engine.py` divergence | `CORE_CANONICAL_DROPBOX_FREEZE` | Report-only | none | Isolated functional validation |
| 2026-07-13 | Post-REBASE 001 Task 2 — Isolated functional validation of Market Engine release (corrected, 5-scenario) | `CORE_OUTPUT_REQUIRES_OWNER_DECISION` | Report-only | none | Project Owner decision |
| 2026-07-13 | Project Owner Decision — Market Engine rendering divergence | `INTENTIONAL_IMPROVEMENT`; Dropbox source reclassified `HISTORICAL_BEHAVIOUR_ONLY` | `00_CONFIG/ADR_MARKET_ENGINE_RENDERING_DIVERGENCE.md`, `00_CONFIG/LEGACY_ENGINE_INVENTORY.md` (updated) | `e308c1c` | System Authority Audit |
| 2026-07-13 | Post-REBASE 001 Task 3 — System Authority Audit | Complete; surfaced the untracked `scripts/gmv_*.sh` automation family and the separate `~/GMV_CORE` root | Report-only | none | GMV Engine/Decision Engine archaeology |
| 2026-07-13 | Post-REBASE 001 Task 4 — Forensic archaeology of GMV Engine / Decision Engine chain | `FREEZE_UNAPPROVED_AUTOMATION` | Report-only | none | Project Owner decision |
| 2026-07-13 | Post-REBASE 001 Task 5 — Freeze GMV Engine / Decision Engine automation | Complete; `com.gmv.engine` disabled at both launchd layers | `00_CONFIG/GMV_ENGINE_DECISION_AUTOMATION_FREEZE.md` | `ab71c7e` | Fenix archaeology |
| 2026-07-13 | Post-REBASE 001 Task 6 — Forensic archaeology of Fenix automation | `FREEZE_UNAPPROVED_AUTOMATION` (recommended; not yet authorized) | Report-only | none | Freeze `com.gmv.fenix` (pending approval) |
| 2026-07-13 | Post-REBASE 001 Meta Task — Create Project Operational Ledger | This document created | `00_CONFIG/PROJECT_STATUS.md` | none (not staged/committed per task instruction) | Per Next Approved Task above |
| 2026-07-13 | Meta Task — Establish Permanent Project Governance | Task Completion Protocol added (Rules 6–9, "PROJECT STATUS UPDATE" block) | `00_CONFIG/PROJECT_STATUS.md` | `e29395d` | Create `SYSTEM_MAP.md` |
| 2026-07-13 | Post-REBASE 001 Meta Task — Create `SYSTEM_MAP.md` | Permanent architectural map created from existing evidence only; no new architecture inferred | `00_CONFIG/SYSTEM_MAP.md`, `00_CONFIG/PROJECT_STATUS.md` | `cd239fb` | Per Next Approved Task above |
| 2026-07-13 | Meta Task — Define Stabilization Exit Criteria | `NEAR COMPLETION` — 2 BLOCKER items remain (freeze `com.gmv.fenix`; archaeology/disposition of `~/GMV_CORE`'s two loaded LaunchAgents); all other remaining work classified `POST-STABILIZATION` or `HISTORICAL` | `00_CONFIG/STABILIZATION_EXIT_CRITERIA.md`, `00_CONFIG/PROJECT_STATUS.md` | this commit (see `git log`) | Freeze `com.gmv.fenix` (pending approval); archaeology of `~/GMV_CORE`'s live LaunchAgents |
| 2026-07-13 | Post-REBASE 001 Task 7 — Provisional Suspension of Fenix Pending Technical Review | `PROVISIONALLY SUSPENDED — PENDING TECHNICAL REVIEW` (operational suspension only; no final architectural disposition); `com.gmv.fenix` disabled at both launchd layers; blocker count reduced from 2 to 1 | `00_CONFIG/FENIX_PROVISIONAL_SUSPENSION.md`, `00_CONFIG/PROJECT_STATUS.md` | `345ca3e` | Forensic archaeology of `~/GMV_CORE`, `com.gmv.morningbrief.email`, `com.gmv.dailybrief` |
| 2026-07-13 | Stabilization — Final Blocker Task: Forensic Archaeology of `~/GMV_CORE` and its two live automations | Report-only. Root: `PROTOTYPE_ROOT` (relationship classification), `PRESERVE_PENDING_REVIEW` (disposition). `morning_os.py`: `PROVISIONALLY_SUSPEND` (7/7 runs failed, exit 1; live external-email capability sharing governed SMTP infrastructure). `dropbox_daily_brief.py`: `PROVISIONALLY_SUSPEND` (6/6 runs failed, `EX_CONFIG` 78, from a confirmed unescaped-`&&` plist XML defect, independently reproduced from the 2026-07-10 archaeology pass). No operational modification performed. | Report-only (no new document created) | not staged/committed, per task instruction | Provisional suspension of `com.gmv.morningbrief.email` and `com.gmv.dailybrief`, pending Project Owner authorization |
| 2026-07-13 | Stabilization — Final Blocker Resolution: Provisional Suspension of `~/GMV_CORE` Live Automations | `PROVISIONALLY SUSPENDED` for both `com.gmv.dailybrief` and `com.gmv.morningbrief.email` (operational suspension only; `~/GMV_CORE` preserved as `PROTOTYPE_ROOT`, `PRESERVE_PENDING_REVIEW`, not classified as legacy). `com.gmv.morningbrief.email` disabled at both plist and launchd-database layers; `com.gmv.dailybrief` disabled at the launchd-database layer only — its plist could not be safely edited due to its pre-existing, unrepaired XML defect (recorded as a limitation, not fixed). Live ungoverned automation blocker count reduced to zero; Stabilization exit criteria operationally satisfied, but Stabilization not yet formally closed. | `00_CONFIG/GMV_RESEARCH_LAB_AUTOMATIONS_SUSPENSION.md`, `00_CONFIG/PROJECT_STATUS.md` | this commit (see `git log`) | Formal closure of Stabilization and opening of GMV Core Development |

---

## 5. Document Index

*Canonical documents only, grouped by category. This is an index, not a copy — read the referenced file for full content.*

**ADR**
- `00_CONFIG/ADR_MARKET_ENGINE_RENDERING_DIVERGENCE.md`

**Freeze**
- `00_CONFIG/APPRENTICE_LEGACY_FREEZE.md`
- `00_CONFIG/CONSTITUTION_CLI_FEATURE_FREEZE.md`
- `00_CONFIG/REALESTATE_LEGACY_FREEZE.md`
- `00_CONFIG/GMV_ENGINE_DECISION_AUTOMATION_FREEZE.md`

**Suspension** (operational only — not a Freeze/legacy classification; final disposition pending)
- `00_CONFIG/FENIX_PROVISIONAL_SUSPENSION.md`
- `00_CONFIG/GMV_RESEARCH_LAB_AUTOMATIONS_SUSPENSION.md`

**Specification**
- `00_CONFIG/SERVICE_SPECIFICATION.md`
- `00_CONFIG/LEGACY_ENGINE_INVENTORY.md`
- `00_CONFIG/OID_CONTRACT.md`

**Architecture**
- `00_CONFIG/GMV_CORE_ARCHITECTURE.md`
- `00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md`
- `00_CONFIG/RUNTIME_DATA_GIT_POLICY.md`
- `00_CONFIG/LOCAL_CODING_ENGINE.md` (experimental scope)

**Status**
- `00_CONFIG/PROJECT_STATUS.md` (this document)
- `00_CONFIG/REBASE_001_CLOSED.md`
- `00_CONFIG/REBASE_001_INTERIM_STATE.md`
- `00_CONFIG/WHAT_TO_DO_NEXT.md`
- `00_CONFIG/SYSTEM_MAP.md` (permanent architectural map, not a status document — indexed here for discoverability)
- `00_CONFIG/STABILIZATION_EXIT_CRITERIA.md` (governance document — exit conditions for the Stabilization phase)

Additional pre-existing governance documents (security, retention, backup, versioning, and per-domain architecture references) exist under `00_CONFIG/` outside the scope of REBASE 001 / Post-REBASE 001 and are not indexed here.

---

## 6. Open Questions

*Intentionally unresolved. Not blockers unless stated in §1.*

1. Root cause of the persistent `gmv status` CLI failure observed under `launchd` execution (Post-REBASE 001 Tasks 4 and 6 — occurs even when the environment is correctly sourced, per Task 6).
2. Whether `gmv_snapshot.sh` has been silently failing since 2026-07-07 (confirmed: no new snapshot file created since that date; root cause not diagnosed — Post-REBASE 001 Task 6).
3. Classification of Dropbox `property_engine.py` (open since REBASE 001 Task 3; never resolved).
4. Correction: `~/GMV_CORE` was earlier described in this ledger as the "Local Coding Engine workspace root." This task (Stabilization Final Blocker Task) found `~/GMV_CORE`'s own `README.md` self-identifies it as "GMV RESEARCH LAB," an experimental prototyping lab — a distinct stated purpose from `00_CONFIG/LOCAL_CODING_ENGINE.md`'s "Local Coding Engine v0" concept. No evidence directly links the two; the earlier conflation in this ledger was not evidence-based and is corrected here. `~/GMV_CORE`'s root-level disposition is `PRESERVE_PENDING_REVIEW`; its two live LaunchAgents have a separate, resolved verdict (`PROVISIONALLY_SUSPEND` each) pending execution — see the Stabilization Final Blocker Task report.
5. Disposition of `gmv_watchdog.sh` and `gmv_orchestrator.sh` — flagged as sharing the same governance-contradiction evidence as the frozen GMV Engine and archaeologized Fenix, not yet individually archaeologized.
6. Fenix's final architectural disposition (keep/govern, merge, or decommission) — operationally suspended pending technical review (Post-REBASE 001 Task 7); see `FENIX_PROVISIONAL_SUSPENSION.md` for the minimum requirements that must be satisfied before this question can be resolved.
7. `com.gmv.dailybrief`'s and `com.gmv.morningbrief.email`'s final architectural disposition (keep/govern, merge, or decommission) — operationally suspended pending technical review (Stabilization Final Blocker Resolution); see `GMV_RESEARCH_LAB_AUTOMATIONS_SUSPENSION.md` for the minimum requirements that must be satisfied before this question can be resolved.
8. Whether `com.gmv.morningbrief.email`'s dormant external-email capability (to `gmv@area35artgallery.com`, via the same local SMTP relay used by `SRV-000002`) was ever actually exercised during its one manual test run on 2026-07-07 — unconfirmed either way; the capability remains preserved but inactive under suspension.
9. The origin and Dropbox-authenticity of `04_RESULTS/dropbox_decisions.json` (consumed by both `~/GMV_CORE` runners) was not verified — out of scope for the Stabilization Final Blocker Task.

---

## 7. Project Health

*Each an explicit qualitative status, evidenced by the referenced work.*

- **Architecture:** STABLE — core principles (Runtime belongs to Core; Dropbox is Repository; freeze before deletion; authority before execution; archaeology before implementation) established in REBASE 001 and consistently applied through Post-REBASE 001.
- **Governance:** IMPROVING — REBASE 001 resolved four long-standing ungoverned components; a previously-undiscovered automation family (`scripts/gmv_*.sh` plus `~/GMV_CORE`'s two LaunchAgents) was surfaced by the System Authority Audit; every live instance of it has now been suspended or frozen — no live, ungoverned, scheduled automation remains loaded.
- **Repository:** CLEAN — no unexplained tracked modifications as of the last audit (Post-REBASE 001 Task 3).
- **Runtime:** GOVERNED — one native service and three compatibility services are registered and documented; the previously-discovered ungoverned automation family is now fully frozen or suspended (none remains loaded/scheduled).
- **Compatibility:** STABLE — three compatibility services registered, hash-pinned, and documented; one output-rendering divergence formally resolved by ADR.
- **Legacy Review:** IN PROGRESS — four components frozen with documented reactivation conditions; `property_engine.py` remains unclassified; `~/GMV_CORE`'s root is now archaeologized (`PRESERVE_PENDING_REVIEW`) but its ~40 further scripts beyond the two audited (and now suspended) LaunchAgents remain unexamined.
- **Automation Review:** COMPLETE for all previously-live, scheduled automation — System Authority Audit found 12 untracked `scripts/gmv_*.sh` scripts across 6 LaunchAgents plus 2 further live automations in `~/GMV_CORE`; 2 scripts (`gmv_engine.sh`, `gmv_decision_engine.sh`) are frozen, 3 (`gmv_fenix_engine.sh`, `morning_os.py`, `dropbox_daily_brief.py`) are provisionally suspended; 3 remain unaudited but were already dormant/unloaded at last check (`gmv_watchdog.sh`, `gmv_orchestrator.sh`, and their further sub-scripts) — none of these three is currently live.
- **Development Readiness:** READY FOR CONTROLLED WORK — the evidence-first, report-then-freeze pattern is well-established, repeatable, and has produced consistent, reversible outcomes across every component examined to date; no blocking technical issue prevents continued work.

---

## 8. Next Session Bootstrap

**This is the mandatory session entry point.**

Future sessions must:

1. Read this document (`00_CONFIG/PROJECT_STATUS.md`) in full.
2. Read only the documents listed under **Required Context** below.
3. Continue from **Next Approved Task** (§1). If none is set, treat the
   highest-priority `PENDING_APPROVAL` item in §3 as the item requiring a
   Project Owner decision before work resumes — do not begin it unilaterally.

Do not reconstruct context from unrelated documents unless explicitly
instructed by the user.

**Required Context:**

- `00_CONFIG/REBASE_001_CLOSED.md`
- `00_CONFIG/WHAT_TO_DO_NEXT.md`
- `00_CONFIG/APPRENTICE_LEGACY_FREEZE.md`
- `00_CONFIG/CONSTITUTION_CLI_FEATURE_FREEZE.md`
- `00_CONFIG/REALESTATE_LEGACY_FREEZE.md`
- `00_CONFIG/ADR_MARKET_ENGINE_RENDERING_DIVERGENCE.md`
- `00_CONFIG/GMV_ENGINE_DECISION_AUTOMATION_FREEZE.md`
- `00_CONFIG/SERVICE_SPECIFICATION.md`
- `00_CONFIG/LEGACY_ENGINE_INVENTORY.md`
