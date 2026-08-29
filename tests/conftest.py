"""Per-test disposable GMV home and live database protection."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.helpers import install_live_database_guard

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LIVE_DATABASE = REPOSITORY_ROOT / "09_DATABASE" / "GMV.db"


@dataclass(frozen=True, slots=True)
class IsolatedGMV:
    home: Path
    database: Path
    live_database: Path


@pytest.fixture(autouse=True)
def isolated_gmv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> IsolatedGMV:
    """Give every test a disposable home/database and reject live writes."""
    home = tmp_path / ".gmv_core"
    database = home / "09_DATABASE" / "GMV.db"
    database.parent.mkdir(parents=True)

    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE test_sentinel (id INTEGER PRIMARY KEY)")

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GMV_HOME", str(home))
    install_live_database_guard(monkeypatch, LIVE_DATABASE)

    return IsolatedGMV(home=home, database=database, live_database=LIVE_DATABASE)
