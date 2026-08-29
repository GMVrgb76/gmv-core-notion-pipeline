"""Connection ownership for the Core persistence boundary.

First lifecycle-owning module under ADR_CORE_PERSISTENCE_BOUNDARY.md: resolves
the GMV database path via gmv_core's own configuration surface and opens the
connection. Callers retain sqlite3.Connection's own context-manager semantics
(commit/rollback on exit; the connection is not closed). DB-002 additionally
enables SQLite foreign-key enforcement before returning every Core-owned
connection. SEC-006 additionally installs enforced write-capability
authorization (gmv_core.authorization) on every ordinary connection, with
the statement cache disabled (cached_statements=0) -- required because a
cached prepared statement skips SQLite's authorizer callback entirely on
reuse, regardless of which caller or mode is active.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from collections.abc import Mapping
from pathlib import Path

from gmv_core import authorization
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


def _connect_path(
    database: str | os.PathLike[str],
    *,
    authorization_mode: str,
    uri: bool = False,
    timeout: float = 5.0,
) -> sqlite3.Connection:
    connection = sqlite3.connect(
        database,
        uri=uri,
        timeout=timeout,
        cached_statements=0,
        factory=authorization.AuthorizingConnection,
    )
    try:
        enable_foreign_keys(connection)
        authorization.install(connection, mode=authorization_mode, database=database)
        return connection
    except Exception:
        connection.close()
        raise


def connect_path(
    database: str | os.PathLike[str],
    *,
    uri: bool = False,
    timeout: float = 5.0,
) -> sqlite3.Connection:
    """Open an explicit SQLite target with verified FK enforcement.

    Every ordinary Core connection is opened with ``cached_statements=0``
    and enforced write-capability authorization. The mode is a literal here:
    no production caller or environment setting can weaken it to log-only.
    """
    return _connect_path(
        database,
        authorization_mode="enforce",
        uri=uri,
        timeout=timeout,
    )


def connect_path_isolated_enforcement(
    database: str | os.PathLike[str],
    *,
    isolation_root: str | os.PathLike[str],
    uri: bool = False,
    timeout: float = 5.0,
) -> sqlite3.Connection:
    """Open enforce mode only for a strictly temporary rehearsal target.

    This separate factory is deliberately unsuitable for the live database:
    ``isolation_root`` must be a proper child of the operating-system temp
    directory, SQLite URIs are rejected, and a file-backed target must be the
    exact ``09_DATABASE/GMV.db`` beneath that root. ``:memory:`` is accepted
    so the canonical migration runner can build its baseline signature while
    an isolated rehearsal is active.
    """
    if uri:
        raise DatabaseConfigurationError(
            "isolated enforce mode does not accept SQLite URI targets"
        )

    root = Path(isolation_root).resolve(strict=False)
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=False)
    if root == temporary_root or not root.is_relative_to(temporary_root):
        raise DatabaseConfigurationError(
            f"isolated enforce root must be below the system temp directory: {root}"
        )

    if os.fspath(database) != ":memory:":
        target = Path(database).resolve(strict=False)
        expected = (root / "09_DATABASE" / "GMV.db").resolve(strict=False)
        if target != expected:
            raise DatabaseConfigurationError(
                f"isolated enforce target must be exactly {expected}; got {target}"
            )

    return _connect_path(
        database,
        authorization_mode="enforce",
        timeout=timeout,
    )


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
    return connect_path(paths.database)
