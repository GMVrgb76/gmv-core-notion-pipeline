#!/usr/bin/env python3
import sqlite3
import sys
from pathlib import Path

DB = Path.home() / ".gmv_core/09_DATABASE/GMV.db"


def connect():
    return sqlite3.connect(DB)


def list_resources():
    with connect() as conn:
        return conn.execute("""
        SELECT resource_oid,resource_name,path,filename,status
        FROM resource_view
        ORDER BY resource_oid
        """).fetchall()


def count_resources():
    with connect() as conn:
        return conn.execute("""
        SELECT status,COUNT(*)
        FROM resources
        GROUP BY status
        ORDER BY status
        """).fetchall()


def show_resource(resource_oid):
    with connect() as conn:
        return conn.execute("""
        SELECT resource_oid,resource_name,object_status,path,filename,extension,
               size_bytes,sha256,imported_at,status
        FROM resource_view
        WHERE resource_oid=?
        """, (resource_oid,)).fetchone()


def print_row(row):
    print("|".join("" if value is None else str(value) for value in row))


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  resource_service.py list")
        print("  resource_service.py show <RES-OID>")
        print("  resource_service.py count")
        sys.exit(2)

    command = sys.argv[1]
    if command == "list":
        for row in list_resources():
            print_row(row)
    elif command == "show":
        if len(sys.argv) < 3:
            print("Usage: resource_service.py show <RES-OID>")
            sys.exit(2)
        row = show_resource(sys.argv[2])
        if not row:
            print("Resource not found")
            sys.exit(1)
        labels = [
            "OID", "Name", "Object Status", "Path", "Filename", "Extension",
            "Size", "SHA256", "Imported", "Resource Status",
        ]
        for label, value in zip(labels, row):
            print(f"{label}: {value if value is not None else ''}")
    elif command == "count":
        for row in count_resources():
            print_row(row)
    else:
        print("Unknown command:", command)
        sys.exit(2)


if __name__ == "__main__":
    main()
