# GMV System Map

Permanent structural map of the GMV ecosystem. This is not a status report,
task report, handoff, or chronology — see `PROJECT_STATUS.md` for those.
This document describes what the system *is*, not what is currently being
worked on.

Built entirely from evidence already established in: `PROJECT_STATUS.md`,
`REBASE_001_CLOSED.md`, `LEGACY_ENGINE_INVENTORY.md`,
`SERVICE_SPECIFICATION.md`, all ADR documents, and all Freeze documents. No
new architecture is inferred here.

---

## 1. System Overview

GMV OS separates a canonical **Repository** (Dropbox `GMV_MASTER_SYSTEM`,
non-runtime material) from a canonical **Runtime** (git-tracked Core at
`~/.gmv_core`, executable code). Runtime components are represented as
persistent Objects and, where they are Services, carry a Service OID
governed by `SERVICE_SPECIFICATION.md`. Legacy V1 components are bridged
into the Runtime through a hash-pinned **Compatibility Layer**, which is
distinct from components that have been forensically reviewed and formally
**Frozen**, and distinct again from automation that has been discovered but
not yet classified at all.

## 2. Architectural Layers

| Layer | Purpose | Authority | Canonical document | Current status |
|---|---|---|---|---|
| **Repository** | Canonical store for non-runtime material (documents, reports, historical data) | Dropbox is Repository, never a canonical runtime source | `REBASE_001_CLOSED.md` | CANONICAL |
| **Core Runtime** | Houses all executable runtime code | Runtime belongs to Core (git-tracked) | `REBASE_001_CLOSED.md` | CANONICAL |
| **CLI** | Operative access point (`11_CLI/gmv`) | Baseline restored to `HEAD`; unauthorized additions removed | `CONSTITUTION_CLI_FEATURE_FREEZE.md` | CANONICAL |
| **Service Layer** | Registers, executes, and observes Services (native + compatibility) as Objects of type Service | `SERVICE_SPECIFICATION.md` (Normativo, v1.0) | `SERVICE_SPECIFICATION.md` | CANONICAL (spec); partially populated (4 registered Service OIDs) |
| **Scheduler** | Time-based invocation of Services and compatibility wrappers | `scheduler` field per Service contract (`SERVICE_SPECIFICATION.md` §3/§10–13) | `SERVICE_SPECIFICATION.md`, `GMV_ENGINE_DECISION_AUTOMATION_FREEZE.md` | PARTIALLY GOVERNED — a separate, ungoverned scheduled-automation family exists outside this model; one of its components is FROZEN, the rest UNCLASSIFIED |
| **Database** | Canonical persistent store (Objects, Timeline, `engine_runs`) | "Read the Core as the source of truth" (`SERVICE_SPECIFICATION.md` §5.1) | `SERVICE_SPECIFICATION.md` | CANONICAL |
| **Knowledge System** | Structured knowledge layer (`SRV-000001`) | Native Core Service, `compatibility_mode: 0` | `SERVICE_SPECIFICATION.md` §10 | CANONICAL |
| **Compatibility Layer** | Encapsulates V1 legacy components with hash-pinned, rollback-capable execution | `SERVICE_SPECIFICATION.md` §9 | `SERVICE_SPECIFICATION.md`, `LEGACY_ENGINE_INVENTORY.md` | COMPATIBILITY (3 registered: `SRV-000002/3/4`) |
| **Legacy Layer** | Preserved, non-authoritative historical/superseded components | Freeze-before-deletion; no execution authority | The four Freeze documents + `ADR_MARKET_ENGINE_RENDERING_DIVERGENCE.md` | FROZEN / HISTORICAL (per component) |

## 3. Authority Graph

| Layer | Source of truth | Owner | Canonical document |
|---|---|---|---|
| Repository | Dropbox `GMV_MASTER_SYSTEM` | Not recorded in any reviewed document | `REBASE_001_CLOSED.md` |
| Core Runtime | `~/.gmv_core` (git) | Not recorded in any reviewed document | `REBASE_001_CLOSED.md` |
| CLI | `11_CLI/gmv` at `HEAD` | Not recorded | `CONSTITUTION_CLI_FEATURE_FREEZE.md` |
| Service Layer | `GMV.db` Objects of type Service | Not recorded | `SERVICE_SPECIFICATION.md` |
| Scheduler | `launchd` LaunchAgents + Service `scheduler` field | Not recorded | `SERVICE_SPECIFICATION.md` |
| Database | `~/.gmv_core/09_DATABASE/GMV.db` | Not recorded | `SERVICE_SPECIFICATION.md` |
| Knowledge System | `01_RUNTIME/knowledge_engine.py` (`SRV-000001`) | Not recorded | `SERVICE_SPECIFICATION.md` §10 |
| Compatibility Layer | `10_API/gmv_compatibility.py` + `12_SCHEDULER/run_*_compatibility.sh` | Not recorded | `SERVICE_SPECIFICATION.md` §9, `LEGACY_ENGINE_INVENTORY.md` |
| Legacy Layer | The relevant Freeze document per component | Not recorded | See §4 below |

No reviewed document records an individual human or role as Owner for any
layer; this is stated as fact, not inferred.

## 4. Runtime Components

Classification drawn only from the referenced documents.

| Component | Classification | Reference |
|---|---|---|
| Knowledge Engine (`SRV-000001`) | **CANONICAL** | `SERVICE_SPECIFICATION.md` §10 |
| Morning Brief (`SRV-000002`) | **COMPATIBILITY** | `SERVICE_SPECIFICATION.md` §11, `LEGACY_ENGINE_INVENTORY.md` |
| Daily Log (`SRV-000003`) | **COMPATIBILITY** | `SERVICE_SPECIFICATION.md` §12, `LEGACY_ENGINE_INVENTORY.md` |
| Market Engine / `market_engine_v2.py` (`SRV-000004`) | **COMPATIBILITY** | `SERVICE_SPECIFICATION.md` §13, `LEGACY_ENGINE_INVENTORY.md`, `ADR_MARKET_ENGINE_RENDERING_DIVERGENCE.md` |
| Dropbox `market_engine.py` (historical source) | **HISTORICAL** | `ADR_MARKET_ENGINE_RENDERING_DIVERGENCE.md` (`HISTORICAL_BEHAVIOUR_ONLY`) |
| Apprentice runtime | **FROZEN** | `APPRENTICE_LEGACY_FREEZE.md` |
| Constitution CLI feature (`constitution_service.py`) | **FROZEN** | `CONSTITUTION_CLI_FEATURE_FREEZE.md` |
| Real Estate orchestration (`realestate_runner.py` family) | **FROZEN** | `REALESTATE_LEGACY_FREEZE.md` |
| GMV Engine / Decision Engine automation (`com.gmv.engine`, `gmv_engine.sh`, `gmv_decision_engine.sh`) | **FROZEN** | `GMV_ENGINE_DECISION_AUTOMATION_FREEZE.md` |
| Fenix automation (`gmv_fenix_engine.sh`) | **UNCLASSIFIED** | `PROJECT_STATUS.md` §3/§6 — archaeologized, freeze recommended, not yet authorized; no Freeze document exists |
| `gmv_watchdog.sh` / `gmv_orchestrator.sh` | **UNCLASSIFIED** | `PROJECT_STATUS.md` §3/§6 — not yet archaeologized |
| Dropbox `property_engine.py` | **UNCLASSIFIED** | `PROJECT_STATUS.md` §6 — open since REBASE 001, never resolved |
| `~/GMV_CORE` (Local Coding Engine workspace root) | **UNCLASSIFIED** | `PROJECT_STATUS.md` §6 |

## 5. Documentation Map

| Document | Role |
|---|---|
| `PROJECT_STATUS.md` | Unique operational source of truth for current project state, active work, and chronological history. |
| `SERVICE_SPECIFICATION.md` | Normative technical contract every Service (native or compatibility) must satisfy. |
| `LEGACY_ENGINE_INVENTORY.md` | Version-evidence record for legacy engines bridged through the Compatibility Layer. |
| ADRs | Authoritative architectural decision records. Never restated elsewhere — referenced only. |
| Freeze Records | Authoritative component lifecycle records for anything taken out of active/authoritative status. |
| `REBASE_001_CLOSED.md` | Closure record of REBASE 001: the objective, completed scope, and the architectural decisions it established. |
| `SYSTEM_MAP.md` (this document) | Permanent structural map. Changes only on permanent architectural change (§8). |

## 6. Development Rules

Summarized from already-approved sources; none invented here.

From `REBASE_001_CLOSED.md`:
- Runtime belongs to Core.
- Dropbox is Repository.
- Runtime ≠ Repository.
- Freeze before deletion.
- Authority before execution.
- Archaeology before implementation.

From `SERVICE_SPECIFICATION.md` §5 (operative rules for every Service):
1. Read the Core as the source of truth.
2. Record every execution in `engine_runs` (or the future `service_runs` table).
3. Create at least one Timeline event per execution.
4. Never retain permanent state outside the Core.
5. Produce inspectable technical logs.
6. Be re-executable.
7. Fail explicitly.
8. Declare inputs and outputs.
9. Declare the OIDs read and modified.
10. Be replaceable without modifying the Core.

From `SERVICE_SPECIFICATION.md` §14 (admission rule): no new Service enters
GMV OS without an OID, a conformant contract, an entrypoint, a category, a
status, logging, a Timeline event, and a minimum test.

From `PROJECT_STATUS.md` (Operational Rules): `PROJECT_STATUS.md` is the
single operational ledger; every completed task updates it; it records
facts only; historical records are append-only; ADRs and Freeze documents
remain the respective authorities for decisions and lifecycle.

## 7. Current Architecture State

GMV OS currently has one native Core Service (Knowledge Engine,
`SRV-000001`) and three Compatibility Services (Morning Brief `SRV-000002`,
Daily Log `SRV-000003`, Market Engine `SRV-000004`), all registered per
`SERVICE_SPECIFICATION.md`. Five components are formally Frozen with
documented reactivation conditions: Apprentice, the Constitution CLI
feature, Real Estate orchestration, the Dropbox `market_engine.py`
historical source, and the GMV Engine/Decision Engine automation. A
discovered automation family (Fenix, Watchdog, Orchestrator, and the
`~/GMV_CORE` workspace root) remains partially unclassified — none of it
has a canonical document assigning it CANONICAL, COMPATIBILITY, FROZEN, or
HISTORICAL status. The Repository/Runtime boundary, the Compatibility
Layer's hash-pin mechanism, and the Service Registry's OID-based contract
are the three governing structures currently in force across the whole
system.

## 8. Maintenance Rules

`SYSTEM_MAP.md` changes only when a **permanent architectural change**
occurs — the addition, freezing, reclassification, or retirement of a
layer or component, established by one of: a new or amended ADR, a new
Freeze document, a `SERVICE_SPECIFICATION.md` contract change, or a REBASE
closure record. Task progress, active-work status, risks, and chronology
belong exclusively in `PROJECT_STATUS.md` and must never be reflected here.
Every edit to this document must cite the specific canonical document that
authorized the change.
