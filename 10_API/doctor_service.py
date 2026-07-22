#!/usr/bin/env python3
"""Evidence-based strict health diagnostics for GMV Core.

`identity.json_conformance` is diagnostic enforcement only: it detects and
reports non-conformant or duplicate JSON-sourced Object identities after
the fact (see `gmv_core/json_identity_audit.py`). It does not lock, freeze,
or otherwise physically prevent a write to `03_STATE/objects/*.json` or
`02_INDEXES/OBJECT_INDEX.json` — that would be a separate, unauthorized
enforcement mechanism (`MAIN-011`'s "reject new parallel state writes",
still open).
"""

from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sqlite3
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from artifact_audit import audit_artifacts

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from gmv_core.json_identity_audit import audit_json_identities  # noqa: E402
from gmv_core.paths import GMVPaths  # noqa: E402

database_module = importlib.import_module("gmv_core.database")

SCHEMA_VERSION = 1
REQUIRED_SCHEMA = {
    "events",
    "import_queue",
    "objects",
    "plugin_metadata",
    "resources",
    "service_runs",
    "service_registry_view",
}


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: str
    message: str


def _database_uri(database: Path) -> str:
    return f"{database.resolve().as_uri()}?mode=ro"


def _with_database(
    database: Path,
    name: str,
    check: Callable[[sqlite3.Connection], str],
) -> CheckResult:
    try:
        with database_module.connect_path(
            _database_uri(database), uri=True
        ) as connection:
            message = check(connection)
    except (OSError, sqlite3.Error, ValueError) as error:
        return CheckResult(name, "FAIL", str(error))
    return CheckResult(name, "PASS", message)


def _legacy_rows(database: Path, sql: str) -> list[tuple[object, ...]]:
    """Run one legacy Doctor query through a genuinely read-only Core URI."""
    with database_module.connect_path(_database_uri(database), uri=True) as connection:
        return list(connection.execute(sql))


def _print_legacy_rows(rows: list[tuple[object, ...]]) -> None:
    for row in rows:
        print("|".join("" if value is None else str(value) for value in row))


def _print_legacy_launchagents() -> None:
    executable = shutil.which("launchctl")
    if executable is None:
        print("warning: optional command not found: launchctl", file=sys.stderr)
        return
    result = subprocess.run(  # noqa: S603 - executable resolved by shutil.which
        [executable, "list"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("warning: optional command failed: launchctl list", file=sys.stderr)
        return
    for line in result.stdout.splitlines():
        if "com.gmv" in line:
            print(line)


def run_legacy_doctor(database: Path) -> int:
    """Preserve the historical human Doctor report without shell SQLite."""
    print()
    print("==================================================")
    print("               GMV DOCTOR")
    print("==================================================")

    checks: tuple[tuple[str, str | None], ...] = (
        ("[1] DATABASE", "PRAGMA integrity_check"),
        (
            "[2] OBJECT COUNTS",
            "SELECT type, COUNT(*) FROM objects GROUP BY type ORDER BY type",
        ),
        (
            "[3] REGISTERED SERVICES",
            "SELECT service_name,status FROM service_registry_view",
        ),
        (
            "[4] REGISTERED PLUGINS",
            "SELECT plugin_name,status FROM plugin_registry_view",
        ),
        (
            "[5] DATABASE VIEWS",
            "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name",
        ),
        (
            "[6] LAST SERVICE RUNS",
            "SELECT service_oid,service_name,run_at,status "
            "FROM service_runs ORDER BY id DESC LIMIT 10",
        ),
        ("[7] LAUNCHAGENTS", None),
        (
            "[8] ORPHAN SERVICE RUNS",
            "SELECT COUNT(*) FROM service_runs sr "
            "LEFT JOIN objects o ON sr.service_oid=o.oid WHERE o.oid IS NULL",
        ),
        (
            "[9] ORPHAN EVENTS",
            "SELECT COUNT(*) FROM events e "
            "LEFT JOIN objects o ON e.oid=o.oid WHERE o.oid IS NULL",
        ),
        (
            "[10] PENDING PLUGINS",
            "SELECT plugin_name FROM plugin_registry_view WHERE status='pending'",
        ),
    )

    for heading, sql in checks:
        print()
        print(heading)
        if sql is None:
            _print_legacy_launchagents()
            continue
        try:
            _print_legacy_rows(_legacy_rows(database, sql))
        except (OSError, sqlite3.Error, ValueError) as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1

    print()
    print("==================================================")
    print("GMV DOCTOR COMPLETED")
    print("==================================================")
    return 0


def run_checks(database: Path, home: Path | None = None) -> list[CheckResult]:
    paths = GMVPaths.from_home(home or Path.home() / ".gmv_core")
    results = []
    if database.is_file():
        results.append(CheckResult("database.exists", "PASS", str(database)))
    else:
        results.append(CheckResult("database.exists", "FAIL", f"missing: {database}"))

    def integrity(connection: sqlite3.Connection) -> str:
        rows = [str(row[0]) for row in connection.execute("PRAGMA integrity_check")]
        if rows != ["ok"]:
            raise ValueError("; ".join(rows))
        return "ok"

    results.append(_with_database(database, "database.integrity", integrity))

    def foreign_keys(connection: sqlite3.Connection) -> str:
        rows = list(connection.execute("PRAGMA foreign_key_check"))
        if rows:
            raise ValueError(f"{len(rows)} foreign-key violation(s)")
        return "no violations"

    results.append(_with_database(database, "database.foreign_keys", foreign_keys))

    def schema(connection: sqlite3.Connection) -> str:
        names = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            )
        }
        missing = sorted(REQUIRED_SCHEMA - names)
        if missing:
            raise ValueError(f"missing schema objects: {', '.join(missing)}")
        return f"{len(REQUIRED_SCHEMA)} required objects present"

    results.append(_with_database(database, "database.schema", schema))

    def queries(connection: sqlite3.Connection) -> str:
        object_count = int(connection.execute("SELECT COUNT(*) FROM objects").fetchone()[0])
        service_count = int(
            connection.execute("SELECT COUNT(*) FROM service_registry_view").fetchone()[0]
        )
        return f"objects={object_count}, services={service_count}"

    results.append(_with_database(database, "database.queries", queries))

    try:
        unavailable = [
            record
            for record in audit_artifacts(database)
            if record["availability"] == "unavailable"
        ]
        if unavailable:
            message = ", ".join(
                f"run {record['run_id']} {record['stream']}" for record in unavailable
            )
            results.append(CheckResult("artifacts.references", "FAIL", message))
        else:
            results.append(
                CheckResult(
                    "artifacts.references",
                    "PASS",
                    "all recorded artifacts available",
                )
            )
    except (OSError, sqlite3.Error) as error:
        results.append(CheckResult("artifacts.references", "FAIL", str(error)))

    try:
        mode = stat.S_IMODE(database.stat().st_mode)
        if mode & 0o077:
            results.append(
                CheckResult(
                    "database.permissions",
                    "FAIL",
                    f"mode {mode:04o} permits group or other access",
                )
            )
        else:
            results.append(CheckResult("database.permissions", "PASS", f"mode {mode:04o}"))
    except OSError as error:
        results.append(CheckResult("database.permissions", "FAIL", str(error)))

    def json_identities(connection: sqlite3.Connection) -> str:
        audit = audit_json_identities(paths, connection)
        if audit.status == "FAIL":
            raise ValueError(audit.message)
        return audit.message

    results.append(_with_database(database, "identity.json_conformance", json_identities))
    return results


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument(
        "--database",
        type=Path,
        default=Path.home() / ".gmv_core" / "09_DATABASE" / "GMV.db",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=Path.home() / ".gmv_core",
    )
    options = parser.parse_args(arguments)
    if options.legacy:
        return run_legacy_doctor(options.database)
    checks = run_checks(options.database, options.home)
    failed = any(check.status == "FAIL" for check in checks)
    if options.json:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "overall": "failed" if failed else "ready",
                    "checks": [asdict(check) for check in checks],
                },
                sort_keys=True,
            )
        )
    else:
        for check in checks:
            print(f"{check.status}|{check.name}|{check.message}")
        print(f"OVERALL|{'FAILED' if failed else 'READY'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
