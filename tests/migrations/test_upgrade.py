"""Safe adoption of the characterized unversioned schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gmv_core.errors import MigrationStateError
from gmv_core.migrations import BASELINE_VERSION, migrate

SCHEMA_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "current_schema.sql"


def _dump(database: Path) -> tuple[str, ...]:
    with sqlite3.connect(database) as connection:
        return tuple(connection.iterdump())


def test_current_shape_adoption_preserves_schema_and_rows(tmp_path: Path) -> None:
    database = tmp_path / "current-shape.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA_FIXTURE.read_text(encoding="utf-8"))

    before = _dump(database)
    assert migrate(database, target_version=BASELINE_VERSION) == BASELINE_VERSION
    assert _dump(database) == before

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (
            BASELINE_VERSION,
        )


def test_nonmatching_unversioned_database_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "unknown.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE unknown (id INTEGER PRIMARY KEY)")

    with pytest.raises(MigrationStateError, match="does not match the baseline"):
        migrate(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (0,)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall() == [("unknown",)]
