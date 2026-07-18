# JSON / SQLite Identity Mapping — MAIN-011 Preliminary Audit

Status: Read-only evidence collection only. No migration, freeze, or
architectural decision made here.

## Scope and Authority

This document is the sole authorized output of the MAIN-011 preliminary
slice: a read-only audit of every identifier in `03_STATE/objects/*.json`
and `02_INDEXES/OBJECT_INDEX.json`, cross-referenced against the canonical
`objects` table in `09_DATABASE/GMV.db`.

Explicitly **not** authorized or performed by this task: freezing JSON
writes, migrating any field, deleting or demoting any file, writing an ADR,
or proposing an architecture. `MAIN-011`'s full reconciliation remains
blocked on two circular backlog dependencies not resolved here:
`ARC-005` ↔ `MAIN-011`, and `DB-020` ↔ `ARC-009`.

## Method

1. Enumerated every `*.json` file under `03_STATE/objects/`.
2. Read `02_INDEXES/OBJECT_INDEX.json` in full.
3. Read the complete `objects` table from `09_DATABASE/GMV.db` (read-only
   connection).
4. Checked each JSON-sourced identifier's format against
   `00_CONFIG/OID_CONTRACT.md`'s grammar (`AAA-000001`: exactly three
   uppercase ASCII letters, a hyphen, six decimal digits).
5. Checked each JSON-sourced identifier for a corresponding SQLite `objects`
   row by exact OID match, and separately by `type`+`name` match (to detect
   the same real-world entity under a different identifier).

## Findings

**FACT** — `03_STATE/objects/` contains exactly one file:
`OBJECT-0000001_GMV.json`.

**FACT** — `02_INDEXES/OBJECT_INDEX.json` declares exactly one object entry,
`oid: "OBJECT-0000001"`, pointing at that same file. Index and directory
contents agree; no orphaned index entry, no untracked file.

**FACT** — The SQLite `objects` table (read at audit time) contains 12 rows:
`COR-000001`, `PER-000001`, `PLG-000001..004`, `RES-000001`,
`SRV-000001..004`, `SYS-000001`.

**FACT** — `OBJECT-0000001` does not match `OID_CONTRACT.md`'s grammar: the
prefix `OBJECT` is six letters (contract requires exactly three), and the
sequence `0000001` is seven digits (contract requires exactly six).

**FACT** — `OBJECT-0000001_GMV.json`'s content (`type: "Person"`,
`name: "Giacomo Marco Valerio"`) is identical, entity-for-entity, to SQLite
row `PER-000001` (`type='Person'`, `name='Giacomo Marco Valerio'`). No other
JSON-sourced identifier exists to compare against the remaining 11 SQLite
rows.

## Mapping Table

| JSON identifier | Source file | Format valid (`OID_CONTRACT.md`) | SQLite exact-OID match | SQLite type+name match | Classification |
|---|---|---|---|---|---|
| `OBJECT-0000001` | `03_STATE/objects/OBJECT-0000001_GMV.json` (indexed by `02_INDEXES/OBJECT_INDEX.json`) | No — prefix is 6 letters, sequence is 7 digits | None (no `OBJECT-*` row exists in SQLite) | Yes — `PER-000001` (`Person`, `Giacomo Marco Valerio`) | **CONFLICT** — non-conformant identifier aliasing an existing, differently-numbered canonical identity for the same entity |

## Completeness Statement

Every file present under `03_STATE/objects/` was read (1 of 1). Every entry
declared in `02_INDEXES/OBJECT_INDEX.json` was read (1 of 1), and it
resolves to the same single file with no discrepancy. Every row in the
SQLite `objects` table was read (12 of 12) and checked against the one
JSON-sourced identifier. No JSON identifier in the audited scope was left
unclassified. This audit found exactly one identifier in scope, and it is
fully classified above.

## What This Audit Does Not Resolve

- Whether `OBJECT-0000001_GMV.json`'s non-identity fields (`role`,
  `attributes`, `relations`, `timeline`, `documents`, `state`, `metrics`)
  have any SQLite equivalent — out of scope for an identity-only audit.
- Which identifier (`OBJECT-0000001` or `PER-000001`) is authoritative going
  forward.
- Whether the JSON file should be migrated, frozen, demoted to a derived
  artifact, or deleted.
- The two circular backlog dependencies blocking `MAIN-011`'s full
  reconciliation (`ARC-005` ↔ `MAIN-011`, `DB-020` ↔ `ARC-009`), which
  require a Project Owner sequencing decision before any migration step —
  the same category of decision already made once for `ARC-001` via
  `00_CONFIG/ADR_CORE_PERSISTENCE_BOUNDARY.md`.
