"""Read-only Service repository — Core persistence boundary for service_service.py.

Service run history is read exclusively from the canonical ``service_runs``
table. Connection lifecycle remains owned by the caller.
"""

from __future__ import annotations

import sqlite3


def list_services(connection: sqlite3.Connection) -> list[tuple]:
    return connection.execute(
        """
        SELECT service_oid,service_name,status,created_at,updated_at
        FROM service_registry_view
        ORDER BY service_oid
        """
    ).fetchall()


def list_runs(connection: sqlite3.Connection) -> list[tuple]:
    return connection.execute(
        """
        SELECT 'service' AS source,id AS run_id,service_oid,service_name,
               run_at,status,duration_seconds
        FROM service_runs
        ORDER BY run_at DESC,id DESC
        """
    ).fetchall()


def get_service(connection: sqlite3.Connection, service_oid: str) -> tuple | None:
    return connection.execute(
        """
        SELECT service_oid,service_name,status,created_at,updated_at
        FROM service_registry_view
        WHERE service_oid=?
        """,
        (service_oid,),
    ).fetchone()
