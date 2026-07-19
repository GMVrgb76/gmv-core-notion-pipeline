"""Migration 005: atomically retire the reconciled Engine Run table."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import gmv_core.migrations as migrations
from gmv_core.errors import MigrationError

ENGINE_RUN = (
    1,
    "knowledge_engine",
    "2026-01-01T00:00:00Z",
    "OK",
    1.25,
    "fixture --run",
    "/fixtures/out",
    "/fixtures/err",
    "fixture summary",
)


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


def _version_four_database(tmp_path: Path) -> Path:
    database = tmp_path / "version-four.db"
    assert (
        migrations.migrate(
            database, target_version=migrations.APPEND_ONLY_EVENTS_VERSION
        )
        == migrations.APPEND_ONLY_EVENTS_VERSION
    )
    return database


def _insert_engine_runs(connection: sqlite3.Connection, rows: list[tuple]) -> None:
    connection.executemany(
        """
        INSERT INTO engine_runs
        (id,engine,run_at,status,duration_seconds,command,stdout_path,stderr_path,summary)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )


def _matching_service(run_id: int, engine_run: tuple) -> tuple:
    return (run_id, "SRV-000001", "Knowledge Engine", *engine_run[2:])


def _insert_service_runs(connection: sqlite3.Connection, rows: list[tuple]) -> None:
    connection.executemany(
        """
        INSERT INTO service_runs
        (id,service_oid,service_name,run_at,status,duration_seconds,
         command,stdout_path,stderr_path,summary)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )


def _object_type(connection: sqlite3.Connection, name: str) -> str | None:
    row = connection.execute(
        "SELECT type FROM sqlite_master WHERE name=?", (name,)
    ).fetchone()
    return None if row is None else str(row[0])


def test_explicit_migration_five_retires_only_reconciled_engine_history(
    tmp_path: Path,
) -> None:
    database = _version_four_database(tmp_path)
    second_engine = (2, *ENGINE_RUN[1:])
    with sqlite3.connect(database) as connection:
        _insert_engine_runs(
            connection,
            [ENGINE_RUN, second_engine, _approved_excluded_engine_run()],
        )
        _insert_service_runs(
            connection,
            [_matching_service(1, ENGINE_RUN), _matching_service(2, second_engine)],
        )
        service_rows_before = list(connection.execute("SELECT * FROM service_runs"))

    assert (
        migrations.migrate(
            database, target_version=migrations.ENGINE_RUNS_RETIRED_VERSION
        )
        == migrations.ENGINE_RUNS_RETIRED_VERSION
    )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (5,)
        assert _object_type(connection, "engine_runs") is None
        assert list(connection.execute("SELECT * FROM service_runs")) == service_rows_before


def test_migration_rejects_multiset_parity_deficit_atomically(tmp_path: Path) -> None:
    database = _version_four_database(tmp_path)
    duplicate = (2, *ENGINE_RUN[1:])
    with sqlite3.connect(database) as connection:
        _insert_engine_runs(connection, [ENGINE_RUN, duplicate])
        _insert_service_runs(connection, [_matching_service(1, ENGINE_RUN)])

    with pytest.raises(MigrationError, match="migration 5 failed"):
        migrations.migrate(
            database, target_version=migrations.ENGINE_RUNS_RETIRED_VERSION
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (4,)
        assert _object_type(connection, "engine_runs") == "table"
        assert connection.execute("SELECT COUNT(*) FROM engine_runs").fetchone() == (2,)


def test_migration_rejects_changed_exclusion_without_dropping_table(
    tmp_path: Path,
) -> None:
    database = _version_four_database(tmp_path)
    changed = list(_approved_excluded_engine_run())
    changed[-1] = "changed summary"
    with sqlite3.connect(database) as connection:
        _insert_engine_runs(connection, [tuple(changed)])

    with pytest.raises(MigrationError, match="migration 5 failed"):
        migrations.migrate(
            database, target_version=migrations.ENGINE_RUNS_RETIRED_VERSION
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (4,)
        assert _object_type(connection, "engine_runs") == "table"


def test_failure_after_drop_rolls_back_engine_table_and_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _version_four_database(tmp_path)
    with sqlite3.connect(database) as connection:
        _insert_engine_runs(connection, [ENGINE_RUN])
        _insert_service_runs(connection, [_matching_service(1, ENGINE_RUN)])
    valid_loader = migrations._migration_sql

    def broken_loader(resource: str) -> str:
        if resource == migrations.ENGINE_RUNS_RETIRED_RESOURCE:
            return """
                BEGIN IMMEDIATE;
                DROP TABLE engine_runs;
                THIS IS NOT VALID SQL;
                PRAGMA user_version = 5;
                COMMIT;
            """
        return valid_loader(resource)

    monkeypatch.setattr(migrations, "_migration_sql", broken_loader)

    with pytest.raises(MigrationError, match="migration 5 failed"):
        migrations.migrate(
            database, target_version=migrations.ENGINE_RUNS_RETIRED_VERSION
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (4,)
        assert _object_type(connection, "engine_runs") == "table"
        assert connection.execute("SELECT COUNT(*) FROM engine_runs").fetchone() == (1,)
