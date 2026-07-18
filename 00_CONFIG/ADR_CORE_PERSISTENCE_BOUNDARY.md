# ADR: Core Package Designation and Persistence Boundary Sequencing

Status: Accepted
Date: 2026-07-18
Decision owner: Project Owner

## Context

`GMV_V2_EXECUTION_ROADMAP.md`'s Sprint 003 ("Data / Database") opens with a
"Small-step execution sequence" whose first step is: "Implement the minimal
Core package/repository boundary under `ARC-001`, `ARC-002`, `MAIN-001`, and
`MAIN-004`." Two conflicts prevented starting this step directly:

1. **Undesignated package.** `gmv_core/` already exists (`__init__.py`,
   `config.py`, `paths.py`, `errors.py`, `validation.py`, `migrations.py`,
   `identity.py`, `repositories/identity.py`), built during Sprint 001 for
   `ARC-004` (canonical Identity API). No document states whether this
   package is the intended target of `ARC-001` ("Implement an executable
   Core") or whether a separate boundary was intended.
2. **Contradictory dependency ordering.** `GMV_V2_BACKLOG.md` lists `ARC-001`'s
   own `Dependencies` as `DB-001, DB-002, DB-003`. `DB-001` is complete
   (Sprint 001). `DB-002` and `DB-003` (foreign keys and domain constraints)
   are themselves Sprint 003 backlog items, scheduled at step 6 of the same
   execution sequence — after `ARC-001` at step 1. The roadmap's prose order
   and the backlog's declared dependency graph disagreed on whether `ARC-001`
   could begin before `DB-002`/`DB-003` land.

A further scope question: 18 of the ~21 scripts under `10_API/` currently
call `sqlite3.connect` directly, and `ARC-002`'s recommended action ("add a
static check that rejects direct `sqlite3.connect` outside the Core
package") would break all of them at once if enforced immediately.

## Decision

1. **`gmv_core/` is the intended Core package.** `ARC-001`/`MAIN-001` are
   satisfied by extending this existing package, not by creating a new one.
2. **Migration to the Core boundary is incremental, one vertical slice at a
   time.** No task migrates more than one named `10_API` service in a single
   step; the 18 direct-`sqlite3.connect` call sites are not migrated
   together.
3. **`DB-002`/`DB-003` block final enforcement, not initial construction.**
   The repository boundary (`gmv_core/repositories/*`) may be built and
   individual services may be migrated onto it now. The `ARC-002` static
   check that rejects direct `sqlite3.connect` outside `gmv_core` is
   deferred until `DB-002` and `DB-003` (foreign keys, domain constraints)
   are in place — enforcement without those constraints would lock in an
   unconstrained schema behind a boundary that looks authoritative before it
   actually is.
4. **"Minimal" for the first slice means one behavior-preserving vertical
   migration**, not a framework. The first implemented slice is
   `10_API/object_service.py`'s `list`/`show`/`count` commands, routed
   through `gmv_core/repositories/objects.py`, with no output, exit-code, or
   validation-order change and no schema change.
5. **No other service is migrated by this decision.** Each subsequent
   service migration is its own future task, evaluated against this same
   incremental rule.

## Consequences

- `gmv_core/repositories/objects.py` becomes the first read-path repository
  module outside the identity/OID slice, establishing the pattern (typed
  functions taking an open `sqlite3.Connection`, no connection-lifecycle
  ownership) that later service migrations under this ADR are expected to
  follow.
- The remaining 17 direct-`sqlite3.connect` call sites in `10_API/` are
  unaffected by this decision and are not currently in violation of any
  enforced rule — `ARC-002`'s static check does not exist yet, by design
  (see Decision §3).
- Future Sprint 003 work that touches `DB-002`/`DB-003` must, once
  complete, trigger a review of whether `ARC-002`'s static enforcement
  check can now be safely added.
- This ADR does not authorize a schema change, a second service migration,
  or the `ARC-002` enforcement check. Each requires its own task.

## References

- `GMV_V2_EXECUTION_ROADMAP.md` — Sprint 003, "Small-step execution
  sequence", step 1.
- `GMV_V2_BACKLOG.md` — `ARC-001`, `ARC-002`, `MAIN-001`, `MAIN-004`.
- Sprint Review (2026-07-18) that first surfaced the `ARC-001` dependency
  conflict and the undesignated package question, reported prior to this
  decision.
- Project Owner decision (2026-07-18) resolving both questions and scoping
  the first implementation slice, recorded in `00_CONFIG/PROJECT_STATUS.md`.
