"""Migration 004: immutable Events and compensating correction references."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

import gmv_core.migrations as migrations
from gmv_core.errors import MigrationError

EVENT = (
    "SYS-000001",
    "2026-01-01T00:00:00Z",
    "system_event",
    "original",
    "test",
)


def _version_three_database(tmp_path: Path) -> Path:
    database = tmp_path / "version-three.db"
    assert (
        migrations.migrate(
            database, target_version=migrations.TIMELINE_VIEW_VERSION
        )
        == migrations.TIMELINE_VIEW_VERSION
    )
    return database


def _insert_event(
    connection: sqlite3.Connection,
    event: tuple = EVENT,
    *,
    event_id: int | None = None,
    supersedes_event_id: int | None = None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO events
        (id,oid,event_at,event_type,description,source,supersedes_event_id)
        VALUES (?,?,?,?,?,?,?)
        """,
        (event_id, *event, supersedes_event_id),
    )
    return int(cursor.lastrowid)


def _trigger_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='events'"
        )
    }


def test_migration_four_is_current_and_byte_stable_after_live_cutover(
    tmp_path: Path,
) -> None:
    database = tmp_path / "current-version.db"

    assert migrations.migrate(database) == migrations.CURRENT_SCHEMA_VERSION
    assert migrations.CURRENT_SCHEMA_VERSION == migrations.APPEND_ONLY_EVENTS_VERSION
    with sqlite3.connect(database) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(events)")]
        assert "supersedes_event_id" in columns
    migrated_digest = hashlib.sha256(database.read_bytes()).hexdigest()

    assert migrations.migrate(database) == migrations.CURRENT_SCHEMA_VERSION
    assert hashlib.sha256(database.read_bytes()).hexdigest() == migrated_digest

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (4,)
        assert "supersedes_event_id" in {
            row[1] for row in connection.execute("PRAGMA table_info(events)")
        }
        assert _trigger_names(connection) == {
            "events_reject_update",
            "events_reject_delete",
            "events_reject_id_reuse",
            "events_require_superseded_event",
        }


def test_correction_is_a_new_event_with_an_existing_supersession_reference(
    tmp_path: Path,
) -> None:
    database = _version_three_database(tmp_path)
    migrations.migrate(database, target_version=migrations.APPEND_ONLY_EVENTS_VERSION)

    correction = (*EVENT[:3], "corrected", EVENT[4])
    with sqlite3.connect(database) as connection:
        cursor = connection.execute(
            """
            INSERT INTO events (oid,event_at,event_type,description,source)
            VALUES (?,?,?,?,?)
            """,
            EVENT,
        )
        original_id = int(cursor.lastrowid)
        correction_id = _insert_event(
            connection,
            correction,
            supersedes_event_id=original_id,
        )
        latest_id = _insert_event(
            connection,
            (*EVENT[:3], "corrected again", EVENT[4]),
            supersedes_event_id=correction_id,
        )
        assert correction_id != original_id
        assert connection.execute(
            "SELECT supersedes_event_id FROM events WHERE id=?", (correction_id,)
        ).fetchone() == (original_id,)
        assert connection.execute(
            "SELECT supersedes_event_id FROM events WHERE id=?", (latest_id,)
        ).fetchone() == (correction_id,)
        assert connection.execute(
            "SELECT COUNT(*) FROM timeline WHERE id IN (?,?,?)",
            (original_id, correction_id, latest_id),
        ).fetchone() == (3,)


def test_missing_superseded_event_is_rejected_without_inserting(
    tmp_path: Path,
) -> None:
    database = _version_three_database(tmp_path)
    migrations.migrate(database, target_version=migrations.APPEND_ONLY_EVENTS_VERSION)

    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="does not exist"):
            _insert_event(connection, supersedes_event_id=999)
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)


def test_update_delete_and_id_reuse_are_rejected_without_mutation(
    tmp_path: Path,
) -> None:
    database = _version_three_database(tmp_path)
    migrations.migrate(database, target_version=migrations.APPEND_ONLY_EVENTS_VERSION)

    with sqlite3.connect(database) as connection:
        event_id = _insert_event(connection)
        before = connection.execute(
            "SELECT * FROM events WHERE id=?", (event_id,)
        ).fetchone()

        with pytest.raises(sqlite3.IntegrityError, match="UPDATE prohibited"):
            connection.execute(
                "UPDATE events SET description='rewritten' WHERE id=?", (event_id,)
            )
        with pytest.raises(sqlite3.IntegrityError, match="DELETE prohibited"):
            connection.execute("DELETE FROM events WHERE id=?", (event_id,))
        with pytest.raises(sqlite3.IntegrityError, match="id reuse prohibited"):
            connection.execute(
                """
                INSERT OR REPLACE INTO events
                (id,oid,event_at,event_type,description,source,supersedes_event_id)
                VALUES (?,?,?,?,?,?,NULL)
                """,
                (event_id, *EVENT),
            )

        assert connection.execute(
            "SELECT * FROM events WHERE id=?", (event_id,)
        ).fetchone() == before


def test_failed_migration_rolls_back_column_and_triggers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _version_three_database(tmp_path)
    valid_loader = migrations._migration_sql

    def broken_loader(resource: str) -> str:
        if resource == migrations.APPEND_ONLY_EVENTS_RESOURCE:
            return """
                BEGIN IMMEDIATE;
                ALTER TABLE events ADD COLUMN supersedes_event_id INTEGER;
                CREATE TRIGGER partial_trigger BEFORE UPDATE ON events
                BEGIN SELECT RAISE(ABORT, 'partial'); END;
                THIS IS NOT VALID SQL;
                PRAGMA user_version = 4;
                COMMIT;
            """
        return valid_loader(resource)

    monkeypatch.setattr(migrations, "_migration_sql", broken_loader)

    with pytest.raises(MigrationError, match="migration 4 failed"):
        migrations.migrate(
            database, target_version=migrations.APPEND_ONLY_EVENTS_VERSION
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (3,)
        assert "supersedes_event_id" not in {
            row[1] for row in connection.execute("PRAGMA table_info(events)")
        }
        assert _trigger_names(connection) == set()
