"""Read-only Import Queue repository — Core persistence boundary for queue_service.py.

Seventh slice under ADR_CORE_PERSISTENCE_BOUNDARY.md: list/show only,
no schema change, connection lifecycle remains owned by the caller.
"""

from __future__ import annotations

import sqlite3

QUEUE_COLUMNS = """
import_id,resource_oid,filename,status,review_status,proposed_destination,
confidence,error,created_at,updated_at
"""


def list_queue(connection: sqlite3.Connection, *, pending_only: bool = False) -> list[tuple]:
    query = f"SELECT {QUEUE_COLUMNS} FROM import_queue_view"
    if pending_only:
        query += " WHERE status='pending' OR review_status='pending_review'"
    query += " ORDER BY created_at DESC,import_id DESC"
    return connection.execute(query).fetchall()


def get_queue_entry(connection: sqlite3.Connection, import_id: int) -> tuple | None:
    return connection.execute(
        f"SELECT {QUEUE_COLUMNS} FROM import_queue_view WHERE import_id=?",
        (import_id,),
    ).fetchone()
