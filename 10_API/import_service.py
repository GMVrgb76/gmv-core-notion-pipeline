#!/usr/bin/env python3
import hashlib
import mimetypes
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

DB = Path.home() / ".gmv_core/09_DATABASE/GMV.db"

QUEUE_COLUMNS = """
import_id,resource_oid,source_path,filename,status,review_status,
proposed_destination,confidence,error,created_at,updated_at
"""

def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def next_resource_oid(cur):
    cur.execute("SELECT COUNT(*) FROM objects WHERE type='Resource'")
    n = cur.fetchone()[0] + 1
    return f"RES-{n:06d}"

def update_import_queue(cur, resource_oid, path, filename, now):
    cur.execute(
        "SELECT import_id FROM import_queue WHERE source_path=? ORDER BY import_id LIMIT 1",
        (str(path),),
    )
    row = cur.fetchone()
    if row:
        cur.execute("""
        UPDATE import_queue
        SET resource_oid=?, filename=?, error=NULL, updated_at=?
        WHERE import_id=?
        """, (resource_oid, filename, now, row[0]))
    else:
        cur.execute("""
        INSERT INTO import_queue
        (resource_oid,source_path,filename,created_at,updated_at)
        VALUES (?,?,?,?,?)
        """, (resource_oid, str(path), filename, now, now))

def list_import_queue(pending_only=False):
    query = f"SELECT {QUEUE_COLUMNS} FROM import_queue"
    if pending_only:
        query += " WHERE status='pending' OR review_status='pending_review'"
    query += " ORDER BY created_at DESC, import_id DESC"

    with sqlite3.connect(DB) as conn:
        return conn.execute(query).fetchall()

def print_import_queue(rows):
    for row in rows:
        print("|".join("" if value is None else str(value) for value in row))

def import_file(file_path):
    p = Path(file_path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        print(f"File not found: {p}")
        sys.exit(1)

    now = datetime.now().isoformat(timespec="seconds")
    digest = sha256_file(p)
    mime, _ = mimetypes.guess_type(str(p))

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT resource_oid FROM resources WHERE sha256=?", (digest,))
    existing = cur.fetchone()

    if existing:
        oid = existing[0]
        update_import_queue(cur, oid, p, p.name, now)
        cur.execute("""
        INSERT INTO events (oid,event_at,event_type,description,source)
        VALUES (?,?,?,?,?)
        """, (oid, now, "resource_seen_again", f"Resource seen again: {p}", "import_service"))
        conn.commit()
        conn.close()
        print(f"Existing resource: {oid}")
        return

    oid = next_resource_oid(cur)

    cur.execute("""
    INSERT INTO objects (oid,type,name,status,created_at,updated_at)
    VALUES (?,?,?,?,?,?)
    """, (oid, "Resource", p.name, "active", now, now))

    cur.execute("""
    INSERT INTO resources
    (resource_oid,path,filename,extension,mime_guess,size_bytes,sha256,imported_at,status)
    VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        oid,
        str(p),
        p.name,
        p.suffix.lower(),
        mime or "",
        p.stat().st_size,
        digest,
        now,
        "active"
    ))

    cur.execute("""
    INSERT INTO events (oid,event_at,event_type,description,source)
    VALUES (?,?,?,?,?)
    """, (oid, now, "resource_imported", f"Resource imported: {p}", "import_service"))

    update_import_queue(cur, oid, p, p.name, now)

    conn.commit()
    conn.close()

    print(f"Imported resource: {oid}")
    print(f"Path: {p}")
    print(f"SHA256: {digest}")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  import_service.py file <path>")
        print("  import_service.py queue")
        print("  import_service.py pending")
        sys.exit(2)

    command = sys.argv[1]
    if command == "file":
        if len(sys.argv) < 3:
            print("Usage: import_service.py file <path>")
            sys.exit(2)
        import_file(sys.argv[2])
    elif command == "queue":
        print_import_queue(list_import_queue())
    elif command == "pending":
        print_import_queue(list_import_queue(pending_only=True))
    else:
        print("Unknown command:", command)
        sys.exit(2)

if __name__ == "__main__":
    main()
