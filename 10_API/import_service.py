#!/usr/bin/env python3
import hashlib
import mimetypes
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

DB = Path.home() / ".gmv_core/09_DATABASE/GMV.db"

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

    conn.commit()
    conn.close()

    print(f"Imported resource: {oid}")
    print(f"Path: {p}")
    print(f"SHA256: {digest}")

def main():
    if len(sys.argv) < 3 or sys.argv[1] != "file":
        print("Usage: import_service.py file <path>")
        sys.exit(2)
    import_file(sys.argv[2])

if __name__ == "__main__":
    main()
