"""Search repository — Core persistence boundary fourth slice (ADR_CORE_PERSISTENCE_BOUNDARY.md)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gmv_core.repositories.search import search

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
            CREATE TABLE resources (
                resource_oid TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                filename TEXT NOT NULL,
                extension TEXT,
                mime_guess TEXT,
                size_bytes INTEGER,
                sha256 TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                status TEXT DEFAULT 'active'
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                oid TEXT NOT NULL,
                event_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                description TEXT,
                source TEXT
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
            "INSERT INTO objects VALUES ('SYS-000001','System','Fixture System','active',?,?)",
            (NOW, NOW),
        )
        connection.execute(
            "INSERT INTO resources VALUES ('RES-000001','/fixtures/fixture.txt','fixture.txt',"
            "'.txt','text/plain',7,?,?,'active')",
            ("0" * 64, NOW),
        )
        connection.execute(
            "INSERT INTO events VALUES (1,'SYS-000001',?,'fixture_event','Synthetic event','fixture')",
            (NOW,),
        )
        connection.execute(
            "INSERT INTO relations VALUES (1,'SYS-000001','uses','RES-000001',?,'fixture')",
            (NOW,),
        )
    return database


def test_search_matches_object_by_name(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = search(connection, "fixture")
    assert ("object", "SYS-000001", "Fixture System", "name:Fixture System") in rows
    assert ("resource", "RES-000001", "fixture.txt", "filename:fixture.txt") in rows


def test_search_matches_event_description(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = search(connection, "synthetic")
    assert rows == [("event", "1", "fixture_event", "description:Synthetic event")]


def test_search_matches_relation_type(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = search(connection, "uses")
    assert rows == [("relation", "1", "SYS-000001->RES-000001", "relation_type:uses")]


def test_search_returns_empty_list_when_no_match(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = search(connection, "nomatchxyz")
    assert rows == []
