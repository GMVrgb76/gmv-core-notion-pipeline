"""Transaction, rollback, concurrency, and importer tests for OID allocation."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from gmv_core.errors import OIDAllocationError
from gmv_core.migrations import (
    BASELINE_VERSION,
    CURRENT_SCHEMA_VERSION,
    migrate,
)
from gmv_core.repositories.identity import allocate_and_create_object

IMPORT_SERVICE = Path(__file__).resolve().parents[2] / "10_API" / "import_service.py"
NOW = "2026-01-01T00:00:00"


def _allocate(connection: sqlite3.Connection, name: str = "Object") -> str:
    return allocate_and_create_object(
        connection,
        object_type="Resource",
        name=name,
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )


def _committed_allocation(database: Path, name: str) -> str:
    with sqlite3.connect(database, timeout=10) as connection:
        connection.execute("BEGIN IMMEDIATE")
        oid = _allocate(connection, name)
        connection.commit()
        return oid


def test_sequential_allocations_are_monotonic(tmp_path: Path) -> None:
    database = tmp_path / "sequential.db"
    assert migrate(database) == CURRENT_SCHEMA_VERSION

    assert _committed_allocation(database, "One") == "RES-000001"
    assert _committed_allocation(database, "Two") == "RES-000002"


def test_migration_seeds_sequence_above_existing_gaps(tmp_path: Path) -> None:
    database = tmp_path / "gaps.db"
    assert migrate(database, target_version=BASELINE_VERSION) == BASELINE_VERSION
    with sqlite3.connect(database) as connection:
        connection.executemany(
            """
            INSERT INTO objects (oid,type,name,status,created_at,updated_at)
            VALUES (?, 'Resource', ?, 'active', ?, ?)
            """,
            [
                ("RES-000001", "One", NOW, NOW),
                ("RES-000003", "Three", NOW, NOW),
            ],
        )

    assert migrate(database) == CURRENT_SCHEMA_VERSION
    assert _committed_allocation(database, "Four") == "RES-000004"


def test_rollback_candidate_is_not_an_allocated_identity(tmp_path: Path) -> None:
    database = tmp_path / "rollback.db"
    migrate(database)

    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        candidate = _allocate(connection, "Rolled back")
        connection.rollback()

        assert connection.execute(
            "SELECT oid FROM objects WHERE oid=?", (candidate,)
        ).fetchone() is None
        assert connection.execute(
            "SELECT last_value FROM oid_sequences WHERE object_type='Resource'"
        ).fetchone() == (0,)

    assert candidate == "RES-000001"
    assert _committed_allocation(database, "Committed") == "RES-000001"


def test_allocator_requires_caller_transaction(tmp_path: Path) -> None:
    database = tmp_path / "transaction-required.db"
    migrate(database)

    with sqlite3.connect(database) as connection:
        with pytest.raises(OIDAllocationError, match="active transaction"):
            _allocate(connection)


def test_concurrent_allocations_are_unique(tmp_path: Path) -> None:
    database = tmp_path / "concurrent.db"
    migrate(database)

    with ThreadPoolExecutor(max_workers=8) as executor:
        allocated = list(
            executor.map(
                lambda number: _committed_allocation(database, f"Object {number}"),
                range(32),
            )
        )

    assert len(set(allocated)) == 32
    assert sorted(int(oid[4:]) for oid in allocated) == list(range(1, 33))


def test_exhausted_sequence_fails_without_object(tmp_path: Path) -> None:
    database = tmp_path / "exhausted.db"
    migrate(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE oid_sequences SET last_value=999999 WHERE object_type='Resource'"
        )
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(OIDAllocationError, match="exhausted"):
            _allocate(connection)
        connection.rollback()
        assert connection.execute(
            "SELECT COUNT(*) FROM objects WHERE type='Resource'"
        ).fetchone() == (0,)


def test_importer_fails_closed_before_migration(
    isolated_gmv: object,
    tmp_path: Path,
) -> None:
    database = Path(getattr(isolated_gmv, "database"))
    source = tmp_path / "source.txt"
    source.write_text("fixture", encoding="utf-8")
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    result = subprocess.run(
        [sys.executable, str(IMPORT_SERVICE), "file", str(source)],
        env=os.environ.copy(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Import requires schema version 4; found 0" in result.stderr
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_migrated_importer_uses_sequence_transaction(
    isolated_gmv: object,
    tmp_path: Path,
) -> None:
    database = Path(getattr(isolated_gmv, "database"))
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE test_sentinel")
    migrate(database)
    source = tmp_path / "source.txt"
    source.write_text("fixture", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(IMPORT_SERVICE), "file", str(source)],
        env=os.environ.copy(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Imported resource: RES-000001" in result.stdout
    assert result.stderr == ""
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT oid,type FROM objects WHERE oid='RES-000001'"
        ).fetchone() == ("RES-000001", "Resource")
        assert connection.execute(
            "SELECT last_value FROM oid_sequences WHERE object_type='Resource'"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT resource_oid FROM resources"
        ).fetchone() == ("RES-000001",)
        assert connection.execute(
            "SELECT resource_oid FROM import_queue"
        ).fetchone() == ("RES-000001",)
