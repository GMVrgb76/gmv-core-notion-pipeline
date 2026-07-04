"""Acceptance tests for the S001-04 isolation boundary."""

from __future__ import annotations

import sqlite3
import subprocess
import sys

import pytest

from gmv_core.config import load_config
from gmv_core.paths import GMVPaths
from tests.conftest import IsolatedGMV
from tests.helpers import LiveDatabaseWriteError


def test_default_configuration_uses_disposable_home(isolated_gmv: IsolatedGMV) -> None:
    config = load_config()

    assert config.home == isolated_gmv.home
    assert GMVPaths.from_config(config).database == isolated_gmv.database
    assert isolated_gmv.database.exists()


def test_disposable_database_accepts_writes(isolated_gmv: IsolatedGMV) -> None:
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute("INSERT INTO test_sentinel DEFAULT VALUES")

    with sqlite3.connect(isolated_gmv.database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM test_sentinel").fetchone()

    assert count == (1,)


def test_live_database_write_is_rejected(isolated_gmv: IsolatedGMV) -> None:
    with pytest.raises(LiveDatabaseWriteError, match="may not open the live database"):
        sqlite3.connect(isolated_gmv.live_database)


def test_subprocess_inherits_disposable_home(isolated_gmv: IsolatedGMV) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from gmv_core.config import load_config; print(load_config().home)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.strip() == str(isolated_gmv.home)
