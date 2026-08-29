"""Read-only Object repository — Core persistence boundary for object_service.py.

First slice under ADR_CORE_PERSISTENCE_BOUNDARY.md: list/show/count only,
no schema change, connection lifecycle remains owned by the caller.
"""

from __future__ import annotations

import sqlite3


def list_objects(connection: sqlite3.Connection) -> list[tuple]:
    return connection.execute(
        """
        SELECT oid,type,name,status
        FROM objects
        ORDER BY type, oid
        """
    ).fetchall()


def count_objects(connection: sqlite3.Connection) -> list[tuple]:
    return connection.execute(
        """
        SELECT type, COUNT(*)
        FROM objects
        GROUP BY type
        ORDER BY type
        """
    ).fetchall()


def get_object(connection: sqlite3.Connection, oid: str) -> tuple | None:
    return connection.execute(
        """
        SELECT oid,type,name,status,created_at,updated_at
        FROM objects
        WHERE oid=?
        """,
        (oid,),
    ).fetchone()
