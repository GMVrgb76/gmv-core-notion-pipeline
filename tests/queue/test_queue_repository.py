"""Import Queue repository — Core persistence boundary seventh slice (ADR_CORE_PERSISTENCE_BOUNDARY.md)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gmv_core.repositories.queue import get_queue_entry, list_queue


def _database(tmp_path: Path) -> Path:
    database = tmp_path / "GMV.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE import_queue (
                import_id INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_oid TEXT,
                source_path TEXT NOT NULL,
                filename TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                review_status TEXT NOT NULL DEFAULT 'pending_review',
                proposed_destination TEXT,
                confidence REAL,
                error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE VIEW import_queue_view AS
            SELECT import_id, resource_oid, filename, status, review_status,
                   proposed_destination, confidence, error, created_at, updated_at
            FROM import_queue
            ORDER BY created_at DESC
            """
        )
        connection.execute(
            "INSERT INTO import_queue VALUES (1,'RES-000001','/f/a.txt','a.txt','pending',"
            "'pending_review',NULL,1.0,NULL,'2026-01-01T00:00:00','2026-01-01T00:00:00')"
        )
        connection.execute(
            "INSERT INTO import_queue VALUES (2,'RES-000002','/f/b.txt','b.txt','complete',"
            "'reviewed','07_IMPORT/b.txt',0.9,NULL,'2026-01-02T00:00:00','2026-01-02T00:00:00')"
        )
    return database


def test_list_queue_orders_by_created_at_desc(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = list_queue(connection)
    assert [row[0] for row in rows] == [2, 1]


def test_list_queue_pending_only_filters_by_status(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = list_queue(connection, pending_only=True)
    assert len(rows) == 1
    assert rows[0][0] == 1
    assert rows[0][3] == "pending"


def test_get_queue_entry_returns_full_row(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        row = get_queue_entry(connection, 1)
    assert row == (
        1,
        "RES-000001",
        "a.txt",
        "pending",
        "pending_review",
        None,
        1.0,
        None,
        "2026-01-01T00:00:00",
        "2026-01-01T00:00:00",
    )


def test_get_queue_entry_returns_none_when_missing(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        row = get_queue_entry(connection, 99)
    assert row is None
