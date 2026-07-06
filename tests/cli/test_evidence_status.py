"""Evidence-based status state and CLI contracts."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.characterization.conftest import CLI, SCHEMA_FIXTURE

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "10_API"))
import status_service as STATUS  # noqa: E402
from health_service import HealthResult  # noqa: E402


def _database(tmp_path: Path, *, pending: bool = False) -> Path:
    database = tmp_path / ".gmv_core" / "09_DATABASE" / "GMV.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA_FIXTURE.read_text(encoding="utf-8"))
        connection.execute("DELETE FROM engine_runs")
        if not pending:
            connection.execute("DELETE FROM import_queue")
    database.chmod(0o600)
    return database


def _run(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), "status", *arguments],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(tmp_path)},
    )


def test_state_derivation_ready_degraded_and_failed() -> None:
    passing = [HealthResult("database", "PASS", "required", "ok")]
    stale_service = [
        *passing,
        HealthResult("service.freshness.fixture", "DEGRADED", "degraded", "stale"),
    ]
    failed_query = [HealthResult("database.queries", "FAIL", "required", "failed")]

    assert STATUS.derive_state(passing) == "ready"
    assert STATUS.derive_state(stale_service) == "degraded"
    assert STATUS.derive_state(failed_query) == "failed"


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("service.freshness.fixture", "stale service"),
        ("queue.pending", "1 pending item"),
        ("backup.freshness", "stale backup"),
    ],
)
def test_degraded_evidence_never_reports_ready(name: str, message: str) -> None:
    results = [HealthResult(name, "DEGRADED", "degraded", message)]
    assert STATUS.derive_state(results) == "degraded"


def test_pending_queue_is_explicit_degraded_evidence(tmp_path: Path) -> None:
    database = _database(tmp_path, pending=True)
    result = STATUS._queue_result(database)
    assert result.status == "DEGRADED"
    assert result.message.startswith("1 item")


def test_query_failure_is_failed_and_returns_nonzero(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP VIEW import_queue_view")
    result = _run(
        tmp_path,
        "--json",
        "--now",
        "2026-07-06T12:00:00+00:00",
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["state"] == "failed"
    assert any(check["name"] == "queue.pending" for check in payload["checks"])


def test_cli_output_is_stable_and_never_unconditionally_ready(tmp_path: Path) -> None:
    _database(tmp_path)
    now = datetime(2026, 7, 6, 12, tzinfo=UTC)
    records = tmp_path / "missing-records.jsonl"
    arguments = (
        "--now",
        now.isoformat(),
        "--records",
        str(records),
    )
    first = _run(tmp_path, *arguments)
    second = _run(tmp_path, *arguments)

    assert first.returncode == 0
    assert first.stdout == second.stdout
    assert "SYSTEM READY" not in first.stdout
    assert first.stdout.endswith("STATE|DEGRADED\n")
    assert "UNAVAILABLE|unavailable|backup.freshness|requires S002-20" in first.stdout


def test_stale_operational_record_is_visible_in_cli(tmp_path: Path) -> None:
    _database(tmp_path)
    now = datetime(2026, 7, 6, 12, tzinfo=UTC)
    ended_at = now - timedelta(days=2)
    records = tmp_path / "operations.jsonl"
    record = {
        "schema_version": 1,
        "run_id": f"RUN-{'1' * 32}",
        "correlation_id": f"COR-{'2' * 32}",
        "service": "fixture",
        "status": "OK",
        "error_code": "none",
        "started_at": (ended_at - timedelta(seconds=1)).isoformat(),
        "ended_at": ended_at.isoformat(),
        "fresh_until": (ended_at + timedelta(days=7)).isoformat(),
        "return_code": 0,
        "command": ["fixture"],
        "summary": "fixture",
        "artifacts": [],
        "runbook": "RUNBOOK-NONE",
    }
    records.write_text(json.dumps(record) + "\n", encoding="utf-8")

    result = _run(
        tmp_path,
        "--now",
        now.isoformat(),
        "--records",
        str(records),
    )

    assert result.returncode == 0
    assert "DEGRADED|degraded|service.freshness.fixture|stale since" in result.stdout
