"""Read-only Resource repository — Core persistence boundary for resource_service.py.

Fifth slice under ADR_CORE_PERSISTENCE_BOUNDARY.md: list/show/count only,
no schema change, connection lifecycle remains owned by the caller.
"""

from __future__ import annotations

import sqlite3


def list_resources(connection: sqlite3.Connection) -> list[tuple]:
    return connection.execute(
        """
        SELECT resource_oid,resource_name,path,filename,status
        FROM resource_view
        ORDER BY resource_oid
        """
    ).fetchall()


def count_resources(connection: sqlite3.Connection) -> list[tuple]:
    return connection.execute(
        """
        SELECT status,COUNT(*)
        FROM resources
        GROUP BY status
        ORDER BY status
        """
    ).fetchall()


def get_resource(connection: sqlite3.Connection, resource_oid: str) -> tuple | None:
    return connection.execute(
        """
        SELECT resource_oid,resource_name,object_status,path,filename,extension,
               size_bytes,sha256,imported_at,status
        FROM resource_view
        WHERE resource_oid=?
        """,
        (resource_oid,),
    ).fetchone()
