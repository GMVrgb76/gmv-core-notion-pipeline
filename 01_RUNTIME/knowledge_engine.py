#!/usr/bin/env python3
from datetime import datetime
from pathlib import Path
import importlib, json, sys

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

database = importlib.import_module("gmv_core.database")
DatabaseConfigurationError = importlib.import_module(
    "gmv_core.errors"
).DatabaseConfigurationError

CORE = Path.home() / ".gmv_core"
DB = CORE / "09_DATABASE" / "GMV.db"
OUT = CORE / "05_OUTPUT" / "knowledge_engine"
LOG = CORE / "04_LOGS" / "knowledge_engine.log"

now = datetime.now().isoformat(timespec="seconds")

conn = database.connect_path(DB)
cur = conn.cursor()

try:
    database.require_object_identities(conn, {"SRV-000001": "Service"})
except DatabaseConfigurationError as error:
    conn.close()
    print(f"error: {error}", file=sys.stderr)
    raise SystemExit(2) from None

cur.execute("""
CREATE TABLE IF NOT EXISTS objects (
    oid TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TEXT,
    updated_at TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS service_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_oid TEXT NOT NULL,
    service_name TEXT NOT NULL,
    run_at TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_seconds REAL,
    command TEXT,
    stdout_path TEXT,
    stderr_path TEXT,
    summary TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oid TEXT NOT NULL,
    event_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT,
    source TEXT
)
""")

cur.execute("""
INSERT OR IGNORE INTO objects
(oid, type, name, status, created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?)
""", (
    "PER-000001",
    "Person",
    "Giacomo Marco Valerio",
    "active",
    now,
    now
))

cur.execute("""
INSERT INTO events
(oid, event_at, event_type, description, source)
VALUES (?, ?, ?, ?, ?)
""", (
    "PER-000001",
    now,
    "system_event",
    "Knowledge Engine V0 initialized from former Apprentice concept.",
    "knowledge_engine.py"
))

summary = "Knowledge Engine V0 executed. GMV.db initialized. First persistent OID verified: PER-000001."

cur.execute("""
INSERT INTO service_runs
(service_oid, service_name, run_at, status, summary)
VALUES (?, ?, ?, ?, ?)
""", (
    "SRV-000001",
    "Knowledge Engine",
    now,
    "OK",
    summary
))

conn.commit()

cur.execute("SELECT oid, type, name, status FROM objects ORDER BY oid")
objects = cur.fetchall()

report = {
    "engine": "knowledge_engine",
    "former_codename": "apprentice",
    "run_at": now,
    "status": "OK",
    "summary": summary,
    "objects": [
        {"oid": o[0], "type": o[1], "name": o[2], "status": o[3]}
        for o in objects
    ],
    "next_step": "Implement importer: read new files, detect OID, create missing objects, update timeline."
}

OUT.mkdir(parents=True, exist_ok=True)
report_path = OUT / f"{datetime.now().strftime('%Y_%m_%d_%H%M%S')}_KNOWLEDGE_ENGINE_REPORT.json"
report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

LOG.write_text(f"{now} | OK | {summary}\n")

print("=== KNOWLEDGE ENGINE V0 ===")
print(summary)
print()
print("Database:", DB)
print("Report:", report_path)
