"""knowledge_engine.py writes Events, not Timeline (DB-005 first writer slice).

Isolated only: runs the real script as a subprocess against a disposable
`.gmv_core` home (never the live database), verifying the Timeline write was
replaced with an equivalent Events write while objects/engine_runs behavior
is unchanged. Never invoked against 09_DATABASE/GMV.db.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ENGINE = ROOT / "01_RUNTIME" / "knowledge_engine.py"


def _run_knowledge_engine(cli_environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    home = Path(cli_environment["HOME"]) / ".gmv_core"
    (home / "04_LOGS").mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [sys.executable, str(KNOWLEDGE_ENGINE)],
        env=cli_environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _counts(database: Path) -> dict[str, int]:
    with sqlite3.connect(database) as connection:
        return {
            "objects": int(connection.execute("SELECT COUNT(*) FROM objects").fetchone()[0]),
            "engine_runs": int(
                connection.execute("SELECT COUNT(*) FROM engine_runs").fetchone()[0]
            ),
            "timeline": int(connection.execute("SELECT COUNT(*) FROM timeline").fetchone()[0]),
            "events": int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]),
        }


def test_knowledge_engine_writes_events_not_timeline(
    cli_environment: dict[str, str], characterized_database: Path
) -> None:
    before = _counts(characterized_database)

    result = _run_knowledge_engine(cli_environment)

    assert result.returncode == 0, result.stderr
    after = _counts(characterized_database)

    assert after["events"] == before["events"] + 1
    assert after["timeline"] == before["timeline"]

    with sqlite3.connect(characterized_database) as connection:
        event = connection.execute(
            "SELECT oid,event_type,description,source FROM events ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert event == (
        "PER-000001",
        "system_event",
        "Knowledge Engine V0 initialized from former Apprentice concept.",
        "knowledge_engine.py",
    )


def test_knowledge_engine_objects_and_engine_runs_behavior_is_unchanged(
    cli_environment: dict[str, str], characterized_database: Path
) -> None:
    before = _counts(characterized_database)

    result = _run_knowledge_engine(cli_environment)

    assert result.returncode == 0, result.stderr
    after = _counts(characterized_database)

    # PER-000001 does not exist in the fixture baseline (only SYS/SRV/PLG/RES
    # do), so INSERT OR IGNORE inserts exactly one new object row.
    assert after["objects"] == before["objects"] + 1
    assert after["engine_runs"] == before["engine_runs"] + 1

    with sqlite3.connect(characterized_database) as connection:
        person = connection.execute(
            "SELECT oid,type,name,status FROM objects WHERE oid='PER-000001'"
        ).fetchone()
        run = connection.execute(
            "SELECT engine,status,summary FROM engine_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert person == ("PER-000001", "Person", "Giacomo Marco Valerio", "active")
    assert run == (
        "knowledge_engine",
        "OK",
        "Knowledge Engine V0 executed. GMV.db initialized. First persistent OID verified: PER-000001.",
    )


def test_knowledge_engine_second_run_does_not_duplicate_the_object(
    cli_environment: dict[str, str], characterized_database: Path
) -> None:
    first = _run_knowledge_engine(cli_environment)
    assert first.returncode == 0, first.stderr
    after_first = _counts(characterized_database)

    second = _run_knowledge_engine(cli_environment)
    assert second.returncode == 0, second.stderr
    after_second = _counts(characterized_database)

    # objects: INSERT OR IGNORE keeps PER-000001 unique across runs.
    assert after_second["objects"] == after_first["objects"]
    # events/engine_runs: one new row appended per run.
    assert after_second["events"] == after_first["events"] + 1
    assert after_second["engine_runs"] == after_first["engine_runs"] + 1
    # timeline: never touched by either run.
    assert after_second["timeline"] == after_first["timeline"]
