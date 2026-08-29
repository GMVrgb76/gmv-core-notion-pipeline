"""Object repository — Core persistence boundary first slice (ADR_CORE_PERSISTENCE_BOUNDARY.md)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gmv_core.repositories.objects import count_objects, get_object, list_objects

NOW = "2026-01-01T00:00:00"


def _database(tmp_path: Path) -> Path:
    database = tmp_path / "GMV.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE objects (
                oid TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        connection.executemany(
            "INSERT INTO objects VALUES (?,?,?,?,?,?)",
            [
                ("SYS-000001", "System", "Fixture System", "active", NOW, NOW),
                ("SRV-000001", "Service", "Fixture Service", "active", NOW, NOW),
                ("PLG-000001", "Plugin", "Fixture Plugin", "active", NOW, NOW),
                ("RES-000001", "Resource", "fixture.txt", "active", NOW, NOW),
            ],
        )
    return database


def test_list_objects_orders_by_type_then_oid(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = list_objects(connection)
    assert rows == [
        ("PLG-000001", "Plugin", "Fixture Plugin", "active"),
        ("RES-000001", "Resource", "fixture.txt", "active"),
        ("SRV-000001", "Service", "Fixture Service", "active"),
        ("SYS-000001", "System", "Fixture System", "active"),
    ]


def test_count_objects_groups_by_type(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = count_objects(connection)
    assert rows == [
        ("Plugin", 1),
        ("Resource", 1),
        ("Service", 1),
        ("System", 1),
    ]


def test_get_object_returns_full_row(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        row = get_object(connection, "SRV-000001")
    assert row == ("SRV-000001", "Service", "Fixture Service", "active", NOW, NOW)


def test_get_object_returns_none_when_missing(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        row = get_object(connection, "SRV-000099")
    assert row is None
