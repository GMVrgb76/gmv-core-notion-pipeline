"""Migration 010: entities/entity_aliases, available but not current.

Mirrors the design of 009_crawler_source_registry.sql: the crawler
subsystem that owns these tables does not exist yet, so this migration
must be reachable only via an explicit target_version, never changing
behavior for a caller of migrate(db) that does not ask for it by name.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import gmv_core.migrations as migrations
from gmv_core.database import connect_path
from tests.helpers import connect_fixture_database

ONTOLOGY_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_v0.1.json"
)


def _version_nine_database(tmp_path: Path, name: str = "entity-registry.db") -> Path:
    database = tmp_path / name
    assert (
        migrations.migrate(database, target_version=migrations.CRAWLER_SOURCE_REGISTRY_VERSION)
        == migrations.CRAWLER_SOURCE_REGISTRY_VERSION
        == 9
    )
    return database


def _dump(connection: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(connection.iterdump())


def test_entity_registry_version_is_not_current_or_supported() -> None:
    assert migrations.ENTITY_REGISTRY_VERSION == 10
    assert migrations.CURRENT_SCHEMA_VERSION == migrations.OID_TYPE_CONSISTENCY_VERSION == 8
    assert migrations.ENTITY_REGISTRY_VERSION not in migrations.SUPPORTED_SCHEMA_VERSIONS


def test_default_migrate_still_stops_at_eight(tmp_path: Path) -> None:
    database = tmp_path / "default.db"
    assert migrations.migrate(database) == 8

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "entities" not in tables
    assert "entity_aliases" not in tables


def test_explicit_target_ten_creates_tables_with_expected_shape(tmp_path: Path) -> None:
    database = _version_nine_database(tmp_path)
    assert migrations.migrate(database, target_version=migrations.ENTITY_REGISTRY_VERSION) == 10

    with connect_fixture_database(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (10,)
        entity_columns = {row[1] for row in connection.execute("PRAGMA table_info(entities)")}
        assert entity_columns == {
            "gmv_id", "entity_type", "canonical_name", "status", "merged_into", "created_at",
        }
        alias_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(entity_aliases)")
        }
        assert alias_columns == {"id", "entity_gmv_id", "alias", "added_at"}

        entity_fks = tuple(connection.execute("PRAGMA foreign_key_list(entities)"))
        assert len(entity_fks) == 1
        assert entity_fks[0][2] == "entities"  # self-referencing merged_into

        alias_fks = tuple(connection.execute("PRAGMA foreign_key_list(entity_aliases)"))
        assert len(alias_fks) == 1
        assert alias_fks[0][2] == "entities"  # table
        assert alias_fks[0][3] == "entity_gmv_id"  # from (local column)
        assert alias_fks[0][4] == "gmv_id"  # to (referenced column)


def test_entity_type_check_matches_ontology_registry_non_deprecated_classes(
    tmp_path: Path,
) -> None:
    """Cross-checks the migration's entity_type CHECK against the real,
    committed 00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json instead of a
    second hardcoded copy, so the two files cannot silently drift apart
    -- the exact class of bug an earlier review found in a different
    contract on this branch (a vocabulary claimed to match a real source
    that, on inspection, did not).

    Filters on status in {CORE, DOMAIN} specifically, not "not
    DEPRECATED": an earlier version of this test (and of the migration's
    CHECK) used the weaker "not DEPRECATED" filter, which silently let
    CANDIDATE-status classes (SPONSOR, CONTRACT) through -- exactly the
    silent CANDIDATE-to-canonical promotion the registry's own governance
    rule forbids. Caught by review; fixed in both files together."""
    registry = json.loads(ONTOLOGY_REGISTRY_PATH.read_text(encoding="utf-8"))
    governed = {
        entry["class_id"]
        for entry in registry["entity_classes"]
        if entry["status"] in ("CORE", "DOMAIN")
    }
    assert "ARTWORK" not in governed  # DEPRECATED, sanity check
    assert "SPONSOR" not in governed  # CANDIDATE, sanity check
    assert "CONTRACT" not in governed  # CANDIDATE, sanity check

    database = _version_nine_database(tmp_path)
    migrations.migrate(database, target_version=migrations.ENTITY_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        for entity_type in governed:
            connection.execute(
                "INSERT INTO entities (gmv_id, entity_type, canonical_name, created_at) "
                "VALUES (?, ?, 'fixture', 't')",
                (f"GMV-{entity_type}", entity_type),
            )
        connection.execute("DELETE FROM entities")

        for rejected_type in ("ARTWORK", "SPONSOR", "CONTRACT"):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO entities (gmv_id, entity_type, canonical_name, created_at) "
                    "VALUES ('GMV-x', ?, 'fixture', 't')",
                    (rejected_type,),
                )


def test_gmv_id_check_rejects_malformed_values(tmp_path: Path) -> None:
    database = _version_nine_database(tmp_path)
    migrations.migrate(database, target_version=migrations.ENTITY_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        for bad_id in ("", "GMV-", "not-a-gmv-id", "gmv-lowercase"):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO entities (gmv_id, entity_type, canonical_name, created_at) "
                    "VALUES (?, 'PERSON', 'fixture', 't')",
                    (bad_id,),
                )

        connection.execute(
            "INSERT INTO entities (gmv_id, entity_type, canonical_name, created_at) "
            "VALUES ('GMV-000001', 'PERSON', 'fixture', 't')"
        )


def test_status_check_rejects_unknown_values(tmp_path: Path) -> None:
    database = _version_nine_database(tmp_path)
    migrations.migrate(database, target_version=migrations.ENTITY_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO entities (gmv_id, entity_type, canonical_name, status, created_at) "
                "VALUES ('GMV-000001', 'PERSON', 'fixture', 'DELETED', 't')"
            )


def test_merged_into_required_exactly_when_status_merged_on_insert(tmp_path: Path) -> None:
    database = _version_nine_database(tmp_path)
    migrations.migrate(database, target_version=migrations.ENTITY_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        # MERGED without merged_into: rejected.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO entities (gmv_id, entity_type, canonical_name, status, created_at) "
                "VALUES ('GMV-000001', 'PERSON', 'fixture', 'MERGED', 't')"
            )
        # ACTIVE with a merged_into set: rejected -- must not carry a
        # dangling pointer.
        connection.execute(
            "INSERT INTO entities (gmv_id, entity_type, canonical_name, created_at) "
            "VALUES ('GMV-000002', 'PERSON', 'survivor', 't')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO entities "
                "(gmv_id, entity_type, canonical_name, status, merged_into, created_at) "
                "VALUES ('GMV-000003', 'PERSON', 'fixture', 'ACTIVE', 'GMV-000002', 't')"
            )
        # MERGED with merged_into pointing at a real entity: accepted.
        connection.execute(
            "INSERT INTO entities "
            "(gmv_id, entity_type, canonical_name, status, merged_into, created_at) "
            "VALUES ('GMV-000004', 'PERSON', 'duplicate', 'MERGED', 'GMV-000002', 't')"
        )


def test_merged_into_required_exactly_when_status_merged_on_update(tmp_path: Path) -> None:
    database = _version_nine_database(tmp_path)
    migrations.migrate(database, target_version=migrations.ENTITY_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        connection.execute(
            "INSERT INTO entities (gmv_id, entity_type, canonical_name, created_at) "
            "VALUES ('GMV-000001', 'PERSON', 'survivor', 't')"
        )
        connection.execute(
            "INSERT INTO entities (gmv_id, entity_type, canonical_name, created_at) "
            "VALUES ('GMV-000002', 'PERSON', 'duplicate', 't')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE entities SET status='MERGED' WHERE gmv_id='GMV-000002'"
            )

        # Setting status and merged_into together is accepted.
        connection.execute(
            "UPDATE entities SET status='MERGED', merged_into='GMV-000001' "
            "WHERE gmv_id='GMV-000002'"
        )

        # Clearing merged_into while still MERGED (touching only that
        # column) must still be caught -- same class of gap review found
        # in migration 009's first draft.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE entities SET merged_into=NULL WHERE gmv_id='GMV-000002'"
            )


def test_merged_into_cannot_reference_self(tmp_path: Path) -> None:
    database = _version_nine_database(tmp_path)
    migrations.migrate(database, target_version=migrations.ENTITY_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO entities "
                "(gmv_id, entity_type, canonical_name, status, merged_into, created_at) "
                "VALUES ('GMV-000001', 'PERSON', 'fixture', 'MERGED', 'GMV-000001', 't')"
            )

        connection.execute(
            "INSERT INTO entities (gmv_id, entity_type, canonical_name, status, created_at) "
            "VALUES ('GMV-000002', 'PERSON', 'fixture', 'ACTIVE', 't')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE entities SET status='MERGED', merged_into='GMV-000002' "
                "WHERE gmv_id='GMV-000002'"
            )


def test_merged_into_must_reference_an_existing_entity(tmp_path: Path) -> None:
    database = _version_nine_database(tmp_path)
    migrations.migrate(database, target_version=migrations.ENTITY_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO entities "
                "(gmv_id, entity_type, canonical_name, status, merged_into, created_at) "
                "VALUES ('GMV-000001', 'PERSON', 'fixture', 'MERGED', 'GMV-999999', 't')"
            )


def test_merged_into_rejects_indirect_cycles_and_chains(tmp_path: Path) -> None:
    """Regression guard for a real gap review found: the self-reference
    guard (merged_into != gmv_id) only covers depth 1. Without this,
    A merged_into B followed by B merged_into A was accepted outright --
    both rows MERGED, no ACTIVE survivor, a resolver would loop forever.
    merged_into may only point at an entity that is not itself already
    MERGED, which rejects both 2-cycles and longer chains in one rule."""
    database = _version_nine_database(tmp_path)
    migrations.migrate(database, target_version=migrations.ENTITY_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        connection.execute(
            "INSERT INTO entities (gmv_id, entity_type, canonical_name, created_at) "
            "VALUES ('GMV-A', 'PERSON', 'fixture-a', 't')"
        )
        connection.execute(
            "INSERT INTO entities (gmv_id, entity_type, canonical_name, created_at) "
            "VALUES ('GMV-B', 'PERSON', 'fixture-b', 't')"
        )
        # A merged_into B: fine, B is still ACTIVE.
        connection.execute(
            "UPDATE entities SET status='MERGED', merged_into='GMV-B' WHERE gmv_id='GMV-A'"
        )
        # B merged_into A: A is now MERGED -- rejected, closing the cycle
        # the earlier schema left open.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE entities SET status='MERGED', merged_into='GMV-A' WHERE gmv_id='GMV-B'"
            )

        # Chain case: C merged_into A is rejected too, since A is MERGED.
        connection.execute(
            "INSERT INTO entities (gmv_id, entity_type, canonical_name, created_at) "
            "VALUES ('GMV-C', 'PERSON', 'fixture-c', 't')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE entities SET status='MERGED', merged_into='GMV-A' WHERE gmv_id='GMV-C'"
            )
        # But C merged_into B (still ACTIVE) is fine.
        connection.execute(
            "UPDATE entities SET status='MERGED', merged_into='GMV-B' WHERE gmv_id='GMV-C'"
        )


def test_entity_aliases_require_a_real_entity_and_reject_duplicates(tmp_path: Path) -> None:
    database = _version_nine_database(tmp_path)
    migrations.migrate(database, target_version=migrations.ENTITY_REGISTRY_VERSION)

    with connect_fixture_database(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO entity_aliases (entity_gmv_id, alias, added_at) "
                "VALUES ('GMV-999999', 'Alias', 't')"
            )

        connection.execute(
            "INSERT INTO entities (gmv_id, entity_type, canonical_name, created_at) "
            "VALUES ('GMV-000001', 'ARTIST', 'Federico Garibaldi', 't')"
        )
        connection.execute(
            "INSERT INTO entity_aliases (entity_gmv_id, alias, added_at) "
            "VALUES ('GMV-000001', 'F. Garibaldi', 't')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO entity_aliases (entity_gmv_id, alias, added_at) "
                "VALUES ('GMV-000001', 'F. Garibaldi', 't')"
            )


def test_migrating_to_ten_twice_is_idempotent(tmp_path: Path) -> None:
    database = _version_nine_database(tmp_path)
    assert migrations.migrate(database, target_version=migrations.ENTITY_REGISTRY_VERSION) == 10
    assert migrations.migrate(database, target_version=migrations.ENTITY_REGISTRY_VERSION) == 10


def test_fault_injection_rolls_back_schema_data_version_and_enforcement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _version_nine_database(tmp_path)
    valid_loader = migrations._migration_sql

    with connect_fixture_database(database) as connection:
        before = _dump(connection)

    with connect_path(database) as connection:
        def broken_loader(resource: str) -> str:
            sql = valid_loader(resource)
            if resource == migrations.ENTITY_REGISTRY_RESOURCE:
                return sql.replace(
                    "PRAGMA user_version = 10;",
                    "SELECT no_such_db010_function();\nPRAGMA user_version = 10;",
                    1,
                )
            return sql

        monkeypatch.setattr(migrations, "_migration_sql", broken_loader)

        with pytest.raises(migrations.MigrationError, match="migration 10 failed"):
            migrations._apply_migration(
                connection,
                target=database,
                version=migrations.ENTITY_REGISTRY_VERSION,
                resource=migrations.ENTITY_REGISTRY_RESOURCE,
            )

        assert connection.execute("PRAGMA user_version").fetchone() == (9,)
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert _dump(connection) == before
