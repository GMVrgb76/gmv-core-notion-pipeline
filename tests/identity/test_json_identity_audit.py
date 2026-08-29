"""JSON-sourced Object identity conformance audit (MAIN-011 diagnostic slice)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from gmv_core.json_identity_audit import audit_json_identities
from gmv_core.paths import GMVPaths

NOW = "2026-01-01T00:00:00"


def _sqlite_connection(tmp_path: Path) -> sqlite3.Connection:
    database = tmp_path / "GMV.db"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE objects (
            oid TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    connection.execute(
        "INSERT INTO objects VALUES ('PER-000001','Person','Giacomo Marco Valerio','active',?,?)",
        (NOW, NOW),
    )
    return connection


def _write_state_and_index(home: Path, oid: str, *, index_oid: str | None = None) -> None:
    state_dir = home / "03_STATE" / "objects"
    state_dir.mkdir(parents=True)
    file_name = f"{oid}_GMV.json"
    (state_dir / file_name).write_text(
        json.dumps({"oid": oid, "type": "Person", "name": "Giacomo Marco Valerio", "status": "active"}),
        encoding="utf-8",
    )
    index_dir = home / "02_INDEXES"
    index_dir.mkdir(parents=True)
    (index_dir / "OBJECT_INDEX.json").write_text(
        json.dumps(
            {
                "version": "0.1",
                "created_at": "2026-07-02",
                "objects": [
                    {
                        "oid": index_oid or oid,
                        "type": "Person",
                        "name": "Giacomo Marco Valerio",
                        "path": f"~/.gmv_core/03_STATE/objects/{file_name}",
                        "status": "active",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_audit_passes_when_runtime_files_absent(tmp_path: Path) -> None:
    connection = _sqlite_connection(tmp_path)
    paths = GMVPaths.from_home(tmp_path / "home")
    result = audit_json_identities(paths, connection)
    assert result.status == "PASS"
    assert result.message == "no JSON-sourced Object identity runtime files present"


def test_audit_passes_when_conformant_and_consistent(tmp_path: Path) -> None:
    connection = _sqlite_connection(tmp_path)
    home = tmp_path / "home"
    _write_state_and_index(home, "PER-000001")
    paths = GMVPaths.from_home(home)
    result = audit_json_identities(paths, connection)
    assert result.status == "PASS"
    assert result.message == "1 JSON-sourced identifier(s) conformant"


def test_audit_fails_on_non_conformant_oid(tmp_path: Path) -> None:
    connection = _sqlite_connection(tmp_path)
    home = tmp_path / "home"
    _write_state_and_index(home, "OBJECT-0000001")
    paths = GMVPaths.from_home(home)
    result = audit_json_identities(paths, connection)
    assert result.status == "FAIL"
    assert "non-conformant OID" in result.message
    assert "OBJECT-0000001" in result.message


def test_audit_fails_on_file_index_inconsistency(tmp_path: Path) -> None:
    connection = _sqlite_connection(tmp_path)
    home = tmp_path / "home"
    # State file is PER-000001, but the index declares a different OID entirely
    # (PER-000002), so PER-000001 is present in state but missing from the
    # index, and PER-000002 is present in the index but has no state file.
    _write_state_and_index(home, "PER-000001", index_oid="PER-000002")
    paths = GMVPaths.from_home(home)
    result = audit_json_identities(paths, connection)
    assert result.status == "FAIL"
    assert "missing from" in result.message
    assert "no matching state file" in result.message


def test_audit_fails_on_type_name_duplication_with_different_oid(tmp_path: Path) -> None:
    connection = _sqlite_connection(tmp_path)
    home = tmp_path / "home"
    _write_state_and_index(home, "PER-000002")
    paths = GMVPaths.from_home(home)
    result = audit_json_identities(paths, connection)
    assert result.status == "FAIL"
    assert "duplicates" in result.message
    assert "already canonical as PER-000001" in result.message
