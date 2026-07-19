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

## Consequences

- Referenced parents cannot be updated or deleted until references are handled
  explicitly under a future approved domain workflow.
- Object subtype correctness remains a separate DB-003 concern; ordinary
  foreign keys prove existence, not that an Object has the expected domain type.
- Raw SQLite connections still default to enforcement off. Remaining read-only,
  diagnostic, backup, and historical migration call sites must be classified
  and covered before DB-002 can satisfy the roadmap's every-connection exit
  criterion.
- A failed pre-commit migration rolls back transactionally to v5. After a live
  commit, rollback is restore from a verified milestone backup, never reverse
  destructive DDL; that operation requires separate Project Owner approval.

## References

- `GMV_V2_BACKLOG.md` — DB-002.
- `GMV_V2_EXECUTION_ROADMAP.md` — Sprint 003 step 6 and exit criteria.
- `00_CONFIG/ADR_CORE_PERSISTENCE_BOUNDARY.md`.
- Project Owner approval recorded in the DB-002 task on 2026-07-19.
