"""Legacy and current-schema fixtures for characterization tests."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from gmv_core.migrations import CURRENT_SCHEMA_VERSION, migrate

SCHEMA_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "current_schema.sql"
CLI = Path(__file__).resolve().parents[2] / "11_CLI" / "gmv"


@pytest.fixture
def characterized_database(isolated_gmv: object) -> Path:
    """Legacy pre-migration (v0/baseline) schema fixture -- NOT the current
    canonical schema. Matches the v1 baseline shape exactly (no CHECK
    constraints, no foreign keys, `timeline`/`engine_runs`/`engines` as
    real tables) and is deliberately left at `PRAGMA user_version = 0` by
    tests/fixtures/current_schema.sql. Use this only for tests that
    specifically require that legacy shape (migration-adoption and
    Timeline/Events reconciliation characterization); see
    `current_v8_database` for the real, currently-migrated schema.
    """
    database = Path(getattr(isolated_gmv, "database"))
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE test_sentinel")
        connection.executescript(SCHEMA_FIXTURE.read_text(encoding="utf-8"))
    return database


@pytest.fixture
def current_v8_database(isolated_gmv: object) -> Path:
    """The real, currently-migrated canonical schema (user_version == 8),
    built exclusively through the canonical migration path -- never from
    tests/fixtures/current_schema.sql, never copied from the live
    database, and dependent on no external state. Isolation and cleanup
    are inherited from `isolated_gmv` (a disposable `tmp_path` home).
    """
    database = Path(getattr(isolated_gmv, "database"))
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE test_sentinel")
    assert migrate(database, target_version=CURRENT_SCHEMA_VERSION) == CURRENT_SCHEMA_VERSION
    with sqlite3.connect(database) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == CURRENT_SCHEMA_VERSION
    return database


@pytest.fixture
def cli_environment(
    characterized_database: Path,
    tmp_path: Path,
) -> Iterator[dict[str, str]]:
    del characterized_database
    executable_directory = tmp_path / "test-bin"
    executable_directory.mkdir()
    launchctl = executable_directory / "launchctl"
    launchctl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    launchctl.chmod(0o755)

    environment = os.environ.copy()
    environment["PATH"] = f"{executable_directory}:{environment['PATH']}"
    yield environment
