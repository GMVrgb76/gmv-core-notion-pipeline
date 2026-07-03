#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import sqlite3, json

CORE = Path.home() / ".gmv_core"
DB = CORE / "09_DATABASE" / "GMV.db"
OUT = CORE / "05_OUTPUT" / "knowledge_engine"
LOG = CORE / "04_LOGS" / "knowledge_engine.log"

now = datetime.now().isoformat(timespec="seconds")

conn = sqlite3.connect(DB)
cur = conn.cursor()

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
CREATE TABLE IF NOT EXISTS engine_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engine TEXT NOT NULL,
    run_at TEXT NOT NULL,
    status TEXT NOT NULL,
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
INSERT INTO timeline
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
INSERT INTO engine_runs
(engine, run_at, status, summary)
VALUES (?, ?, ?, ?)
""", (
    "knowledge_engine",
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
