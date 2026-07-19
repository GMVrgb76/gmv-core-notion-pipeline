"""A disposable v6 database for Compatibility Layer subprocess tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gmv_core.migrations import FOREIGN_KEYS_VERSION, migrate
from tests.conftest import IsolatedGMV


@pytest.fixture(autouse=True)
def compatibility_database(isolated_gmv: IsolatedGMV) -> Path:
    database = isolated_gmv.database
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE test_sentinel")
    assert migrate(database, target_version=FOREIGN_KEYS_VERSION) == FOREIGN_KEYS_VERSION
    with sqlite3.connect(database) as connection:
        connection.executemany(
            """
            INSERT INTO objects(oid,type,name,status)
            VALUES (?,?,?,'active')
            """,
            [
                ("SYS-000001", "System", "GMV OS"),
                ("SRV-000002", "Service", "Morning Brief"),
                ("SRV-000003", "Service", "Daily Log"),
                ("SRV-000004", "Service", "Market Engine"),
            ],
        )
    return database
