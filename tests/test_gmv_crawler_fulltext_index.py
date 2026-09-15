"""Crawler preplan step 13: Full-text index (spec v0.2 §21-22).

Uses real sqlite3 connections against tmp_path files (FTS5 is a compiled-
in SQLite feature, not something meaningfully mockable) -- no gmv_core.database
involved anywhere, per the module's own documented reason for bypassing
it (SEC-006's authorizer denies SQLITE_CREATE_VTABLE unconditionally).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

from gmv_atom_validator import AtomCandidate  # noqa: E402
from gmv_crawler_fulltext_index import (  # noqa: E402
    index_atom,
    open_index,
    search_atoms,
)


def make_atom(**overrides) -> AtomCandidate:
    fields = {
        "atom_id": "GMV-ATOM-001",
        "subject": "Federico Garibaldi",
        "predicate": "born_in",
        "predicate_class": "EVENT",
        "object": "Nizza",
        "object_type": "PLACE",
        "source": "SRC-001",
        "status": "VALID",
        "valid_from": None,
        "valid_to": None,
        "asserted_at": "2026-01-01T00:00:00Z",
        "ingested_at": "2026-01-01T00:00:00Z",
        "asserted_by": "gemma4:12b",
        "confidence": 0.9,
        "visibility": "PUBLIC",
    }
    fields.update(overrides)
    return AtomCandidate(**fields)


def test_open_index_creates_file_and_table(tmp_path: Path) -> None:
    db_path = tmp_path / "atoms.db"
    connection = open_index(db_path)
    assert db_path.exists()
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE name = 'atoms_fts'"
    ).fetchall()
    assert tables == [("atoms_fts",)]


def test_open_index_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "atoms.db"
    open_index(db_path).close()
    connection = open_index(db_path)  # must not raise on second call
    assert db_path.exists()
    connection.close()


def test_open_index_requires_existing_parent_directory(tmp_path: Path) -> None:
    missing_parent = tmp_path / "does_not_exist" / "atoms.db"
    with pytest.raises(sqlite3.OperationalError):
        open_index(missing_parent)


def test_index_and_search_round_trip_by_subject(tmp_path: Path) -> None:
    connection = open_index(tmp_path / "atoms.db")
    index_atom(connection, make_atom())
    assert search_atoms(connection, "Garibaldi") == ("GMV-ATOM-001",)


def test_index_and_search_round_trip_by_object(tmp_path: Path) -> None:
    connection = open_index(tmp_path / "atoms.db")
    index_atom(connection, make_atom())
    assert search_atoms(connection, "Nizza") == ("GMV-ATOM-001",)


def test_index_and_search_round_trip_by_predicate(tmp_path: Path) -> None:
    connection = open_index(tmp_path / "atoms.db")
    index_atom(connection, make_atom())
    assert search_atoms(connection, "born_in") == ("GMV-ATOM-001",)


def test_search_no_match_returns_empty_tuple(tmp_path: Path) -> None:
    connection = open_index(tmp_path / "atoms.db")
    index_atom(connection, make_atom())
    assert search_atoms(connection, "Milano") == ()


def test_tokenizer_removes_diacritics(tmp_path: Path) -> None:
    """Grounds the module docstring's tokenizer justification with a real
    query: the Italian corpus this crawler targets uses accented text
    ("città"), and a plain-ASCII query ("citta") must still match it."""
    connection = open_index(tmp_path / "atoms.db")
    index_atom(connection, make_atom(atom_id="GMV-ATOM-002", object="Città di Nizza"))
    assert search_atoms(connection, "citta") == ("GMV-ATOM-002",)


def test_search_respects_limit(tmp_path: Path) -> None:
    connection = open_index(tmp_path / "atoms.db")
    for i in range(5):
        index_atom(connection, make_atom(atom_id=f"GMV-ATOM-{i:03d}"))
    results = search_atoms(connection, "Garibaldi", limit=2)
    assert len(results) == 2


def test_indexing_same_atom_id_twice_creates_two_matching_rows(tmp_path: Path) -> None:
    """Pins the documented v1 gap: no dedup guard exists yet, so indexing
    the same atom_id twice is not rejected and both rows match a search --
    a future consumer must not assume atom_id uniqueness in results."""
    connection = open_index(tmp_path / "atoms.db")
    index_atom(connection, make_atom())
    index_atom(connection, make_atom())
    results = search_atoms(connection, "Garibaldi")
    assert results == ("GMV-ATOM-001", "GMV-ATOM-001")


def test_malformed_fts5_query_raises_operational_error_not_swallowed(tmp_path: Path) -> None:
    connection = open_index(tmp_path / "atoms.db")
    index_atom(connection, make_atom())
    with pytest.raises(sqlite3.OperationalError):
        search_atoms(connection, '"unterminated phrase')
