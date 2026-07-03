#!/usr/bin/env python3
import sqlite3
import sys
from pathlib import Path

DB = Path.home() / ".gmv_core/09_DATABASE/GMV.db"


def connect():
    return sqlite3.connect(DB)


def list_services():
    with connect() as conn:
        return conn.execute("""
        SELECT service_oid,service_name,status,created_at,updated_at
        FROM service_registry_view
        ORDER BY service_oid
        """).fetchall()


def list_runs():
    with connect() as conn:
        return conn.execute("""
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
        """).fetchall()


def show_service(service_oid):
    with connect() as conn:
        return conn.execute("""
        SELECT service_oid,service_name,status,created_at,updated_at
        FROM service_registry_view
        WHERE service_oid=?
        """, (service_oid,)).fetchone()


def print_row(row):
    print("|".join("" if value is None else str(value) for value in row))


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  service_service.py list")
        print("  service_service.py runs")
        print("  service_service.py show <SRV-OID>")
        sys.exit(2)

    command = sys.argv[1]
    if command == "list":
        for row in list_services():
            print_row(row)
    elif command == "runs":
        for row in list_runs():
            print_row(row)
    elif command == "show":
        if len(sys.argv) < 3:
            print("Usage: service_service.py show <SRV-OID>")
            sys.exit(2)
        row = show_service(sys.argv[2])
        if not row:
            print("Service not found")
            sys.exit(1)
        labels = ["OID", "Name", "Status", "Created", "Updated"]
        for label, value in zip(labels, row):
            print(f"{label}: {value if value is not None else ''}")
    else:
        print("Unknown command:", command)
        sys.exit(2)


if __name__ == "__main__":
    main()
