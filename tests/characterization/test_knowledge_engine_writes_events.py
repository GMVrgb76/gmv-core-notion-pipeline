"""Knowledge Engine writes canonical Events and Service Runs.

Isolated only: runs the real script as a subprocess against a disposable
`.gmv_core` home (never the live database), verifying the DB-005 Events writer
and the DB-006 Service-run writer. Never invoked against 09_DATABASE/GMV.db.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from gmv_core.migrations import FOREIGN_KEYS_VERSION, migrate
from tests.conftest import IsolatedGMV

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
            "service_runs": int(
                connection.execute("SELECT COUNT(*) FROM service_runs").fetchone()[0]
            ),
            "timeline": int(connection.execute("SELECT COUNT(*) FROM timeline").fetchone()[0]),
            "events": int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]),
        }


def _seed_required_person(database: Path, *, object_type: str = "Person") -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO objects(oid,type,name,status)
            VALUES ('PER-000001',?,'Giacomo Marco Valerio','active')
            """,
            (object_type,),
        )


def test_knowledge_engine_writes_events_not_timeline(
    cli_environment: dict[str, str], characterized_database: Path
) -> None:
    _seed_required_person(characterized_database)
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


def test_knowledge_engine_writes_canonical_service_run(
    cli_environment: dict[str, str], characterized_database: Path
) -> None:
    _seed_required_person(characterized_database)
    before = _counts(characterized_database)

    result = _run_knowledge_engine(cli_environment)

    assert result.returncode == 0, result.stderr
    after = _counts(characterized_database)

    assert after["objects"] == before["objects"]
    assert after["engine_runs"] == before["engine_runs"]
    assert after["service_runs"] == before["service_runs"] + 1

    with sqlite3.connect(characterized_database) as connection:
        person = connection.execute(
            "SELECT oid,type,name,status FROM objects WHERE oid='PER-000001'"
        ).fetchone()
        run = connection.execute(
            "SELECT service_oid,service_name,status,summary "
            "FROM service_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert person == ("PER-000001", "Person", "Giacomo Marco Valerio", "active")
    assert run == (
        "SRV-000001",
        "Knowledge Engine",
        "OK",
        "Knowledge Engine V0 executed. GMV.db initialized. First persistent OID verified: PER-000001.",
    )


def test_knowledge_engine_second_run_does_not_duplicate_the_object(
    cli_environment: dict[str, str], characterized_database: Path
) -> None:
    _seed_required_person(characterized_database)
    first = _run_knowledge_engine(cli_environment)
    assert first.returncode == 0, first.stderr
    after_first = _counts(characterized_database)

    second = _run_knowledge_engine(cli_environment)
    assert second.returncode == 0, second.stderr
    after_second = _counts(characterized_database)

    assert after_second["objects"] == after_first["objects"]
    # Events and Service Runs append once per execution; the legacy Engine
    # ledger is no longer a Knowledge Engine writer.
    assert after_second["events"] == after_first["events"] + 1
    assert after_second["service_runs"] == after_first["service_runs"] + 1
    assert after_second["engine_runs"] == after_first["engine_runs"]
    # timeline: never touched by either run.
    assert after_second["timeline"] == after_first["timeline"]


def test_knowledge_engine_event_and_service_run_share_one_transaction(
    cli_environment: dict[str, str], characterized_database: Path
) -> None:
    _seed_required_person(characterized_database)
    before = _counts(characterized_database)
    with sqlite3.connect(characterized_database) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_knowledge_service_run
            BEFORE INSERT ON service_runs
            WHEN NEW.service_oid = 'SRV-000001'
            BEGIN
                SELECT RAISE(ABORT, 'synthetic service-run failure');
            END
            """
        )

    result = _run_knowledge_engine(cli_environment)

    assert result.returncode != 0
    assert "synthetic service-run failure" in result.stderr
    assert _counts(characterized_database) == before


def test_knowledge_engine_missing_service_identity_fails_without_creating_authority(
    isolated_gmv: IsolatedGMV,
) -> None:
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute("DROP TABLE test_sentinel")
    assert (
        migrate(isolated_gmv.database, target_version=FOREIGN_KEYS_VERSION)
        == FOREIGN_KEYS_VERSION
    )
    _seed_required_person(isolated_gmv.database)
    environment = os.environ.copy()

    result = _run_knowledge_engine(environment)

    assert result.returncode == 2
    assert result.stderr == (
        "error: required Object identities are unavailable: "
        "SRV-000001 (Service)\n"
    )
    with sqlite3.connect(isolated_gmv.database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM objects WHERE oid='SRV-000001'"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM objects WHERE oid='PER-000001'"
        ).fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM service_runs").fetchone() == (0,)


@pytest.mark.parametrize("person_type", (None, "System"), ids=("missing", "mistyped"))
def test_knowledge_engine_person_identity_fails_closed_without_writes(
    isolated_gmv: IsolatedGMV,
    person_type: str | None,
) -> None:
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute("DROP TABLE test_sentinel")
    migrate(isolated_gmv.database, target_version=FOREIGN_KEYS_VERSION)
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute(
            """
            INSERT INTO objects(oid,type,name,status)
            VALUES ('SRV-000001','Service','Knowledge Engine','active')
            """
        )
    if person_type is not None:
        _seed_required_person(isolated_gmv.database, object_type=person_type)

    result = _run_knowledge_engine(os.environ.copy())

    assert result.returncode == 2
    assert result.stderr == (
        "error: required Object identities are unavailable: PER-000001 (Person)\n"
    )
    with sqlite3.connect(isolated_gmv.database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM service_runs").fetchone() == (0,)


def test_knowledge_engine_writes_valid_references_on_version_six(
    isolated_gmv: IsolatedGMV,
) -> None:
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute("DROP TABLE test_sentinel")
    migrate(isolated_gmv.database, target_version=FOREIGN_KEYS_VERSION)
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute(
            """
            INSERT INTO objects(oid,type,name,status)
            VALUES ('SRV-000001','Service','Knowledge Engine','active')
            """
        )
    _seed_required_person(isolated_gmv.database)

    result = _run_knowledge_engine(os.environ.copy())

    assert result.returncode == 0, result.stderr
    with sqlite3.connect(isolated_gmv.database) as connection:
        assert tuple(connection.execute("PRAGMA foreign_key_check")) == ()
        assert connection.execute(
            "SELECT oid FROM events ORDER BY id DESC LIMIT 1"
        ).fetchone() == ("PER-000001",)
        assert connection.execute(
            "SELECT service_oid FROM service_runs ORDER BY id DESC LIMIT 1"
        ).fetchone() == ("SRV-000001",)
