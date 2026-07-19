#!/usr/bin/env python3
"""CLI for DB-006 Engine Runs -> Service Runs reconciliation."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from gmv_core.engine_service_runs_migration import (  # noqa: E402
    RECORDED_GATE_COUNTS,
    ExcludedRun,
    MatchedRun,
    apply_migration,
    plan_migration,
    reconcile_evidence,
)
from gmv_core.database import connect_path  # noqa: E402

from audit_integrity import append as append_audit  # noqa: E402
from audit_integrity import validate as validate_audit  # noqa: E402
from backup_service import verify_backup  # noqa: E402

EVIDENCE_RELATIVE_PATH = Path("04_LOGS") / "engine_service_runs_migration.v1.jsonl"
MAPPED_ACTIONS = {"engine_run.migrated", "engine_run.reconciled"}
EXCLUDED_ACTIONS = {"engine_run.excluded", "engine_run.exclusion_reconciled"}


def _database_uri(database: Path) -> str:
    return f"{database.resolve().as_uri()}?mode=ro"


def _validate_milestone_backup(backup_path: Path) -> dict[str, object]:
    verify_backup(backup_path)
    manifest = json.loads((backup_path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("kind") != "milestone":
        raise ValueError(
            f"apply requires a milestone backup, got kind={manifest.get('kind')!r}"
        )
    return manifest


def _cmd_plan(options: argparse.Namespace) -> int:
    with connect_path(_database_uri(options.database), uri=True) as connection:
        plan = plan_migration(connection)
    payload = {
        "counts": {
            "matched": plan.counts[0],
            "pending": plan.counts[1],
            "excluded": plan.counts[2],
        },
        "pending": [asdict(row) for row in plan.pending],
        "excluded": [asdict(row) for row in plan.excluded],
    }
    if options.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            f"matched={plan.counts[0]} pending={plan.counts[1]} "
            f"excluded={plan.counts[2]}"
        )
    return 0


def _existing_evidence(path: Path) -> tuple[set[tuple[int, int]], set[int]]:
    records = validate_audit(path)
    mapped = {
        (int(record["engine_run_id"]), int(record["service_run_id"]))
        for record in records
        if record.get("action") in MAPPED_ACTIONS
    }
    excluded = {
        int(record["engine_run_id"])
        for record in records
        if record.get("action") in EXCLUDED_ACTIONS
    }
    return mapped, excluded


def _append_mapped(
    path: Path,
    row: MatchedRun,
    *,
    action: str,
    observed_at: str,
    backup_id: object = None,
) -> None:
    record = {
        "action": action,
        "engine_run_id": row.engine_run_id,
        "service_run_id": row.service_run_id,
        "engine": row.engine,
        "service_oid": row.service_oid,
        "service_name": row.service_name,
        "run_at": row.run_at,
        "content_sha256": row.content_sha256,
        "observed_at": observed_at,
    }
    if backup_id is not None:
        record["backup_id"] = backup_id
    append_audit(path, record)


def _append_excluded(
    path: Path,
    row: ExcludedRun,
    *,
    action: str,
    observed_at: str,
    backup_id: object = None,
) -> None:
    record = {
        "action": action,
        "engine_run_id": row.engine_run_id,
        "engine": row.engine,
        "run_at": row.run_at,
        "reason": row.reason,
        "content_sha256": row.content_sha256,
        "observed_at": observed_at,
    }
    if backup_id is not None:
        record["backup_id"] = backup_id
    append_audit(path, record)


def _cmd_apply(options: argparse.Namespace) -> int:
    if not options.confirm:
        print("error: apply requires --confirm", file=sys.stderr)
        return 2
    if options.backup is None:
        print("error: apply requires --backup <VERIFIED_MILESTONE_BACKUP_PATH>", file=sys.stderr)
        return 2

    try:
        manifest = _validate_milestone_backup(options.backup)
        evidence_path = options.home / EVIDENCE_RELATIVE_PATH
        _mapped, logged_exclusions = _existing_evidence(evidence_path)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"error: apply precondition failed: {error}", file=sys.stderr)
        return 2

    with connect_path(options.database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        result = apply_migration(
            connection,
            allowed_gate_counts=RECORDED_GATE_COUNTS,
        )

    now = datetime.now(UTC).isoformat()
    for row in result.migrated:
        _append_mapped(
            evidence_path,
            row,
            action="engine_run.migrated",
            observed_at=now,
            backup_id=manifest.get("backup_id"),
        )
    for row in result.excluded:
        if row.engine_run_id not in logged_exclusions:
            _append_excluded(
                evidence_path,
                row,
                action="engine_run.excluded",
                observed_at=now,
                backup_id=manifest.get("backup_id"),
            )

    print(
        f"migrated {len(result.migrated)} row(s); "
        f"excluded {len(result.excluded)} approved row(s); evidence: {evidence_path}"
    )
    return 0


def _cmd_reconcile(options: argparse.Namespace) -> int:
    evidence_path = options.home / EVIDENCE_RELATIVE_PATH
    mapped_logged, excluded_logged = _existing_evidence(evidence_path)
    with connect_path(_database_uri(options.database), uri=True) as connection:
        plan = reconcile_evidence(connection)

    mapped_gap = [
        row
        for row in plan.matched
        if (row.engine_run_id, row.service_run_id) not in mapped_logged
    ]
    excluded_gap = [
        row for row in plan.excluded if row.engine_run_id not in excluded_logged
    ]
    now = datetime.now(UTC).isoformat()
    for row in mapped_gap:
        _append_mapped(
            evidence_path,
            row,
            action="engine_run.reconciled",
            observed_at=now,
        )
    for row in excluded_gap:
        _append_excluded(
            evidence_path,
            row,
            action="engine_run.exclusion_reconciled",
            observed_at=now,
        )

    payload = {
        "mapped": [asdict(row) for row in mapped_gap],
        "excluded": [asdict(row) for row in excluded_gap],
        "pending": len(plan.pending),
    }
    if options.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            f"reconciled {len(mapped_gap)} mapped and {len(excluded_gap)} excluded; "
            f"{len(plan.pending)} pending"
        )
    return 0


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path.home() / ".gmv_core" / "09_DATABASE" / "GMV.db"
    )
    parser.add_argument("--home", type=Path, default=Path.home() / ".gmv_core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--json", action="store_true")

    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--confirm", action="store_true")
    apply_parser.add_argument("--backup", type=Path, default=None)

    reconcile_parser = subparsers.add_parser("reconcile")
    reconcile_parser.add_argument("--json", action="store_true")

    options = parser.parse_args(arguments)
    try:
        if options.command == "plan":
            return _cmd_plan(options)
        if options.command == "apply":
            return _cmd_apply(options)
        return _cmd_reconcile(options)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
