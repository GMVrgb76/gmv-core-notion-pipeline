"""Characterize the human-facing, non-strict ``gmv doctor`` contract."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from tests.characterization.conftest import CLI

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "10_API"))
import doctor_service  # noqa: E402

from gmv_core import authorization  # noqa: E402


def _environment(tmp_path: Path) -> dict[str, str]:
    executable_directory = tmp_path / "test-bin"
    executable_directory.mkdir(exist_ok=True)
    launchctl = executable_directory / "launchctl"
    launchctl.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' '- 0 com.gmv.fixture' '- 0 com.example.other'\n",
        encoding="utf-8",
    )
    launchctl.chmod(0o755)

    environment = os.environ.copy()
    environment["HOME"] = str(tmp_path / "doctor-home")
    environment["PATH"] = f"{executable_directory}:{environment['PATH']}"
    return environment


def _database(tmp_path: Path, *, complete: bool = True) -> Path:
    database = tmp_path / "doctor-home" / ".gmv_core" / "09_DATABASE" / "GMV.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE objects (
                oid TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL
            );
            INSERT INTO objects VALUES
                ('COR-000001', 'Core', 'GMV Core', 'active'),
                ('PLG-000001', 'Plugin', 'Fixture Plugin', 'active'),
                ('SRV-000001', 'Service', 'Fixture Service', 'active');
            """
        )
        if complete:
            connection.executescript(
                """
                CREATE TABLE service_runs (
                    id INTEGER PRIMARY KEY,
                    service_oid TEXT NOT NULL,
                    service_name TEXT NOT NULL,
                    run_at TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE events (
                    id INTEGER PRIMARY KEY,
                    oid TEXT NOT NULL
                );
                CREATE TABLE plugin_metadata (
                    plugin_oid TEXT PRIMARY KEY,
                    status TEXT NOT NULL
                );
                INSERT INTO service_runs VALUES
                    (1, 'SRV-000001', 'Fixture Service', '2026-07-22T10:00:00', 'OK');
                INSERT INTO events VALUES (1, 'COR-000001');
                INSERT INTO plugin_metadata VALUES ('PLG-000001', 'active');
                CREATE VIEW service_registry_view AS
                    SELECT name AS service_name, status
                    FROM objects WHERE type = 'Service';
                CREATE VIEW plugin_registry_view AS
                    SELECT o.name AS plugin_name, p.status
                    FROM objects o JOIN plugin_metadata p ON p.plugin_oid = o.oid;
                """
            )
    return database


def _run(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), "doctor"],
        env=_environment(tmp_path),
        check=False,
        capture_output=True,
        text=True,
    )


def test_valid_database_preserves_exact_output_and_success(tmp_path: Path) -> None:
    database = _database(tmp_path)
    before = (database.read_bytes(), database.stat().st_mtime_ns)

    result = _run(tmp_path)

    after = (database.read_bytes(), database.stat().st_mtime_ns)
    assert result.returncode == 0
    assert result.stderr == ""
    assert after == before
    assert result.stdout == """
==================================================
               GMV DOCTOR
==================================================

[1] DATABASE
ok

[2] OBJECT COUNTS
Core|1
Plugin|1
Service|1

[3] REGISTERED SERVICES
Fixture Service|active

[4] REGISTERED PLUGINS
Fixture Plugin|active

[5] DATABASE VIEWS
plugin_registry_view
service_registry_view

[6] LAST SERVICE RUNS
SRV-000001|Fixture Service|2026-07-22T10:00:00|OK

[7] LAUNCHAGENTS
- 0 com.gmv.fixture

[8] ORPHAN SERVICE RUNS
0

[9] ORPHAN EVENTS
0

[10] PENDING PLUGINS

==================================================
GMV DOCTOR COMPLETED
==================================================
"""


def test_missing_database_fails_at_first_check_without_creating_it(
    tmp_path: Path,
) -> None:
    database = (
        tmp_path / "doctor-home" / ".gmv_core" / "09_DATABASE" / "GMV.db"
    )

    result = _run(tmp_path)

    assert result.returncode == 1
    assert result.stdout == """
==================================================
               GMV DOCTOR
==================================================

[1] DATABASE
"""
    assert "unable to open database" in result.stderr.lower()
    assert not database.exists()


def test_invalid_schema_preserves_partial_output_and_failure(tmp_path: Path) -> None:
    _database(tmp_path, complete=False)

    result = _run(tmp_path)

    assert result.returncode == 1
    assert result.stdout == """
==================================================
               GMV DOCTOR
==================================================

[1] DATABASE
ok

[2] OBJECT COUNTS
Core|1
Plugin|1
Service|1

[3] REGISTERED SERVICES
"""
    assert "no such table: service_registry_view" in result.stderr


def test_doctor_does_not_require_or_invoke_external_sqlite(tmp_path: Path) -> None:
    _database(tmp_path)
    sqlite = tmp_path / "test-bin" / "sqlite3"
    sqlite.parent.mkdir(exist_ok=True)
    sqlite.write_text("#!/bin/sh\nexit 19\n", encoding="utf-8")
    sqlite.chmod(0o755)

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "GMV DOCTOR COMPLETED" in result.stdout


def test_legacy_queries_use_core_read_only_uri(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = _database(tmp_path)
    calls: list[tuple[object, dict[str, object]]] = []
    original = doctor_service.database_module.connect_path

    def recording_connect_path(target, **kwargs):
        calls.append((target, kwargs))
        return original(target, **kwargs)

    monkeypatch.setattr(
        doctor_service.database_module,
        "connect_path",
        recording_connect_path,
    )

    rows = doctor_service._legacy_rows(database, "SELECT COUNT(*) FROM objects")

    assert rows == [(3,)]
    assert len(calls) == 1
    target, kwargs = calls[0]
    assert str(target).endswith("/GMV.db?mode=ro")
    assert kwargs == {"uri": True}


def test_doctor_has_no_write_capability() -> None:
    doctor = "10_API/doctor_service.py"

    assert all(capability[0] != doctor for capability in authorization.DML_CAPABILITIES)
    assert all(capability[0] != doctor for capability in authorization.DDL_CALLERS)
    assert all(
        capability[0] != doctor
        for capability in authorization.PRAGMA_WRITE_CAPABILITIES
    )
