"""Connection ownership for the Core persistence boundary.

First lifecycle-owning module under ADR_CORE_PERSISTENCE_BOUNDARY.md: resolves
the GMV database path via gmv_core's own configuration surface and opens the
connection. Callers retain sqlite3.Connection's own context-manager semantics
(commit/rollback on exit; the connection is not closed). DB-002 additionally
enables SQLite foreign-key enforcement before returning every Core-owned
connection.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Mapping

from gmv_core.config import load_config
from gmv_core.errors import DatabaseConfigurationError
from gmv_core.paths import GMVPaths


def enable_foreign_keys(connection: sqlite3.Connection) -> sqlite3.Connection:
    """Enable and verify per-connection SQLite foreign-key enforcement.

    SQLite silently ignores ``PRAGMA foreign_keys=ON`` inside an active
    transaction. Reading the setting back makes that unsafe state fail closed.
    """
    connection.execute("PRAGMA foreign_keys = ON")
    row = connection.execute("PRAGMA foreign_keys").fetchone()
    if row != (1,):
        raise DatabaseConfigurationError(
            "SQLite foreign-key enforcement could not be enabled"
        )
    return connection


def require_object_identities(
    connection: sqlite3.Connection,
    required: Mapping[str, str],
) -> None:
    """Fail closed unless every required OID exists with its expected type."""
    try:
        actual = {}
        for oid in required:
            row = connection.execute(
                "SELECT type FROM objects WHERE oid=?",
                (oid,),
            ).fetchone()
            if row is not None:
                actual[oid] = str(row[0])
    except sqlite3.OperationalError as error:
        raise DatabaseConfigurationError(
            "required Object identities are unavailable: objects table is missing"
        ) from error

    invalid = [
        f"{oid} ({expected_type})"
        for oid, expected_type in required.items()
        if actual.get(oid) != expected_type
    ]
    if invalid:
        raise DatabaseConfigurationError(
            "required Object identities are unavailable: " + ", ".join(invalid)
        )


def connect(home: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    """Open a connection to the GMV database at the resolved home.

    `home` is forwarded to `load_config()` unchanged: when None (the
    default), resolution follows `load_config()`'s own precedence (GMV_HOME,
    then HOME/.gmv_core) — the same precedence already proven identical to
    the old hardcoded path in every currently-exercised case. Returns a live
    sqlite3.Connection with foreign-key enforcement enabled; callers own its
    lifecycle exactly as sqlite3.connect() callers always have.
    """
    paths = GMVPaths.from_config(load_config(home))
    connection = sqlite3.connect(paths.database)
    try:
        return enable_foreign_keys(connection)
    except Exception:
        connection.close()
        raise
