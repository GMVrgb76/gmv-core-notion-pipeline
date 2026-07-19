"""gmv_compatibility.py writes Events, not Timeline (DB-005 second writer slice).

Isolated only: runs the real script as a subprocess against a fresh,
disposable .gmv_core home (never a pre-loaded fixture, mirroring the other
compatibility tests), confirming the Timeline write and its bootstrap were
fully replaced by an equivalent Events write. Never touches the live
database.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY = ROOT / "10_API" / "gmv_compatibility.py"


def _write_program(path: Path, body: str) -> None:
    path.write_text(f"#!{sys.executable}\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _run_compatibility(
    home: Path, engine: str, executable: Path
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(COMPATIBILITY), engine, "--", str(executable)],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _database(home: Path) -> Path:
    return home / ".gmv_core" / "09_DATABASE" / "GMV.db"


def test_run_writes_events_row_with_expected_payload(tmp_path: Path) -> None:
    helper = tmp_path / "engine.py"
    _write_program(helper, "print('ok')")

    result = _run_compatibility(tmp_path, "events_test", helper)

    assert result.returncode == 0
    with sqlite3.connect(_database(tmp_path)) as connection:
        row = connection.execute(
            "SELECT oid,event_type,description,source FROM events ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row == (
        "SYS-000001",
        "engine_run",
        "events_test compatibility run completed with status OK, return code 0",
        "gmv_compatibility.py",
    )


def test_run_does_not_create_or_write_timeline_on_a_fresh_database(tmp_path: Path) -> None:
    helper = tmp_path / "engine.py"
    _write_program(helper, "print('ok')")

    result = _run_compatibility(tmp_path, "events_test", helper)

    assert result.returncode == 0
    with sqlite3.connect(_database(tmp_path)) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "timeline" not in tables
    assert "events" in tables
    assert "engine_runs" in tables


def test_engine_runs_and_audit_record_are_unchanged(tmp_path: Path) -> None:
    helper = tmp_path / "engine.py"
    _write_program(helper, "print('ok')")

    result = _run_compatibility(tmp_path, "events_test", helper)

    assert result.returncode == 0
    with sqlite3.connect(_database(tmp_path)) as connection:
        run = connection.execute(
            "SELECT engine,status,summary FROM engine_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert run == (
        "events_test",
        "OK",
        "events_test compatibility run completed with status OK, return code 0",
    )

    operations = tmp_path / ".gmv_core" / "04_LOGS" / "operations.jsonl"
    records = [json.loads(line) for line in operations.read_text(encoding="utf-8").splitlines() if line]
    assert len(records) == 1
    record = records[0]
    assert record["service"] == "events_test"
    assert record["status"] == "OK"
    assert record["error_code"] == "none"
    assert record["return_code"] == 0
    assert record["summary"] == (
        "events_test compatibility run completed with status OK, return code 0"
    )


def test_engine_runs_and_events_share_the_same_transaction(tmp_path: Path) -> None:
    helper = tmp_path / "engine.py"
    _write_program(helper, "print('ok')")

    result = _run_compatibility(tmp_path, "events_test", helper)

    assert result.returncode == 0
    with sqlite3.connect(_database(tmp_path)) as connection:
        run_count = connection.execute("SELECT COUNT(*) FROM engine_runs").fetchone()[0]
        event_count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert run_count == 1
    assert event_count == 1
