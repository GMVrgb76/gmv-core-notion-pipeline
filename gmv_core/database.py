"""Connection ownership for the Core persistence boundary.

First lifecycle-owning module under ADR_CORE_PERSISTENCE_BOUNDARY.md: resolves
the GMV database path via gmv_core's own configuration surface and opens the
connection. Callers retain sqlite3.Connection's own context-manager semantics
(commit/rollback on exit; the connection is not closed) — this module does not
alter transaction behavior, only who calls sqlite3.connect.
"""

from __future__ import annotations

import os
import sqlite3

from gmv_core.config import load_config
from gmv_core.paths import GMVPaths


def connect(home: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    """Open a connection to the GMV database at the resolved home.

    `home` is forwarded to `load_config()` unchanged: when None (the
    default), resolution follows `load_config()`'s own precedence (GMV_HOME,
    then HOME/.gmv_core) — the same precedence already proven identical to
    the old hardcoded path in every currently-exercised case. Returns a live
    sqlite3.Connection; callers own its lifecycle exactly as sqlite3.connect()
    callers always have.
    """
    paths = GMVPaths.from_config(load_config(home))
    return sqlite3.connect(paths.database)
