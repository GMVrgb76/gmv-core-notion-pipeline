# GMV Stabilization Exit Criteria

Governance document. Determines the minimum objective conditions required
to close the Stabilization phase (REBASE 001 + Post-REBASE 001) and open
GMV Core Development. No runtime code, Service, LaunchAgent, or Dropbox
content was modified to produce this document; it is built entirely from
`PROJECT_STATUS.md`, `SYSTEM_MAP.md`, `REBASE_001_CLOSED.md`,
`SERVICE_SPECIFICATION.md`, `LEGACY_ENGINE_INVENTORY.md`, and the existing
ADR/Freeze documents.

---

## GMV Stabilization Exit Criteria

| # | Criterion | Current status | Evidence | Remaining work |
|---|---|---|---|---|
| 1 | **Repository cleanliness** — no unexplained tracked modifications in `~/.gmv_core` | **MET** | `PROJECT_STATUS.md` §1: "Repository Status: Clean — no unexplained tracked modifications as of the last System Authority Audit (Post-REBASE 001 Task 3, 2026-07-13)." | None. |
| 2 | **All discovered automation classified** — every scheduled/automated component found during REBASE 001 / Post-REBASE 001 archaeology has a canonical classification (CANONICAL / COMPATIBILITY / FROZEN / HISTORICAL) | **NOT MET** | `SYSTEM_MAP.md` §4 lists four components as `UNCLASSIFIED`: Fenix automation, `gmv_watchdog.sh`/`gmv_orchestrator.sh`, Dropbox `property_engine.py`, and the `~/GMV_CORE` workspace root. | Archaeology and disposition of all four (see per-target classification below). |
| 3 | **Registered Services satisfy `SERVICE_SPECIFICATION.md`** — every Service OID meets the normative contract (§14 admission rule: OID, contract, entrypoint, category, status, logging, Timeline event, minimum test) | **MET** | `SERVICE_SPECIFICATION.md` §10–13 document all four registered services (`SRV-000001`–`SRV-000004`) with full contract fields declared. | None found in the reviewed documents. |
| 4 | **No unapproved, ungoverned scheduled automation remains live** | **NOT MET** | `GMV_ENGINE_DECISION_AUTOMATION_FREEZE.md` confirms `com.gmv.engine` frozen. `PROJECT_STATUS.md` §3/§7 confirms `com.gmv.fenix` remains loaded and scheduled, not frozen; `gmv_watchdog.sh`/`gmv_orchestrator.sh` are not yet archaeologized; the `~/GMV_CORE` root has two loaded LaunchAgents (`com.gmv.morningbrief.email`, `com.gmv.dailybrief`) with no governance record at all. | Freeze `com.gmv.fenix`; archaeology and disposition of the remaining live/ungoverned automation. |
| 5 | **Open Questions triaged** — every item in `PROJECT_STATUS.md` §6 is either resolved or explicitly classified as blocking or deferrable | **MET by this document** | `PROJECT_STATUS.md` §6 lists six open questions; this document performs that triage in the section below. | None beyond acting on the triage. |
| 6 | **Governance infrastructure operational** — operational ledger, architectural map, and task completion protocol established and in active use | **MET** | `PROJECT_STATUS.md` created and actively maintained; Task Completion Protocol (Rules 6–9) added; `SYSTEM_MAP.md` created; all committed. | None. |
| 7 | **Frozen components have complete, consistent freeze records** | **MET** | Four Freeze documents exist (Apprentice, Constitution CLI feature, Real Estate orchestration, GMV Engine/Decision Engine automation), each cross-referenced in `SYSTEM_MAP.md` §4 with matching classification. | None for existing frozen components. New freezes required per Criterion 4 will need their own records, following the established pattern. |
| 8 | **Known operational defects diagnosed or explicitly deferred** | **NOT MET, deferrable** | `PROJECT_STATUS.md` §6 items 1–2: persistent `gmv status` CLI failure under `launchd`, and `gmv_snapshot.sh`'s undiagnosed silent failure since 2026-07-07. Both are contained within already-frozen or soon-to-be-frozen automation; no evidence of Core-state corruption was found. | Diagnosis, but classified as non-blocking (see below). |

---

## Remaining Work — Three Categories

### A. BLOCKERS
*Must be completed before Stabilization can close.*

1. **Freeze `com.gmv.fenix` / `gmv_fenix_engine.sh`.** Fully archaeologized (Post-REBASE 001 Task 6, verdict `FREEZE_UNAPPROVED_AUTOMATION`); currently loaded and scheduled; awaiting Project Owner authorization to execute the freeze already precedented for `com.gmv.engine`.
2. **Archaeology and disposition of the `~/GMV_CORE` workspace's two loaded LaunchAgents** (`com.gmv.morningbrief.email` running `06_RUNNER/morning_os.py`; `com.gmv.dailybrief` running `06_RUNNER/dropbox_daily_brief.py`). Both are live and scheduled with zero governance record — no OID, no registration, no documentation, per `PROJECT_STATUS.md` §6. This is scoped to these two live components specifically, not a full audit of the entire `~/GMV_CORE` workspace.

### B. POST-STABILIZATION
*May continue during GMV Core Development.*

1. Archaeology of `gmv_watchdog.sh` and `gmv_orchestrator.sh` — both are confirmed **not currently loaded** (per the System Authority Audit underlying `PROJECT_STATUS.md`), so they are dormant rather than an active, ongoing governance violation.
2. Classification of Dropbox `property_engine.py` — manual-invocation-only, not scheduled or automatically executed.
3. Diagnosis of the persistent `gmv status` CLI failure under `launchd`.
4. Diagnosis of `gmv_snapshot.sh`'s silent failure since 2026-07-07.
5. Any broader classification of the `~/GMV_CORE` workspace beyond its two live LaunchAgents (Blocker item A.2).

### C. HISTORICAL
*May remain indefinitely without affecting governance.*

1. Apprentice runtime and LaunchAgent — `APPRENTICE_LEGACY_FREEZE.md`.
2. Constitution CLI feature — `CONSTITUTION_CLI_FEATURE_FREEZE.md`.
3. Real Estate orchestration (`realestate_runner.py` family) — `REALESTATE_LEGACY_FREEZE.md`.
4. GMV Engine / Decision Engine automation — `GMV_ENGINE_DECISION_AUTOMATION_FREEZE.md`.
5. Dropbox `market_engine.py` historical source — reclassified `HISTORICAL_BEHAVIOUR_ONLY` by `ADR_MARKET_ENGINE_RENDERING_DIVERGENCE.md`.

---

## Per-Target Classification (Remaining Archaeology Targets)

| Target | Classification |
|---|---|
| `com.gmv.fenix` / `gmv_fenix_engine.sh` | **BLOCKER** |
| `~/GMV_CORE`'s two loaded LaunchAgents (`com.gmv.morningbrief.email`, `com.gmv.dailybrief`) | **BLOCKER** |
| `gmv_watchdog.sh` / `gmv_orchestrator.sh` | **POST-STABILIZATION** |
| Dropbox `property_engine.py` | **POST-STABILIZATION** |
| `gmv status` CLI failure diagnosis | **POST-STABILIZATION** |
| `gmv_snapshot.sh` silent-failure diagnosis | **POST-STABILIZATION** |
| Broader `~/GMV_CORE` workspace classification (beyond its two live agents) | **POST-STABILIZATION** |
| Apprentice, Constitution CLI, Real Estate orchestration, GMV Engine/Decision Engine, Dropbox `market_engine.py` | **HISTORICAL** |

---

## Readiness Determination

**NEAR COMPLETION.**

Evidence for this conclusion, not speculation:

- All governance infrastructure required to operate Stabilization-style work is in place and in active use (`PROJECT_STATUS.md`, `SYSTEM_MAP.md`, Task Completion Protocol) — Criterion 6, MET.
- The repository is clean, and all four registered Services meet the normative specification — Criteria 1 and 3, MET.
- Four components have already been carried through the full evidence-first archaeology-then-freeze cycle with consistent, cross-referenced documentation — Criterion 7, MET.
- Two BLOCKER-class items remain, but both are narrowly scoped and follow an already-proven, precedented procedure (archaeology already complete for Fenix; the `~/GMV_CORE` LaunchAgents require the same procedure already executed four times) — not open-ended or unknown work.
- No evidence in any reviewed document indicates unresolved risk of Core-state corruption, data loss, or an ungoverned component that has caused operational harm — the live blockers are governance gaps, not confirmed incidents.

This is not `READY TO CLOSE STABILIZATION`, because live, scheduled, ungoverned automation remains running (`com.gmv.fenix`, and the two `~/GMV_CORE` LaunchAgents) with zero registration, documentation, or ownership — Criterion 4 is not met. It is not `NOT READY`, because the remaining work is narrow, precedented, and does not require discovering new unknowns — only executing the same evidence-first procedure already applied successfully four times.

## Minimum Remaining Work to Close Stabilization

1. Obtain Project Owner approval and execute the freeze of `com.gmv.fenix` / `gmv_fenix_engine.sh`, following the exact procedure already used for `com.gmv.engine` (Post-REBASE 001 Task 5).
2. Perform forensic archaeology of `com.gmv.morningbrief.email` and `com.gmv.dailybrief` (the two loaded `~/GMV_CORE` LaunchAgents) and reach and execute a disposition (freeze, register, or another documented outcome), following the same evidence-first pattern.

Once both are complete and documented, Stabilization may be reassessed for closure. All other remaining work (§ POST-STABILIZATION) may proceed in parallel with GMV Core Development without blocking that transition.
