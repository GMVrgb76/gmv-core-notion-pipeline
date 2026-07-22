"""Safety helpers for tests that must never write to the live GMV database."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import pytest


class LiveDatabaseWriteError(RuntimeError):
    """Raised before a test opens the live database in writable mode."""


def connect_fixture_database(database: str | os.PathLike[str]) -> sqlite3.Connection:
    """Open a disposable schema-test connection with foreign keys enabled.

    Constraint and migration tests use this only when they must insert
    deliberately arbitrary or invalid fixture rows. Production behavior is
    exercised through ``gmv_core.database`` and remains authorization-gated.
    """
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys = ON")
    if connection.execute("PRAGMA foreign_keys").fetchone() != (1,):
        connection.close()
        raise RuntimeError("fixture connection could not enable foreign keys")
    return connection


def _database_path(database: object, *, uri: bool) -> tuple[Path | None, bool]:
    if isinstance(database, int):
        return None, False

    raw = os.fsdecode(os.fspath(database))
    if raw == ":memory:":
        return None, False

    read_only = False
    if uri and raw.startswith("file:"):
        parsed = urlparse(raw)
        raw = unquote(parsed.path)
        read_only = parse_qs(parsed.query).get("mode") == ["ro"]

    return Path(raw).resolve(strict=False), read_only


def install_live_database_guard(
    monkeypatch: pytest.MonkeyPatch,
    live_database: Path,
) -> None:
    """Reject writable sqlite3 connections to the canonical live database."""
    original_connect: Callable[..., sqlite3.Connection] = sqlite3.connect
    canonical_live_database = live_database.resolve(strict=False)

    def guarded_connect(
        database: object,
        *args: Any,
        **kwargs: Any,
    ) -> sqlite3.Connection:
        target, read_only = _database_path(database, uri=bool(kwargs.get("uri")))
        if target == canonical_live_database and not read_only:
            raise LiveDatabaseWriteError(
                f"tests may not open the live database for writing: {target}"
            )
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
