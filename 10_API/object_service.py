#!/usr/bin/env python3
import sqlite3
import sys
from pathlib import Path

DB = Path.home() / ".gmv_core/09_DATABASE/GMV.db"

def connect():
    return sqlite3.connect(DB)

def list_objects():
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT oid,type,name,status
        FROM objects
        ORDER BY type, oid
        """)
        return cur.fetchall()

def count_objects():
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT type, COUNT(*)
        FROM objects
        GROUP BY type
        ORDER BY type
        """)
        return cur.fetchall()

def show_object(oid):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT oid,type,name,status,created_at,updated_at
        FROM objects
        WHERE oid=?
        """, (oid,))
        return cur.fetchone()

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  object_service.py list")
        print("  object_service.py count")
        print("  object_service.py show <OID>")
        sys.exit(2)

    cmd = sys.argv[1]

    if cmd == "list":
        for row in list_objects():
            print("|".join("" if v is None else str(v) for v in row))

    elif cmd == "count":
        for row in count_objects():
            print("|".join(str(v) for v in row))

    elif cmd == "show":
        if len(sys.argv) < 3:
            print("Usage: object_service.py show <OID>")
            sys.exit(2)
        row = show_object(sys.argv[2])
        if not row:
            print("Object not found")
            sys.exit(1)
        labels = ["OID", "Type", "Name", "Status", "Created", "Updated"]
        for label, value in zip(labels, row):
            print(f"{label}: {value if value is not None else ''}")

    else:
        print("Unknown command:", cmd)
        sys.exit(2)

if __name__ == "__main__":
    main()
