"""Pure DB-006 reconciliation tests; never use the live database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gmv_core.engine_service_runs_migration import (
    apply_migration,
    plan_migration,
    reconcile_evidence,
)

NOW = "2026-01-01T00:00:00"


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


def _database(tmp_path: Path) -> Path:
    database = tmp_path / "GMV.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE engine_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                engine TEXT NOT NULL,
                run_at TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT,
                duration_seconds REAL,
                command TEXT,
                stdout_path TEXT,
                stderr_path TEXT
            );
            CREATE TABLE service_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_oid TEXT NOT NULL,
                service_name TEXT NOT NULL,
                run_at TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_seconds REAL,
                command TEXT,
                stdout_path TEXT,
                stderr_path TEXT,
                summary TEXT
            );
            """
        )
    return database


def _engine(
    run_id: int,
    engine: str,
    *,
    run_at: str = NOW,
    status: str = "OK",
    duration: float | None = 1.25,
    command: str | None = "fixture --run",
    stdout: str | None = "/fixtures/out",
    stderr: str | None = "/fixtures/err",
    summary: str | None = "fixture summary",
) -> tuple:
    return (
        run_id,
        engine,
        run_at,
        status,
        duration,
        command,
        stdout,
        stderr,
        summary,
    )


def _insert_engine(database: Path, rows: list[tuple]) -> None:
    with sqlite3.connect(database) as connection:
        connection.executemany(
            """
            INSERT INTO engine_runs
            (id,engine,run_at,status,duration_seconds,command,stdout_path,stderr_path,summary)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )


def _insert_service(database: Path, rows: list[tuple]) -> None:
    with sqlite3.connect(database) as connection:
        connection.executemany(
            """
            INSERT INTO service_runs
            (id,service_oid,service_name,run_at,status,duration_seconds,
             command,stdout_path,stderr_path,summary)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )


def _matching_service(service_id: int, engine_row: tuple) -> tuple:
    identities = {
        "knowledge_engine": ("SRV-000001", "Knowledge Engine"),
        "morning_brief": ("SRV-000002", "Morning Brief"),
        "daily_log": ("SRV-000003", "Daily Log"),
        "market_engine": ("SRV-000004", "Market Engine"),
    }
    service_oid, service_name = identities[engine_row[1]]
    return (service_id, service_oid, service_name, *engine_row[2:])


def test_plan_classifies_exact_pending_and_approved_exclusion(tmp_path: Path) -> None:
    database = _database(tmp_path)
    exact = _engine(1, "knowledge_engine")
    pending = _engine(2, "daily_log")
    _insert_engine(database, [exact, pending, _approved_excluded_engine_run()])
    _insert_service(database, [_matching_service(7, exact)])

    with sqlite3.connect(database) as connection:
        plan = plan_migration(connection)

    assert plan.counts == (1, 1, 1)
    assert plan.matched[0].service_run_id == 7
    assert plan.pending[0].service_oid == "SRV-000003"
    assert plan.excluded[0].engine_run_id == 23
    assert plan.excluded[0].reason == "frozen_unapproved_constitution_cli"


def test_plan_matches_duplicate_payloads_one_to_one(tmp_path: Path) -> None:
    database = _database(tmp_path)
    first = _engine(1, "knowledge_engine")
    second = _engine(2, "knowledge_engine")
    _insert_engine(database, [first, second])
    _insert_service(database, [_matching_service(1, first)])

    with sqlite3.connect(database) as connection:
        plan = plan_migration(connection)

    assert plan.counts == (1, 1, 0)
    assert plan.matched[0].engine_run_id == 1
    assert plan.pending[0].engine_run_id == 2


def test_plan_uses_null_safe_full_payload_matching(tmp_path: Path) -> None:
    database = _database(tmp_path)
    run = _engine(
        1,
        "knowledge_engine",
        duration=None,
        command=None,
        stdout=None,
        stderr=None,
        summary=None,
    )
    _insert_engine(database, [run])
    _insert_service(database, [_matching_service(1, run)])

    with sqlite3.connect(database) as connection:
        plan = plan_migration(connection)

    assert plan.counts == (1, 0, 0)


def test_plan_fails_closed_for_unknown_engine(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert_engine(database, [_engine(1, "unknown_engine")])

    with sqlite3.connect(database) as connection:
        with pytest.raises(ValueError, match="unapproved unmapped Engine Run"):
            plan_migration(connection)


def test_plan_fails_closed_if_approved_exclusion_payload_changes(tmp_path: Path) -> None:
    database = _database(tmp_path)
    changed = list(_approved_excluded_engine_run())
    changed[-1] = "changed summary"
    _insert_engine(database, [tuple(changed)])

    with sqlite3.connect(database) as connection:
        with pytest.raises(ValueError, match="unapproved unmapped Engine Run"):
            plan_migration(connection)


def test_apply_requires_active_transaction(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with sqlite3.connect(database) as connection:
        with pytest.raises(ValueError, match="active transaction"):
            apply_migration(connection)


def test_apply_migrates_exact_payload_preserves_source_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    run = _engine(1, "market_engine")
    _insert_engine(database, [run])

    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        first = apply_migration(connection)
        connection.commit()
    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        second = apply_migration(connection)
        connection.commit()
        engine_rows = list(connection.execute("SELECT * FROM engine_runs"))
        service_rows = list(
            connection.execute(
                "SELECT service_oid,service_name,run_at,status,duration_seconds,"
                "command,stdout_path,stderr_path,summary FROM service_runs"
            )
        )

    assert len(first.migrated) == 1
    assert second.migrated == ()
    assert engine_rows[0][0] == 1
    assert service_rows == [("SRV-000004", "Market Engine", *run[2:])]


def test_apply_gate_mismatch_fails_before_insert(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert_engine(database, [_engine(1, "daily_log")])

    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValueError, match="gate mismatch"):
            apply_migration(connection, allowed_gate_counts={(5, 25, 1)})
        connection.rollback()

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM service_runs").fetchone()[0] == 0


def test_apply_failure_rolls_back_all_rows(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert_engine(
        database,
        [_engine(1, "daily_log"), _engine(2, "market_engine")],
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_market
            BEFORE INSERT ON service_runs
            WHEN NEW.service_oid = 'SRV-000004'
            BEGIN
                SELECT RAISE(ABORT, 'synthetic migration failure');
            END
            """
        )

    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.IntegrityError, match="synthetic migration failure"):
            apply_migration(connection)
        connection.rollback()

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM service_runs").fetchone()[0] == 0


def test_reconcile_reconstructs_mapping_after_commit_without_evidence(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    run = _engine(1, "morning_brief")
    _insert_engine(database, [run])
    _insert_service(database, [_matching_service(9, run)])

    with sqlite3.connect(database) as connection:
        plan = reconcile_evidence(connection)

    assert plan.counts == (1, 0, 0)
    assert plan.matched[0].engine_run_id == 1
    assert plan.matched[0].service_run_id == 9
