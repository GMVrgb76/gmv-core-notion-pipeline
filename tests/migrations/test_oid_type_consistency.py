"""Migration 008: isolated OID prefix/type and typed-reference enforcement."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

import gmv_core.migrations as migrations
from gmv_core.database import connect_path
from gmv_core.errors import MigrationError, OIDValidationError
from gmv_core.identity import PREFIX_TO_TYPE, validate_oid
from gmv_core.repositories.identity import allocate_and_create_object

PAIRS = tuple(PREFIX_TO_TYPE.items())
DB008_TRIGGER_PREFIX = "gmv_"
DB008_TRIGGER_MARKER = "_type_"
HISTORICAL_NON_OIDS = (
    "OBJECT-0000001",
    "ENG-000001",
    "COR-0123456789abcdef0123456789abcdef",
    "RUN-0123456789abcdef0123456789abcdef",
    "LEG-MORNING-BRIEF-001",
)


def _version_seven_database(tmp_path: Path, name: str = "oid-types.db") -> Path:
    database = tmp_path / name
    assert (
        migrations.migrate(
            database,
            target_version=migrations.DOMAIN_CONSTRAINTS_VERSION,
        )
        == migrations.DOMAIN_CONSTRAINTS_VERSION
        == 7
    )
    return database


def _dump(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(connection.iterdump())


def _table_rows(connection: sqlite3.Connection) -> dict[str, tuple[tuple, ...]]:
    tables = tuple(
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
        table: tuple(
            connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid')  # noqa: S608
        )
        for table in tables
    }


def _view_rows(connection: sqlite3.Connection) -> dict[str, tuple[tuple, ...]]:
    views = tuple(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
        )
    )
    return {
        view: tuple(connection.execute(f'SELECT * FROM "{view}"'))  # noqa: S608
        for view in views
    }


def _preserved_schema(connection: sqlite3.Connection) -> tuple[tuple, ...]:
    return tuple(
        row
        for row in connection.execute(
            """
            SELECT type,name,tbl_name,sql
            FROM sqlite_master
            WHERE type IN ('table','view','index','trigger')
            ORDER BY type,name
            """
        )
        if not (row[0] == "table" and row[1] in {"objects", "oid_sequences"})
        and not (
            row[0] == "trigger"
            and str(row[1]).startswith(DB008_TRIGGER_PREFIX)
            and DB008_TRIGGER_MARKER in str(row[1])
        )
    )


def _index_signature(connection: sqlite3.Connection) -> tuple[tuple, ...]:
    tables = tuple(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    )
    return tuple(
        (table, tuple(connection.execute(f'PRAGMA index_list("{table}")')))
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
        (table, tuple(connection.execute(f'PRAGMA foreign_key_list("{table}")')))
        for table in tables
    )


def _seed_all_pairs(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    for _prefix, object_type in PAIRS:
        allocated = allocate_and_create_object(
            connection,
            object_type=object_type,
            name=object_type,
            status="active",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
        )
        assert allocated == f"{next(p for p, t in PAIRS if t == object_type)}-000001"
    connection.commit()


def _seed_complete_v7(connection: sqlite3.Connection) -> None:
    _seed_all_pairs(connection)
    connection.execute(
        "INSERT INTO events(id,oid,event_at,event_type) VALUES (1,'SYS-000001','t','x')"
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
    connection.execute(
        """
        INSERT INTO architecture_decisions(id,decision,consequence)
        VALUES (1,'fixture','preserved')
        """
    )
    connection.execute("UPDATE sqlite_sequence SET seq=50 WHERE name='service_runs'")
    connection.execute("UPDATE sqlite_sequence SET seq=40 WHERE name='relations'")
    connection.commit()


def test_migration_eight_preserves_data_schema_views_indexes_fks_and_sequences(
    tmp_path: Path,
) -> None:
    database = _version_seven_database(tmp_path)
    with sqlite3.connect(database) as connection:
        _seed_complete_v7(connection)
        rows_before = _table_rows(connection)
        views_before = _view_rows(connection)
        schema_before = _preserved_schema(connection)
        indexes_before = _index_signature(connection)
        foreign_keys_before = _foreign_key_signature(connection)
        sequences_before = tuple(
            connection.execute("SELECT name,seq FROM sqlite_sequence ORDER BY name")
        )
        oid_sequences_before = tuple(
            connection.execute(
                "SELECT object_type,prefix,last_value FROM oid_sequences ORDER BY prefix"
            )
        )

    assert (
        migrations.migrate(
            database,
            target_version=migrations.OID_TYPE_CONSISTENCY_VERSION,
        )
        == migrations.OID_TYPE_CONSISTENCY_VERSION
        == 8
    )

    with connect_path(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (8,)
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert tuple(connection.execute("PRAGMA foreign_key_check")) == ()
        assert _table_rows(connection) == rows_before
        assert _view_rows(connection) == views_before
        assert _preserved_schema(connection) == schema_before
        assert _index_signature(connection) == indexes_before
        assert _foreign_key_signature(connection) == foreign_keys_before
        assert tuple(
            connection.execute("SELECT name,seq FROM sqlite_sequence ORDER BY name")
        ) == sequences_before
        assert tuple(
            connection.execute(
                "SELECT object_type,prefix,last_value FROM oid_sequences ORDER BY prefix"
            )
        ) == oid_sequences_before
        triggers = tuple(
            row[0]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='trigger' AND name LIKE 'gmv_%_type_%'
                ORDER BY name
                """
            )
        )
        assert len(triggers) == 12


def test_all_six_pairs_are_accepted_and_every_mismatch_is_rejected(
    tmp_path: Path,
) -> None:
    database = _version_seven_database(tmp_path)
    migrations.migrate(database, target_version=migrations.OID_TYPE_CONSISTENCY_VERSION)

    types = tuple(PREFIX_TO_TYPE.values())
    with connect_path(database) as connection:
        for prefix, object_type in PAIRS:
            connection.execute(
                "INSERT INTO objects(oid,type,name) VALUES (?,?,?)",
                (f"{prefix}-000001", object_type, object_type),
            )
        for index, (prefix, object_type) in enumerate(PAIRS):
            wrong_type = types[(types.index(object_type) + 1) % len(types)]
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO objects(oid,type,name) VALUES (?,?,?)",
                    (f"{prefix}-{index + 2:06d}", wrong_type, "mismatch"),
                )


@pytest.mark.parametrize("value", HISTORICAL_NON_OIDS)
def test_historical_and_operational_identifiers_are_not_object_oids(
    tmp_path: Path,
    value: str,
) -> None:
    with pytest.raises(OIDValidationError):
        validate_oid(value)

    database = _version_seven_database(tmp_path, f"excluded-{value[:3]}.db")
    migrations.migrate(database, target_version=migrations.OID_TYPE_CONSISTENCY_VERSION)
    with connect_path(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO objects(oid,type,name) VALUES (?,'Core','excluded')",
                (value,),
            )


def test_all_six_typed_reference_classes_accept_valid_and_reject_wrong_types(
    tmp_path: Path,
) -> None:
    database = _version_seven_database(tmp_path)
    migrations.migrate(database, target_version=migrations.OID_TYPE_CONSISTENCY_VERSION)

    with connect_path(database) as connection:
        _seed_all_pairs(connection)
        connection.execute(
            """
            INSERT INTO resources(resource_oid,path,filename,sha256,imported_at)
            VALUES ('RES-000001','/valid','valid','valid-hash','t')
            """
        )
        connection.execute(
            """
            INSERT INTO plugin_metadata(plugin_oid,slug,version,status)
            VALUES ('PLG-000001','valid','1','active')
            """
        )
        connection.execute(
            """
            INSERT INTO plugin_services(plugin_oid,service_oid)
            VALUES ('PLG-000001','SRV-000001')
            """
        )
        connection.execute(
            """
            INSERT INTO service_runs(service_oid,service_name,run_at,status)
            VALUES ('SRV-000001','Service','t','OK')
            """
        )
        connection.execute(
            """
            INSERT INTO import_queue(resource_oid,source_path,filename)
            VALUES ('RES-000001','/valid','valid')
            """
        )
        connection.execute(
            """
            INSERT INTO import_queue(resource_oid,source_path,filename)
            VALUES (NULL,'/pending','pending')
            """
        )

        invalid_inserts = (
            "INSERT INTO resources(resource_oid,path,filename,sha256,imported_at) VALUES ('SYS-000001','/bad','bad','bad-resource','t')",
            "INSERT INTO plugin_metadata(plugin_oid,slug,version,status) VALUES ('SYS-000001','bad-plugin','1','active')",
            "INSERT INTO plugin_services(plugin_oid,service_oid) VALUES ('SYS-000001','SRV-000001')",
            "INSERT INTO plugin_services(plugin_oid,service_oid) VALUES ('PLG-000001','SYS-000001')",
            "INSERT INTO service_runs(service_oid,service_name,run_at,status) VALUES ('SYS-000001','bad','t','OK')",
            "INSERT INTO import_queue(resource_oid,source_path,filename) VALUES ('SYS-000001','/bad','bad')",
        )
        for statement in invalid_inserts:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)

        invalid_updates = (
            "UPDATE resources SET resource_oid='SYS-000001' WHERE resource_oid='RES-000001'",
            "UPDATE plugin_metadata SET plugin_oid='SYS-000001' WHERE plugin_oid='PLG-000001'",
            "UPDATE plugin_services SET plugin_oid='SYS-000001' WHERE plugin_oid='PLG-000001'",
            "UPDATE plugin_services SET service_oid='SYS-000001' WHERE service_oid='SRV-000001'",
            "UPDATE service_runs SET service_oid='SYS-000001' WHERE service_oid='SRV-000001'",
            "UPDATE import_queue SET resource_oid='SYS-000001' WHERE resource_oid='RES-000001'",
        )
        for statement in invalid_updates:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)


def _invalid_object_pair(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO objects(oid,type,name) VALUES ('ENG-000001','Service','legacy')"
    )


def _invalid_resources_reference(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO resources(resource_oid,path,filename,sha256,imported_at)
        VALUES ('SYS-000001','/bad','bad','bad-resource','t')
        """
    )


def _invalid_plugin_metadata_reference(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO plugin_metadata(plugin_oid,slug,version,status)
        VALUES ('SYS-000001','bad-plugin','1','active')
        """
    )


def _invalid_plugin_services_plugin_reference(connection: sqlite3.Connection) -> None:
    _invalid_plugin_metadata_reference(connection)
    connection.execute(
        """
        INSERT INTO plugin_services(plugin_oid,service_oid)
        VALUES ('SYS-000001','SRV-000001')
        """
    )


def _invalid_plugin_services_service_reference(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO plugin_metadata(plugin_oid,slug,version,status)
        VALUES ('PLG-000001','valid-plugin','1','active')
        """
    )
    connection.execute(
        """
        INSERT INTO plugin_services(plugin_oid,service_oid)
        VALUES ('PLG-000001','SYS-000001')
        """
    )


def _invalid_service_runs_reference(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO service_runs(service_oid,service_name,run_at,status)
        VALUES ('SYS-000001','bad','t','OK')
        """
    )


def _invalid_import_queue_reference(connection: sqlite3.Connection) -> None:
    _invalid_resources_reference(connection)
    connection.execute(
        """
        INSERT INTO import_queue(resource_oid,source_path,filename)
        VALUES ('SYS-000001','/bad','bad')
        """
    )


InvalidSeed = Callable[[sqlite3.Connection], None]


@pytest.mark.parametrize(
    "seed_invalid",
    (
        _invalid_object_pair,
        _invalid_resources_reference,
        _invalid_plugin_metadata_reference,
        _invalid_plugin_services_plugin_reference,
        _invalid_plugin_services_service_reference,
        _invalid_service_runs_reference,
        _invalid_import_queue_reference,
    ),
    ids=(
        "object-pair",
        "resource",
        "plugin-metadata",
        "plugin-services-plugin",
        "plugin-services-service",
        "service-run",
        "import-queue",
    ),
)
def test_preflight_rejects_invalid_pairs_and_each_typed_reference_before_ddl(
    tmp_path: Path,
    seed_invalid: InvalidSeed,
) -> None:
    database = _version_seven_database(tmp_path)
    with sqlite3.connect(database) as connection:
        if seed_invalid is _invalid_object_pair:
            seed_invalid(connection)
        else:
            _seed_all_pairs(connection)
            seed_invalid(connection)
        before = _dump(connection)

    with pytest.raises(MigrationError, match="migration 8 failed"):
        migrations.migrate(
            database,
            target_version=migrations.OID_TYPE_CONSISTENCY_VERSION,
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (7,)
        assert _dump(connection) == before


@pytest.mark.parametrize("fault", ("missing-map-row", "sequence-lag"))
def test_preflight_rejects_sequence_map_or_position_divergence(
    tmp_path: Path,
    fault: str,
) -> None:
    database = _version_seven_database(tmp_path)
    with sqlite3.connect(database) as connection:
        _seed_all_pairs(connection)
        if fault == "missing-map-row":
            connection.execute("DELETE FROM oid_sequences WHERE object_type='Core'")
        else:
            connection.execute(
                "UPDATE oid_sequences SET last_value=0 WHERE object_type='Core'"
            )
        connection.commit()
        before = _dump(connection)

    with pytest.raises(MigrationError, match="migration 8 failed"):
        migrations.migrate(
            database,
            target_version=migrations.OID_TYPE_CONSISTENCY_VERSION,
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (7,)
        assert _dump(connection) == before


def test_sequence_table_rejects_new_noncanonical_mapping(tmp_path: Path) -> None:
    database = _version_seven_database(tmp_path)
    migrations.migrate(database, target_version=migrations.OID_TYPE_CONSISTENCY_VERSION)

    with connect_path(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO oid_sequences(object_type,prefix,last_value)
                VALUES ('Engine','ENG',0)
                """
            )


def test_preflight_rejects_existing_foreign_key_violation(tmp_path: Path) -> None:
    database = _version_seven_database(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO events(oid,event_at,event_type) VALUES ('SYS-999999','t','bad')"
        )
        before = _dump(connection)

    with pytest.raises(MigrationError, match="migration 8 failed"):
        migrations.migrate(
            database,
            target_version=migrations.OID_TYPE_CONSISTENCY_VERSION,
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (7,)
        assert _dump(connection) == before


@pytest.mark.parametrize(
    "marker",
    ("DROP TABLE objects;", "PRAGMA user_version = 8;"),
    ids=("after-table-drop", "before-version-commit"),
)
def test_fault_injection_rolls_back_schema_data_version_and_enforcement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    marker: str,
) -> None:
    database = _version_seven_database(tmp_path)
    valid_loader = migrations._migration_sql

    with connect_path(database) as connection:
        _seed_complete_v7(connection)
        before = _dump(connection)

        def broken_loader(resource: str) -> str:
            sql = valid_loader(resource)
            if resource == migrations.OID_TYPE_CONSISTENCY_RESOURCE:
                return sql.replace(
                    marker,
                    f"SELECT no_such_db008_function();\n{marker}",
                    1,
                )
            return sql

        monkeypatch.setattr(migrations, "_migration_sql", broken_loader)

        with pytest.raises(MigrationError, match="migration 8 failed"):
            migrations._apply_migration(
                connection,
                target=database,
                version=migrations.OID_TYPE_CONSISTENCY_VERSION,
                resource=migrations.OID_TYPE_CONSISTENCY_RESOURCE,
            )

        assert connection.execute("PRAGMA user_version").fetchone() == (7,)
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert _dump(connection) == before


def test_version_eight_is_explicit_and_default_remains_v7(tmp_path: Path) -> None:
    default_database = tmp_path / "default-v7.db"
    explicit_database = tmp_path / "explicit-v8.db"

    assert migrations.CURRENT_SCHEMA_VERSION == migrations.DOMAIN_CONSTRAINTS_VERSION == 7
    assert migrations.OID_TYPE_CONSISTENCY_VERSION == 8
    assert migrations.migrate(default_database) == 7
    assert migrations.migrate(explicit_database, target_version=8) == 8
    assert migrations.migrate(explicit_database, target_version=8) == 8
