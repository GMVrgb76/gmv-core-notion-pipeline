#!/usr/bin/env python3

import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CORE = Path.home() / ".gmv_core"
DB = CORE / "09_DATABASE" / "GMV.db"
LOGDIR = CORE / "04_LOGS"
OUTDIR = CORE / "05_OUTPUT" / "compatibility"
ENGINE_PATTERN = re.compile(r"[a-z][a-z0-9_]*\Z")

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

def validate_invocation(arguments: list[str]) -> tuple[str, list[str]]:
    if len(arguments) < 4 or arguments[2] != "--":
        raise ValueError("usage: gmv_compatibility.py ENGINE_NAME -- COMMAND [ARG ...]")

    engine = arguments[1]
    command = arguments[3:]
    if not ENGINE_PATTERN.fullmatch(engine):
        raise ValueError("invalid engine name: use lowercase letters, digits, and underscores")

    executable = command[0]
    if "/" in executable:
        executable_path = Path(executable).expanduser()
        if not executable_path.is_file() or not executable_path.stat().st_mode & 0o111:
            raise ValueError(f"command is not executable: {executable}")
    elif shutil.which(executable) is None:
        raise ValueError(f"command not found: {executable}")

    return engine, command


def run_engine(engine: str, command: list[str]) -> int:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    DB.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat(timespec="seconds")
    stamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    stdout_path = OUTDIR / f"{stamp}_{engine}.out.log"
    stderr_path = OUTDIR / f"{stamp}_{engine}.err.log"

    start = datetime.now()
    # The argv vector and executable are validated above; a shell is never used.
    proc = subprocess.run(  # noqa: S603 - required compatibility execution boundary
        command,
        shell=False,
        capture_output=True,
        text=True,
    )
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
        engine, now, status, duration, shlex.join(command),
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
    try:
        engine_name, command_argv = validate_invocation(sys.argv)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)

    sys.exit(run_engine(engine_name, command_argv))
