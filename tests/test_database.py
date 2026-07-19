"""Connection ownership for the Core persistence boundary (gmv_core/database.py)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gmv_core import database
from gmv_core.errors import ConfigurationError, DatabaseConfigurationError
from gmv_core.paths import GMVPaths
from tests.conftest import IsolatedGMV


def test_connect_resolves_database_under_injected_home(tmp_path: Path) -> None:
    home = tmp_path / "injected-core"
    expected = GMVPaths.from_home(home).database
    expected.parent.mkdir(parents=True)
    with sqlite3.connect(expected):
        pass

    with database.connect(home=home) as connection:
        opened = connection.execute("PRAGMA database_list").fetchone()[2]

    assert Path(opened) == expected


def test_connect_opens_a_working_connection(tmp_path: Path) -> None:
    home = tmp_path / "injected-core"
    database_path = GMVPaths.from_home(home).database
    database_path.parent.mkdir(parents=True)
    with sqlite3.connect(database_path):
        pass

    with database.connect(home=home) as connection:
        connection.execute("CREATE TABLE sentinel (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO sentinel DEFAULT VALUES")
        count = connection.execute("SELECT COUNT(*) FROM sentinel").fetchone()

    assert count == (1,)


def test_connect_enables_foreign_keys(tmp_path: Path) -> None:
    home = tmp_path / "injected-core"
    database_path = GMVPaths.from_home(home).database
    database_path.parent.mkdir(parents=True)
    with sqlite3.connect(database_path):
        pass

    with database.connect(home=home) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)


def test_enforcement_fails_closed_inside_an_active_transaction() -> None:
    with sqlite3.connect(":memory:") as connection:
        connection.execute("BEGIN")
        with pytest.raises(
            DatabaseConfigurationError,
            match="foreign-key enforcement could not be enabled",
        ):
            database.enable_foreign_keys(connection)


def test_required_object_identity_rejects_wrong_type() -> None:
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE objects(oid TEXT PRIMARY KEY,type TEXT NOT NULL)")
        connection.execute("INSERT INTO objects VALUES('SRV-000001','System')")

        with pytest.raises(
            DatabaseConfigurationError,
            match=r"SRV-000001 \(Service\)",
        ):
            database.require_object_identities(
                connection,
                {"SRV-000001": "Service"},
            )


def test_connect_uses_load_config_precedence_by_default(isolated_gmv: IsolatedGMV) -> None:
    with database.connect() as connection:
        connection.execute("INSERT INTO test_sentinel DEFAULT VALUES")

    with sqlite3.connect(isolated_gmv.database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM test_sentinel").fetchone()

    assert count == (1,)


def test_connect_preserves_context_manager_semantics(isolated_gmv: IsolatedGMV) -> None:
    with database.connect() as connection:
        connection.execute("INSERT INTO test_sentinel DEFAULT VALUES")

    count = connection.execute("SELECT COUNT(*) FROM test_sentinel").fetchone()

    assert count == (1,)


def test_connect_propagates_configuration_error_when_home_unresolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GMV_HOME", raising=False)
    monkeypatch.delenv("HOME", raising=False)

    with pytest.raises(ConfigurationError):
        database.connect()
