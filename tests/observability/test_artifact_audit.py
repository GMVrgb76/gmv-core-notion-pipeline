"""Missing Engine artifacts remain explicit and are never fabricated."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "10_API" / "artifact_audit.py"
SPEC = importlib.util.spec_from_file_location("artifact_audit", AUDIT_PATH)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def _database(path: Path, stdout_path: Path | None, stderr_path: Path | None) -> Path:
    database = path / "audit.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE engine_runs ("
            "id INTEGER PRIMARY KEY, engine TEXT, run_at TEXT, "
            "stdout_path TEXT, stderr_path TEXT)"
        )
        connection.execute(
            "INSERT INTO engine_runs VALUES (1,'fixture','2026-01-01T00:00:00',?,?)",
            (
                str(stdout_path) if stdout_path is not None else None,
                str(stderr_path) if stderr_path is not None else None,
            ),
        )
    return database


def test_audit_distinguishes_available_unavailable_and_unrecorded(
    tmp_path: Path,
) -> None:
    present = tmp_path / "present ü.log"
    present.write_text("evidence", encoding="utf-8")
    missing = tmp_path / "missing.log"
    database = _database(tmp_path, present, missing)

    records = AUDIT.audit_artifacts(database)

    assert [record["availability"] for record in records] == [
        "available",
        "unavailable",
    ]
    assert not missing.exists()

    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE engine_runs SET stderr_path=NULL WHERE id=1")
    records = AUDIT.audit_artifacts(database)
    assert records[1]["availability"] == "not_recorded"


def test_json_command_is_machine_stable_and_nonzero_for_missing(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.log"
    database = _database(tmp_path, missing, None)

    result = subprocess.run(
        [sys.executable, str(AUDIT_PATH), "--database", str(database), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    records = json.loads(result.stdout)
    assert records[0]["availability"] == "unavailable"
    assert records[1]["availability"] == "not_recorded"
    assert result.stderr == ""
    assert not missing.exists()


def test_audit_never_changes_database_bytes(tmp_path: Path) -> None:
    database = _database(tmp_path, None, None)
    before = database.read_bytes()

    assert AUDIT.audit_artifacts(database)

    assert database.read_bytes() == before
