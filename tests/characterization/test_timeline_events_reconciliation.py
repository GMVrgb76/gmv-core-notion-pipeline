"""Deterministic Timeline/Events reconciliation characterization (AUTO-003 first slice).

Test-only, per DB-005/AUTO-003. Builds on the existing SCHEMA_FIXTURE/
characterized_database baseline (which already seeds one row with the same
id and divergent content in each table) and adds further deterministic rows
covering every reconciliation category. Never touches the live database,
never depends on wall-clock dates or the current, ever-growing row counts
in 09_DATABASE/GMV.db. Comparison is always over full row content, not id
alone.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

FIXED_AT = "2026-06-01T00:00:00"


def _timeline_rows_by_id(connection: sqlite3.Connection) -> dict[int, tuple]:
    return {
        int(row[0]): row
        for row in connection.execute(
            "SELECT id,oid,event_at,event_type,description,source FROM timeline"
        )
    }


def _events_rows_by_id(connection: sqlite3.Connection) -> dict[int, tuple]:
    return {
        int(row[0]): row
        for row in connection.execute(
            "SELECT id,oid,event_at,event_type,description,source FROM events"
        )
    }


def _reconcile(connection: sqlite3.Connection) -> dict[str, set[int]]:
    timeline = _timeline_rows_by_id(connection)
    events = _events_rows_by_id(connection)
    shared = set(timeline) & set(events)
    identical = {row_id for row_id in shared if timeline[row_id] == events[row_id]}
    return {
        "identical": identical,
        "divergent": shared - identical,
        "timeline_only": set(timeline) - set(events),
        "events_only": set(events) - set(timeline),
    }


def _seed_deterministic_divergence(connection: sqlite3.Connection) -> None:
    # id=1 is already seeded by SCHEMA_FIXTURE with the same id and
    # divergent content in each table ("Synthetic event" vs "Synthetic
    # legacy event") -- exercised directly, not duplicated here.

    # Identical row: byte-identical id and content in both tables.
    connection.execute(
        "INSERT INTO timeline (id,oid,event_at,event_type,description,source) "
        "VALUES (2,'SYS-000001',?,'engine_run','identical fixture row','gmv_compatibility.py')",
        (FIXED_AT,),
    )
    connection.execute(
        "INSERT INTO events (id,oid,event_at,event_type,description,source) "
        "VALUES (2,'SYS-000001',?,'engine_run','identical fixture row','gmv_compatibility.py')",
        (FIXED_AT,),
    )

    # Same id, divergent content -- a second, dedicated case (explicit,
    # not relying only on the fixture's own incidental id=1 divergence).
    connection.execute(
        "INSERT INTO timeline (id,oid,event_at,event_type,description,source) "
        "VALUES (3,'SYS-000001',?,'engine_run','timeline text','gmv_compatibility.py')",
        (FIXED_AT,),
    )
    connection.execute(
        "INSERT INTO events (id,oid,event_at,event_type,description,source) "
        "VALUES (3,'SYS-000001',?,'engine_run','events text','gmv_compatibility.py')",
        (FIXED_AT,),
    )

    # Events-only row: never mirrored to timeline (matches the real
    # resource_imported/plugin/relation-bootstrap pattern).
    connection.execute(
        "INSERT INTO events (id,oid,event_at,event_type,description,source) "
        "VALUES (4,'RES-000001',?,'resource_imported','fixture resource','import_service')",
        (FIXED_AT,),
    )

    # Timeline-only rows, one from each of the two known active writers.
    connection.execute(
        "INSERT INTO timeline (id,oid,event_at,event_type,description,source) "
        "VALUES (5,'PER-000001',?,'system_event','knowledge engine only','knowledge_engine.py')",
        (FIXED_AT,),
    )
    connection.execute(
        "INSERT INTO timeline (id,oid,event_at,event_type,description,source) "
        "VALUES (6,'SYS-000001',?,'engine_run','compatibility only','gmv_compatibility.py')",
        (FIXED_AT,),
    )

    # Historical writer, permanently present in data but no longer in the
    # tracked tree (mirrors the real gmv_bridge.py row still in GMV.db).
    connection.execute(
        "INSERT INTO timeline (id,oid,event_at,event_type,description,source) "
        "VALUES (7,'SYS-000001',?,'engine_run','historical bridge row','gmv_bridge.py')",
        (FIXED_AT,),
    )
    connection.commit()


def test_reconciliation_identifies_every_category(characterized_database: Path) -> None:
    with sqlite3.connect(characterized_database) as connection:
        _seed_deterministic_divergence(connection)
        diff = _reconcile(connection)

    assert diff["identical"] == {2}
    assert diff["divergent"] == {1, 3}
    assert diff["events_only"] == {4}
    assert diff["timeline_only"] == {5, 6, 7}


def test_divergent_rows_share_id_but_differ_in_full_content(
    characterized_database: Path,
) -> None:
    with sqlite3.connect(characterized_database) as connection:
        _seed_deterministic_divergence(connection)
        timeline = _timeline_rows_by_id(connection)
        events = _events_rows_by_id(connection)

    for row_id in (1, 3):
        assert timeline[row_id][0] == events[row_id][0]
        assert timeline[row_id] != events[row_id]


def test_identical_row_matches_on_full_content_not_just_id(
    characterized_database: Path,
) -> None:
    with sqlite3.connect(characterized_database) as connection:
        _seed_deterministic_divergence(connection)
        timeline = _timeline_rows_by_id(connection)
        events = _events_rows_by_id(connection)

    assert timeline[2] == events[2]


def test_historical_writer_row_is_timeline_only_and_not_an_active_writer(
    characterized_database: Path,
) -> None:
    with sqlite3.connect(characterized_database) as connection:
        _seed_deterministic_divergence(connection)
        timeline = _timeline_rows_by_id(connection)
        events = _events_rows_by_id(connection)

    historical = timeline[7]
    assert historical[5] == "gmv_bridge.py"
    assert historical[5] not in {"knowledge_engine.py", "gmv_compatibility.py"}
    assert 7 not in events
