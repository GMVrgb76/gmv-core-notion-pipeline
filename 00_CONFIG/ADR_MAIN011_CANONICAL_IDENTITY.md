# ADR: Canonical Identity for the GMV Core Owner Person Record

Status: Accepted
Date: 2026-07-18
Decision owner: Project Owner

## Context

`00_CONFIG/JSON_SQLITE_IDENTITY_MAPPING.md` (2026-07-18 preliminary audit,
authorized under `MAIN-011`) found exactly one JSON-sourced identifier in
`03_STATE/objects/*.json` and `02_INDEXES/OBJECT_INDEX.json`:
`OBJECT-0000001`, describing the same real-world Person as the canonical
SQLite `objects` row `PER-000001` (`Person`, `Giacomo Marco Valerio`).
`OBJECT-0000001` does not conform to `00_CONFIG/OID_CONTRACT.md`'s grammar
(a 6-letter/7-digit prefix/sequence where the contract requires exactly
3 letters/6 digits) and was classified `CONFLICT`.

A repository-wide search of every tracked file (`git grep`, source and
documentation) found no live, programmatic consumer of `OBJECT-0000001` or
of the `03_STATE/objects/` / `02_INDEXES/OBJECT_INDEX.json` paths outside
the two mapped artifacts themselves. All other matches were prose
description of the same known conflict in `GMV_TECHNICAL_REVIEW.md`,
`GMV_V2_BACKLOG.md`, and `GMV_V2_EXECUTION_ROADMAP.md` — none of them code
or data consumed at runtime.

`MAIN-011`'s full dependency closure (`ARC-004`, `ARC-005`, `DB-020`) still
contains two circular references in `GMV_V2_BACKLOG.md`
(`ARC-005` ↔ `MAIN-011`; `DB-020` ↔ `ARC-009`), which block `MAIN-011`'s
final closure. They do not block this narrow migration, which touches only
the two already-mapped, unreferenced artifacts.

## Decision

**`PER-000001` is the canonical identity** for this Person going forward.
**`OBJECT-0000001` is retired as a documented legacy alias** — its
historical use is recorded here and in the audit above; it is not preserved
as an active identifier, field, or code path.

`03_STATE/objects/OBJECT-0000001_GMV.json` is renamed to
`03_STATE/objects/PER-000001_GMV.json`, with only its `oid` field changed
from `OBJECT-0000001` to `PER-000001`. All other structure and content
(`role`, `identity`, `attributes`, `relations`, `timeline`, `documents`,
`state`, `metrics`) is preserved unchanged. `02_INDEXES/OBJECT_INDEX.json`
is updated to the same `oid` and to the renamed file's path; its `version`,
`created_at`, `type`, `name`, and `status` fields are unchanged.

This migration is authorized as a bounded `MAIN-011` slice. It does not
resolve `ARC-005`, `DB-020`, `ARC-009`, or `MAIN-011`'s broader "reject new
parallel state writes" requirement — those remain open, blocked by the
circular dependencies above, and are not addressed by this ADR.

## Consequences

- No code, database row, or other tracked file required a change beyond the
  two JSON artifacts themselves — confirmed by the repository-wide search
  above.
- Any future tooling that reads `03_STATE/objects/` must resolve this
  Person by `PER-000001`; `OBJECT-0000001` is not expected to resolve to
  anything and should not be reintroduced.
- `MAIN-011`'s remaining scope (freezing/enforcing no new parallel JSON
  identities, and the broader multi-store reconciliation under `ARC-005`)
  is unchanged by this ADR and requires its own future authorization.

## References

- `00_CONFIG/JSON_SQLITE_IDENTITY_MAPPING.md` — the preliminary audit that
  produced this finding.
- `GMV_V2_BACKLOG.md` — `MAIN-011`, `ARC-004`, `ARC-005`, `ARC-009`,
  `DB-020`.
- `00_CONFIG/OID_CONTRACT.md` — canonical OID grammar.
- Project Owner decision (2026-07-18): `PER-000001` canonical,
  `OBJECT-0000001` a documented legacy alias, migration of the two mapped
  artifacts authorized independently of `MAIN-011`'s closing dependencies.
