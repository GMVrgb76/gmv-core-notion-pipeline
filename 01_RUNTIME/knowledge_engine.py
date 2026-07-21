#!/usr/bin/env python3
from datetime import datetime
from pathlib import Path
import importlib, json, sys

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

database = importlib.import_module("gmv_core.database")
migrations = importlib.import_module("gmv_core.migrations")
errors = importlib.import_module("gmv_core.errors")
DatabaseConfigurationError = errors.DatabaseConfigurationError
MigrationStateError = errors.MigrationStateError

CORE = Path.home() / ".gmv_core"
DB = CORE / "09_DATABASE" / "GMV.db"
OUT = CORE / "05_OUTPUT" / "knowledge_engine"
LOG = CORE / "04_LOGS" / "knowledge_engine.log"

now = datetime.now().isoformat(timespec="seconds")

conn = database.connect_path(DB)
cur = conn.cursor()

try:
    migrations.require_supported_schema_version(conn)
    database.require_object_identities(
        conn,
        {
            "SRV-000001": "Service",
            "PER-000001": "Person",
        },
    )
except (MigrationStateError, DatabaseConfigurationError) as error:
    conn.close()
    print(f"error: {error}", file=sys.stderr)
    raise SystemExit(2) from None

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
