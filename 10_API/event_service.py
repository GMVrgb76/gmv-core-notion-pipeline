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


def latest_events():
    with connect() as conn:
        return conn.execute("""
        SELECT id,oid,object_type,object_name,event_at,event_type,description,source
        FROM timeline_view
        ORDER BY event_at DESC,id DESC
        LIMIT 10
        """).fetchall()


def show_events(oid):
    with connect() as conn:
        return conn.execute("""
        SELECT id,oid,object_type,object_name,event_at,event_type,description,source
        FROM timeline_view
        WHERE oid=?
        ORDER BY event_at DESC,id DESC
        """, (oid,)).fetchall()


def count_events():
    with connect() as conn:
        return conn.execute("""
        SELECT event_type,COUNT(*)
        FROM events
        GROUP BY event_type
        ORDER BY event_type
        """).fetchall()


def print_rows(rows):
    for row in rows:
        print("|".join("" if value is None else str(value) for value in row))


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  event_service.py latest")
        print("  event_service.py show <OID>")
        print("  event_service.py count")
        sys.exit(2)

    command = sys.argv[1]
    if command == "latest":
        print_rows(latest_events())
    elif command == "show":
        if len(sys.argv) < 3:
            print("Usage: event_service.py show <OID>")
            sys.exit(2)
        rows = show_events(sys.argv[2])
        if not rows:
            print("No events found")
            sys.exit(1)
        print_rows(rows)
    elif command == "count":
        print_rows(count_events())
    else:
        print("Unknown command:", command)
        sys.exit(2)


if __name__ == "__main__":
    main()
