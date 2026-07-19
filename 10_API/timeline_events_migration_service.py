#!/usr/bin/env python3
"""CLI for the DB-005 Timeline -> Events data migration (plan/apply/reconcile).

`apply` performs a real, transactional data migration into `events` and
requires explicit confirmation and a reference to a verified milestone
backup -- it is not a diagnostic. `plan` is always read-only. `reconcile`
never writes to `timeline` or `events`, but may append to the evidence log
(04_LOGS/timeline_events_migration.v1.jsonl) to backfill missing or partial
entries.

`timeline` is never dropped, altered, or written by any subcommand here.
"""

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

from gmv_core.timeline_events_migration import (  # noqa: E402
    MatchedRow,
    apply_migration,
    plan_migration,
    reconcile_evidence,
)
from gmv_core.database import connect_path  # noqa: E402

from audit_integrity import append as append_audit  # noqa: E402
from audit_integrity import validate as validate_audit  # noqa: E402
from backup_service import verify_backup  # noqa: E402

EVIDENCE_RELATIVE_PATH = Path("04_LOGS") / "timeline_events_migration.v1.jsonl"
LOGGED_ACTIONS = {"timeline_row.migrated", "timeline_row.reconciled"}


def _database_uri(database: Path) -> str:
    return f"{database.resolve().as_uri()}?mode=ro"


def _row_dict(row: MatchedRow | tuple) -> dict[str, object]:
    if isinstance(row, MatchedRow):
        return asdict(row)
    timeline_id, oid, event_at, event_type, description, source = row
    return {
        "timeline_id": timeline_id,
        "oid": oid,
        "event_at": event_at,
        "event_type": event_type,
        "description": description,
        "source": source,
    }


def _cmd_plan(options: argparse.Namespace) -> int:
    with connect_path(_database_uri(options.database), uri=True) as connection:
        pending = plan_migration(connection)
    payload = [_row_dict(row) for row in pending]
    if options.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        if not payload:
            print("No Timeline rows pending migration.")
        for row in payload:
            print(
                f"timeline_id={row['timeline_id']} oid={row['oid']} "
                f"event_type={row['event_type']} source={row['source']}"
            )
    return 0


def _validate_milestone_backup(backup_path: Path) -> dict[str, object]:
    verify_backup(backup_path)
    manifest = json.loads((backup_path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("kind") != "milestone":
        raise ValueError(
            f"apply requires a milestone backup, got kind={manifest.get('kind')!r}"
        )
    return manifest


def _cmd_apply(options: argparse.Namespace) -> int:
    if not options.confirm:
        print("error: apply requires --confirm", file=sys.stderr)
        return 2
    if options.backup is None:
        print("error: apply requires --backup <VERIFIED_MILESTONE_BACKUP_PATH>", file=sys.stderr)
        return 2

    try:
        manifest = _validate_milestone_backup(options.backup)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"error: backup reference failed verification: {error}", file=sys.stderr)
        return 2

    with connect_path(options.database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        migrated = apply_migration(connection)
        # `with` commits here on normal exit, or rolls back on exception --
        # the evidence log is written only after this block returns, i.e.
        # strictly after COMMIT has already succeeded.

    evidence_path = options.home / EVIDENCE_RELATIVE_PATH
    now = datetime.now(UTC).isoformat()
    for row in migrated:
        append_audit(
            evidence_path,
            {
                "action": "timeline_row.migrated",
                "timeline_id": row.timeline_id,
                "events_id": row.events_id,
                "oid": row.oid,
                "event_at": row.event_at,
                "content_sha256": row.content_sha256,
                "migrated_at": now,
                "backup_id": manifest.get("backup_id"),
            },
        )

    print(f"migrated {len(migrated)} row(s); evidence: {evidence_path}")
    return 0


def _cmd_reconcile(options: argparse.Namespace) -> int:
    evidence_path = options.home / EVIDENCE_RELATIVE_PATH
    existing_records = validate_audit(evidence_path)
    already_logged = {
        (int(record["timeline_id"]), int(record["events_id"]))
        for record in existing_records
        if record.get("action") in LOGGED_ACTIONS
    }

    with connect_path(_database_uri(options.database), uri=True) as connection:
        full_mapping = reconcile_evidence(connection)

    gap = [row for row in full_mapping if (row.timeline_id, row.events_id) not in already_logged]

    now = datetime.now(UTC).isoformat()
    for row in gap:
        append_audit(
            evidence_path,
            {
                "action": "timeline_row.reconciled",
                "timeline_id": row.timeline_id,
                "events_id": row.events_id,
                "oid": row.oid,
                "event_at": row.event_at,
                "content_sha256": row.content_sha256,
                "reconciled_at": now,
            },
        )

    if options.json:
        print(json.dumps([asdict(row) for row in gap], sort_keys=True))
    else:
        print(
            f"reconciled {len(gap)} previously-unlogged row(s); "
            f"{len(full_mapping)} total mapped"
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
