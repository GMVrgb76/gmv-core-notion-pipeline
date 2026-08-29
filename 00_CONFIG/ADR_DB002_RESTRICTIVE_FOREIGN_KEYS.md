# ADR: DB-002 Restrictive Foreign-Key Policy

Status: Accepted
Date: 2026-07-19
Decision owner: Project Owner

## Context

The live schema at version 5 declares no foreign keys and every raw SQLite
connection starts with `PRAGMA foreign_keys=0`. A read-only inventory found no
orphans across the ten canonical references, but this is accidental integrity.
SQLite requires table rebuilds to add these constraints and enables enforcement
per connection rather than persistently in the database file.

## Decision

DB-002 uses `ON UPDATE RESTRICT ON DELETE RESTRICT` for all ten references:

1. `events.oid` to `objects.oid`;
2. `events.supersedes_event_id` to `events.id`;
3. `service_runs.service_oid` to `objects.oid`;
4. `plugin_metadata.plugin_oid` to `objects.oid`;
5. `plugin_services.plugin_oid` to `plugin_metadata.plugin_oid`;
6. `plugin_services.service_oid` to `objects.oid`;
7. `relations.source_oid` to `objects.oid`;
8. `relations.target_oid` to `objects.oid`;
9. `resources.resource_oid` to `objects.oid`;
10. `import_queue.resource_oid` to `resources.resource_oid`.

No cascade and no nullification policy is permitted. Permanent identity,
history, graph provenance, Plugin registration, Resource custody, and run
evidence must not disappear as a side effect of deleting or changing a parent.

Migration 006 is initially an explicit target only. It must reject any orphan
before DDL, rebuild all seven affected tables inside one transaction, preserve
rows/views/Event triggers/autoincrement sequences, run `foreign_key_check`
before commit, and advance `user_version` only on success. The default schema
target remains v5 until a separately approved live cutover.

Application connections covered by this isolated slice enable and read back
`PRAGMA foreign_keys=ON`: the Core connection factory and the three active
writers (Knowledge Engine, Compatibility Layer, and Import Service). Knowledge
and Compatibility writers must require their pre-existing Object identities
and fail before execution/writes when authority is absent or mistyped; they
must never synthesize System or Service Objects.

The subsequent connection-completion slice routes every remaining tracked
production connection through `gmv_core.database.connect_path()`, including:

- read-only Event, Timeline, Plugin, artifact, Doctor, and Status queries;
- the dormant `BaseService` and `plugin_manager` paths;
- Snapshot export;
- backup source, destination, verification, Resource evidence, and OID checks;
- DB-005/DB-006 historical plan, apply, and reconciliation tools; and
- the schema migration runner itself, including its in-memory baseline check.

`gmv_core.database.py` is the only tracked production file permitted to call
`sqlite3.connect()` directly. A static AST test enforces that ownership and
also rejects any unapproved `PRAGMA foreign_keys=OFF` or `=0` in tracked
production Python/SQL.

The initial sole exception was the first statement of migration 006. SQLite
requires foreign-key enforcement to be disabled while its seven constrained
tables are rebuilt. The isolated DB-003 migration 007 adds a second confined
exception because it atomically rebuilds the referenced `objects` table plus
`service_runs`, `engines`, and `relations`. The isolated DB-008 migration 008
adds a third because it rebuilds `objects` and `oid_sequences` while preserving
the ten restrictive foreign keys and adding typed-reference triggers. Each
resource verifies enforcement before disabling it, acquires `BEGIN IMMEDIATE`,
performs its data and post-copy guards in the same transaction, commits, then
restores enforcement. The runner also restores and verifies enforcement after
a failed script. Static and injected-failure tests prove ordering, rollback,
restoration to `foreign_keys=1`, and the exact three-file allow-list; no other
exception exists.

## Consequences

- Referenced parents cannot be updated or deleted until references are handled
  explicitly under a future approved domain workflow.
- Object subtype correctness remains a separate DB-008 concern; ordinary
  foreign keys prove existence, not that an Object has the expected domain
  type. Explicit migration 008 implements that additional enforcement but is
  not yet the live/default schema.
- Raw SQLite connections still default to enforcement off, so the static
  boundary permanently confines them to the fail-closed Core factory. All
  currently tracked production connection classes are covered; there is no
  residual application exception.
- A failed pre-commit migration rolls back transactionally to v5. After a live
  commit, rollback is restore from a verified milestone backup, never reverse
  destructive DDL; that operation requires separate Project Owner approval.

## References

- `GMV_V2_BACKLOG.md` — DB-002.
- `GMV_V2_EXECUTION_ROADMAP.md` — Sprint 003 step 6 and exit criteria.
- `00_CONFIG/ADR_CORE_PERSISTENCE_BOUNDARY.md`.
- Project Owner approval recorded in the DB-002 task on 2026-07-19.
