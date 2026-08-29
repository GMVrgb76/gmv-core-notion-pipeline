# What To Do Next

Status: Official entry point after REBASE 001 closure (`00_CONFIG/REBASE_001_CLOSED.md`)
Recorded: 2026-07-12

## Current System State

REBASE 001 is closed. One runtime component is migrated into git-tracked
Core (Apprentice). Three legacy components are frozen with documented
reactivation conditions (Apprentice, Constitution CLI, Real Estate
orchestration). The working tree has no unexplained tracked modifications.
One classification item is open: `market_engine.py` exists in two
divergent forms (an ungoverned Dropbox copy and a Core-governed,
hash-pinned `SRV-000004` copy) with no reconciliation yet performed.

## Immediate Priorities

1. Resolve the `market_engine.py` divergence surfaced in Task 12/13
   (Dropbox copy vs. Core's hash-pinned `SRV-000004` copy).
2. Continue Dropbox runtime classification beyond the items REBASE 001
   examined (Apprentice, Constitution CLI feature, Real Estate
   orchestration) — the Task 2 classification report and Task 3 resolution
   report were not exhaustively re-walked item-by-item during REBASE 001's
   closing tasks.
3. Decide, with evidence, whether any frozen component's reactivation
   conditions should be pursued, deferred indefinitely, or formally
   revisited on a schedule.

## Recommended Sequence

1. **Legacy Catalog** — consolidate what REBASE 001 found (frozen
   components, classification reports, divergence findings) into a single
   living catalog, rather than leaving it spread across per-component
   freeze documents.
2. **Runtime authority reconstruction** — for each Core-resident runtime
   component, confirm it has a defined authority (Service OID, or an
   explicit documented exception) before treating it as settled.
3. **Remaining Dropbox runtime classification** — apply the same
   evidence-first archaeology pattern used for Apprentice, Constitution
   CLI, and Real Estate to any Dropbox executable not yet classified or
   left at REVIEW/UNKNOWN in Task 2's report.
4. **Runtime migrations only when justified** — do not migrate a component
   into Core unless a specific, evidenced necessity is established; the
   Market Engine divergence (item 1 above) is the first candidate for this
   evaluation, not an automatic migration.
5. **Service authority consolidation** — reconcile `SERVICE_SPECIFICATION.md`
   and `GMV.db.service_registry_view` against whatever the Legacy Catalog
   (step 1) and remaining classification (step 3) surface.
6. **Knowledge System integration** — evaluate how the Knowledge Engine
   (`SRV-000001`), which REBASE 001 confirmed as Apprentice's successor,
   should relate to any newly classified or migrated component.
7. **Orchestrator architecture** — only after the above, evaluate whether
   a generalized Orchestrator concept is warranted, informed by the
   Real Estate Director/Runner's coordination and recursion-cycle logic
   (Task 12), which remains the closest existing reference implementation.
8. **Runtime simplification** — once authority and classification are
   settled, identify redundant or obsolete runtime paths for
   simplification (not deletion, per the freeze-before-deletion
   principle, unless a specific, separately evidenced case for removal is
   made).
9. **REBASE 002 planning** — once steps 1–8 have produced enough new
   evidence, plan the next REBASE cycle; do not begin it before that
   evidence exists.

## Principles

Carried forward from REBASE 001, evidence-backed only:

- Runtime belongs to Core.
- Dropbox is Repository.
- Runtime ≠ Repository.
- Freeze before deletion.
- Authority before execution.
- Archaeology before implementation.

## Explicit Prohibitions

- No migration without archaeology.
- No runtime in Dropbox.
- No authority without documentation.
- No implementation before evidence.
- No component treated as decided without a corresponding freeze,
  migration, or governance document.

## First Recommended Task

Forensic archaeology of the `market_engine.py` divergence: compare the
Dropbox copy (`99_SYSTEM/02_SERVICES/RealEstate/market_engine.py`) against
the Core-governed, hash-pinned copy
(`01_RUNTIME/legacy/market_engine_v2.py`, `SRV-000004`), establish which
functional differences exist between them, and determine whether the
Dropbox copy should be frozen, retired, or reconciled — following the
same report-only, evidence-first pattern used throughout REBASE 001.
