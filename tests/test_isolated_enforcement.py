"""SEC-006 enforce rehearsal, confined to disposable databases."""

from __future__ import annotations

import inspect
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from gmv_core import database as database_module
from gmv_core import migrations
from gmv_core.errors import DatabaseConfigurationError, MigrationError
from tests.conftest import IsolatedGMV

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ENGINE = ROOT / "01_RUNTIME" / "knowledge_engine.py"
COMPATIBILITY = ROOT / "10_API" / "gmv_compatibility.py"
IMPORT_SERVICE = ROOT / "10_API" / "import_service.py"
SCHEMA_FIXTURE = ROOT / "tests" / "fixtures" / "current_schema.sql"

_RUNNER = """
import os
import runpy
import sys
from pathlib import Path
from gmv_core import database

isolation_root = Path(os.environ.pop("GMV_ENFORCEMENT_TEST_ROOT"))
script = Path(sys.argv[1])
script_arguments = sys.argv[2:]

def isolated_connect(target, *, uri=False, timeout=5.0):
    return database.connect_path_isolated_enforcement(
        target,
        isolation_root=isolation_root,
        uri=uri,
        timeout=timeout,
    )

database.connect_path = isolated_connect
sys.path.insert(0, str(script.parent))
sys.argv = [str(script), *script_arguments]
runpy.run_path(str(script), run_name="__main__")
"""

_BROKEN_BASELINE = """
BEGIN IMMEDIATE;
CREATE TABLE partial_write (id INTEGER PRIMARY KEY);
THIS IS NOT VALID SQL;
PRAGMA user_version = 1;
COMMIT;
"""


def _environment(isolated_gmv: IsolatedGMV) -> dict[str, str]:
    environment = os.environ.copy()
    environment["HOME"] = str(isolated_gmv.home.parent)
    environment["GMV_HOME"] = str(isolated_gmv.home)
    environment["GMV_ENFORCEMENT_TEST_ROOT"] = str(isolated_gmv.home)
    return environment


def _run_enforced(
    isolated_gmv: IsolatedGMV,
    script: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _RUNNER, str(script), *arguments],
        cwd=ROOT,
        env=_environment(isolated_gmv),
        check=False,
        capture_output=True,
        text=True,
    )


def _prepare_current_database(isolated_gmv: IsolatedGMV) -> None:
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute("DROP TABLE test_sentinel")
    assert migrations.migrate(isolated_gmv.database) == migrations.CURRENT_SCHEMA_VERSION


def _authorization_log(isolated_gmv: IsolatedGMV) -> Path:
    return isolated_gmv.home / "04_LOGS" / "write_authorization.jsonl"


def _enforced_migration_connect(isolated_gmv: IsolatedGMV):
    def connect(target, *, uri=False, timeout=5.0):
        return database_module.connect_path_isolated_enforcement(
            target,
            isolation_root=isolated_gmv.home,
            uri=uri,
            timeout=timeout,
        )

    return connect


def test_live_factory_remains_literal_log_only(isolated_gmv: IsolatedGMV) -> None:
    assert "authorization_mode" not in inspect.signature(database_module.connect_path).parameters
    connection = database_module.connect_path(isolated_gmv.database)
    try:
        assert connection._gmv_mode == "log"
    finally:
        connection.close()


def test_isolated_factory_enforces_only_exact_temporary_target(
    isolated_gmv: IsolatedGMV, tmp_path: Path
) -> None:
    connection = database_module.connect_path_isolated_enforcement(
        isolated_gmv.database,
        isolation_root=isolated_gmv.home,
    )
    try:
        assert connection._gmv_mode == "enforce"
    finally:
        connection.close()

    with pytest.raises(DatabaseConfigurationError, match="must be exactly"):
        database_module.connect_path_isolated_enforcement(
            tmp_path / "other.db",
            isolation_root=isolated_gmv.home,
        )
    with pytest.raises(DatabaseConfigurationError, match="must be exactly"):
        database_module.connect_path_isolated_enforcement(
            isolated_gmv.live_database,
            isolation_root=isolated_gmv.home,
        )
    with pytest.raises(DatabaseConfigurationError, match="below the system temp"):
        database_module.connect_path_isolated_enforcement(
            isolated_gmv.live_database,
            isolation_root=ROOT,
        )
    with pytest.raises(DatabaseConfigurationError, match="does not accept SQLite URI"):
        database_module.connect_path_isolated_enforcement(
            "file:ignored?mode=ro",
            isolation_root=isolated_gmv.home,
            uri=True,
        )


def test_empty_to_current_migration_succeeds_under_isolated_enforce(
    isolated_gmv: IsolatedGMV, monkeypatch: pytest.MonkeyPatch
) -> None:
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute("DROP TABLE test_sentinel")
    monkeypatch.setattr(migrations, "connect_path", _enforced_migration_connect(isolated_gmv))

    assert migrations.migrate(isolated_gmv.database) == migrations.CURRENT_SCHEMA_VERSION
    with sqlite3.connect(isolated_gmv.database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (
            migrations.CURRENT_SCHEMA_VERSION,
        )
    assert not _authorization_log(isolated_gmv).exists()


def test_legacy_shape_adoption_succeeds_under_isolated_enforce(
    isolated_gmv: IsolatedGMV, monkeypatch: pytest.MonkeyPatch
) -> None:
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute("DROP TABLE test_sentinel")
        connection.executescript(SCHEMA_FIXTURE.read_text(encoding="utf-8"))
    monkeypatch.setattr(migrations, "connect_path", _enforced_migration_connect(isolated_gmv))

    assert (
        migrations.migrate(
            isolated_gmv.database,
            target_version=migrations.BASELINE_VERSION,
        )
        == migrations.BASELINE_VERSION
    )
    assert not _authorization_log(isolated_gmv).exists()


def test_migration_failure_restores_foreign_keys_under_isolated_enforce(
    isolated_gmv: IsolatedGMV, monkeypatch: pytest.MonkeyPatch
) -> None:
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute("DROP TABLE test_sentinel")
    original_loader = migrations._migration_sql

    def broken_loader(resource: str) -> str:
        if resource == migrations.BASELINE_RESOURCE:
            return _BROKEN_BASELINE
        return original_loader(resource)

    monkeypatch.setattr(migrations, "connect_path", _enforced_migration_connect(isolated_gmv))
    monkeypatch.setattr(migrations, "_migration_sql", broken_loader)

    with pytest.raises(MigrationError, match="migration 1 failed"):
        migrations.migrate(
            isolated_gmv.database,
            target_version=migrations.BASELINE_VERSION,
        )
    with sqlite3.connect(isolated_gmv.database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (0,)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name='partial_write'"
        ).fetchone() is None
    assert not _authorization_log(isolated_gmv).exists()


def test_knowledge_engine_legitimate_writes_succeed_end_to_end_in_enforce(
    isolated_gmv: IsolatedGMV,
) -> None:
    _prepare_current_database(isolated_gmv)
    (isolated_gmv.home / "04_LOGS").mkdir(parents=True)
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.executemany(
            "INSERT INTO objects(oid,type,name,status) VALUES (?,?,?,'active')",
            [
                ("SRV-000001", "Service", "Knowledge Engine"),
                ("PER-000001", "Person", "Giacomo Marco Valerio"),
            ],
        )

    result = _run_enforced(isolated_gmv, KNOWLEDGE_ENGINE)

    assert result.returncode == 0, result.stderr
    with sqlite3.connect(isolated_gmv.database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM service_runs").fetchone() == (1,)
    assert not _authorization_log(isolated_gmv).exists()


def test_compatibility_legitimate_writes_succeed_end_to_end_in_enforce(
    isolated_gmv: IsolatedGMV,
) -> None:
    _prepare_current_database(isolated_gmv)
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.executemany(
            "INSERT INTO objects(oid,type,name,status) VALUES (?,?,?,'active')",
            [
                ("SYS-000001", "System", "GMV OS"),
                ("SRV-000003", "Service", "Daily Log"),
            ],
        )

    result = _run_enforced(
        isolated_gmv,
        COMPATIBILITY,
        "daily_log",
        "--",
        "/usr/bin/true",
    )

    assert result.returncode == 0, result.stderr
    with sqlite3.connect(isolated_gmv.database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM service_runs").fetchone() == (1,)
    assert not _authorization_log(isolated_gmv).exists()


def test_import_all_legitimate_capabilities_succeed_end_to_end_in_enforce(
    isolated_gmv: IsolatedGMV, tmp_path: Path
) -> None:
    _prepare_current_database(isolated_gmv)
    source = tmp_path / "isolated-import.txt"
    source.write_text("SEC-006 isolated enforcement fixture\n", encoding="utf-8")

    first = _run_enforced(isolated_gmv, IMPORT_SERVICE, "file", str(source))
    second = _run_enforced(isolated_gmv, IMPORT_SERVICE, "file", str(source))

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    with sqlite3.connect(isolated_gmv.database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM resources").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM import_queue").fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM objects WHERE type='Resource'"
        ).fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone() == (2,)
    assert not _authorization_log(isolated_gmv).exists()


def test_forbidden_write_is_blocked_end_to_end_and_leaves_database_unchanged(
    isolated_gmv: IsolatedGMV, tmp_path: Path
) -> None:
    _prepare_current_database(isolated_gmv)
    with sqlite3.connect(isolated_gmv.database) as connection:
        connection.execute(
            "INSERT INTO objects(oid,type,name,status) "
            "VALUES ('PER-000001','Person','Protected fixture','active')"
        )
    forbidden_writer = tmp_path / "forbidden_writer.py"
    forbidden_writer.write_text(
        "from pathlib import Path\n"
        "from gmv_core import database\n"
        "target = Path.home() / '.gmv_core/09_DATABASE/GMV.db'\n"
        "with database.connect_path(target) as connection:\n"
        "    connection.execute(\"DELETE FROM objects WHERE oid='PER-000001'\")\n",
        encoding="utf-8",
    )

    result = _run_enforced(isolated_gmv, forbidden_writer)

    assert result.returncode != 0
    assert "UnauthorizedWriteError" in result.stderr
    with sqlite3.connect(isolated_gmv.database) as connection:
        assert connection.execute(
            "SELECT name FROM objects WHERE oid='PER-000001'"
        ).fetchone() == ("Protected fixture",)

    records = [
        json.loads(line)
        for line in _authorization_log(isolated_gmv).read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(records) == 1
    assert records[0]["mode"] == "enforce"
    assert records[0]["outcome"] == "denied"
    assert records[0]["verb"] == "DELETE"
    assert records[0]["table"] == "objects"
