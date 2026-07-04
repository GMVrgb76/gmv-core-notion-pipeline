"""Explicit-target SQLite migration runner for GMV Core."""

from __future__ import annotations

import argparse
import sqlite3
from importlib import resources
from pathlib import Path

from gmv_core.errors import MigrationError, MigrationStateError

BASELINE_VERSION = 1
BASELINE_RESOURCE = "migration_sql/001_baseline.sql"


def _schema_object_count(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*)
        FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%'
          AND type IN ('table', 'view', 'index', 'trigger')
        """
    ).fetchone()
    return int(row[0]) if row is not None else 0


def _baseline_sql() -> str:
    return resources.files("gmv_core").joinpath(BASELINE_RESOURCE).read_text(
        encoding="utf-8"
    )


def migrate(database: str | Path) -> int:
    """Migrate an explicit SQLite target and return its resulting version."""
    target = Path(database)
    if not target.parent.exists():
        raise MigrationStateError(f"migration target directory does not exist: {target.parent}")

    try:
        with sqlite3.connect(target) as connection:
            version_row = connection.execute("PRAGMA user_version").fetchone()
            current_version = int(version_row[0]) if version_row is not None else 0

            if current_version == BASELINE_VERSION:
                return current_version
            if current_version != 0:
                raise MigrationStateError(
                    f"unsupported schema version {current_version}; expected 0 or {BASELINE_VERSION}"
                )
            if _schema_object_count(connection) != 0:
                raise MigrationStateError(
                    "refusing to apply baseline to an unversioned non-empty database"
                )

            try:
                connection.executescript(_baseline_sql())
            except sqlite3.Error as error:
                connection.rollback()
                raise MigrationError(f"baseline migration failed for {target}: {error}") from error

            result_row = connection.execute("PRAGMA user_version").fetchone()
            result = int(result_row[0]) if result_row is not None else 0
            if result != BASELINE_VERSION:
                raise MigrationError(
                    f"baseline migration did not set version {BASELINE_VERSION}: {result}"
                )
            return result
    except sqlite3.Error as error:
        raise MigrationError(f"could not open migration target {target}: {error}") from error


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate an explicit GMV SQLite target")
    parser.add_argument("--database", required=True, type=Path)
    options = parser.parse_args(arguments)
    version = migrate(options.database)
    print(f"schema_version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
