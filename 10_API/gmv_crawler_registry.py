#!/usr/bin/env python3
"""GMV Crawler — crawler_source_registry driver for REGISTER + DETECT CHANGE.

Drives the REGISTER and DETECT CHANGE stages (crawler spec §3 / Correction 6)
against ``crawler_source_registry`` (gmv_core/migration_sql/009_crawler_
source_registry.sql, migration version 9): for every ``SourceListing`` a
``SourceConnector`` (step 4) reports, compute the content identity and
transition the registry to the real post-scan picture — never a bare
``DELETE FROM``.

This is the closest real precedent, read before writing this module, and
the bug this module is deliberately written NOT to inherit:
``gmv_evidence_pipeline.py::scan()`` (line 194) does ``if not row["paths"]:
del old[fid]`` — it silently removes the identity when a file disappears,
instead of marking it removed. Correction 6's rule, made structural by
migration 009's own triggers (``state='DELETED'`` requires a non-NULL
``deleted_at``, on both INSERT and UPDATE): the crawler never deletes a
row; a source that is no longer seen transitions to ``DELETED`` and stays
in the table.

Algorithm, exactly as specified by the Task 2 brief (``opencode_task_2.md``):

1. ``content_hash = connector.content_hash(listing.locator)``.
2. A **live** (non-``DELETED``) row in ``crawler_source_registry`` with
   that ``content_hash`` exists: same ``canonical_locator`` ->
   ``UNCHANGED`` (only ``last_seen_at`` updated); different
   ``canonical_locator`` -> ``MOVED`` (locator and ``last_seen_at``
   updated).
2b. A ``DELETED`` row with that ``content_hash`` exists (content
    previously seen, then removed, now seen again — by this connector or
    a different one): revived in place (the row cannot be re-INSERTed,
    ``content_hash`` is the PRIMARY KEY) to ``state='NEW'``, ``connector``
    and ``canonical_locator`` reassigned to this scan's values,
    ``deleted_at`` cleared, ``last_seen_at`` updated. ``discovered_at`` is
    left untouched (rule 4 below: it marks this identity's first-ever
    appearance, not the current observation streak). See "Bug fixed"
    below for why this step exists.
3. No row (live or ``DELETED``) with that ``content_hash``: a row with
   the same ``canonical_locator`` (this connector) exists -> the content
   at that path changed; a **new** row (new content_hash = new PK) is
   inserted with ``MODIFIED`` and the old row is left untouched here — if
   that old content_hash is not seen anywhere else in this scan it
   transitions to ``DELETED`` in step 5 below, never removed. Otherwise
   -> ``NEW``.
4. ``discovered_at`` is set only on INSERT; ``last_seen_at`` on every
   write, including the ``DELETED`` sweep and the ``2b`` revival.
5. After every item: each row for this connector whose content_hash was
   **not** seen in this scan and whose state is not already ``DELETED``
   transitions to ``DELETED`` with ``deleted_at = now``. Never a
   ``DELETE FROM``.

Bug fixed after the first version of this module shipped (found by
independent adversarial review, reproduced empirically, not hypothetical):
the original ``content_hash`` lookup (step 2) matched **any** row
regardless of ``state``, including ``DELETED`` ones — which are never
removed from the table by design (rule 5). Two concrete, reproducible
failures resulted whenever previously-deleted content reappeared:
(a) the revived row kept its stale ``deleted_at`` timestamp forever (it
was only ever cleared on INSERT, and this path is an UPDATE), leaving a
row with an active ``state`` and a non-NULL ``deleted_at`` — a
self-contradictory combination no migration-009 trigger catches (the
triggers only forbid the opposite: ``DELETED`` with ``deleted_at`` NULL);
(b) because the ``content_hash`` lookup is deliberately global (not
scoped by ``connector_id`` — content-addressed identity, see below) but
the old code's UNCHANGED/MOVED branch never touched the ``connector``
column, a row could be silently hijacked across connectors: connector A's
deleted row, revived by connector B reporting the same content, kept
``connector='A'`` forever — B's own sweep would never see it (scoped to
B), and A's next sweep would still claim it (scoped to A), each connector
now permanently blind to a row it should own. Step 2b closes both: a
``DELETED`` match is never folded into the UNCHANGED/MOVED branch, and
its revival explicitly reassigns ``connector``/``canonical_locator`` and
clears ``deleted_at``.

Decisions made while implementing, explicit rather than silent (the brief
requires the undocumented ones to be stated in the commit, not hidden):

- **``connector_id`` is caller-supplied.** The schema's ``connector``
  column is NOT NULL, but `SourceConnector` (gmv_crawler_contracts.py,
  read in full) has ``list()/metadata()/download()/revision()/
  content_hash()`` and nothing that names the source. Deriving a name
  from ``connector.__class__.__name__`` would be a fragile, implicit
  identity (a fake in tests, a renamed class, a renamed connector all
  silently change it); the caller states the stable connector identity
  explicitly — the same "accept from the caller what no upstream object
  yet supplies" pattern steps 9-12 already established.
- **Locator and sweep lookups are scoped per ``connector_id``; the
  content_hash lookup is not.** The brief scopes step 5 explicitly ("per
  questo connector"), and step 3's "stesso canonical_locator" has to mean
  the same thing — two connectors are independent locator namespaces
  (two different sources can legitimately have a path with the same
  string), so a locator match against another connector's row would be a
  false MODIFIED/NEW. The content_hash lookup is global because
  ``content_hash`` is the table's PRIMARY KEY (content-addressed identity,
  Correction 6) — at most one row, by definition, regardless of connector.
- **``connector.content_hash(locator)`` failure for a single item does
  not abort the scan** (no real precedent for this case exists anywhere
  in the repo — the task brief names it as an open decision). Each such
  item is isolated the same way step 11 (Candidate extraction) isolated
  malformed candidates: it is reported in ``RegisterScanResult.failed``,
  the locator is excluded from step 5's sweep, and:
  - if a non-``DELETED`` row already exists for (``connector_id``,
    ``canonical_locator``), it transitions to ``state='FAILED'`` with
    ``last_seen_at = now`` (``deleted_at`` stays NULL — ``FAILED`` is the
    schema's own DETECT-CHANGE vocabulary for "source present but
    currently unreadable", crawler spec §24, and the migration's trigger
    only requires ``deleted_at`` for ``DELETED``). The failure is
    visible in the registry, and the next successful scan replaces it
    (self-correcting: UNCHANGED/MOVED/MODIFIED/DELETED all overwrite it);
  - if no row exists (a brand-new item that cannot be read), nothing is
    written — ``content_hash`` is the PRIMARY KEY and the column is NOT
    NULL, so there is no consistent row to create; the failure is
    reported in the result only.
  This never deletes anything and never silently drops a previously seen
  identity. A failure of ``connector.list()`` itself still propagates —
  nothing has been written yet, so there is nothing to isolate.
- **All writes commit together.** ``register_scan()`` commits its own
  transaction at the end (the pattern ``index_atom()`` in
  gmv_crawler_fulltext_index.py already uses); on an unexpected error the
  partial scan is rolled back and the exception re-raised, so a scan is
  all-or-nothing as far as the registry is concerned.
- **``resource_oid`` and ``remote_revision`` stay NULL** for every row
  this function writes: linking registry rows to Core ``resources`` is a
  later step, and ``metadata()``/``revision()`` are not part of the
  algorithm the brief specifies (identity is content-hash-first, per
  Correction 6). This function calls only ``list()`` and ``content_hash()``
  on the connector.

Deliberate out of scope: no CLI, no Run Ledger wiring, no orchestration —
just this function and the transitions it owns.
"""
from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_crawler_contracts import (  # noqa: E402 -- reused, not reimplemented
    SourceConnector,
    validate_content_hash,
)

@dataclass(frozen=True, slots=True)
class RegisterScanResult:
    """One scan's outcome. ``failed`` lists ``(locator, message)`` for
    every item whose content identity could not be computed this scan
    (``connector.content_hash()`` raised or returned a malformed value)
    — those locators were excluded from the ``DELETED`` sweep. ``deleted``
    counts ``DELETED`` *transitions* (rows never removed from the table);
    ``transitioned_to_failed`` counts existing rows moved to ``FAILED``.
    ``revived`` counts step 2b: a previously ``DELETED`` row whose
    content reappeared this scan (by this connector or another one) —
    kept distinct from ``created`` because no INSERT happened and
    ``discovered_at`` was deliberately left untouched, not because the
    observable effect ("this content is live again") differs."""

    connector_id: str
    scanned_at: str
    created: int
    unchanged: int
    modified: int
    moved: int
    deleted: int
    revived: int
    transitioned_to_failed: int
    failed: tuple[tuple[str, str], ...]


def _failure_message(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def register_scan(
    connection: sqlite3.Connection,
    connector: SourceConnector,
    *,
    connector_id: str,
    now: str,
) -> RegisterScanResult:
    """Run one REGISTER + DETECT CHANGE pass and return its outcome.

    `connector_id` is the identity written to every row's ``connector``
    column and the scope of the locator/sweep lookups (see module
    docstring for why the Protocol does not supply it). `now` is one
    consistent timestamp used for *every* stamp this scan writes
    (``discovered_at`` on INSERTs, ``last_seen_at`` everywhere, and
    ``deleted_at`` on the sweep) so a single scan is internally coherent.
    `connection` must have migration 009 applied; this function does not
    create schema. `resource_oid`/`remote_revision` are never written
    here (module docstring). All writes commit together; on any
    unhandled error the scan is rolled back and the exception re-raised.
    """
    listings = connector.list()

    seen_hashes: set[str] = set()
    failed_locators: set[str] = set()
    failed_items: list[tuple[str, str]] = []

    created = unchanged = modified = moved = deleted = revived = transitioned_to_failed = 0

    try:
        for listing in listings:
            locator = listing.locator
            try:
                content_hash = validate_content_hash(connector.content_hash(locator))
            except Exception as error:  # per-item isolation, never abort the scan
                failed_locators.add(locator)
                failed_items.append((locator, _failure_message(error)))
                rows = connection.execute(
                    "SELECT content_hash FROM crawler_source_registry "
                    "WHERE connector = ? AND canonical_locator = ? AND state != 'DELETED'",
                    (connector_id, locator),
                ).fetchall()
                for (row_hash,) in rows:
                    connection.execute(
                        "UPDATE crawler_source_registry SET state = 'FAILED', last_seen_at = ? "
                        "WHERE content_hash = ?",
                        (now, row_hash),
                    )
                    transitioned_to_failed += 1
                continue

            seen_hashes.add(content_hash)

            existing = connection.execute(
                "SELECT canonical_locator, state FROM crawler_source_registry "
                "WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
            if existing is not None and existing[1] != "DELETED":
                existing_locator, _existing_state = existing
                if existing_locator == locator:
                    connection.execute(
                        "UPDATE crawler_source_registry SET state = 'UNCHANGED', last_seen_at = ? "
                        "WHERE content_hash = ?",
                        (now, content_hash),
                    )
                    unchanged += 1
                else:
                    connection.execute(
                        "UPDATE crawler_source_registry SET state = 'MOVED', canonical_locator = ?, "
                        "last_seen_at = ? WHERE content_hash = ?",
                        (locator, now, content_hash),
                    )
                    moved += 1
                continue

            if existing is not None:  # state == 'DELETED': content reappeared, revive in place
                connection.execute(
                    "UPDATE crawler_source_registry SET state = 'NEW', connector = ?, "
                    "canonical_locator = ?, last_seen_at = ?, deleted_at = NULL "
                    "WHERE content_hash = ?",
                    (connector_id, locator, now, content_hash),
                )
                revived += 1
                continue

            same_locator_row = connection.execute(
                "SELECT content_hash FROM crawler_source_registry "
                "WHERE connector = ? AND canonical_locator = ?",
                (connector_id, locator),
            ).fetchone()
            state = "MODIFIED" if same_locator_row is not None else "NEW"
            connection.execute(
                "INSERT INTO crawler_source_registry "
                "(content_hash, connector, canonical_locator, state, discovered_at, last_seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (content_hash, connector_id, locator, state, now, now),
            )
            if state == "MODIFIED":
                modified += 1
            else:
                created += 1

        stale = connection.execute(
            "SELECT content_hash, canonical_locator FROM crawler_source_registry "
            "WHERE connector = ? AND state != 'DELETED'",
            (connector_id,),
        ).fetchall()
        for row_hash, locator in stale:
            if row_hash in seen_hashes or locator in failed_locators:
                continue
            connection.execute(
                "UPDATE crawler_source_registry SET state = 'DELETED', deleted_at = ?, "
                "last_seen_at = ? WHERE content_hash = ?",
                (now, now, row_hash),
            )
            deleted += 1

        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return RegisterScanResult(
        connector_id=connector_id,
        scanned_at=now,
        created=created,
        unchanged=unchanged,
        modified=modified,
        moved=moved,
        deleted=deleted,
        revived=revived,
        transitioned_to_failed=transitioned_to_failed,
        failed=tuple(failed_items),
    )