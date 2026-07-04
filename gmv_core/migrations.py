"""Explicit-target SQLite migration runner for GMV Core."""

from __future__ import annotations

import argparse
import sqlite3
from importlib import resources
from pathlib import Path

from gmv_core.errors import MigrationError, MigrationStateError

BASELINE_VERSION = 1
BASELINE_RESOURCE = "migration_sql/001_baseline.sql"


def _quoted_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


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


def _schema_signature(connection: sqlite3.Connection) -> tuple[object, ...]:
    objects = tuple(
        connection.execute(
            """
            SELECT type, name, tbl_name
            FROM sqlite_master
            WHERE type IN ('table', 'view', 'index', 'trigger')
            ORDER BY type, name
            """
        )
    )
    tables_and_views = tuple(
        str(row[1])
        for row in objects
        if row[0] in {"table", "view"} and row[1] != "sqlite_sequence"
    )
    columns = tuple(
        (
            name,
            tuple(
                connection.execute(
                    f"PRAGMA table_info({_quoted_identifier(name)})"
                )
            ),
        )
        for name in tables_and_views
    )
    indexes = tuple(
        (
            table,
            tuple(connection.execute(f"PRAGMA index_list({_quoted_identifier(table)})")),
        )
        for table in tables_and_views
    )
    index_columns = tuple(
        (
            str(row[1]),
            tuple(
                connection.execute(
                    f"PRAGMA index_xinfo({_quoted_identifier(str(row[1]))})"
                )
            ),
        )
        for row in objects
        if row[0] == "index"
    )
    foreign_keys = tuple(
        (
            table,
            tuple(
                connection.execute(
                    f"PRAGMA foreign_key_list({_quoted_identifier(table)})"
                )
            ),
        )
        for table in tables_and_views
    )
    return objects, columns, indexes, index_columns, foreign_keys


def _baseline_sql() -> str:
    return resources.files("gmv_core").joinpath(BASELINE_RESOURCE).read_text(
        encoding="utf-8"
    )


def _baseline_signature() -> tuple[object, ...]:
    with sqlite3.connect(":memory:") as connection:
        connection.executescript(_baseline_sql())
        return _schema_signature(connection)


def _adopt_current_shape(connection: sqlite3.Connection) -> int:
    if _schema_signature(connection) != _baseline_signature():
        raise MigrationStateError(
            "refusing to adopt an unversioned database that does not match the baseline"
        )

    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(f"PRAGMA user_version = {BASELINE_VERSION}")
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    return BASELINE_VERSION


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
                return _adopt_current_shape(connection)

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
