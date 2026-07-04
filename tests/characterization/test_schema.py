"""Characterize the current pre-migration SQLite schema and data shape."""

from __future__ import annotations

import sqlite3
from pathlib import Path

EXPECTED_TABLES = {
    "architecture_decisions",
    "engine_runs",
    "engines",
    "events",
    "import_queue",
    "objects",
    "plugin_metadata",
    "plugin_services",
    "relations",
    "resources",
    "service_runs",
    "sqlite_sequence",
    "timeline",
}

EXPECTED_VIEWS = {
    "import_queue_view",
    "plugin_registry_view",
    "plugin_services_view",
    "relation_view",
    "resource_view",
    "service_registry_view",
    "timeline_view",
}

EXPECTED_INDEXES = {
    "sqlite_autoindex_engines_1",
    "sqlite_autoindex_objects_1",
    "sqlite_autoindex_plugin_metadata_1",
    "sqlite_autoindex_plugin_metadata_2",
    "sqlite_autoindex_plugin_services_1",
    "sqlite_autoindex_relations_1",
    "sqlite_autoindex_resources_1",
    "sqlite_autoindex_resources_2",
}

EXPECTED_COLUMNS = {
    "objects": ("oid", "type", "name", "status", "created_at", "updated_at"),
    "engine_runs": (
        "id",
        "engine",
        "run_at",
        "status",
        "summary",
        "duration_seconds",
        "command",
        "stdout_path",
        "stderr_path",
    ),
    "events": ("id", "oid", "event_at", "event_type", "description", "source"),
    "relations": (
        "id",
        "source_oid",
        "relation_type",
        "target_oid",
        "created_at",
        "source",
    ),
    "resources": (
        "resource_oid",
        "path",
        "filename",
        "extension",
        "mime_guess",
        "size_bytes",
        "sha256",
        "imported_at",
        "status",
    ),
    "import_queue": (
        "import_id",
        "resource_oid",
        "source_path",
        "filename",
        "status",
        "review_status",
        "proposed_destination",
        "confidence",
        "error",
        "created_at",
        "updated_at",
    ),
}


def _object_names(connection: sqlite3.Connection, object_type: str) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ?",
        (object_type,),
    )
    return {str(row[0]) for row in rows}


def test_current_schema_inventory(characterized_database: Path) -> None:
    with sqlite3.connect(characterized_database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (0,)
        assert _object_names(connection, "table") == EXPECTED_TABLES
        assert _object_names(connection, "view") == EXPECTED_VIEWS
        assert _object_names(connection, "index") == EXPECTED_INDEXES


def test_current_key_columns(characterized_database: Path) -> None:
    with sqlite3.connect(characterized_database) as connection:
        for table, expected_columns in EXPECTED_COLUMNS.items():
            columns = tuple(
                str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
            )
            assert columns == expected_columns


def test_synthetic_data_exercises_current_views(characterized_database: Path) -> None:
    with sqlite3.connect(characterized_database) as connection:
        resource = connection.execute(
            "SELECT resource_oid, resource_name, filename, status FROM resource_view"
        ).fetchone()
        relation = connection.execute(
            "SELECT source_oid, relation_type, target_oid FROM relation_view"
        ).fetchone()
        queue = connection.execute(
            "SELECT resource_oid, status, review_status FROM import_queue_view"
        ).fetchone()

    assert resource == ("RES-000001", "fixture.txt", "fixture.txt", "active")
    assert relation == ("SYS-000001", "uses", "RES-000001")
    assert queue == ("RES-000001", "pending", "pending_review")
