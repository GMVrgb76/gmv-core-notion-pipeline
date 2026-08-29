#!/usr/bin/env python3
import importlib
import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

database_module = importlib.import_module("gmv_core.database")

DB = Path.home() / ".gmv_core/09_DATABASE/GMV.db"


def connect():
    return database_module.connect_path(DB)


def latest_timeline():
    with connect() as conn:
        return conn.execute("""
        SELECT id,oid,object_type,object_name,event_at,event_type,description,source
        FROM timeline_view
        ORDER BY event_at DESC,id DESC
        LIMIT 10
        """).fetchall()


def show_timeline(oid):
    with connect() as conn:
        return conn.execute("""
        SELECT id,oid,object_type,object_name,event_at,event_type,description,source
        FROM timeline_view
        WHERE oid=?
        ORDER BY event_at DESC,id DESC
        """, (oid,)).fetchall()


def print_rows(rows):
    for row in rows:
        print("|".join("" if value is None else str(value) for value in row))


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  timeline_service.py latest")
        print("  timeline_service.py show <OID>")
        sys.exit(2)

    command = sys.argv[1]
    if command == "latest":
        print_rows(latest_timeline())
    elif command == "show":
        if len(sys.argv) < 3:
            print("Usage: timeline_service.py show <OID>")
            sys.exit(2)
        rows = show_timeline(sys.argv[2])
        if not rows:
            print("No timeline entries found")
            sys.exit(1)
        print_rows(rows)
    else:
        print("Unknown command:", command)
        sys.exit(2)


if __name__ == "__main__":
    main()
