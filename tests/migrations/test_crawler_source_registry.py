"""Migration 009: crawler_source_registry, available but not current.

The GMV Crawler subsystem that owns this table does not exist yet. This
migration must be reachable via an explicit target_version, exactly like
versions 1-7 remain reachable today without being CURRENT_SCHEMA_VERSION,
and must not change behavior for any caller of migrate(db) that does not
ask for it by name.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import gmv_core.migrations as migrations
from gmv_core.database import connect_path
from tests.helpers import connect_fixture_database


def _version_eight_database(tmp_path: Path, name: str = "crawler-source.db") -> Path:
    database = tmp_path / name
    assert (
        migrations.migrate(
            database,
            target_version=migrations.OID_TYPE_CONSISTENCY_VERSION,
        )
        == migrations.OID_TYPE_CONSISTENCY_VERSION
        == 8
    )
    return database


def _seed_resource(
    connection: sqlite3.Connection,
    *,
    oid: str = "RES-000001",
    sha256: str = "fixture-hash-1",
) -> None:
    connection.execute(
        """
        INSERT INTO objects(oid,type,name,status,created_at,updated_at)
        VALUES (?,?,?,?,?,?)
        """,
        (oid, "Resource", "fixture", "active", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    )
    connection.execute(
        """
        INSERT INTO resources(resource_oid,path,filename,sha256,imported_at)
        VALUES (?,?,?,?,?)
        """,
        (oid, "/fixture", "fixture", sha256, "2026-01-01T00:00:00"),
    )


def _dump(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(connection.iterdump())


def test_crawler_source_registry_version_is_not_current_or_supported() -> None:
    assert migrations.CRAWLER_SOURCE_REGISTRY_VERSION == 9
    assert migrations.CURRENT_SCHEMA_VERSION == migrations.OID_TYPE_CONSISTENCY_VERSION == 8
    assert migrations.CRAWLER_SOURCE_REGISTRY_VERSION not in migrations.SUPPORTED_SCHEMA_VERSIONS


def test_default_migrate_still_stops_at_eight(tmp_path: Path) -> None:
    database = tmp_path / "default.db"
    assert migrations.migrate(database) == 8

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "crawler_source_registry" not in tables


def test_explicit_target_nine_creates_table_with_expected_shape(tmp_path: Path) -> None:
    database = _version_eight_database(tmp_path)
    assert (
        migrations.migrate(database, target_version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION)
        == 9
    )

    with connect_fixture_database(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (9,)
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(crawler_source_registry)")
        }
        assert columns == {
            "content_hash",
            "connector",
            "canonical_locator",
            "resource_oid",
            "remote_revision",
            "state",
            "discovered_at",
            "last_seen_at",
            "deleted_at",
        }
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(crawler_source_registry)")
        }
        assert {
            "crawler_source_registry_resource_oid_idx",
            "crawler_source_registry_state_idx",
            "crawler_source_registry_connector_idx",
        } <= indexes
        foreign_keys = tuple(
            connection.execute("PRAGMA foreign_key_list(crawler_source_registry)")
        )
        assert len(foreign_keys) == 1
        assert foreign_keys[0][2] == "resources"
        assert foreign_keys[0][3] == "resource_oid"


@pytest.mark.parametrize(
    "bad_hash",
    [
        "not-a-hash",
        "sha256:abc",  # too short
        "sha256:" + "a" * 63,  # 63 hex chars instead of 64
        "sha256:" + "A" * 64,  # uppercase not accepted
        "sha256:" + "g" * 64,  # non-hex character
        "sha256:a" + "A" * 63,  # regression: first char valid hex, rest not --
        # an earlier version of this CHECK used GLOB '[0-9a-f]' unrepeated,
        # which SQLite only applies to ONE character position, silently
        # letting the other 63 through unconstrained. Caught by review.
    ],
)
def test_content_hash_rejects_malformed_values(tmp_path: Path, bad_hash: str) -> None:
    database = _version_eight_database(tmp_path)
    migrations.migrate(database, target_version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO crawler_source_registry
                    (content_hash, connector, canonical_locator, discovered_at, last_seen_at)
                VALUES (?, 'dropbox', '/x', 't', 't')
                """,
                (bad_hash,),
            )


def test_content_hash_accepts_well_formed_sha256(tmp_path: Path) -> None:
    database = _version_eight_database(tmp_path)
    migrations.migrate(database, target_version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        connection.execute(
            """
            INSERT INTO crawler_source_registry
                (content_hash, connector, canonical_locator, discovered_at, last_seen_at)
            VALUES (?, 'dropbox', '/x', 't', 't')
            """,
            ("sha256:" + "a" * 64,),
        )


def test_state_enum_rejects_unknown_values(tmp_path: Path) -> None:
    database = _version_eight_database(tmp_path)
    migrations.migrate(database, target_version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO crawler_source_registry
                    (content_hash, connector, canonical_locator, state, discovered_at, last_seen_at)
                VALUES (?, 'dropbox', '/x', 'ARCHIVED', 't', 't')
                """,
                ("sha256:" + "b" * 64,),
            )


def test_resource_oid_nullable_but_must_reference_a_real_resource(tmp_path: Path) -> None:
    database = _version_eight_database(tmp_path)
    migrations.migrate(database, target_version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        _seed_resource(connection)

        # NULL resource_oid is accepted: DISCOVER-stage rows exist before REGISTER.
        connection.execute(
            """
            INSERT INTO crawler_source_registry
                (content_hash, connector, canonical_locator, resource_oid, discovered_at, last_seen_at)
            VALUES (?, 'dropbox', '/x', NULL, 't', 't')
            """,
            ("sha256:" + "c" * 64,),
        )

        # A resource_oid that has no matching row in `resources` at all is
        # rejected by the foreign key itself -- not by a bespoke trigger.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO crawler_source_registry
                    (content_hash, connector, canonical_locator, resource_oid, discovered_at, last_seen_at)
                VALUES (?, 'dropbox', '/x', 'RES-999999', 't', 't')
                """,
                ("sha256:" + "d" * 64,),
            )

        # A resource_oid pointing at a real resources row is accepted.
        connection.execute(
            """
            INSERT INTO crawler_source_registry
                (content_hash, connector, canonical_locator, resource_oid, discovered_at, last_seen_at)
            VALUES (?, 'dropbox', '/x', 'RES-000001', 't', 't')
            """,
            ("sha256:" + "e" * 64,),
        )

        # Updating resource_oid to a non-existent resource is rejected too.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE crawler_source_registry SET resource_oid='RES-999999' "
                "WHERE content_hash=?",
                ("sha256:" + "c" * 64,),
            )


def test_deleted_state_requires_deleted_at_on_insert(tmp_path: Path) -> None:
    """Regression guard: an INSERT that lands directly on state='DELETED'
    with deleted_at NULL must be rejected exactly like an UPDATE would be.
    A trigger scoped only to UPDATE OF state does not catch this path."""
    database = _version_eight_database(tmp_path)
    migrations.migrate(database, target_version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO crawler_source_registry
                    (content_hash, connector, canonical_locator, state, discovered_at, last_seen_at)
                VALUES (?, 'dropbox', '/x', 'DELETED', 't', 't')
                """,
                ("sha256:" + "f" * 64,),
            )


def test_deleted_state_requires_deleted_at_on_update(tmp_path: Path) -> None:
    database = _version_eight_database(tmp_path)
    migrations.migrate(database, target_version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        connection.execute(
            """
            INSERT INTO crawler_source_registry
                (content_hash, connector, canonical_locator, state, discovered_at, last_seen_at)
            VALUES (?, 'dropbox', '/x', 'NEW', 't', 't')
            """,
            ("sha256:" + "1" * 64,),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE crawler_source_registry SET state='DELETED' WHERE content_hash=?",
                ("sha256:" + "1" * 64,),
            )

        # Setting deleted_at together with state=DELETED is accepted -- no
        # row is ever silently removed to represent the transition.
        connection.execute(
            "UPDATE crawler_source_registry SET state='DELETED', deleted_at='t' "
            "WHERE content_hash=?",
            ("sha256:" + "1" * 64,),
        )
        row = connection.execute(
            "SELECT state, deleted_at FROM crawler_source_registry WHERE content_hash=?",
            ("sha256:" + "1" * 64,),
        ).fetchone()
        assert row == ("DELETED", "t")


def test_clearing_deleted_at_while_still_deleted_is_rejected(tmp_path: Path) -> None:
    """An UPDATE that touches only deleted_at (not state) must still be
    caught -- closing the gap a trigger scoped only to UPDATE OF state
    would leave open."""
    database = _version_eight_database(tmp_path)
    migrations.migrate(database, target_version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        connection.execute(
            """
            INSERT INTO crawler_source_registry
                (content_hash, connector, canonical_locator, state, deleted_at, discovered_at, last_seen_at)
            VALUES (?, 'dropbox', '/x', 'DELETED', 't', 't', 't')
            """,
            ("sha256:" + "2" * 64,),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE crawler_source_registry SET deleted_at=NULL WHERE content_hash=?",
                ("sha256:" + "2" * 64,),
            )


def test_migrating_to_nine_twice_is_idempotent(tmp_path: Path) -> None:
    database = _version_eight_database(tmp_path)
    assert (
        migrations.migrate(database, target_version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION)
        == 9
    )
    assert (
        migrations.migrate(database, target_version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION)
        == 9
    )


def test_fault_injection_rolls_back_schema_data_version_and_enforcement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _version_eight_database(tmp_path)
    valid_loader = migrations._migration_sql

    with connect_fixture_database(database) as connection:
        _seed_resource(connection)
        before = _dump(connection)

    with connect_path(database) as connection:
        def broken_loader(resource: str) -> str:
            sql = valid_loader(resource)
            if resource == migrations.CRAWLER_SOURCE_REGISTRY_RESOURCE:
                return sql.replace(
                    "PRAGMA user_version = 9;",
                    "SELECT no_such_db009_function();\nPRAGMA user_version = 9;",
                    1,
                )
            return sql

        monkeypatch.setattr(migrations, "_migration_sql", broken_loader)

        with pytest.raises(migrations.MigrationError, match="migration 9 failed"):
            migrations._apply_migration(
                connection,
                target=database,
                version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION,
                resource=migrations.CRAWLER_SOURCE_REGISTRY_RESOURCE,
            )

        assert connection.execute("PRAGMA user_version").fetchone() == (8,)
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert _dump(connection) == before
