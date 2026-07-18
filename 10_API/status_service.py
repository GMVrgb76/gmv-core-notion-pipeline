#!/usr/bin/env python3
"""Evidence-based GMV status presentation."""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from health_service import (
    HealthResult,
    HealthTimeoutError,
    collect_health,
    overall_state,
    run_with_timeout,
)

SCHEMA_VERSION = 1
UTC = timezone.utc


def _queue_result(database: Path) -> HealthResult:
    uri = f"{database.resolve().as_uri()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as connection:
            count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM import_queue_view "
                    "WHERE status = 'pending' OR review_status = 'pending_review'"
                ).fetchone()[0]
            )
    except (OSError, sqlite3.Error) as error:
        return HealthResult("queue.pending", "FAIL", "required", str(error))
    if count:
        return HealthResult(
            "queue.pending",
            "DEGRADED",
            "degraded",
            f"{count} item(s) require processing or review",
        )
    return HealthResult("queue.pending", "PASS", "degraded", "0 pending items")


def derive_state(results: list[HealthResult]) -> str:
    return overall_state(results)


def collect_status(
    database: Path,
    records: Path,
    *,
    now: datetime,
    stale_after_seconds: int,
    backup_root: Path | None = None,
) -> list[HealthResult]:
    results = collect_health(
        database,
        records,
        now=now,
        stale_after_seconds=stale_after_seconds,
        backup_root=backup_root,
    )
    results.append(_queue_result(database))
    return results


def _payload(results: list[HealthResult], observed_at: datetime) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at": observed_at.astimezone(UTC).isoformat(),
        "state": derive_state(results),
        "checks": [asdict(result) for result in results],
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--database",
        type=Path,
        default=Path.home() / ".gmv_core" / "09_DATABASE" / "GMV.db",
    )
    parser.add_argument(
        "--records",
        type=Path,
        default=Path.home() / ".gmv_core" / "04_LOGS" / "operations.jsonl",
    )
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=Path.home() / ".gmv_backups",
    )
    parser.add_argument("--now", type=datetime.fromisoformat)
    parser.add_argument("--stale-after-seconds", type=int, default=86400)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    options = parser.parse_args(arguments)
    observed_at = (options.now or datetime.now(UTC)).astimezone(UTC)
    try:
        results = run_with_timeout(
            lambda: collect_status(
                options.database,
                options.records,
                now=observed_at,
                stale_after_seconds=options.stale_after_seconds,
                backup_root=options.backup_root,
            ),
            options.timeout_seconds,
        )
    except (HealthTimeoutError, ValueError) as error:
        results = [HealthResult("status.execution", "FAIL", "required", str(error))]
    payload = _payload(results, observed_at)
    if options.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"GMV STATUS|schema={SCHEMA_VERSION}|observed_at={payload['observed_at']}")
        for result in results:
            print(
                f"{result.status}|{result.classification}|"
                f"{result.name}|{result.message}"
            )
        print(f"STATE|{str(payload['state']).upper()}")
    return 1 if payload["state"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
