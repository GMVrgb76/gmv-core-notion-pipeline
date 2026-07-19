"""Explicit-target SQLite migration runner for GMV Core."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from importlib import resources
from pathlib import Path

from gmv_core.errors import MigrationError, MigrationStateError

BASELINE_VERSION = 1
BASELINE_RESOURCE = "migration_sql/001_baseline.sql"
OID_SEQUENCE_VERSION = 2
OID_SEQUENCE_RESOURCE = "migration_sql/002_oid_sequences.sql"
TIMELINE_VIEW_VERSION = 3
TIMELINE_VIEW_RESOURCE = "migration_sql/003_timeline_view.sql"
APPEND_ONLY_EVENTS_VERSION = 4
APPEND_ONLY_EVENTS_RESOURCE = "migration_sql/004_append_only_events.sql"
ENGINE_RUNS_RETIRED_VERSION = 5
ENGINE_RUNS_RETIRED_RESOURCE = "migration_sql/005_retire_engine_runs.sql"
FOREIGN_KEYS_VERSION = 6
FOREIGN_KEYS_RESOURCE = "migration_sql/006_foreign_keys.sql"
CURRENT_SCHEMA_VERSION = ENGINE_RUNS_RETIRED_VERSION


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


def _migration_sql(resource: str) -> str:
    return resources.files("gmv_core").joinpath(resource).read_text(encoding="utf-8")


def _baseline_sql() -> str:
    return _migration_sql(BASELINE_RESOURCE)


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


def _version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row is not None else 0


def _apply_migration(
    connection: sqlite3.Connection,
    *,
    target: Path,
    version: int,
    resource: str,
) -> None:
    try:
        connection.executescript(_migration_sql(resource))
    except sqlite3.Error as error:
        connection.rollback()
        raise MigrationError(
            f"migration {version} failed for {target}: {error}"
        ) from error
    result = _version(connection)
    if result != version:
        raise MigrationError(f"migration {version} did not set expected version: {result}")


def _register_engine_run_content_hash(connection: sqlite3.Connection) -> None:
    def content_hash(*values: object) -> str:
        payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    connection.create_function(
        "gmv_engine_run_content_sha256",
        8,
        content_hash,
        deterministic=True,
    )


def migrate(
    database: str | Path,
    *,
    target_version: int = CURRENT_SCHEMA_VERSION,
) -> int:
    """Migrate an explicit SQLite target and return its resulting version."""
    target = Path(database)
    if not target.parent.exists():
        raise MigrationStateError(f"migration target directory does not exist: {target.parent}")
    supported_versions = {
        BASELINE_VERSION,
        OID_SEQUENCE_VERSION,
        TIMELINE_VIEW_VERSION,
        APPEND_ONLY_EVENTS_VERSION,
        ENGINE_RUNS_RETIRED_VERSION,
        FOREIGN_KEYS_VERSION,
    }
    if target_version not in supported_versions:
        raise MigrationStateError(f"unsupported target schema version: {target_version}")

    try:
        with sqlite3.connect(target) as connection:
            current_version = _version(connection)
            if current_version > target_version:
                raise MigrationStateError(
                    f"database version {current_version} is newer than target {target_version}"
                )
            if current_version == 0:
                if _schema_object_count(connection) != 0:
                    current_version = _adopt_current_shape(connection)
                else:
                    _apply_migration(
                        connection,
                        target=target,
                        version=BASELINE_VERSION,
                        resource=BASELINE_RESOURCE,
                    )
                    current_version = BASELINE_VERSION
            if target_version >= OID_SEQUENCE_VERSION and current_version == BASELINE_VERSION:
                _apply_migration(
                    connection,
                    target=target,
                    version=OID_SEQUENCE_VERSION,
                    resource=OID_SEQUENCE_RESOURCE,
                )
                current_version = OID_SEQUENCE_VERSION
            if target_version >= TIMELINE_VIEW_VERSION and current_version == OID_SEQUENCE_VERSION:
                _apply_migration(
                    connection,
                    target=target,
                    version=TIMELINE_VIEW_VERSION,
                    resource=TIMELINE_VIEW_RESOURCE,
                )
                current_version = TIMELINE_VIEW_VERSION
            if (
                target_version >= APPEND_ONLY_EVENTS_VERSION
                and current_version == TIMELINE_VIEW_VERSION
            ):
                _apply_migration(
                    connection,
                    target=target,
                    version=APPEND_ONLY_EVENTS_VERSION,
                    resource=APPEND_ONLY_EVENTS_RESOURCE,
                )
                current_version = APPEND_ONLY_EVENTS_VERSION
            if (
                target_version >= ENGINE_RUNS_RETIRED_VERSION
                and current_version == APPEND_ONLY_EVENTS_VERSION
            ):
                _register_engine_run_content_hash(connection)
                _apply_migration(
                    connection,
                    target=target,
                    version=ENGINE_RUNS_RETIRED_VERSION,
                    resource=ENGINE_RUNS_RETIRED_RESOURCE,
                )
                current_version = ENGINE_RUNS_RETIRED_VERSION
            if (
                target_version >= FOREIGN_KEYS_VERSION
                and current_version == ENGINE_RUNS_RETIRED_VERSION
            ):
                _apply_migration(
                    connection,
                    target=target,
                    version=FOREIGN_KEYS_VERSION,
                    resource=FOREIGN_KEYS_RESOURCE,
                )
                current_version = FOREIGN_KEYS_VERSION
            return current_version
    except sqlite3.Error as error:
        raise MigrationError(f"could not open migration target {target}: {error}") from error


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate an explicit GMV SQLite target")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument(
        "--target-version",
        type=int,
        choices=(
            BASELINE_VERSION,
            OID_SEQUENCE_VERSION,
            TIMELINE_VIEW_VERSION,
            APPEND_ONLY_EVENTS_VERSION,
            ENGINE_RUNS_RETIRED_VERSION,
            FOREIGN_KEYS_VERSION,
        ),
        default=CURRENT_SCHEMA_VERSION,
    )
    options = parser.parse_args(arguments)
    version = migrate(options.database, target_version=options.target_version)
    print(f"schema_version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
