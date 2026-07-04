"""Repeated migration behavior for disposable databases."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from gmv_core.migrations import BASELINE_VERSION, migrate


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_repeated_migration_is_byte_stable(tmp_path: Path) -> None:
    database = tmp_path / "repeated.db"

    assert migrate(database) == BASELINE_VERSION
    first_digest = _digest(database)

    assert migrate(database) == BASELINE_VERSION
    assert _digest(database) == first_digest

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (
            BASELINE_VERSION,
        )
