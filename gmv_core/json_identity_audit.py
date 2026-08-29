"""JSON-sourced Object identity conformance check (MAIN-011 diagnostic slice).

Read-only. Detects three problems in `03_STATE/objects/*.json` and
`02_INDEXES/OBJECT_INDEX.json`: OIDs that do not conform to
`OID_CONTRACT.md`, inconsistency between a state file and its index entry,
and a JSON-sourced `type`+`name` pair already canonical in SQLite under a
different OID (a parallel identity, per `ADR_MAIN011_CANONICAL_IDENTITY.md`).

This is diagnostic enforcement only: it reports a conflict after the fact.
It does not lock, freeze, or otherwise prevent a write to these files —
see `10_API/doctor_service.py`'s docstring note on this distinction.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gmv_core.errors import OIDValidationError
from gmv_core.identity import validate_oid
from gmv_core.paths import GMVPaths


@dataclass(frozen=True, slots=True)
class IdentityAuditResult:
    status: str
    message: str


def _load_json(path: Path) -> tuple[Any, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as error:
        return None, f"{path.name}: unreadable or invalid JSON ({error})"


def audit_json_identities(
    paths: GMVPaths, connection: sqlite3.Connection
) -> IdentityAuditResult:
    state_files = sorted(paths.state_objects.glob("*.json")) if paths.state_objects.is_dir() else []
    index_exists = paths.object_index.is_file()

    if not state_files and not index_exists:
        return IdentityAuditResult(
            "PASS", "no JSON-sourced Object identity runtime files present"
        )

    problems: list[str] = []

    state_by_oid: dict[str, dict[str, Any]] = {}
    for file_path in state_files:
        data, error = _load_json(file_path)
        if error is not None:
            problems.append(error)
            continue
        oid = data.get("oid") if isinstance(data, dict) else None
        if not isinstance(oid, str):
            problems.append(f"{file_path.name}: missing or non-string 'oid'")
            continue
        state_by_oid[oid] = {"file": file_path, "data": data}

    index_entries: dict[str, dict[str, Any]] = {}
    if index_exists:
        index_data, error = _load_json(paths.object_index)
        if error is not None:
            problems.append(error)
            index_data = {}
        objects = index_data.get("objects", []) if isinstance(index_data, dict) else []
        for entry in objects:
            oid = entry.get("oid") if isinstance(entry, dict) else None
            if not isinstance(oid, str):
                problems.append(f"{paths.object_index.name}: entry missing or non-string 'oid'")
                continue
            index_entries[oid] = entry

    for oid in sorted(set(state_by_oid) | set(index_entries)):
        in_state = oid in state_by_oid
        in_index = oid in index_entries
        record: dict[str, Any] = state_by_oid[oid]["data"] if in_state else index_entries.get(oid, {})
        object_type = record.get("type") if isinstance(record, dict) else None
        object_name = record.get("name") if isinstance(record, dict) else None

        try:
            validate_oid(oid, expected_type=object_type if isinstance(object_type, str) else None)
        except OIDValidationError as error:
            problems.append(f"{oid}: non-conformant OID ({error})")
            continue

        if in_state and not in_index:
            problems.append(
                f"{oid}: present in {state_by_oid[oid]['file'].name} but missing from "
                f"{paths.object_index.name}"
            )
        elif in_index and not in_state:
            problems.append(f"{oid}: present in {paths.object_index.name} but no matching state file")
        else:
            declared_path = str(index_entries[oid].get("path", ""))
            file_name = state_by_oid[oid]["file"].name
            if not declared_path.endswith(file_name):
                problems.append(
                    f"{oid}: index path {declared_path!r} does not match state file {file_name!r}"
                )

        if object_type and object_name:
            row = connection.execute(
                "SELECT oid FROM objects WHERE type=? AND name=? AND oid<>?",
                (object_type, object_name, oid),
            ).fetchone()
            if row is not None:
                problems.append(
                    f"{oid}: duplicates type={object_type!r} name={object_name!r} "
                    f"already canonical as {row[0]}"
                )

    if problems:
        return IdentityAuditResult("FAIL", "; ".join(problems))
    total = len(set(state_by_oid) | set(index_entries))
    return IdentityAuditResult("PASS", f"{total} JSON-sourced identifier(s) conformant")
