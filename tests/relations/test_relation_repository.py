"""Relation repository — Core persistence boundary sixth slice (ADR_CORE_PERSISTENCE_BOUNDARY.md)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gmv_core.repositories.relations import count_relations, get_relations, list_relations

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
        connection.execute(
            """
            CREATE TABLE relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_oid TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                target_oid TEXT NOT NULL,
                created_at TEXT,
                source TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE VIEW relation_view AS
            SELECT r.id, r.source_oid, so.name AS source_name, so.type AS source_type,
                   r.relation_type, r.target_oid, target.name AS target_name,
                   target.type AS target_type, r.created_at, r.source
            FROM relations r
            LEFT JOIN objects so ON so.oid = r.source_oid
            LEFT JOIN objects target ON target.oid = r.target_oid
            """
        )
        connection.execute(
            "INSERT INTO objects VALUES ('SYS-000001','System','Fixture System','active',?,?)",
            (NOW, NOW),
        )
        connection.execute(
            "INSERT INTO objects VALUES ('RES-000001','Resource','fixture.txt','active',?,?)",
            (NOW, NOW),
        )
        connection.execute(
            "INSERT INTO relations VALUES (1,'SYS-000001','uses','RES-000001',?,'fixture')",
            (NOW,),
        )
    return database


def test_list_relations_orders_by_source_type_target(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = list_relations(connection)
    assert rows == [("SYS-000001", "Fixture System", "uses", "RES-000001", "fixture.txt")]


def test_count_relations_groups_by_type(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = count_relations(connection)
    assert rows == [("uses", 1)]


def test_get_relations_matches_source_or_target(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        as_source = get_relations(connection, "SYS-000001")
        as_target = get_relations(connection, "RES-000001")
    expected = [("SYS-000001", "Fixture System", "uses", "RES-000001", "fixture.txt")]
    assert as_source == expected
    assert as_target == expected


def test_get_relations_returns_empty_list_when_no_match(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = get_relations(connection, "ZZZ-000001")
    assert rows == []
