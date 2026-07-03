#!/usr/bin/env python3
import sqlite3
import sys
from pathlib import Path

DB = Path.home() / ".gmv_core/09_DATABASE/GMV.db"


def connect():
    return sqlite3.connect(DB)


def search(query):
    match = query.lower()
    rows = []

    with connect() as conn:
        rows.extend(conn.execute("""
        SELECT 'object',oid,name,
               CASE
                   WHEN instr(lower(name),?) > 0 THEN 'name:' || name
                   ELSE 'type:' || type
               END
        FROM objects
        WHERE instr(lower(name),?) > 0 OR instr(lower(type),?) > 0
        ORDER BY oid
        """, (match, match, match)).fetchall())

        rows.extend(conn.execute("""
        SELECT 'resource',resource_oid,filename,
               CASE
                   WHEN instr(lower(filename),?) > 0 THEN 'filename:' || filename
                   ELSE 'path:' || path
               END
        FROM resources
        WHERE instr(lower(filename),?) > 0 OR instr(lower(path),?) > 0
        ORDER BY resource_oid
        """, (match, match, match)).fetchall())

        rows.extend(conn.execute("""
        SELECT 'event',CAST(id AS TEXT),event_type,'description:' || description
        FROM events
        WHERE instr(lower(COALESCE(description,'')),?) > 0
        ORDER BY id DESC
        """, (match,)).fetchall())

        rows.extend(conn.execute("""
        SELECT 'relation',CAST(id AS TEXT),source_oid || '->' || target_oid,
               'relation_type:' || relation_type
        FROM relations
        WHERE instr(lower(relation_type),?) > 0
        ORDER BY id
        """, (match,)).fetchall())

    return rows


def main():
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        print("Usage: search_service.py <query>")
        sys.exit(2)

    for row in search(query):
        print("|".join("" if value is None else str(value) for value in row))


if __name__ == "__main__":
    main()
