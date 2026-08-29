"""require_supported_schema_version: read-only schema-version preflight.

Added for SEC-006's second corrective slice, shared under gmv_core.migrations
so both 01_RUNTIME/knowledge_engine.py and any future caller can fail fast on
a missing or incompatible schema without creating an improper dependency
from 01_RUNTIME onto 10_API.
"""

from __future__ import annotations

import sqlite3

import pytest

from gmv_core.errors import MigrationStateError
from gmv_core.migrations import (
    DOMAIN_CONSTRAINTS_VERSION,
    ENGINE_RUNS_RETIRED_VERSION,
    FOREIGN_KEYS_VERSION,
    OID_TYPE_CONSISTENCY_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    migrate,
    require_supported_schema_version,
)
from tests.conftest import IsolatedGMV


def _schema_snapshot(connection: sqlite3.Connection) -> tuple[object, ...]:
    return tuple(
        connection.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        )
    )


class _RecordingConnection(sqlite3.Connection):
    """Records every SQL string executed, to prove read-only-only access."""

    def execute(self, sql, parameters=()):  # noqa: D102
        self._recorded.append(sql)
        return super().execute(sql, parameters)


@pytest.mark.parametrize(
    "target_version",
    [FOREIGN_KEYS_VERSION, DOMAIN_CONSTRAINTS_VERSION, OID_TYPE_CONSISTENCY_VERSION],
)
def test_accepts_and_returns_each_canonical_version(
    isolated_gmv: IsolatedGMV, target_version: int
) -> None:
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute("DROP TABLE test_sentinel")
    migrate(isolated_gmv.database, target_version=target_version)

    with sqlite3.connect(isolated_gmv.database) as connection:
        before = _schema_snapshot(connection)
        result = require_supported_schema_version(connection)
        after = _schema_snapshot(connection)

    assert result == target_version
    assert before == after  # no schema change of any kind


@pytest.mark.parametrize(
    "bad_version",
    [0, ENGINE_RUNS_RETIRED_VERSION, OID_TYPE_CONSISTENCY_VERSION + 1, 999],
    ids=["unversioned_zero", "pre_canonical_five", "next_future_nine", "arbitrary_future_999"],
)
def test_rejects_every_non_canonical_version(
    isolated_gmv: IsolatedGMV, bad_version: int
) -> None:
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute("DROP TABLE test_sentinel")
        connection.execute(f"PRAGMA user_version = {bad_version}")
        connection.commit()
        before = _schema_snapshot(connection)

    with sqlite3.connect(isolated_gmv.database) as connection:
        with pytest.raises(MigrationStateError) as excinfo:
            require_supported_schema_version(connection)

    with sqlite3.connect(isolated_gmv.database) as connection:
        after = _schema_snapshot(connection)
    assert before == after  # no repair, no create, no migration attempted

    message = str(excinfo.value)
    assert f"found {bad_version}" in message
    assert "expected 6 or 7 or 8" in message
    assert "approved migration" in message


def test_supported_versions_are_exactly_six_seven_eight() -> None:
    assert SUPPORTED_SCHEMA_VERSIONS == (6, 7, 8)


def test_performs_only_a_pragma_user_version_read(isolated_gmv: IsolatedGMV) -> None:
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute("DROP TABLE test_sentinel")
    migrate(isolated_gmv.database, target_version=FOREIGN_KEYS_VERSION)

    connection = sqlite3.connect(str(isolated_gmv.database), factory=_RecordingConnection)
    connection._recorded = []
    try:
        require_supported_schema_version(connection)
    finally:
        recorded = connection._recorded
        connection.close()

    assert recorded == ["PRAGMA user_version"]
