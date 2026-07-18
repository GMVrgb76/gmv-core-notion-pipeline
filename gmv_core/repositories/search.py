"""Read-only Search repository — Core persistence boundary for search_service.py.

Fourth slice under ADR_CORE_PERSISTENCE_BOUNDARY.md: single cross-table
lookup, no schema change, connection lifecycle remains owned by the caller.
"""

from __future__ import annotations

import sqlite3


def search(connection: sqlite3.Connection, query: str) -> list[tuple]:
    match = query.lower()
    rows: list[tuple] = []

    rows.extend(
        connection.execute(
            """
            SELECT 'object',oid,name,
                   CASE
                       WHEN instr(lower(name),?) > 0 THEN 'name:' || name
                       ELSE 'type:' || type
                   END
            FROM objects
            WHERE instr(lower(name),?) > 0 OR instr(lower(type),?) > 0
            ORDER BY oid
            """,
            (match, match, match),
        ).fetchall()
    )

    rows.extend(
        connection.execute(
            """
            SELECT 'resource',resource_oid,filename,
                   CASE
                       WHEN instr(lower(filename),?) > 0 THEN 'filename:' || filename
                       ELSE 'path:' || path
                   END
            FROM resources
            WHERE instr(lower(filename),?) > 0 OR instr(lower(path),?) > 0
            ORDER BY resource_oid
            """,
            (match, match, match),
        ).fetchall()
    )

    rows.extend(
        connection.execute(
            """
            SELECT 'event',CAST(id AS TEXT),event_type,'description:' || description
            FROM events
            WHERE instr(lower(COALESCE(description,'')),?) > 0
            ORDER BY id DESC
            """,
            (match,),
        ).fetchall()
    )

    rows.extend(
        connection.execute(
            """
            SELECT 'relation',CAST(id AS TEXT),source_oid || '->' || target_oid,
                   'relation_type:' || relation_type
            FROM relations
            WHERE instr(lower(relation_type),?) > 0
            ORDER BY id
            """,
            (match,),
        ).fetchall()
    )

    return rows
