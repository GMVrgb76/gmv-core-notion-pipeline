# ADR: DB-003 Canonical Import Queue State Machine

Status: Accepted
Date: 2026-07-19
Decision owner: Project Owner
Backlog: `DB-003`, `DB-010`

## Context

`DB-003` requires constrained queue states, while `DB-010` requires one Import
Queue state machine. The backlog previously made each item depend on the other.
That circular dependency left neither item able to establish the contract that
the other was expected to enforce.

Schema v6 has two writable state fields, `status` and `review_status`, with no
legal-transition rule and an ambiguous definition of "pending". The live queue
is empty at this decision gate. `GMV_CORE_ARCHITECTURE.md` already establishes
`new`, `processing`, `classified`, `rejected`, and `archived`; the roadmap also
requires explicit approval, retryable versus terminal failures, and legal
approve/reject/retry/archive operations. Values found only in tests, including
`complete` and `reviewed`, are characterization data and are not authority.

## Decision

### One canonical field

The Import Queue has one canonical lifecycle field named `state`. `status` and
`review_status` are legacy fields and must not remain writable authorities after
the future `DB-010` cutover. There is no dual-write period. All tracked readers
and writers must switch atomically with that cutover; any temporary compatibility
projection must be read-only and explicitly derived from `state`.

State values are exact lowercase ASCII snake-case tokens:

| State | Meaning | Owner | Terminal |
|---|---|---|---|
| `new` | Accepted into the queue and waiting for a worker. This is the only initial state. | Enqueuer | No |
| `processing` | A worker owns the current processing attempt. | Queue worker | No |
| `classified` | Processing succeeded and the item awaits a human review outcome. | Queue worker | No |
| `approved` | Human review accepted the item; custody/archive work remains. | Reviewer | No |
| `retryable_error` | The current processing attempt failed for an explicitly retryable reason. | Queue worker | No |
| `rejected` | Human review rejected the item. | Reviewer | Yes |
| `failed` | Processing ended with a non-retryable failure. | Queue worker | Yes |
| `archived` | Approved custody/archive work completed. | Archive/custody writer | Yes |

`pending` is not a persisted state. Operational commands derive actionable
work from `new`, `classified`, `approved`, and `retryable_error`. `processing`
is open but actively owned; stale-processing detection belongs to the future
lease/attempt metadata under `DB-011`. Terminal states are never pending.

### Legal transitions

The complete allow-list is:

| From | To | Meaning |
|---|---|---|
| `new` | `processing` | A worker claims the item. |
| `processing` | `classified` | Processing succeeds and human review is required. |
| `processing` | `retryable_error` | Processing fails with a retryable cause. |
| `processing` | `failed` | Processing fails terminally. |
| `retryable_error` | `processing` | An explicitly authorized retry starts. |
| `classified` | `approved` | Human review accepts the item. |
| `classified` | `rejected` | Human review rejects the item. |
| `approved` | `archived` | Custody/archive completes. |

Every unlisted transition is forbidden, including self-transitions, skipped
states, reopening a terminal row, and direct creation in a state other than
`new`. An idempotent repeated command may return the existing state without a
write; it must not manufacture a self-transition or change `updated_at`.

### State payload and error rules

- `confidence` is nullable; when present it is a finite number in the inclusive
  range 0 through 1. No threshold or automatic approval policy is implied.
  This scalar domain is owned by DB-003 and persisted by DB-010 during the
  atomic Queue rebuild; see `ADR_DB003_AUTHORITATIVE_DOMAIN_SCOPE.md`.
- `retryable_error` and `failed` require a non-empty `error`. Every other state
  requires `error` to be null.
- `approved` and `archived` require a non-empty `proposed_destination`.
- A retry records the prior error in the canonical Event before clearing the
  current error as the item re-enters `processing`. Automated retries remain
  blocked until `DB-011` provides attempt/lease history.
- A failed write rolls back the state, associated metadata, and Event together.
  Terminal rows cannot be reopened; a future re-ingestion is a new lifecycle
  governed by `DB-009` source identity, not a mutation of terminal history.

### Writer responsibilities

1. Enqueuers create rows only in `new` and do not perform transitions.
2. Queue workers own `new`/`retryable_error` to `processing` and the three
   outcomes from `processing`. They cannot approve, reject, or archive.
3. Review writers represent an authenticated human decision and own only
   `classified` to `approved` or `rejected`. Approval sets the destination.
4. Archive/custody writers own only `approved` to `archived` and may commit the
   transition only after custody succeeds.
5. The Core transition API is the sole state writer. It validates the allow-list
   and payload, performs the update transactionally, and appends one canonical
   Event containing from/to state, actor, reason, timestamp, and correlation ID.
6. `import_service.py` currently writes the legacy default pair after performing
   synchronous import. `DB-010` must adapt it to create `new` and traverse the
   required states through the Core API; it may not insert `classified` directly.
7. Queue repositories, status, Doctor, and presentation commands remain
   read-only and derive actionable/open state from this contract.

### Persistence enforcement owned by DB-010

`DB-010` will implement this accepted contract with a versioned migration, a
single `state` column and domain `CHECK`, payload `CHECK` constraints, database
transition enforcement, the Core transition API, Event emission, and atomic
reader/writer cutover. No legacy pair is inferred from test fixtures. If the
future preflight finds queue rows, their state requires an explicit reviewed
reconciliation; the migration fails closed rather than guessing.

## Dependency resolution

- The `DB-003` decision contract depends on `DB-001` and `ARC-004`, not on
  completion of `DB-010`.
- `DB-010` implementation depends on this accepted `DB-003` decision contract,
  not on completion of every other `DB-003` constraint.
- Non-queue `DB-003` constraints may be staged separately. Queue persistence and
  transition enforcement remain owned by `DB-010`.
- Duplicated lifecycle-status policy and future checks belong to `DB-013`, not
  to DB-003 or this Queue state contract.

This ordering removes the cycle without moving `DB-010` implementation out of
its documented Sprint 004 position.

## Consequences

- The queue can no longer express contradictory execution/review combinations.
- Human review, processing, retry, terminal failure, and archive responsibility
  are distinct and enforceable.
- Existing queue readers and the synchronous importer are intentionally not
  changed by this decision-only slice; they must move atomically under `DB-010`.
- Migration, backup, live data changes, scheduler work, and automated queue
  execution are not authorized by this ADR or its acceptance task.

## References

- `GMV_V2_EXECUTION_ROADMAP.md` — Sprint 003 step 6 and Sprint 004 sequence.
- `GMV_V2_BACKLOG.md` — `DB-003`, `DB-009`, `DB-010`, `DB-011`, `AUTO-006`,
  and `AUTO-007`.
- `00_CONFIG/GMV_CORE_ARCHITECTURE.md` — Import lifecycle vocabulary.
- `00_CONFIG/ADR_CORE_PERSISTENCE_BOUNDARY.md`.
- `00_CONFIG/ADR_DB003_AUTHORITATIVE_DOMAIN_SCOPE.md`.
- Project Owner approval recorded on 2026-07-19.
