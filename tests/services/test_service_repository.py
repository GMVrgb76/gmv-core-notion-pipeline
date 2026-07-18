"""Service repository — Core persistence boundary second slice (ADR_CORE_PERSISTENCE_BOUNDARY.md)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gmv_core.repositories.services import get_service, list_runs, list_services

NOW = "2026-01-01T00:00:00"
RUN_AT = "2026-01-01T01:00:00"


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
            CREATE TABLE service_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_oid TEXT NOT NULL,
                service_name TEXT NOT NULL,
                run_at TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_seconds REAL,
                command TEXT,
                stdout_path TEXT,
                stderr_path TEXT,
                summary TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE engine_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                engine TEXT NOT NULL,
                run_at TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT,
                duration_seconds REAL,
                command TEXT,
                stdout_path TEXT,
                stderr_path TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE VIEW service_registry_view AS
            SELECT oid AS service_oid, name AS service_name, status, created_at, updated_at
            FROM objects
            WHERE type = 'Service'
            ORDER BY oid
            """
        )
        connection.execute(
            "INSERT INTO objects VALUES ('SRV-000001','Service','Fixture Service','active',?,?)",
            (NOW, NOW),
        )
        connection.execute(
            "INSERT INTO service_runs VALUES (1,'SRV-000001','Fixture Service',?,'OK',1.0,"
            "'fixture','/fixtures/stdout','/fixtures/stderr','Synthetic run')",
            (RUN_AT,),
        )
        connection.execute(
            "INSERT INTO engine_runs VALUES (1,'fixture_engine',?,'OK','Synthetic run',1.0,"
            "'fixture','/fixtures/stdout','/fixtures/stderr')",
            (RUN_AT,),
        )
    return database


def test_list_services_orders_by_oid(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = list_services(connection)
    assert rows == [("SRV-000001", "Fixture Service", "active", NOW, NOW)]


def test_get_service_returns_full_row(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        row = get_service(connection, "SRV-000001")
    assert row == ("SRV-000001", "Fixture Service", "active", NOW, NOW)


def test_get_service_returns_none_when_missing(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        row = get_service(connection, "SRV-000099")
    assert row is None


def test_list_runs_unions_service_and_unmatched_engine_runs(tmp_path: Path) -> None:
    with sqlite3.connect(_database(tmp_path)) as connection:
        rows = list_runs(connection)
    assert rows == [
        ("engine", 1, None, "fixture_engine", RUN_AT, "OK", 1.0),
        ("service", 1, "SRV-000001", "Fixture Service", RUN_AT, "OK", 1.0),
    ]
