"""Migration 006: explicit restrictive foreign-key enforcement."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import gmv_core.migrations as migrations
from gmv_core import database as core_database
from gmv_core.errors import MigrationError

REBUILT_TABLES = (
    "events",
    "service_runs",
    "plugin_metadata",
    "plugin_services",
    "relations",
    "resources",
    "import_queue",
)

EXPECTED_FOREIGN_KEYS = {
    ("events", "oid", "objects", "oid"),
    ("events", "supersedes_event_id", "events", "id"),
    ("service_runs", "service_oid", "objects", "oid"),
    ("plugin_metadata", "plugin_oid", "objects", "oid"),
    ("plugin_services", "plugin_oid", "plugin_metadata", "plugin_oid"),
    ("plugin_services", "service_oid", "objects", "oid"),
    ("relations", "source_oid", "objects", "oid"),
    ("relations", "target_oid", "objects", "oid"),
    ("resources", "resource_oid", "objects", "oid"),
    ("import_queue", "resource_oid", "resources", "resource_oid"),
}


def _version_five_database(tmp_path: Path, name: str = "foreign-keys.db") -> Path:
    home = tmp_path / name
    database = home / "09_DATABASE" / "GMV.db"
    database.parent.mkdir(parents=True)
    assert (
        migrations.migrate(
            database,
            target_version=migrations.ENGINE_RUNS_RETIRED_VERSION,
        )
        == migrations.ENGINE_RUNS_RETIRED_VERSION
    )
    return database


def _seed_references(connection: sqlite3.Connection) -> None:
    connection.executemany(
        "INSERT INTO objects(oid,type,name,status) VALUES (?,?,?,'active')",
        [
            ("SYS-000001", "System", "System"),
            ("SRV-000001", "Service", "Service"),
            ("PLG-000001", "Plugin", "Plugin"),
            ("RES-000001", "Resource", "Resource"),
        ],
    )
    connection.execute(
        "INSERT INTO events(id,oid,event_at,event_type) VALUES (1,'SYS-000001','t1','one')"
    )
    connection.execute(
        """
        INSERT INTO events(id,oid,event_at,event_type,supersedes_event_id)
        VALUES (2,'SYS-000001','t2','two',1)
        """
    )
    connection.execute(
        """
        INSERT INTO service_runs(id,service_oid,service_name,run_at,status)
        VALUES (1,'SRV-000001','Service','t','OK')
        """
    )
    connection.execute(
        """
        INSERT INTO plugin_metadata(plugin_oid,slug,version,status)
        VALUES ('PLG-000001','plugin','1','active')
        """
    )
    connection.execute(
        """
        INSERT INTO plugin_services(id,plugin_oid,service_oid)
        VALUES (1,'PLG-000001','SRV-000001')
        """
    )
    connection.execute(
        """
        INSERT INTO relations(id,source_oid,relation_type,target_oid)
        VALUES (1,'SYS-000001','contains','RES-000001')
        """
    )
    connection.execute(
        """
        INSERT INTO resources(resource_oid,path,filename,sha256,imported_at)
        VALUES ('RES-000001','/fixture','fixture','hash','t')
        """
    )
    connection.execute(
        """
        INSERT INTO import_queue(import_id,resource_oid,source_path,filename)
        VALUES (1,'RES-000001','/fixture','fixture')
        """
    )
    connection.execute("UPDATE sqlite_sequence SET seq=50 WHERE name='events'")


def _rows(connection: sqlite3.Connection) -> dict[str, tuple[tuple, ...]]:
    return {
        table: tuple(
            connection.execute(f'SELECT * FROM "{table}" ORDER BY 1')  # noqa: S608
        )
        for table in REBUILT_TABLES
    }


def _dump(database: Path) -> tuple[str, ...]:
    with sqlite3.connect(database) as connection:
        return tuple(connection.iterdump())


def _view_results(connection: sqlite3.Connection) -> dict[str, tuple[tuple, ...]]:
    names = tuple(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
        )
    )
    return {
        name: tuple(
            connection.execute(f'SELECT * FROM "{name}"')  # noqa: S608
        )
        for name in names
    }


def test_migration_six_preserves_data_views_triggers_and_sequences(
    tmp_path: Path,
) -> None:
    database = _version_five_database(tmp_path)
    with sqlite3.connect(database) as connection:
        _seed_references(connection)
        rows_before = _rows(connection)
        views_before = _view_results(connection)
        triggers_before = tuple(
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
            )
        )
        sequences_before = tuple(
            connection.execute("SELECT name,seq FROM sqlite_sequence ORDER BY name")
        )

    assert (
        migrations.migrate(database, target_version=migrations.FOREIGN_KEYS_VERSION)
        == migrations.FOREIGN_KEYS_VERSION
    )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (6,)
        assert _rows(connection) == rows_before
        assert _view_results(connection) == views_before
        assert tuple(
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
            )
        ) == triggers_before
        assert tuple(
            connection.execute("SELECT name,seq FROM sqlite_sequence ORDER BY name")
        ) == sequences_before
        assert tuple(connection.execute("PRAGMA foreign_key_check")) == ()


def test_all_ten_restrictive_foreign_keys_and_negative_writes(
    tmp_path: Path,
) -> None:
    home = tmp_path / "enforced-home"
    database = _version_five_database(tmp_path, "enforced-home")
    with sqlite3.connect(database) as connection:
        _seed_references(connection)
    migrations.migrate(database, target_version=migrations.FOREIGN_KEYS_VERSION)

    with core_database.connect(home=home) as connection:
        declared = set()
        for table in REBUILT_TABLES:
            for row in connection.execute(f'PRAGMA foreign_key_list("{table}")'):
                declared.add((table, row[3], row[2], row[4]))
                assert row[5:7] == ("RESTRICT", "RESTRICT")
        assert declared == EXPECTED_FOREIGN_KEYS

        invalid_statements = (
            "INSERT INTO events(oid,event_at,event_type) VALUES('BAD-000001','t','x')",
            "INSERT INTO events(oid,event_at,event_type,supersedes_event_id) VALUES('SYS-000001','t','x',999)",
            "INSERT INTO service_runs(service_oid,service_name,run_at,status) VALUES('BAD-000001','x','t','x')",
            "INSERT INTO plugin_metadata(plugin_oid,slug,version,status) VALUES('BAD-000001','bad','1','x')",
            "INSERT INTO plugin_services(plugin_oid,service_oid) VALUES('BAD-000001','SRV-000001')",
            "INSERT INTO plugin_services(plugin_oid,service_oid) VALUES('PLG-000001','BAD-000001')",
            "INSERT INTO relations(source_oid,relation_type,target_oid) VALUES('BAD-000001','x','SYS-000001')",
            "INSERT INTO relations(source_oid,relation_type,target_oid) VALUES('SYS-000001','x','BAD-000001')",
            "INSERT INTO resources(resource_oid,path,filename,sha256,imported_at) VALUES('BAD-000001','x','x','bad','t')",
            "INSERT INTO import_queue(resource_oid,source_path,filename) VALUES('BAD-000001','x','x')",
        )
        for statement in invalid_statements:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)
            connection.rollback()


def test_orphan_preflight_rejects_before_ddl_and_preserves_v5(tmp_path: Path) -> None:
    database = _version_five_database(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO relations(source_oid,relation_type,target_oid)
            VALUES ('BAD-ORPHAN','probe','BAD-TARGET')
            """
        )
    before = _dump(database)

    with pytest.raises(MigrationError, match="migration 6 failed"):
        migrations.migrate(database, target_version=migrations.FOREIGN_KEYS_VERSION)

    assert _dump(database) == before


def test_failure_after_drop_rolls_back_schema_data_and_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _version_five_database(tmp_path)
    with sqlite3.connect(database) as connection:
        _seed_references(connection)
    before = _dump(database)
    valid_loader = migrations._migration_sql

    def broken_loader(resource: str) -> str:
        sql = valid_loader(resource)
        if resource == migrations.FOREIGN_KEYS_RESOURCE:
            return sql.replace(
                "DROP TABLE events;",
                "DROP TABLE events;\nSELECT no_such_db002_function();",
            )
        return sql

    monkeypatch.setattr(migrations, "_migration_sql", broken_loader)

    with pytest.raises(MigrationError, match="migration 6 failed"):
        migrations.migrate(database, target_version=migrations.FOREIGN_KEYS_VERSION)

    assert _dump(database) == before


def test_version_six_is_the_default_after_live_cutover(tmp_path: Path) -> None:
    database = _version_five_database(tmp_path)

    assert migrations.CURRENT_SCHEMA_VERSION == migrations.FOREIGN_KEYS_VERSION == 6
    assert migrations.migrate(database) == 6
    assert migrations.migrate(database, target_version=migrations.FOREIGN_KEYS_VERSION) == 6


def test_rebuild_exception_restores_connection_enforcement(tmp_path: Path) -> None:
    database = _version_five_database(tmp_path)

    with core_database.connect_path(database) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        migrations._apply_migration(
            connection,
            target=database,
            version=migrations.FOREIGN_KEYS_VERSION,
            resource=migrations.FOREIGN_KEYS_RESOURCE,
        )
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert tuple(connection.execute("PRAGMA foreign_key_check")) == ()
