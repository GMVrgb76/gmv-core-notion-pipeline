"""Connection ownership for the Core persistence boundary (gmv_core/database.py)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gmv_core import database
from gmv_core.errors import (
    ConfigurationError,
    DatabaseConfigurationError,
    UnauthorizedWriteError,
)
from gmv_core.paths import GMVPaths
from tests.conftest import IsolatedGMV


def test_connect_resolves_database_under_injected_home(tmp_path: Path) -> None:
    home = tmp_path / "injected-core"
    expected = GMVPaths.from_home(home).database
    expected.parent.mkdir(parents=True)
    with sqlite3.connect(expected) as connection:
        connection.execute("CREATE TABLE path_marker(id INTEGER PRIMARY KEY)")

    with database.connect(home=home) as connection:
        marker = connection.execute(
            "SELECT name FROM sqlite_master WHERE name='path_marker'"
        ).fetchone()

    assert marker == ("path_marker",)


def test_connect_blocks_unapproved_schema_and_data_writes(tmp_path: Path) -> None:
    home = tmp_path / "injected-core"
    database_path = GMVPaths.from_home(home).database
    database_path.parent.mkdir(parents=True)
    with sqlite3.connect(database_path):
        pass

    with database.connect(home=home) as connection:
        with pytest.raises(UnauthorizedWriteError):
            connection.execute("CREATE TABLE sentinel (id INTEGER PRIMARY KEY)")

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name='sentinel'"
        ).fetchone() is None


def test_connect_enables_foreign_keys(tmp_path: Path) -> None:
    home = tmp_path / "injected-core"
    database_path = GMVPaths.from_home(home).database
    database_path.parent.mkdir(parents=True)
    with sqlite3.connect(database_path):
        pass

    with database.connect(home=home) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)


def test_explicit_read_only_connection_enables_foreign_keys(tmp_path: Path) -> None:
    database_path = tmp_path / "read-only.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE sentinel(id INTEGER PRIMARY KEY)")
    uri = f"{database_path.resolve().as_uri()}?mode=ro"

    with database.connect_path(uri, uri=True) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        with pytest.raises(UnauthorizedWriteError):
            connection.execute("INSERT INTO sentinel DEFAULT VALUES")


def test_enforcement_fails_closed_inside_an_active_transaction() -> None:
    with sqlite3.connect(":memory:") as connection:
        connection.execute("BEGIN")
        with pytest.raises(
            DatabaseConfigurationError,
            match="foreign-key enforcement could not be enabled",
        ):
            database.enable_foreign_keys(connection)


def test_explicit_factory_closes_connection_when_enforcement_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DisabledConnection:
        closed = False

        def execute(self, _statement: str) -> DisabledConnection:
            return self

        def fetchone(self) -> tuple[int]:
            return (0,)

        def close(self) -> None:
            self.closed = True

    disabled = DisabledConnection()
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: disabled)

    with pytest.raises(
        DatabaseConfigurationError,
        match="foreign-key enforcement could not be enabled",
    ):
        database.connect_path(":memory:")
    assert disabled.closed is True


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
        count = connection.execute("SELECT COUNT(*) FROM test_sentinel").fetchone()

    assert count == (0,)


def test_connect_preserves_context_manager_semantics(isolated_gmv: IsolatedGMV) -> None:
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")

    assert connection.in_transaction is False
    assert connection.execute("SELECT COUNT(*) FROM test_sentinel").fetchone() == (0,)


def test_connect_propagates_configuration_error_when_home_unresolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GMV_HOME", raising=False)
    monkeypatch.delenv("HOME", raising=False)

    with pytest.raises(ConfigurationError):
        database.connect()
