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

## Amendment — DB-003 / DB-010 dependency resolution

Accepted 2026-07-19 by the Project Owner. `DB-003` now owns the decision
contract for the canonical Import Queue state machine; `DB-010` owns its later
persistence/API implementation. The decision slice depends on `DB-001` and
`ARC-004`, while `DB-010` depends on the accepted contract rather than on full
completion of every `DB-003` constraint. This breaks the former circular
dependency without authorizing a schema migration or moving `DB-010`
implementation out of Sprint 004. The authoritative transition contract is
`ADR_DB003_IMPORT_QUEUE_STATE_MACHINE.md`.

## Addendum — ARC-002 static connect-boundary check confirmed satisfied

Recorded 2026-07-21, following a Project Owner-authorized, strictly
read-only review of this ADR's deferred clause (Decision §3). The review's
sole scope was whether "the `ARC-002` static check that rejects direct
`sqlite3.connect` outside `gmv_core`" — the exact mechanism deferred by
Decision §3 pending `DB-002`/`DB-003` — could now be enabled.

Findings:

1. `DB-002` (restrictive foreign keys, connection enforcement) and `DB-003`
   (non-queue domain constraints) are both complete
   (`00_CONFIG/ADR_DB002_RESTRICTIVE_FOREIGN_KEYS.md`,
   `00_CONFIG/ADR_DB003_AUTHORITATIVE_DOMAIN_SCOPE.md`).
2. The named static check already exists and has been continuously active
   since the `DB-002` completion task on 2026-07-19:
   `tests/test_sqlite_connection_boundary.py::test_only_core_factory_calls_sqlite_connect`.
   It parses every tracked production `.py` file under `01_RUNTIME/`,
   `10_API/`, and `gmv_core/` via `ast` (not text matching) and asserts
   exactly one raw `sqlite3.connect()` call exists, owned by
   `gmv_core/database.py`. Re-run on 2026-07-21 as part of this review:
   2 passed, 0 failed.
3. The specific clause deferred by Decision §3 is therefore formally
   satisfied. This addendum records that closure; it does not itself
   change any code, schema, or test.
4. `ARC-002` as a whole backlog item ("Enforce the persistence boundary")
   remains open and incremental. The connect-boundary check only proves
   connection *creation* is centralized; it does not prove that all
   persistence *access* passes through `gmv_core/repositories/*`. As of
   this review, 14 tracked production files still execute inline SQL
   directly against a factory-created connection rather than through a
   repository module: `10_API/artifact_audit.py`,
   `10_API/backup_service.py`, `10_API/base_service.py`,
   `10_API/doctor_service.py`,
   `10_API/engine_service_runs_migration_service.py`,
   `10_API/event_service.py`, `10_API/gmv_compatibility.py`,
   `10_API/import_service.py`, `10_API/plugin_manager.py`,
   `10_API/plugin_service.py`, `10_API/status_service.py`,
   `10_API/timeline_events_migration_service.py`,
   `10_API/timeline_service.py`, and `01_RUNTIME/knowledge_engine.py`.
   None of these 14 files is declared complete, migrated, or authorized
   for migration by this addendum — each remains its own future,
   individually authorized task under the same incremental rule as
   Decision §2.

This addendum closes only the single deferred clause in Decision §3. It
does not authorize any code change, does not close `ARC-002` overall, and
does not authorize `SEC-006` or any other Sprint 003 execution-sequence
item.

## References

- `GMV_V2_EXECUTION_ROADMAP.md` — Sprint 003, "Small-step execution
  sequence", step 1.
- `GMV_V2_BACKLOG.md` — `ARC-001`, `ARC-002`, `MAIN-001`, `MAIN-004`.
- Sprint Review (2026-07-18) that first surfaced the `ARC-001` dependency
  conflict and the undesignated package question, reported prior to this
  decision.
- Project Owner decision (2026-07-18) resolving both questions and scoping
  the first implementation slice, recorded in `00_CONFIG/PROJECT_STATUS.md`.
- Project Owner-authorized read-only ARC-002 static connect-boundary
  review (2026-07-21), recorded in `00_CONFIG/PROJECT_STATUS.md`.
