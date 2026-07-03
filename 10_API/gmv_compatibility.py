#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import sqlite3, subprocess, sys, json, os

CORE = Path.home() / ".gmv_core"
DB = CORE / "09_DATABASE" / "GMV.db"
LOGDIR = CORE / "04_LOGS"
OUTDIR = CORE / "05_OUTPUT" / "compatibility"

LOGDIR.mkdir(parents=True, exist_ok=True)
OUTDIR.mkdir(parents=True, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS engine_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        engine TEXT NOT NULL,
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
    conn.commit()
    return conn

def run_engine(engine, command):
    now = datetime.now().isoformat(timespec="seconds")
    stamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    stdout_path = OUTDIR / f"{stamp}_{engine}.out.log"
    stderr_path = OUTDIR / f"{stamp}_{engine}.err.log"

    start = datetime.now()
    proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    duration = (datetime.now() - start).total_seconds()

    stdout_path.write_text(proc.stdout or "")
    stderr_path.write_text(proc.stderr or "")

    status = "OK" if proc.returncode == 0 else "ERROR"
    summary = f"{engine} compatibility run completed with status {status}, return code {proc.returncode}"

    conn = init_db()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO engine_runs
    (engine, run_at, status, duration_seconds, command, stdout_path, stderr_path, summary)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        engine, now, status, duration, command,
        str(stdout_path), str(stderr_path), summary
    ))

    cur.execute("""
    INSERT INTO timeline
    (oid, event_at, event_type, description, source)
    VALUES (?, ?, ?, ?, ?)
    """, (
        "SYS-000001", now, "engine_run", summary, "gmv_compatibility.py"
    ))

    conn.commit()
    conn.close()

    print("=== GMV COMPATIBILITY LAYER ===")
    print(summary)
    print("stdout:", stdout_path)
    print("stderr:", stderr_path)

    return proc.returncode

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: gmv_compatibility.py ENGINE_NAME COMMAND", file=sys.stderr)
        sys.exit(2)

    engine = sys.argv[1]
    command = " ".join(sys.argv[2:])
    sys.exit(run_engine(engine, command))
