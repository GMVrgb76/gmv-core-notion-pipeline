#!/usr/bin/env python3
import hashlib
import importlib
import mimetypes
import sys
from pathlib import Path
from datetime import datetime

CORE = Path(__file__).resolve().parents[1]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

migrations = importlib.import_module("gmv_core.migrations")
FOREIGN_KEYS_VERSION = migrations.FOREIGN_KEYS_VERSION
DOMAIN_CONSTRAINTS_VERSION = migrations.DOMAIN_CONSTRAINTS_VERSION
OID_TYPE_CONSISTENCY_VERSION = migrations.OID_TYPE_CONSISTENCY_VERSION
allocate_and_create_object = importlib.import_module(
    "gmv_core.repositories.identity"
).allocate_and_create_object
connect_path = importlib.import_module("gmv_core.database").connect_path

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

def require_current_schema(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    supported_versions = sorted(
        {
            FOREIGN_KEYS_VERSION,
            DOMAIN_CONSTRAINTS_VERSION,
            OID_TYPE_CONSISTENCY_VERSION,
        }
    )
    if version not in supported_versions:
        expected = " or ".join(str(item) for item in supported_versions)
        raise RuntimeError(
            f"Import requires schema version {expected}; found {version}. "
            "Run the approved migration before importing."
        )

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

    with connect_path(DB) as conn:
        return conn.execute(query).fetchall()

def print_import_queue(rows):
    for row in rows:
        print("|".join("" if value is None else str(value) for value in row))

def import_file(file_path):
    p = Path(file_path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        print(f"File not found: {p}")
        sys.exit(1)

    conn = connect_path(DB)
    try:
        require_current_schema(conn)
    except RuntimeError as error:
        conn.close()
        print(str(error), file=sys.stderr)
        return 1

    now = datetime.now().isoformat(timespec="seconds")
    digest = sha256_file(p)
    mime, _ = mimetypes.guess_type(str(p))

    try:
        conn.execute("BEGIN IMMEDIATE")
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
            print(f"Existing resource: {oid}")
            return 0

        oid = allocate_and_create_object(
            conn,
            object_type="Resource",
            name=p.name,
            status="active",
            created_at=now,
            updated_at=now,
        )

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
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Imported resource: {oid}")
    print(f"Path: {p}")
    print(f"SHA256: {digest}")
    return 0

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
        raise SystemExit(import_file(sys.argv[2]))
    elif command == "queue":
        print_import_queue(list_import_queue())
    elif command == "pending":
        print_import_queue(list_import_queue(pending_only=True))
    else:
        print("Unknown command:", command)
        sys.exit(2)

if __name__ == "__main__":
    main()
