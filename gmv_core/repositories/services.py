"""Read-only Service repository — Core persistence boundary for service_service.py.

Second slice under ADR_CORE_PERSISTENCE_BOUNDARY.md: list/runs/show only,
no schema change, connection lifecycle remains owned by the caller.
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
        SELECT source,run_id,service_oid,service_name,run_at,status,duration_seconds
        FROM (
            SELECT 'service' AS source,id AS run_id,service_oid,service_name,
                   run_at,status,duration_seconds
            FROM service_runs

            UNION ALL

            SELECT 'engine' AS source,er.id AS run_id,srv.service_oid,
                   COALESCE(srv.service_name,er.engine) AS service_name,
                   er.run_at,er.status,er.duration_seconds
            FROM engine_runs er
            LEFT JOIN service_registry_view srv
              ON lower(replace(srv.service_name,' ','_'))=lower(er.engine)
            WHERE NOT EXISTS (
                SELECT 1
                FROM service_runs sr
                WHERE sr.run_at=er.run_at
                  AND lower(replace(sr.service_name,' ','_'))=lower(er.engine)
            )
        )
        ORDER BY run_at DESC,source,run_id DESC
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
