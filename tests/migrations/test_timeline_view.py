"""Migration 003: atomically replace legacy Timeline with an Events view."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

import gmv_core.migrations as migrations
from gmv_core.errors import MigrationError

ROW = (
    "SYS-000001",
    "2026-01-01T00:00:00Z",
    "engine_run",
    "duplicate content",
    "test",
)


def _version_two_database(tmp_path: Path) -> Path:
    database = tmp_path / "version-two.db"
    assert (
        migrations.migrate(database, target_version=migrations.OID_SEQUENCE_VERSION)
        == migrations.OID_SEQUENCE_VERSION
    )
    return database


def _insert(connection: sqlite3.Connection, table: str, rows: list[tuple]) -> None:
    if table == "timeline":
        statement = (
            "INSERT INTO timeline (oid,event_at,event_type,description,source) "
            "VALUES (?,?,?,?,?)"
        )
    elif table == "events":
        statement = (
            "INSERT INTO events (oid,event_at,event_type,description,source) "
            "VALUES (?,?,?,?,?)"
        )
    else:
        raise ValueError(f"unsupported table: {table}")
    connection.executemany(statement, rows)


def _timeline_object_type(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT type FROM sqlite_master WHERE name = 'timeline'"
    ).fetchone()
    assert row is not None
    return str(row[0])


def test_migration_three_target_is_byte_stable(
    tmp_path: Path,
) -> None:
    database = tmp_path / "version-three.db"

    assert (
        migrations.migrate(
            database, target_version=migrations.TIMELINE_VIEW_VERSION
        )
        == migrations.TIMELINE_VIEW_VERSION
    )
    with sqlite3.connect(database) as connection:
        assert _timeline_object_type(connection) == "view"

    migrated_digest = hashlib.sha256(database.read_bytes()).hexdigest()

    assert (
        migrations.migrate(
            database, target_version=migrations.TIMELINE_VIEW_VERSION
        )
        == migrations.TIMELINE_VIEW_VERSION
    )
    assert hashlib.sha256(database.read_bytes()).hexdigest() == migrated_digest


def test_migration_replaces_timeline_with_events_view_after_multiset_parity(
    tmp_path: Path,
) -> None:
    database = _version_two_database(tmp_path)
    events_only = (
        "SYS-000001",
        "2026-01-02T00:00:00Z",
        "canonical_only",
        "Events may contain additional history",
        "test",
    )
    with sqlite3.connect(database) as connection:
        _insert(connection, "timeline", [ROW, ROW])
        _insert(connection, "events", [ROW, ROW, events_only])
        events_before = list(connection.execute("SELECT * FROM events ORDER BY id"))

    assert (
        migrations.migrate(
            database, target_version=migrations.TIMELINE_VIEW_VERSION
        )
        == migrations.TIMELINE_VIEW_VERSION
    )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (
            migrations.TIMELINE_VIEW_VERSION,
        )
        assert _timeline_object_type(connection) == "view"
        assert list(connection.execute("SELECT * FROM events ORDER BY id")) == events_before
        assert list(connection.execute("SELECT * FROM timeline ORDER BY id")) == events_before
        assert connection.execute(
            "SELECT object_type,prefix,last_value FROM oid_sequences ORDER BY object_type"
        ).fetchall() == [
            ("Core", "COR", 0),
            ("Person", "PER", 0),
            ("Plugin", "PLG", 0),
            ("Resource", "RES", 0),
            ("Service", "SRV", 0),
            ("System", "SYS", 0),
        ]
        with pytest.raises(sqlite3.OperationalError, match="cannot modify timeline"):
            _insert(connection, "timeline", [ROW])


def test_migration_rejects_a_timeline_multiset_deficit_without_schema_change(
    tmp_path: Path,
) -> None:
    database = _version_two_database(tmp_path)
    with sqlite3.connect(database) as connection:
        _insert(connection, "timeline", [ROW, ROW])
        _insert(connection, "events", [ROW])

    with pytest.raises(MigrationError, match="migration 3 failed"):
        migrations.migrate(
            database, target_version=migrations.TIMELINE_VIEW_VERSION
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (
            migrations.OID_SEQUENCE_VERSION,
        )
        assert _timeline_object_type(connection) == "table"
        assert connection.execute("SELECT COUNT(*) FROM timeline").fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone() == (1,)


def test_failure_after_drop_rolls_back_the_table_to_view_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _version_two_database(tmp_path)
    with sqlite3.connect(database) as connection:
        _insert(connection, "timeline", [ROW])
        _insert(connection, "events", [ROW])

    valid_loader = migrations._migration_sql

    def broken_loader(resource: str) -> str:
        if resource == migrations.TIMELINE_VIEW_RESOURCE:
            return """
                BEGIN IMMEDIATE;
                DROP TABLE timeline;
                THIS IS NOT VALID SQL;
                PRAGMA user_version = 3;
                COMMIT;
            """
        return valid_loader(resource)

    monkeypatch.setattr(migrations, "_migration_sql", broken_loader)

    with pytest.raises(MigrationError, match="migration 3 failed"):
        migrations.migrate(
            database, target_version=migrations.TIMELINE_VIEW_VERSION
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (
            migrations.OID_SEQUENCE_VERSION,
        )
        assert _timeline_object_type(connection) == "table"
        assert connection.execute("SELECT * FROM timeline").fetchall()[0][1:] == ROW
        assert connection.execute("SELECT * FROM events").fetchall()[0][1:] == ROW
