"""DB-006 migration CLI tests; isolated and never pointed at the live DB."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from gmv_core.engine_service_runs_migration import (
    RECORDED_GATE_COUNTS,
    apply_migration,
)
from tests.characterization.conftest import SCHEMA_FIXTURE

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "10_API" / "engine_service_runs_migration_service.py"
sys.path.insert(0, str(ROOT / "10_API"))
import backup_service as BACKUP  # noqa: E402

EVIDENCE_RELATIVE = Path("04_LOGS") / "engine_service_runs_migration.v1.jsonl"


def _approved_excluded_engine_run() -> tuple:
    core = Path("/") / "Users" / ("giacomo" + "marcovalerio") / ".gmv_core"
    output = core / "05_OUTPUT" / "compatibility"
    return (
        23,
        "gmv_core",
        "2026-07-11T14:13:49",
        "OK",
        0.074014,
        "./11_CLI/gmv constitution check",
        str(output / "2026_07_11_141349_gmv_core.out.log"),
        str(output / "2026_07_11_141349_gmv_core.err.log"),
        "gmv_core compatibility run completed with status OK, return code 0",
    )


def _core(tmp_path: Path, *, name: str = "core") -> Path:
    core = tmp_path / name
    core.mkdir()
    subprocess.run(["/usr/bin/git", "init", "-q"], cwd=core, check=True)
    subprocess.run(
        ["/usr/bin/git", "config", "user.email", "test@example.invalid"],
        cwd=core,
        check=True,
    )
    subprocess.run(
        ["/usr/bin/git", "config", "user.name", "Test"],
        cwd=core,
        check=True,
    )
    (core / "source.txt").write_text("source", encoding="utf-8")
    subprocess.run(["/usr/bin/git", "add", "source.txt"], cwd=core, check=True)
    subprocess.run(
        ["/usr/bin/git", "commit", "-qm", "fixture"], cwd=core, check=True
    )

    database = core / "09_DATABASE" / "GMV.db"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA_FIXTURE.read_text(encoding="utf-8"))
        connection.execute("DELETE FROM engine_runs")
        connection.execute("DELETE FROM service_runs")
    database.chmod(0o600)
    return core


def _mapped_engine_row(run_id: int, engine: str) -> tuple:
    return (
        run_id,
        engine,
        f"2026-01-01T00:00:{run_id:02d}",
        "OK",
        float(run_id),
        f"{engine} --run {run_id}",
        f"/fixtures/{run_id}.out",
        f"/fixtures/{run_id}.err",
        f"summary {run_id}",
    )


def _service_row(service_id: int, engine_row: tuple) -> tuple:
    identities = {
        "knowledge_engine": ("SRV-000001", "Knowledge Engine"),
        "morning_brief": ("SRV-000002", "Morning Brief"),
        "daily_log": ("SRV-000003", "Daily Log"),
        "market_engine": ("SRV-000004", "Market Engine"),
    }
    service_oid, service_name = identities[engine_row[1]]
    return (service_id, service_oid, service_name, *engine_row[2:])


def _seed_recorded_gate(database: Path) -> None:
    rows = [
        *[_mapped_engine_row(run_id, "knowledge_engine") for run_id in range(1, 20)],
        *[
            _mapped_engine_row(run_id, "daily_log")
            for run_id in (20, 21, 22, 24, 25, 26)
        ],
        *[_mapped_engine_row(run_id, "morning_brief") for run_id in range(27, 31)],
        _mapped_engine_row(31, "market_engine"),
    ]
    by_id = {row[0]: row for row in rows}
    exact_ids = (1, 20, 21, 27, 31)
    with sqlite3.connect(database) as connection:
        connection.executemany(
            """
            INSERT INTO engine_runs
            (id,engine,run_at,status,duration_seconds,command,stdout_path,stderr_path,summary)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            [*rows, _approved_excluded_engine_run()],
        )
        connection.executemany(
            """
            INSERT INTO service_runs
            (id,service_oid,service_name,run_at,status,duration_seconds,
             command,stdout_path,stderr_path,summary)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            [
                _service_row(service_id, by_id[engine_id])
                for service_id, engine_id in enumerate(exact_ids, start=1)
            ],
        )


def _milestone_backup(core: Path, backups_root: Path) -> Path:
    return BACKUP.create_backup(
        core,
        backups_root,
        kind="milestone",
        milestone="db-006-test",
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _rolling_backup(core: Path, backups_root: Path) -> Path:
    return BACKUP.create_backup(
        core,
        backups_root,
        kind="rolling",
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _run(core: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["HOME"] = str(core.parent)
    return subprocess.run(
        [
            sys.executable,
            str(SERVICE),
            "--database",
            str(core / "09_DATABASE" / "GMV.db"),
            "--home",
            str(core),
            *arguments,
        ],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _counts(database: Path) -> tuple[int, int]:
    with sqlite3.connect(database) as connection:
        return (
            int(connection.execute("SELECT COUNT(*) FROM engine_runs").fetchone()[0]),
            int(connection.execute("SELECT COUNT(*) FROM service_runs").fetchone()[0]),
        )


def _records(core: Path) -> list[dict]:
    path = core / EVIDENCE_RELATIVE
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_plan_is_read_only_and_reports_recorded_gate(tmp_path: Path) -> None:
    core = _core(tmp_path)
    database = core / "09_DATABASE" / "GMV.db"
    _seed_recorded_gate(database)
    before = _counts(database)

    result = _run(core, "plan", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["counts"] == {"matched": 5, "pending": 25, "excluded": 1}
    assert len(payload["pending"]) == 25
    assert payload["excluded"][0]["engine_run_id"] == 23
    assert _counts(database) == before
    assert not (core / EVIDENCE_RELATIVE).exists()


def test_apply_fails_without_confirm(tmp_path: Path) -> None:
    core = _core(tmp_path)
    _seed_recorded_gate(core / "09_DATABASE" / "GMV.db")

    result = _run(core, "apply", "--backup", str(tmp_path))

    assert result.returncode == 2
    assert "--confirm" in result.stderr
    assert _counts(core / "09_DATABASE" / "GMV.db") == (31, 5)


def test_apply_fails_without_backup_reference(tmp_path: Path) -> None:
    core = _core(tmp_path)
    _seed_recorded_gate(core / "09_DATABASE" / "GMV.db")

    result = _run(core, "apply", "--confirm")

    assert result.returncode == 2
    assert "--backup" in result.stderr
    assert _counts(core / "09_DATABASE" / "GMV.db") == (31, 5)


def test_apply_rejects_rolling_backup(tmp_path: Path) -> None:
    core = _core(tmp_path)
    _seed_recorded_gate(core / "09_DATABASE" / "GMV.db")
    backup = _rolling_backup(core, tmp_path / "backups")

    result = _run(core, "apply", "--confirm", "--backup", str(backup))

    assert result.returncode == 2
    assert "milestone" in result.stderr
    assert _counts(core / "09_DATABASE" / "GMV.db") == (31, 5)


def test_apply_rejects_corrupt_backup(tmp_path: Path) -> None:
    core = _core(tmp_path)
    _seed_recorded_gate(core / "09_DATABASE" / "GMV.db")
    backup = _milestone_backup(core, tmp_path / "backups")
    (backup / "database" / "GMV.db").write_bytes(b"corrupt")

    result = _run(core, "apply", "--confirm", "--backup", str(backup))

    assert result.returncode == 2
    assert "precondition failed" in result.stderr
    assert _counts(core / "09_DATABASE" / "GMV.db") == (31, 5)


def test_apply_is_blocked_after_db006_write_capability_revocation(
    tmp_path: Path,
) -> None:
    core = _core(tmp_path)
    database = core / "09_DATABASE" / "GMV.db"
    _seed_recorded_gate(database)
    backup = _milestone_backup(core, tmp_path / "backups")

    result = _run(core, "apply", "--confirm", "--backup", str(backup))

    assert result.returncode == 1
    assert "UnauthorizedWriteError" in result.stderr
    assert "engine_service_runs_migration.py" in result.stderr
    assert _counts(database) == (31, 5)
    assert not (core / EVIDENCE_RELATIVE).exists()


def test_repeated_apply_attempts_remain_blocked_and_non_mutating(tmp_path: Path) -> None:
    core = _core(tmp_path)
    database = core / "09_DATABASE" / "GMV.db"
    _seed_recorded_gate(database)
    backup = _milestone_backup(core, tmp_path / "backups")

    first = _run(core, "apply", "--confirm", "--backup", str(backup))
    second = _run(core, "apply", "--confirm", "--backup", str(backup))

    assert first.returncode == 1
    assert second.returncode == 1
    assert "UnauthorizedWriteError" in first.stderr
    assert "UnauthorizedWriteError" in second.stderr
    assert _counts(database) == (31, 5)
    assert not (core / EVIDENCE_RELATIVE).exists()


def test_apply_fails_closed_when_recorded_counts_diverge(tmp_path: Path) -> None:
    core = _core(tmp_path)
    database = core / "09_DATABASE" / "GMV.db"
    _seed_recorded_gate(database)
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM engine_runs WHERE id=2")
    backup = _milestone_backup(core, tmp_path / "backups")

    result = _run(core, "apply", "--confirm", "--backup", str(backup))

    assert result.returncode == 1
    assert "gate mismatch" in result.stderr
    assert _counts(database) == (30, 5)


def test_reconcile_recovers_commit_without_evidence(tmp_path: Path) -> None:
    core = _core(tmp_path)
    database = core / "09_DATABASE" / "GMV.db"
    _seed_recorded_gate(database)
    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        migrated = apply_migration(
            connection,
            allowed_gate_counts=RECORDED_GATE_COUNTS,
        )
        connection.commit()
    assert len(migrated.migrated) == 25
    assert not (core / EVIDENCE_RELATIVE).exists()

    result = _run(core, "reconcile", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload["mapped"]) == 30
    assert len(payload["excluded"]) == 1
    assert payload["pending"] == 0
    assert _counts(database) == (31, 30)
    assert len(_records(core)) == 31


def test_reconcile_fails_closed_on_corrupt_evidence(tmp_path: Path) -> None:
    core = _core(tmp_path)
    database = core / "09_DATABASE" / "GMV.db"
    _seed_recorded_gate(database)
    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        apply_migration(
            connection,
            allowed_gate_counts=RECORDED_GATE_COUNTS,
        )
        connection.commit()
    baseline = _run(core, "reconcile", "--json")
    assert baseline.returncode == 0, baseline.stderr
    evidence = core / EVIDENCE_RELATIVE
    record = json.loads(evidence.read_text().splitlines()[0])
    record["record_hash"] = "0" * 64
    evidence.write_text(json.dumps(record) + "\n", encoding="utf-8")

    result = _run(core, "reconcile", "--json")

    assert result.returncode == 1
    assert "audit chain failure" in result.stderr
