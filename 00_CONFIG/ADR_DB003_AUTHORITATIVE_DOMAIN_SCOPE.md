# ADR: DB-003 Authoritative Domain Constraint Scope

Status: Accepted
Date: 2026-07-19
Decision owner: Project Owner
Backlog: `DB-003`, `DB-008`, `DB-010`, `DB-013`

## Context

`DB-003` broadly requested checks for statuses, OID formats, confidence,
compatibility flags, queue states, and non-self Relations. Two later backlog
items own semantics that DB-003 must not pre-empt:

- `DB-008` owns OID prefix/type consistency; and
- `DB-013` owns the decision whether current status is stored or derived and
  the removal of duplicated status fields in `objects`, `resources`, and
  `plugin_metadata`.

The accepted Import Queue state decision is separately implemented by
`DB-010`. Constraining duplicated lifecycle statuses before `DB-013` would
freeze the very representation that the roadmap requires `DB-013` to resolve.
The Project Owner therefore limited DB-003 to domains with an existing accepted
authority.

At this decision gate the live v6 data has zero violations across all five
approved domains. That observation is compatibility evidence, not the source
of the domains.

## Decision

DB-003 owns exactly the following five domain contracts.

### 1. Lexical OID grammar

`objects.oid` must be text matching exactly `AAA-000001`: three uppercase ASCII
letters, one hyphen, and six decimal digits, with sequence `000000` forbidden.
This is the lexical subset of `OID_CONTRACT.md`.

DB-003 does not decide whether a syntactically valid prefix is registered or
whether it matches `objects.type`. Supported-prefix and prefix/type consistency
remain exclusively owned by `DB-008`.

### 2. Service Run outcomes

`service_runs.status` is an execution outcome, not an entity lifecycle status.
Its exact domain is:

- `OK`
- `ERROR`
- `TIMEOUT`
- `CANCELLED`

This vocabulary is already authoritative in
`OPERATIONAL_RUN_RECORD_SCHEMA.json` and `operational_records.py`. Matching is
case-sensitive and no normalization is permitted.

### 3. Compatibility flag

`engines.compatibility_mode` is an integer Boolean with exact values `0`
(native) and `1` (compatibility), as defined by `SERVICE_SPECIFICATION.md`.
Text, null, and every other integer are invalid.

### 4. Confidence

`import_queue.confidence` is nullable. When present it is a finite numeric value
in the inclusive range 0 through 1. It is not a percentage and creates no
automatic approval threshold.

DB-003 owns this scalar domain. Because `DB-010` already owns the future atomic
rebuild of `import_queue`, `DB-010` will persist the confidence `CHECK` together
with the accepted state-machine cutover rather than forcing a second table
rebuild under DB-003.

### 5. Non-self Relations

`relations.source_oid` and `relations.target_oid` must differ. A self-edge is
invalid regardless of `relation_type`. Foreign-key existence remains enforced
by DB-002; richer predicate, direction, evidence, and assertion semantics remain
owned by `ARC-010`/`DB-021`.

## Explicit status deferral to DB-013

DB-003 will not add lifecycle-status `CHECK` constraints to `objects.status`,
`resources.status`, or `plugin_metadata.status`. `DB-013` owns:

1. the canonical source of current status;
2. stored-versus-derived semantics per entity;
3. removal or replacement of duplicate fields and dependent views;
4. any normalization/reconciliation of existing values; and
5. future status-domain `CHECK` constraints after that authority is settled.

`engines.status` is also outside the approved DB-003 scope: it is not covered by
this delegation merely by analogy, and receives no new constraint without a
separate authoritative lifecycle/disposition decision.

The Import Queue `state` vocabulary is not one of these duplicated lifecycle
statuses. It remains governed by `ADR_DB003_IMPORT_QUEUE_STATE_MACHINE.md` and
implemented later under DB-010.

## Enforcement sequencing

- A future, separately authorized DB-003 migration may enforce lexical OID
  grammar, Service Run outcomes, compatibility mode, and non-self Relations.
- DB-010 will enforce confidence while implementing the accepted queue state
  contract.
- DB-008 will enforce supported OID prefix/type consistency.
- DB-013 will decide, normalize, and constrain duplicated lifecycle statuses.

No migration, backup, live data change, writer cutover, or scheduler operation
is authorized by this decision.

## Consequences

- DB-003 can reject malformed values without inventing lifecycle vocabularies.
- Status normalization remains loss-averse and can remove duplicate authority
  before constraining it.
- A syntactically valid but unknown or mistyped OID remains a DB-008 concern;
  DB-003 lexical validation alone must not be reported as type integrity.
- Confidence and Queue state can be enforced in one later table rebuild.

## References

- `GMV_V2_EXECUTION_ROADMAP.md` — Sprint 003 steps 6–7.
- `GMV_V2_BACKLOG.md` — `DB-003`, `DB-008`, `DB-010`, `DB-013`.
- `00_CONFIG/OID_CONTRACT.md`.
- `00_CONFIG/SERVICE_SPECIFICATION.md`.
- `00_CONFIG/OPERATIONAL_RUN_RECORD_SCHEMA.json`.
- `00_CONFIG/ADR_DB003_IMPORT_QUEUE_STATE_MACHINE.md`.
- Project Owner approval recorded on 2026-07-19.
