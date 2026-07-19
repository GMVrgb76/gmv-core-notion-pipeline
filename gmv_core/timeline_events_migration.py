"""Timeline -> Events row migration (DB-005 data-migration slice).

Deterministic, one-to-one, multiset-aware content matching: an Events row
reconciles at most one Timeline row, even when several Timeline rows share
identical content. New rows always get fresh AUTOINCREMENT ids in `events`;
`timeline` is only ever read here, never written or altered.

The migration evidence log (see the CLI service in
10_API/timeline_events_migration_service.py) is a convenience audit trail,
not a dependency for correctness: `reconcile_evidence()` always reconstructs
the true, current Timeline<->Events mapping directly from the two tables'
content, so a missing or partial log can always be repaired without ever
needing to touch `timeline`.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass

Content = tuple[str, str, str, "str | None", "str | None"]


@dataclass(frozen=True, slots=True)
class MatchedRow:
    """One Timeline row reconciled against exactly one Events row by content."""

    timeline_id: int
    events_id: int
    oid: str
    event_at: str
    event_type: str
    description: str | None
    source: str | None
    content_sha256: str


def _content_hash(content: Content) -> str:
    payload = "\x1f".join("" if value is None else str(value) for value in content)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rows(connection: sqlite3.Connection, table: str) -> list[tuple]:
    if table == "timeline":
        query = "SELECT id,oid,event_at,event_type,description,source FROM timeline ORDER BY id"
    elif table == "events":
        query = "SELECT id,oid,event_at,event_type,description,source FROM events ORDER BY id"
    else:
        raise ValueError(f"unsupported table: {table}")
    return list(connection.execute(query))


def _match(
    timeline_rows: list[tuple], events_rows: list[tuple]
) -> tuple[list[MatchedRow], list[tuple]]:
    """Deterministic one-to-one multiset match; each Events row used at most once.

    Rows are processed in ascending id order on both sides, so the result is
    reproducible across calls given the same table contents. Returns
    (matched, unmatched): `matched` covers every Timeline row that already
    has a corresponding Events row by full content; `unmatched` lists the
    remaining Timeline rows (raw tuples including their id) that have no
    Events counterpart yet.
    """
    available: dict[Content, deque[int]] = defaultdict(deque)
    for events_id, oid, event_at, event_type, description, source in events_rows:
        available[(oid, event_at, event_type, description, source)].append(events_id)

    matched: list[MatchedRow] = []
    unmatched: list[tuple] = []
    for timeline_id, oid, event_at, event_type, description, source in timeline_rows:
        content: Content = (oid, event_at, event_type, description, source)
        bucket = available.get(content)
        if bucket:
            matched.append(
                MatchedRow(
                    timeline_id=timeline_id,
                    events_id=bucket.popleft(),
                    oid=oid,
                    event_at=event_at,
                    event_type=event_type,
                    description=description,
                    source=source,
                    content_sha256=_content_hash(content),
                )
            )
        else:
            unmatched.append((timeline_id, oid, event_at, event_type, description, source))
    return matched, unmatched


def plan_migration(connection: sqlite3.Connection) -> list[tuple]:
    """Read-only: Timeline rows (full tuples incl. id) with no Events counterpart yet."""
    _matched, unmatched = _match(_rows(connection, "timeline"), _rows(connection, "events"))
    return unmatched


def apply_migration(connection: sqlite3.Connection) -> list[MatchedRow]:
    """Insert missing Timeline rows into Events inside the caller's transaction.

    Requires an already-open transaction (matches
    gmv_core.repositories.identity.allocate_and_create_object's contract).
    `timeline` is read here and never written. Idempotent: once every
    Timeline row has an Events counterpart, a further call inserts nothing
    and returns [].
    """
    if not connection.in_transaction:
        raise ValueError("timeline-to-events migration requires an active transaction")

    pending = plan_migration(connection)
    inserted: list[MatchedRow] = []
    for timeline_id, oid, event_at, event_type, description, source in pending:
        cursor = connection.execute(
            "INSERT INTO events (oid,event_at,event_type,description,source) VALUES (?,?,?,?,?)",
            (oid, event_at, event_type, description, source),
        )
        content: Content = (oid, event_at, event_type, description, source)
        inserted.append(
            MatchedRow(
                timeline_id=timeline_id,
                events_id=int(cursor.lastrowid),
                oid=oid,
                event_at=event_at,
                event_type=event_type,
                description=description,
                source=source,
                content_sha256=_content_hash(content),
            )
        )
    return inserted


def reconcile_evidence(connection: sqlite3.Connection) -> list[MatchedRow]:
    """Read-only: the complete, current Timeline<->Events mapping, by content alone.

    Reconstructible at any time regardless of whether an evidence log exists,
    is missing, or is partial -- `timeline` is never modified by this module,
    so this always reflects ground truth.
    """
    matched, _unmatched = _match(_rows(connection, "timeline"), _rows(connection, "events"))
    return matched
