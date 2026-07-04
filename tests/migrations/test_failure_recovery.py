"""Transactional failure and recovery behavior for migration 001."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import gmv_core.migrations as migrations
from gmv_core.errors import MigrationError

BROKEN_BASELINE = """
BEGIN IMMEDIATE;
CREATE TABLE partial_write (id INTEGER PRIMARY KEY);
THIS IS NOT VALID SQL;
PRAGMA user_version = 1;
COMMIT;
"""


def test_failed_baseline_rolls_back_and_can_recover(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "recoverable.db"
    valid_baseline = migrations._baseline_sql
    monkeypatch.setattr(migrations, "_baseline_sql", lambda: BROKEN_BASELINE)

    with pytest.raises(MigrationError, match="baseline migration failed"):
        migrations.migrate(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (0,)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name='partial_write'"
        ).fetchone() is None

    monkeypatch.setattr(migrations, "_baseline_sql", valid_baseline)
    assert migrations.migrate(database) == migrations.BASELINE_VERSION
