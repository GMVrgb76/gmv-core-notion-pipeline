"""Read-only Relation repository — Core persistence boundary for relation_service.py.

Sixth slice under ADR_CORE_PERSISTENCE_BOUNDARY.md: list/count/show only,
no schema change, connection lifecycle remains owned by the caller.
"""

from __future__ import annotations

import sqlite3


def list_relations(connection: sqlite3.Connection) -> list[tuple]:
    return connection.execute(
        """
        SELECT source_oid, source_name, relation_type, target_oid, target_name
        FROM relation_view
        ORDER BY source_oid, relation_type, target_oid
        """
    ).fetchall()


def count_relations(connection: sqlite3.Connection) -> list[tuple]:
    return connection.execute(
        """
        SELECT relation_type, COUNT(*)
        FROM relations
        GROUP BY relation_type
        ORDER BY relation_type
        """
    ).fetchall()


def get_relations(connection: sqlite3.Connection, oid: str) -> list[tuple]:
    return connection.execute(
        """
        SELECT source_oid, source_name, relation_type, target_oid, target_name
        FROM relation_view
        WHERE source_oid=? OR target_oid=?
        ORDER BY id
        """,
        (oid, oid),
    ).fetchall()
