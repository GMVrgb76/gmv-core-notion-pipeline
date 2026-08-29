"""Resource repository — Core persistence boundary fifth slice (ADR_CORE_PERSISTENCE_BOUNDARY.md)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gmv_core.repositories.resources import count_resources, get_resource, list_resources

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
            CREATE VIEW resource_view AS
            SELECT r.resource_oid, o.name AS resource_name, o.status AS object_status,
                   r.path, r.filename, r.extension, r.size_bytes, r.sha256,
                   r.imported_at, r.status
            FROM resources r
            LEFT JOIN objects o ON o.oid = r.resource_oid
            """
        )
        connection.execute(
            "INSERT INTO objects VALUES ('RES-000001','Resource','fixture.txt','active',?,?)",
            (NOW, NOW),
        )
        connection.execute(
            "INSERT INTO resources VALUES ('RES-000001','/fixtures/fixture.txt','fixture.txt',"
            "'.txt','text/plain',7,?,?,'active')",
            ("0" * 64, NOW),
        )
    return database


def test_list_resources_orders_by_oid(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = list_resources(connection)
    assert rows == [("RES-000001", "fixture.txt", "/fixtures/fixture.txt", "fixture.txt", "active")]


def test_count_resources_groups_by_status(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = count_resources(connection)
    assert rows == [("active", 1)]


def test_get_resource_returns_full_row(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        row = get_resource(connection, "RES-000001")
    assert row == (
        "RES-000001",
        "fixture.txt",
        "active",
        "/fixtures/fixture.txt",
        "fixture.txt",
        ".txt",
        7,
        "0" * 64,
        NOW,
        "active",
    )


def test_get_resource_returns_none_when_missing(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        row = get_resource(connection, "RES-000099")
    assert row is None
