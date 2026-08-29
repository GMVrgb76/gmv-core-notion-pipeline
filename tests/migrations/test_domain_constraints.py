"""Migration 007: isolated enforcement of four non-queue DB-003 domains."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

import gmv_core.migrations as migrations
from gmv_core.database import connect_path
from gmv_core.errors import MigrationError
from tests.helpers import connect_fixture_database

REBUILT_TABLES = {"objects", "service_runs", "engines", "relations"}


def _version_six_database(tmp_path: Path, name: str = "domain-constraints.db") -> Path:
    database = tmp_path / name
    assert (
        migrations.migrate(
            database,
            target_version=migrations.FOREIGN_KEYS_VERSION,
        )
        == migrations.FOREIGN_KEYS_VERSION
        == 6
    )
    return database


def _dump(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(connection.iterdump())


def _table_rows(connection: sqlite3.Connection) -> dict[str, tuple[tuple, ...]]:
    names = tuple(
        row[0]
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
    )
    return {
        name: tuple(
            connection.execute(f'SELECT * FROM "{name}" ORDER BY rowid')  # noqa: S608
        )
        for name in names
    }


def _view_rows(connection: sqlite3.Connection) -> dict[str, tuple[tuple, ...]]:
    names = tuple(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
        )
    )
    return {
        name: tuple(connection.execute(f'SELECT * FROM "{name}"'))  # noqa: S608
        for name in names
    }


def _dependent_schema(connection: sqlite3.Connection) -> tuple[tuple, ...]:
    return tuple(
        row
        for row in connection.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM sqlite_master
            WHERE type IN ('table', 'view', 'trigger')
            ORDER BY type, name
            """
        )
        if not (row[0] == "table" and row[1] in REBUILT_TABLES)
    )


def _index_signature(connection: sqlite3.Connection) -> tuple[tuple, ...]:
    tables = tuple(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    )
    return tuple(
        (
            table,
            tuple(connection.execute(f'PRAGMA index_list("{table}")')),
        )
        for table in tables
    )


def _foreign_key_signature(connection: sqlite3.Connection) -> tuple[tuple, ...]:
    tables = tuple(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    )
    return tuple(
        (
            table,
            tuple(connection.execute(f'PRAGMA foreign_key_list("{table}")')),
        )
        for table in tables
    )


def _seed_complete_v6_shape(connection: sqlite3.Connection) -> None:
    connection.executemany(
        "INSERT INTO objects(oid,type,name,status) VALUES (?,?,?,?)",
        [
            ("SYS-000001", "System", "System", "system-lifecycle-deferred"),
            ("SRV-000001", "Service", "Service", "service-lifecycle-deferred"),
            ("PLG-000001", "Plugin", "Plugin", "plugin-lifecycle-deferred"),
            ("RES-000001", "Resource", "Resource", "resource-lifecycle-deferred"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO engines(engine_id,name,category,version,status,compatibility_mode)
        VALUES (?,?,?,?,?,?)
        """,
        [
            ("native", "Native", "core", "1", "engine-status-deferred", 0),
            ("compat", "Compat", "legacy", "1", "engine-status-deferred", 1),
        ],
    )
    connection.execute(
        "INSERT INTO events(id,oid,event_at,event_type) VALUES (1,'SYS-000001','t','x')"
    )
    connection.executemany(
        """
        INSERT INTO service_runs(id,service_oid,service_name,run_at,status)
        VALUES (?,?,?,?,?)
        """,
        [
            (1, "SRV-000001", "Service", "t1", "OK"),
            (2, "SRV-000001", "Service", "t2", "ERROR"),
            (3, "SRV-000001", "Service", "t3", "TIMEOUT"),
            (4, "SRV-000001", "Service", "t4", "CANCELLED"),
        ],
    )
    connection.execute(
        """
        INSERT INTO plugin_metadata(plugin_oid,slug,version,status)
        VALUES ('PLG-000001','plugin','1','plugin-status-deferred')
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
        INSERT INTO resources(resource_oid,path,filename,sha256,imported_at,status)
        VALUES ('RES-000001','/fixture','fixture','hash','t','resource-status-deferred')
        """
    )
    connection.execute(
        """
        INSERT INTO import_queue(
            import_id,resource_oid,source_path,filename,status,review_status,confidence
        ) VALUES (
            1,'RES-000001','/fixture','fixture','queue-state-deferred',
            'queue-review-deferred',9.0
        )
        """
    )
    connection.execute(
        """
        INSERT INTO architecture_decisions(id,decision,consequence)
        VALUES (1,'fixture','preserved')
        """
    )
    connection.execute("UPDATE sqlite_sequence SET seq=50 WHERE name='service_runs'")
    connection.execute("UPDATE sqlite_sequence SET seq=40 WHERE name='relations'")


def test_migration_seven_preserves_all_data_and_dependent_schema(
    tmp_path: Path,
) -> None:
    database = _version_six_database(tmp_path)
    with sqlite3.connect(database) as connection:
        _seed_complete_v6_shape(connection)
        rows_before = _table_rows(connection)
        views_before = _view_rows(connection)
        schema_before = _dependent_schema(connection)
        indexes_before = _index_signature(connection)
        foreign_keys_before = _foreign_key_signature(connection)
        sequences_before = tuple(
            connection.execute("SELECT name,seq FROM sqlite_sequence ORDER BY name")
        )

    assert (
        migrations.migrate(
            database, target_version=migrations.DOMAIN_CONSTRAINTS_VERSION
        )
        == migrations.DOMAIN_CONSTRAINTS_VERSION
    )

    with connect_path(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (7,)
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert tuple(connection.execute("PRAGMA foreign_key_check")) == ()
        assert _table_rows(connection) == rows_before
        assert _view_rows(connection) == views_before
        assert _dependent_schema(connection) == schema_before
        assert _index_signature(connection) == indexes_before
        assert _foreign_key_signature(connection) == foreign_keys_before
        assert tuple(
            connection.execute("SELECT name,seq FROM sqlite_sequence ORDER BY name")
        ) == sequences_before


def test_positive_and_negative_writes_for_each_constraint(tmp_path: Path) -> None:
    database = _version_six_database(tmp_path)
    migrations.migrate(database, target_version=migrations.DOMAIN_CONSTRAINTS_VERSION)

    with connect_fixture_database(database) as connection:
        connection.executemany(
            "INSERT INTO objects(oid,type,name) VALUES (?,?,?)",
            [
                ("ZZZ-000001", "Unknown", "Lexically valid"),
                ("SRV-000001", "Service", "Service"),
                ("SYS-000001", "System", "System"),
                ("RES-000001", "Resource", "Resource"),
            ],
        )
        for invalid_oid in (
            "SYS-000000",
            "sys-000001",
            "SY-000001",
            "SYS-00001",
            "SYS_000001",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO objects(oid,type,name) VALUES (?,'System','bad')",
                    (invalid_oid,),
                )

        for status in ("OK", "ERROR", "TIMEOUT", "CANCELLED"):
            connection.execute(
                """
                INSERT INTO service_runs(service_oid,service_name,run_at,status)
                VALUES ('SRV-000001','Service','t',?)
                """,
                (status,),
            )
        for status in ("ok", "FAILED", "active", ""):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO service_runs(service_oid,service_name,run_at,status)
                    VALUES ('SRV-000001','Service','t',?)
                    """,
                    (status,),
                )

        for engine_id, mode in (("native", 0), ("compat", 1)):
            connection.execute(
                """
                INSERT INTO engines(
                    engine_id,name,category,version,status,compatibility_mode
                ) VALUES (?,?,'test','1','status-deferred',?)
                """,
                (engine_id, engine_id, mode),
            )
        for engine_id, mode in (("negative", -1), ("two", 2), ("text", "invalid")):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO engines(
                        engine_id,name,category,version,status,compatibility_mode
                    ) VALUES (?,?,'test','1','status-deferred',?)
                    """,
                    (engine_id, engine_id, mode),
                )

        connection.execute(
            """
            INSERT INTO relations(source_oid,relation_type,target_oid)
            VALUES ('SYS-000001','contains','RES-000001')
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO relations(source_oid,relation_type,target_oid)
                VALUES ('SYS-000001','self','SYS-000001')
                """
            )


InvalidSeed = Callable[[sqlite3.Connection], None]


def _invalid_oid(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO objects(oid,type,name) VALUES ('bad','System','bad')"
    )


def _invalid_service_status(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO objects(oid,type,name) VALUES ('SRV-000001','Service','Service')"
    )
    connection.execute(
        """
        INSERT INTO service_runs(service_oid,service_name,run_at,status)
        VALUES ('SRV-000001','Service','t','FAILED')
        """
    )


def _invalid_compatibility_mode(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO engines(
            engine_id,name,category,version,status,compatibility_mode
        ) VALUES ('bad','Bad','test','1','status-deferred',2)
        """
    )


def _invalid_self_relation(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO objects(oid,type,name) VALUES ('SYS-000001','System','System')"
    )
    connection.execute(
        """
        INSERT INTO relations(source_oid,relation_type,target_oid)
        VALUES ('SYS-000001','self','SYS-000001')
        """
    )


@pytest.mark.parametrize(
    "seed_invalid",
    [
        _invalid_oid,
        _invalid_service_status,
        _invalid_compatibility_mode,
        _invalid_self_relation,
    ],
    ids=("oid", "service-run-status", "compatibility-mode", "self-relation"),
)
def test_preflight_rejects_each_invalid_domain_before_ddl(
    tmp_path: Path,
    seed_invalid: InvalidSeed,
) -> None:
    database = _version_six_database(tmp_path)
    with sqlite3.connect(database) as connection:
        seed_invalid(connection)
        before = _dump(connection)

    with pytest.raises(MigrationError, match="migration 7 failed"):
        migrations.migrate(
            database, target_version=migrations.DOMAIN_CONSTRAINTS_VERSION
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (6,)
        assert _dump(connection) == before


@pytest.mark.parametrize(
    "marker",
    ["DROP TABLE objects;", "PRAGMA user_version = 7;"],
    ids=("after-table-drop", "before-version-commit"),
)
def test_injected_errors_roll_back_schema_data_version_and_enforcement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    marker: str,
) -> None:
    database = _version_six_database(tmp_path)
    valid_loader = migrations._migration_sql

    with connect_fixture_database(database) as connection:
        _seed_complete_v6_shape(connection)
        connection.commit()
        before = _dump(connection)

    with connect_path(database) as connection:
        def broken_loader(resource: str) -> str:
            sql = valid_loader(resource)
            if resource == migrations.DOMAIN_CONSTRAINTS_RESOURCE:
                return sql.replace(
                    marker,
                    f"SELECT no_such_db003_function();\n{marker}",
                    1,
                )
            return sql

        monkeypatch.setattr(migrations, "_migration_sql", broken_loader)

        with pytest.raises(MigrationError, match="migration 7 failed"):
            migrations._apply_migration(
                connection,
                target=database,
                version=migrations.DOMAIN_CONSTRAINTS_VERSION,
                resource=migrations.DOMAIN_CONSTRAINTS_RESOURCE,
            )

        assert connection.execute("PRAGMA user_version").fetchone() == (6,)
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert _dump(connection) == before


def test_version_seven_remains_an_explicit_supported_target(tmp_path: Path) -> None:
    database = tmp_path / "explicit-version-seven.db"

    assert migrations.FOREIGN_KEYS_VERSION == 6
    assert migrations.DOMAIN_CONSTRAINTS_VERSION == 7
    assert migrations.migrate(database, target_version=7) == 7
    assert migrations.migrate(database, target_version=7) == 7


def test_runtime_default_resolution_is_disposable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "runtime-default-v6.db"
    assert migrations.CURRENT_SCHEMA_VERSION == 8

    monkeypatch.setattr(
        migrations,
        "CURRENT_SCHEMA_VERSION",
        migrations.FOREIGN_KEYS_VERSION,
    )

    assert migrations.migrate(database) == 6
    assert migrations.migrate(database) == 6
    with connect_path(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (6,)
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert tuple(connection.execute("PRAGMA foreign_key_check")) == ()
