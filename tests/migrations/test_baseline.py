"""Acceptance tests for baseline migration 001."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gmv_core.migrations import BASELINE_VERSION, main, migrate

SCHEMA_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "current_schema.sql"


def _schema_signature(database: Path) -> tuple[object, ...]:
    with sqlite3.connect(database) as connection:
        objects = tuple(
            connection.execute(
                """
                SELECT type, name, tbl_name
                FROM sqlite_master
                WHERE type IN ('table', 'view', 'index')
                ORDER BY type, name
                """
            )
        )
        tables_and_views = tuple(
            str(row[1])
            for row in objects
            if row[0] in {"table", "view"} and row[1] != "sqlite_sequence"
        )
        columns = tuple(
            (
                name,
                tuple(connection.execute(f"PRAGMA table_info({name})")),
            )
            for name in tables_and_views
        )
        indexes = tuple(
            (
                str(row[1]),
                tuple(connection.execute(f"PRAGMA index_info({row[1]})")),
            )
            for row in objects
            if row[0] == "index"
        )
    return objects, columns, indexes


def _create_characterized_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA_FIXTURE.read_text(encoding="utf-8"))


def test_baseline_matches_characterized_schema(tmp_path: Path) -> None:
    characterized = tmp_path / "characterized.db"
    migrated = tmp_path / "migrated.db"
    _create_characterized_database(characterized)

    assert migrate(migrated, target_version=BASELINE_VERSION) == BASELINE_VERSION
    assert _schema_signature(migrated) == _schema_signature(characterized)

    with sqlite3.connect(migrated) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (
            BASELINE_VERSION,
        )


def test_runner_requires_explicit_target() -> None:
    with pytest.raises(SystemExit) as error:
        main([])

    assert error.value.code == 2
