"""Sanitized current-schema fixture for characterization tests."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

SCHEMA_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "current_schema.sql"
CLI = Path(__file__).resolve().parents[2] / "11_CLI" / "gmv"


@pytest.fixture
def characterized_database(isolated_gmv: object) -> Path:
    database = Path(getattr(isolated_gmv, "database"))
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE test_sentinel")
        connection.executescript(SCHEMA_FIXTURE.read_text(encoding="utf-8"))
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
