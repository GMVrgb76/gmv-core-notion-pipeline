"""Strict Doctor aggregates evidence and returns truthful status."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path

from tests.characterization.conftest import CLI, SCHEMA_FIXTURE


def _database(tmp_path: Path) -> Path:
    database = tmp_path / ".gmv_core" / "09_DATABASE" / "GMV.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA_FIXTURE.read_text(encoding="utf-8"))
        connection.execute("DELETE FROM engine_runs")
    database.chmod(0o600)
    return database


def _run(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["HOME"] = str(tmp_path)
    return subprocess.run(
        [str(CLI), "doctor", "--strict", *arguments],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_clean_database_is_ready_in_human_and_json_output(tmp_path: Path) -> None:
    _database(tmp_path)

    human = _run(tmp_path)
    machine = _run(tmp_path, "--json")

    assert human.returncode == 0
    assert "PASS|database.integrity|ok" in human.stdout
    assert human.stdout.endswith("OVERALL|READY\n")
    payload = json.loads(machine.stdout)
    assert machine.returncode == 0
    assert payload["overall"] == "ready"
    assert [check["name"] for check in payload["checks"]] == [
        "database.exists",
        "database.integrity",
        "database.foreign_keys",
        "database.schema",
        "database.queries",
        "artifacts.references",
        "database.permissions",
    ]


def test_missing_artifact_is_required_failure(tmp_path: Path) -> None:
    database = _database(tmp_path)
    missing = tmp_path / "missing.log"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO engine_runs "
            "(engine,run_at,status,stdout_path) VALUES ('fixture','now','OK',?)",
            (str(missing),),
        )

    result = _run(tmp_path, "--json")

    payload = json.loads(result.stdout)
    artifact = next(c for c in payload["checks"] if c["name"] == "artifacts.references")
    assert result.returncode == 1
    assert artifact["status"] == "FAIL"
    assert not missing.exists()


def test_query_schema_and_permission_failures_are_aggregated(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP VIEW service_registry_view")
        connection.execute("DROP TABLE objects")
    database.chmod(0o644)

    result = _run(tmp_path, "--json")

    payload = json.loads(result.stdout)
    failures = {c["name"] for c in payload["checks"] if c["status"] == "FAIL"}
    assert result.returncode == 1
    assert {"database.schema", "database.queries", "database.permissions"} <= failures


def test_missing_database_reports_all_dependent_failures(tmp_path: Path) -> None:
    result = _run(tmp_path / "missing-home", "--json")

    payload = json.loads(result.stdout)
    failures = [c for c in payload["checks"] if c["status"] == "FAIL"]
    assert result.returncode == 1
    assert payload["overall"] == "failed"
    assert len(failures) == len(payload["checks"])
