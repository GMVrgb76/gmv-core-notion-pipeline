#!/usr/bin/env python3
import sqlite3
import sys
from pathlib import Path

DB = Path.home() / ".gmv_core/09_DATABASE/GMV.db"

def connect():
    return sqlite3.connect(DB)

def list_relations():
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT source_oid, source_name, relation_type, target_oid, target_name
        FROM relation_view
        ORDER BY source_oid, relation_type, target_oid
        """)
        return cur.fetchall()

def count_relations():
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT relation_type, COUNT(*)
        FROM relations
        GROUP BY relation_type
        ORDER BY relation_type
        """)
        return cur.fetchall()

def show_relations(oid):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT source_oid, source_name, relation_type, target_oid, target_name
        FROM relation_view
        WHERE source_oid=? OR target_oid=?
        ORDER BY id
        """, (oid, oid))
        return cur.fetchall()

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  relation_service.py list")
        print("  relation_service.py count")
        print("  relation_service.py show <OID>")
        sys.exit(2)

    cmd = sys.argv[1]

    if cmd == "list":
        for r in list_relations():
            print("|".join("" if v is None else str(v) for v in r))

    elif cmd == "count":
        for r in count_relations():
            print("|".join(str(v) for v in r))

    elif cmd == "show":
        if len(sys.argv) < 3:
            print("Usage: relation_service.py show <OID>")
            sys.exit(2)
        rows = show_relations(sys.argv[2])
        if not rows:
            print("No relations found")
            sys.exit(1)
        for r in rows:
            print("|".join("" if v is None else str(v) for v in r))

    else:
        print("Unknown command:", cmd)
        sys.exit(2)

if __name__ == "__main__":
    main()
