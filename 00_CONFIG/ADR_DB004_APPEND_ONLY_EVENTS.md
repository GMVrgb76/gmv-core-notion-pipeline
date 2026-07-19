# ADR: Append-Only Events and Compensating Corrections

Status: Accepted
Date: 2026-07-19
Decision owner: Project Owner

## Context

`DB-005` is complete: `events` is the sole persisted history and `timeline`
is a read-only compatibility view over Events. The live schema is version 3.
The `events` table, however, still permits `UPDATE`, `DELETE`, and primary-key
replacement, so canonical history can be rewritten or erased despite the
documented append-only architecture.

`GMV_V2_EXECUTION_ROADMAP.md` schedules `DB-004` immediately after `DB-005`.
`GMV_V2_BACKLOG.md` requires both restricted writes and compensating Event
semantics. A Project Owner decision was required because choosing how a
correction relates to immutable history is a domain decision, not a purely
technical migration detail.

## Decision

Events are strictly append-only:

1. `UPDATE` and `DELETE` against `events` are rejected at the database
   boundary.
2. Reusing an existing Event ID, including through `INSERT OR REPLACE`, is
   rejected at the database boundary.
3. A correction or supersession is a **new Event**. The original Event remains
   unchanged and the new row identifies it through nullable
   `supersedes_event_id`.
4. A non-null `supersedes_event_id` must identify an Event that already exists
   when the correction is inserted. Corrections may themselves be superseded,
   producing an explicit immutable chain.
5. Ordinary Events leave `supersedes_event_id` null. Existing writers remain
   compatible because they use explicit column lists.

Migration 004 implements these rules with database triggers. It is initially
an explicit migration target only; version 3 remains the live/current version
until a separately authorized live cutover.

## Consequences

- Supported code and direct SQLite callers cannot silently mutate or erase an
  Event once migration 004 is active.
- `timeline` retains its existing six-column compatibility contract and shows
  correction Events like any other Event; the supersession reference remains
  available from `events` itself.
- Migration 004 validates supersession-reference existence with a trigger.
  Formal foreign-key declaration and deletion policy remain owned by `DB-002`.
- A future data-repair migration that truly needs to rewrite Events must
  explicitly manage the append-only triggers inside its own reviewed,
  transactional, Project Owner-authorized migration.
- This decision does not choose a winner when multiple new Events supersede
  the same predecessor. Conflict resolution and derived-current-state policy
  remain outside this bounded DB-004 slice.

## References

- `GMV_V2_EXECUTION_ROADMAP.md` — Sprint 003 sequence step 4 and append-only
  Events exit criterion.
- `GMV_V2_BACKLOG.md` — `DB-004`.
- `00_CONFIG/PROJECT_STATUS.md` — completed `DB-005` live cutover and next
  canonical gate.
- Project Owner decision (2026-07-19): strict append-only Events; corrections
  are new Events that explicitly reference the Event they supersede.
