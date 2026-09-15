#!/usr/bin/env python3
"""GMV Crawler — Full-text index (crawler preplan step 13 / spec v0.2 §21-22).

Spec §21: "MVP obbligatorio = SQLite metadata + FTS5; vector index solo
dopo validazione FTS; graph index solo se necessario." Retrieval cascade
(§21-22): "exact lookup -> structured query -> FTS -> vector -> source-
level." This module builds only the FTS layer of that cascade -- the
exact/structured-lookup layers would need `atoms_runtime` (spec §27),
which no migration has created yet (steps 1-12 never built an atom
persistence table); building the full cascade now would be exactly the
premature-engine mistake this session's discipline avoids elsewhere.

**Architectural correction made while building this step, not assumed
from the spec:** an early draft of this step added a `CREATE VIRTUAL
TABLE ... USING fts5(...)` migration to `gmv_core/migration_sql/`,
following the same numbered-migration pattern steps 3/6 (009/010) used.
That draft failed immediately on first execution (not caught by reading
code alone -- caught by actually running the migration against a real
connection, per this session's own "verify empirically" discipline):
`gmv_core/authorization.py`'s SEC-006 write-capability authorizer denies
`SQLITE_CREATE_VTABLE` unconditionally, for every caller, by explicit
design ("SQLITE_ATTACH, SQLITE_DETACH, SQLITE_ANALYZE,
SQLITE_CREATE_VTABLE, SQLITE_DROP_VTABLE, and any action code introduced
by a future SQLite version and not listed above: denied by construction"
-- `gmv_core/authorization.py`'s own comment, not a bug to route around).
No caller, mode, or migration file can weaken this ("No production
caller or environment setting can weaken this to log-only" -- same
module's docstring).

FTS being a **derived, rebuildable** structure ("STATE/TIMELINE/RELATIONS/
CLAIMS/LEDGER/... registry/FTS/vector/graph=derivati e ricostruibili" --
`GMV_KNOWLEDGE_MONAD_SPEC_v1.0` §11 and the crawler spec's own §2), never
canonical Core data, is why this index has no business being materialized
*as canonical schema* inside `gmv_core`'s SEC-006-governed persistence
boundary (`ADR_CORE_PERSISTENCE_BOUNDARY.md`) -- but it does **not**, on
its own, authorize a second raw `sqlite3.connect()` call site.
`tests/test_sqlite_connection_boundary.py::test_only_core_factory_calls_sqlite_connect`
statically enforces exactly one raw `sqlite3.connect()` owner
repo-wide (`gmv_core/database.py`) -- confirmed **active**, not deferred,
by `ADR_CORE_PERSISTENCE_BOUNDARY.md`'s own 2026-07-21 addendum ("ARC-002
static connect-boundary check confirmed satisfied": `DB-002`/`DB-003`
completed, the check "has been continuously active since ... 2026-07-19").
An earlier draft of this module's docstring cited only the ADR's original,
superseded Decision §3 ("deferred") and missed that addendum entirely --
caught by adversarial review reproducing the boundary test's failure
empirically after staging this file, not by reading the ADR to the end.
Committing this module as originally drafted would have broken that test,
and therefore `scripts/quality_gate.sh`, on the first push.

Presented with this conflict -- a real, deliberate security boundary
(SEC-006/ARC-002) vs. a real, deliberate architectural constraint
(`SQLITE_CREATE_VTABLE` denied unconditionally, no override) -- the user
chose, among three legitimate options (a full ADR amendment; relocating
this module outside the three guarded roots; a named, justified
whitelist entry), to add this file as a second, explicitly named
`sqlite3.connect()` owner directly in
`test_sqlite_connection_boundary.py` itself, not to silently work around
it or decide unilaterally which governance path to take. `02_INDEXES/`
(`00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md`: "Runtime output", "Index
owner", never Git by default) remains the natural on-disk home for the
index file itself, the same way `03_STATE/ombra/` (step 8) is for
materialized Monads -- not hardcoded here, caller-supplied, same as
`target_path` patterns elsewhere in this crawler.

Indexed columns are SUBJECT/PREDICATE/OBJECT -- the ATOM schema's own
semantic core (`GMV_KNOWLEDGE_MONAD_SPEC_v1.0` §2.3) -- not the full
18 fields. Every other field is either non-textual (CONFIDENCE,
VALID_FROM/TO), governed/structured rather than free text (STATUS,
PREDICATE_CLASS, VISIBILITY -- an exact/structured lookup serves these
better than a fuzzy FTS match), or not yet meaningfully populated at this
point in the crawler's build order (SOURCE resolves through
`crawler_source_registry`, migration 009, not duplicated here). `atom_id`
is stored `UNINDEXED` (not full-text-searched) -- the reference key back
to whatever eventually becomes the canonical atom store, not itself
something a free-text query should match against.

Tokenizer: `unicode61 remove_diacritics 2` -- this repo's real corpus
(Federico Garibaldi, RCV_001) is Italian text; without diacritic removal
a query for "citta" would not match text containing "città". No existing
precedent for this choice anywhere in the repo (grepped: no prior FTS5
usage at all) -- a first decision, not a continuation of an established
pattern.

Known v1 gaps, documented not fixed: no `delete`/`update` (no lifecycle
event in this crawler's build order yet requires one -- step 12's
Reconciliation engine never invalidates an existing atom); no dedup
guard against calling `index_atom()` twice for the same `atom_id` (no
canonical atom store exists yet to make that meaningful); `search_atoms()`
passes its `query` argument to FTS5's `MATCH` operator unmodified -- a
caller-supplied string containing FTS5 query-syntax characters (quotes,
`AND`/`OR`/`NOT`, `-`) is interpreted as FTS5 syntax, not escaped to a
literal phrase; a malformed query raises `sqlite3.OperationalError`
straight from SQLite, not normalized to a module-specific error.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_atom_validator import AtomCandidate  # noqa: E402 -- reused, not reimplemented

TOKENIZER = "unicode61 remove_diacritics 2"

_CREATE_TABLE_SQL = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS atoms_fts USING fts5(
    atom_id UNINDEXED,
    subject,
    predicate,
    object,
    tokenize = '{TOKENIZER}'
)
"""


def open_index(path: Path) -> sqlite3.Connection:
    """Open (creating if needed) the derived atom full-text index at
    `path` -- a plain, unguarded `sqlite3.connect()`, deliberately not
    `gmv_core.database.connect_path()` (see module docstring for why).
    `path`'s parent directory must already exist; this function does not
    create directories, matching `gmv_monad_materializer.py`'s (step 8)
    identical stance on `target_path`. `02_INDEXES/` is this repo's own
    classified location for exactly this kind of derived artifact
    (`00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md`), but is not hardcoded here
    -- the caller decides, the same "no premature engine" pattern steps
    8/9/10/11 already established for their own caller-supplied inputs.
    """
    connection = sqlite3.connect(path)
    connection.execute(_CREATE_TABLE_SQL)
    connection.commit()
    return connection


def index_atom(connection: sqlite3.Connection, atom: AtomCandidate) -> None:
    """Add one atom's SUBJECT/PREDICATE/OBJECT to the index. Does not
    check for an existing row with the same `atom_id` (see module
    docstring's "known v1 gaps") -- calling this twice for the same atom
    inserts a duplicate FTS row, both of which will match a future
    search."""
    connection.execute(
        "INSERT INTO atoms_fts (atom_id, subject, predicate, object) VALUES (?, ?, ?, ?)",
        (atom.atom_id, atom.subject, atom.predicate, atom.object),
    )
    connection.commit()


def search_atoms(
    connection: sqlite3.Connection, query: str, *, limit: int = 50
) -> tuple[str, ...]:
    """Return matching `atom_id`s, most relevant first (FTS5's `bm25()`
    ranking function -- lower is more relevant, SQLite's own convention).
    `query` is passed to FTS5's `MATCH` unmodified -- see module
    docstring's "known v1 gaps" on why this is not sanitized/escaped."""
    rows = connection.execute(
        "SELECT atom_id FROM atoms_fts WHERE atoms_fts MATCH ? "
        "ORDER BY bm25(atoms_fts) LIMIT ?",
        (query, limit),
    ).fetchall()
    return tuple(row[0] for row in rows)
