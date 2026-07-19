# ADR: DB-008 OID Prefix/Type Consistency

Status: Accepted
Date: 2026-07-19
Decision owner: Project Owner
Backlog: `ARC-004`, `DB-007`, `DB-008`, `MAIN-011`

## Context and authority

`00_CONFIG/OID_CONTRACT.md` version 1.0.0 is the canonical identity
specification. It intentionally defines only mappings already established by
persisted typed Objects and forbids speculative prefixes. `gmv_core.identity`
is its executable implementation. Live data, tests, views, names, and legacy
identifiers are compatibility evidence only; none can add to or override the
contract.

Schema v7 enforces the lexical OID grammar but does not yet bind a recognized
prefix to `objects.type`. Foreign keys prove that referenced Objects exist but
do not prove their domain type. DB-008 closes those two gaps without changing
the identity vocabulary.

## Decision

### Closed canonical map

The complete OID prefix/type map for contract version 1.0.0 is:

| Prefix | Exact Object type |
|---|---|
| `COR` | `Core` |
| `PER` | `Person` |
| `PLG` | `Plugin` |
| `RES` | `Resource` |
| `SRV` | `Service` |
| `SYS` | `System` |

Matching is exact and case-sensitive. No trimming, case conversion, aliasing,
or normalization is permitted. An unknown prefix or an Object type absent from
this table is unsupported and must fail closed. Adding a prefix or changing a
mapping requires a versioned `OID_CONTRACT.md` update and compatibility review;
observed data alone can never create a mapping.

Every `objects` row must satisfy both the schema-v7 lexical grammar and the
exact prefix/type pair above. The six rows of `oid_sequences` must be the same
closed map, and each `last_value` must be at least the greatest committed
sequence for its pair.

### Typed extension references

The following stored references have an exact target type in addition to their
existing foreign-key existence rule:

| Reference | Required Object type |
|---|---|
| `resources.resource_oid` | `Resource` |
| `plugin_metadata.plugin_oid` | `Plugin` |
| `plugin_services.plugin_oid` | `Plugin` |
| `plugin_services.service_oid` | `Service` |
| `service_runs.service_oid` | `Service` |
| non-null `import_queue.resource_oid` | `Resource` |

`events.oid` and both Relation endpoints intentionally accept any canonical
Object type. Views are derived readers and create no independent type
authority.

### Historical and non-OID identifiers

No live prefix/type exception is accepted.

- `OBJECT-0000001` is the retired legacy alias already resolved by
  `ADR_MAIN011_CANONICAL_IDENTITY.md`; `PER-000001` is canonical. The alias is
  historical evidence, not an allowed OID.
- `ENG-000001` through `ENG-000004` are historical Engine registry identifiers
  governed by `ADR_DB006_ENGINE_SERVICE_RECONCILIATION.md`. `ENG` is not an OID
  prefix; the canonical Service identities are `SRV-000001` through
  `SRV-000004`.
- Operational `COR-` followed by 32 hexadecimal characters is a correlation
  ID under `OPERATIONAL_RUN_RECORD_SCHEMA.json`, not a `Core` Object OID. Its
  field and grammar keep the namespaces distinct.
- Inventory identifiers such as `LEG-MORNING-BRIEF-001` and values that exist
  only in tests are not Object identities and cannot extend this map.

### Writer responsibilities

1. `gmv_core.identity` owns the closed map and exact validation.
2. Dynamic Object creation must use the transaction-bound
   `gmv_core.repositories.identity.allocate_and_create_object`; allocation and
   Object insertion remain one commit.
3. A writer receiving an OID for a typed role must validate it with the exact
   `expected_type` before side effects and must also rely on persistence
   enforcement at commit.
4. Fixed-identity bootstrap code may not use silent `INSERT OR IGNORE` as an
   authority decision. It must validate the declared pair and fail closed on a
   missing or mistyped required Object unless a separate Project Owner decision
   explicitly grants creation authority. The current Knowledge Engine
   `PER-000001` seed is the sole tracked production direct Object insert and is
   a required remediation target, not an exception.
5. Migration code may preserve existing identities only after an in-transaction
   preflight. It must never normalize, rewrite, infer, or auto-create an Object
   to make enforcement pass.
6. The frozen JSON Object artifacts remain derived and non-authoritative. Any
   future writer requires separate approval and must use the Core Identity API.

## Required preflight for future enforcement

A future migration/enforcement slice must fail before DDL unless all of the
following are true:

1. the source schema is exactly v7, foreign-key enforcement is active,
   `integrity_check` is `ok`, and `foreign_key_check` is empty;
2. `OID_CONTRACT.md`, `gmv_core.identity`, and `oid_sequences` expose exactly
   the six accepted pairs, with no missing, extra, or divergent mapping;
3. every `objects` row has a recognized prefix and its exact mapped type;
4. every non-null typed extension reference listed above resolves to the exact
   required Object type;
5. every sequence is at or above the maximum committed number for its pair;
6. frozen JSON identity artifacts pass canonical OID/type and duplicate-identity
   diagnostics;
7. a tracked-writer inventory finds no unapproved direct Object insert/update,
   no count-based allocator, and no bypass of expected-type validation; and
8. the complete rows, views and results, triggers, indexes, sequences, foreign
   keys, and dependent schema have been snapshotted for parity verification.

The data checks must run again inside the same write transaction that performs
future DDL so that verification and enforcement have no time-of-check/time-of-use
gap. Isolated tests must cover each valid pair, unknown prefixes and types,
every prefix/type mismatch, all six typed-reference mismatches, sequence
divergence, injected-error rollback, idempotence, and complete parity. Live
cutover, milestone backup, restore authority, and default-version promotion
remain separate Project Owner gates.

## Compatibility evidence at this decision gate

The live database was opened with `mode=ro` and `query_only=ON`. It is schema
v7, SHA-256 `54df5b9ef7fe9e17c205a15b8fa7569e7f57b898e674ae0aca45ccb1a2b3913d`,
with `integrity_check=ok` and zero foreign-key violations. All 12 Objects match
the closed map; all six typed-reference classes have zero mismatches; all six
`oid_sequences` rows match the map and have no lag. Database hash, mtime, and
size were identical before and after the audit.

This evidence proves current compatibility only. It does not replace the
required future in-transaction preflight or persistence enforcement.

## Consequences

- DB-008 can enforce a closed, already-authoritative mapping without inventing
  an Object vocabulary.
- Existing live data requires no identity repair before isolated migration
  design.
- The Knowledge Engine fixed Person seed must be made fail-closed in the next
  implementation slice; it receives no historical exemption.
- OID immutability, lifecycle status, Queue state, and richer Relation
  semantics remain outside this decision except where already required by
  their own authoritative contracts.

## References

- `00_CONFIG/OID_CONTRACT.md`.
- `gmv_core/identity.py` and `gmv_core/repositories/identity.py`.
- `00_CONFIG/ADR_MAIN011_CANONICAL_IDENTITY.md`.
- `00_CONFIG/ADR_DB006_ENGINE_SERVICE_RECONCILIATION.md`.
- `00_CONFIG/ADR_DB002_RESTRICTIVE_FOREIGN_KEYS.md`.
- `00_CONFIG/OPERATIONAL_RUN_RECORD_SCHEMA.json`.
- `GMV_V2_EXECUTION_ROADMAP.md` — Sprint 003 step 6.
- `GMV_V2_BACKLOG.md` — `DB-008`.
- Project Owner authorization recorded on 2026-07-19.
