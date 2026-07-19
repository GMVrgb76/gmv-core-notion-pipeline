"""Scheduler-safe health policy behavior."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.characterization.conftest import SCHEMA_FIXTURE

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "10_API" / "health_service.py"
sys.path.insert(0, str(ROOT / "10_API"))
import health_service as HEALTH  # noqa: E402


def _database(tmp_path: Path) -> Path:
    database = tmp_path / "GMV.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA_FIXTURE.read_text(encoding="utf-8"))
        connection.execute("DELETE FROM service_runs")
    database.chmod(0o600)
    return database


def _seed_fresh_backup(backup_root: Path, now: datetime) -> None:
    """Give a test a real, currently-fresh backup so backup.freshness stays
    out of the way of the service-freshness behavior under test."""
    core = backup_root.parent / "backup_core"
    core.mkdir(parents=True, exist_ok=True)
    subprocess.run(["/usr/bin/git", "init", "-q"], cwd=core, check=True)
    subprocess.run(["/usr/bin/git", "config", "user.email", "test@example.invalid"], cwd=core, check=True)
    subprocess.run(["/usr/bin/git", "config", "user.name", "Test"], cwd=core, check=True)
    (core / "source.txt").write_text("source")
    subprocess.run(["/usr/bin/git", "add", "source.txt"], cwd=core, check=True)
    subprocess.run(["/usr/bin/git", "commit", "-qm", "fixture"], cwd=core, check=True)
    database = core / "09_DATABASE" / "GMV.db"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA_FIXTURE.read_text(encoding="utf-8"))
    sys.path.insert(0, str(ROOT / "10_API"))
    import backup_service

    backup_service.create_backup(core, backup_root, now=now)


def _record(service: str, ended_at: datetime, *, status: str = "OK") -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": f"RUN-{service.encode().hex():0<32}"[:36],
        "correlation_id": f"COR-{service.encode().hex():0<32}"[:36],
        "service": service,
        "status": status,
        "error_code": "none" if status == "OK" else "process_exit",
        "started_at": (ended_at - timedelta(seconds=1)).isoformat(),
        "ended_at": ended_at.isoformat(),
        "fresh_until": (ended_at + timedelta(days=7)).isoformat(),
        "return_code": 0 if status == "OK" else 1,
        "command": ["fixture"],
        "summary": "fixture",
        "artifacts": [],
        "runbook": "RUNBOOK-NONE",
    }


def _run(
    database: Path,
    records: Path,
    now: datetime,
    *,
    backup_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(SCRIPT),
            "--json",
            "--database",
            str(database),
            "--records",
            str(records),
            "--backup-root",
            str(backup_root or records.parent / "backups"),
            "--now",
            now.isoformat(),
            "--timeout-seconds",
            "2",
        ],
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=3,
    )


def test_scheduler_safe_structured_output_and_unavailable_semantics(tmp_path: Path) -> None:
    database = _database(tmp_path)
    now = datetime(2026, 7, 6, tzinfo=UTC)
    result = _run(database, tmp_path / "absent.jsonl", now)

    payload = json.loads(result.stdout)
    checks = {check["name"]: check for check in payload["checks"]}
    assert result.returncode == 1
    assert payload["schema_version"] == 1
    assert payload["overall"] == "failed"
    assert checks["database.foreign_key_enforcement"]["status"] == "UNAVAILABLE"
    assert checks["backup.freshness"]["status"] == "FAIL"
    assert checks["backup.freshness"]["message"] == "no backup audit evidence recorded"
    assert result.stderr == ""


def test_stale_service_is_degraded_without_failed_exit(tmp_path: Path) -> None:
    database = _database(tmp_path)
    now = datetime(2026, 7, 6, tzinfo=UTC)
    records = tmp_path / "operations.jsonl"
    records.write_text(
        json.dumps(_record("research", now - timedelta(days=2))) + "\n",
        encoding="utf-8",
    )
    backup_root = tmp_path / "backups"
    _seed_fresh_backup(backup_root, now)

    result = _run(database, records, now, backup_root=backup_root)

    payload = json.loads(result.stdout)
    service = next(
        check for check in payload["checks"] if check["name"] == "service.freshness.research"
    )
    assert result.returncode == 0
    assert service["status"] == "DEGRADED"
    assert "stale since" in service["message"]


def test_malformed_historical_record_does_not_block_current_freshness(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    now = datetime(2026, 7, 6, tzinfo=UTC)
    records = tmp_path / "operations.jsonl"
    records.write_text(
        "\n".join(
            [
                (
                    '{"schema_version":1,"run_id":"RUN-reset-'
                    '00000000000000000000000000000000","correlation_id":"COR-reset-'
                    '00000000000000000000000000000000","service":"gmv-core",'
                    '"status":"OK","error_code":"none","started_at":"2026-07-07T00:00:00Z",'
                    '"ended_at":"2026-07-07T00:00:01Z","fresh_until":"2026-07-08T00:00:00Z",'
                    '"return_code":0,"command":["gmv","reset"],"summary":"system reset baseline",'
                    '"artifacts":[],"runbook":"RUNBOOK-NONE"}'
                ),
                json.dumps(_record("research", now - timedelta(hours=1))),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    backup_root = tmp_path / "backups"
    _seed_fresh_backup(backup_root, now)

    result = _run(database, records, now, backup_root=backup_root)

    payload = json.loads(result.stdout)
    research = next(
        check for check in payload["checks"] if check["name"] == "service.freshness.research"
    )
    assert result.returncode == 0
    assert research["status"] == "PASS"
    assert "skipped 1 malformed historical record" in research["message"]


def test_required_failures_aggregate_to_nonzero(tmp_path: Path) -> None:
    now = datetime(2026, 7, 6, tzinfo=UTC)
    result = _run(tmp_path / "missing.db", tmp_path / "missing.jsonl", now)

    payload = json.loads(result.stdout)
    failures = [check for check in payload["checks"] if check["status"] == "FAIL"]
    assert result.returncode == 1
    assert payload["overall"] == "failed"
    assert len(failures) > 1


def test_timeout_is_bounded_and_reported() -> None:
    started = time.monotonic()
    with pytest.raises(HEALTH.HealthTimeoutError):
        HEALTH.run_with_timeout(lambda: time.sleep(1), 0.01)
    assert time.monotonic() - started < 0.5


def test_policy_defines_classifications_and_thresholds() -> None:
    policy = json.loads((ROOT / "00_CONFIG" / "HEALTH_POLICY.json").read_text())
    assert policy["service_stale_after_seconds"] == 86400
    assert policy["checks"]["strict_doctor"]["classification"] == "required"
    assert policy["checks"]["service_freshness"]["classification"] == "degraded"
    assert policy["checks"]["backup.freshness"]["classification"] == "required"
