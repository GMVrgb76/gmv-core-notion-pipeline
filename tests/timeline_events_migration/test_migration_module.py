"""gmv_core.timeline_events_migration -- pure module tests, no CLI, no live database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gmv_core.timeline_events_migration import (
    apply_migration,
    plan_migration,
    reconcile_evidence,
)

NOW = "2026-01-01T00:00:00"


def _database(tmp_path: Path) -> Path:
    database = tmp_path / "GMV.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE timeline (
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
    return database


_INSERT_TIMELINE = (
    "INSERT INTO timeline (oid,event_at,event_type,description,source) VALUES (?,?,?,?,?)"
)
_INSERT_EVENTS = (
    "INSERT INTO events (oid,event_at,event_type,description,source) VALUES (?,?,?,?,?)"
)


def _insert(database: Path, table: str, rows: list[tuple]) -> None:
    statement = _INSERT_TIMELINE if table == "timeline" else _INSERT_EVENTS
    with sqlite3.connect(database) as connection:
        connection.executemany(statement, rows)


def test_plan_migration_classifies_identical_collision_and_timeline_only(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    # Identical: same content in both (already reconciled).
    _insert(database, "timeline", [("SYS-000001", NOW, "a", "same", "src")])
    _insert(database, "events", [("SYS-000001", NOW, "a", "same", "src")])
    # Collision-shape: timeline id will differ from any events id, but the
    # *content* itself has no counterpart in events -- from a content-match
    # perspective this is identical in kind to a plain timeline-only row.
    _insert(database, "timeline", [("SYS-000001", NOW, "b", "collision-content", "src")])
    # Timeline-only: no events counterpart at all.
    _insert(database, "timeline", [("SYS-000001", NOW, "c", "timeline-only", "src")])

    with sqlite3.connect(database) as connection:
        pending = plan_migration(connection)

    descriptions = {row[4] for row in pending}
    assert descriptions == {"collision-content", "timeline-only"}
    assert "same" not in descriptions


def test_plan_migration_handles_duplicate_identical_timeline_rows_one_to_one(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    content = ("SYS-000001", NOW, "engine_run", "duplicate content", "src")
    # Two Timeline rows with byte-identical content, only one Events row.
    _insert(database, "timeline", [content, content])
    _insert(database, "events", [content])

    with sqlite3.connect(database) as connection:
        pending = plan_migration(connection)

    # Exactly one of the two identical Timeline rows must still be pending --
    # the single Events row can reconcile at most one of them.
    assert len(pending) == 1
    assert pending[0][1:] == content


def test_plan_migration_no_duplicate_events_rows_needed_when_events_has_both(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    content = ("SYS-000001", NOW, "engine_run", "duplicate content", "src")
    _insert(database, "timeline", [content, content])
    _insert(database, "events", [content, content])

    with sqlite3.connect(database) as connection:
        pending = plan_migration(connection)

    assert pending == []


def test_apply_migration_requires_active_transaction(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database, "timeline", [("SYS-000001", NOW, "a", "x", "src")])

    with sqlite3.connect(database) as connection:
        with pytest.raises(ValueError, match="active transaction"):
            apply_migration(connection)


def test_apply_migration_is_idempotent(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database, "timeline", [("SYS-000001", NOW, "a", "x", "src")])

    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        first = apply_migration(connection)
        connection.commit()

    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        second = apply_migration(connection)
        connection.commit()

    assert len(first) == 1
    assert second == []


def test_apply_migration_never_modifies_timeline(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(
        database,
        "timeline",
        [
            ("SYS-000001", NOW, "a", "x", "src"),
            ("SYS-000001", NOW, "b", "y", "src"),
        ],
    )

    def _timeline_snapshot() -> list[tuple]:
        with sqlite3.connect(database) as connection:
            return list(
                connection.execute(
                    "SELECT id,oid,event_at,event_type,description,source FROM timeline ORDER BY id"
                )
            )

    before = _timeline_snapshot()
    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        apply_migration(connection)
        connection.commit()
    after = _timeline_snapshot()

    assert before == after


def test_apply_migration_assigns_fresh_autoincrement_ids(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database, "events", [("SYS-000001", NOW, "existing", "e", "src")])  # events id 1
    _insert(
        database,
        "timeline",
        [
            ("SYS-000001", NOW, "a", "x", "src"),
            ("SYS-000001", NOW, "b", "y", "src"),
        ],
    )

    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        migrated = apply_migration(connection)
        connection.commit()

    events_ids = sorted(row.events_id for row in migrated)
    assert events_ids == [2, 3]
    assert len(set(events_ids)) == len(events_ids)


def test_reconcile_evidence_reconstructs_mapping_after_simulated_crash(
    tmp_path: Path,
) -> None:
    """A row was already inserted into events (COMMIT succeeded) but no
    evidence was ever written for it (simulating a crash between COMMIT and
    the audit-log append). reconcile_evidence must recover the correct
    mapping purely from timeline/events content -- no evidence log involved
    at all in this test."""
    database = _database(tmp_path)
    content = ("SYS-000001", NOW, "engine_run", "crashed before audit", "src")
    _insert(database, "timeline", [content])
    _insert(database, "events", [content])  # as if apply_migration had already run

    with sqlite3.connect(database) as connection:
        mapping = reconcile_evidence(connection)

    assert len(mapping) == 1
    assert mapping[0].timeline_id == 1
    assert mapping[0].events_id == 1
    assert (mapping[0].oid, mapping[0].event_at, mapping[0].event_type,
            mapping[0].description, mapping[0].source) == content


def test_reconcile_evidence_matches_apply_migration_output(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database, "timeline", [("SYS-000001", NOW, "a", "x", "src")])

    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        migrated = apply_migration(connection)
        connection.commit()

    with sqlite3.connect(database) as connection:
        mapping = reconcile_evidence(connection)

    assert len(mapping) == 1
    assert mapping[0].timeline_id == migrated[0].timeline_id
    assert mapping[0].events_id == migrated[0].events_id
    assert mapping[0].content_sha256 == migrated[0].content_sha256
