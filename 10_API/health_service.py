#!/usr/bin/env python3
"""Scheduler-safe aggregation of GMV health evidence."""

from __future__ import annotations

import argparse
import json
import signal
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import FrameType
from typing import Any, Callable

import backup_service
from doctor_service import run_checks
from operational_records import read_records, validate_record

UTC = timezone.utc

SCHEMA_VERSION = 1
EXIT_FAILED = 1
EXIT_TIMEOUT = 2


class HealthTimeoutError(TimeoutError):
    """Raised when a scheduled health run exceeds its policy bound."""


@dataclass(frozen=True, )
class HealthResult:
    name: str
    status: str
    classification: str
    message: str


def _parse_datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed.astimezone(UTC)


def _load_service_records(
    records_path: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    valid_records: list[dict[str, Any]] = []
    invalid_records: list[str] = []
    records = read_records(records_path)
    for record in records:
        try:
            validate_record(record)
        except (ValueError, json.JSONDecodeError) as error:
            invalid_records.append(str(error))
        else:
            valid_records.append(record)
    return valid_records, invalid_records


def _service_results(
    records_path: Path,
    *,
    now: datetime,
    stale_after_seconds: int,
) -> list[HealthResult]:
    if not records_path.is_file():
        return [
            HealthResult(
                "service.freshness",
                "UNAVAILABLE",
                "degraded",
                f"operational records unavailable: {records_path}",
            )
        ]
    try:
        records, invalid_records = _load_service_records(records_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [
            HealthResult(
                "service.freshness",
                "UNAVAILABLE",
                "degraded",
                f"invalid operational records: {error}",
            )
        ]
    if not records:
        if invalid_records:
            return [
                HealthResult(
                    "service.freshness",
                    "UNAVAILABLE",
                    "degraded",
                    "historical malformed operational records skipped: "
                    + "; ".join(invalid_records),
                )
            ]
        return [
            HealthResult(
                "service.freshness",
                "UNAVAILABLE",
                "degraded",
                "no operational records",
            )
        ]

    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        service = str(record["service"])
        if service not in latest or _parse_datetime(record["ended_at"]) > _parse_datetime(
            latest[service]["ended_at"]
        ):
            latest[service] = record

    results = []
    for service, record in sorted(latest.items()):
        ended_at = _parse_datetime(record["ended_at"])
        configured_fresh_until = _parse_datetime(record["fresh_until"])
        policy_fresh_until = ended_at + timedelta(seconds=stale_after_seconds)
        fresh_until = min(configured_fresh_until, policy_fresh_until)
        status = str(record["status"])
        note = (
            f"; skipped {len(invalid_records)} malformed historical record(s)"
            if invalid_records
            else ""
        )
        if status != "OK":
            results.append(
                HealthResult(
                    f"service.freshness.{service}",
                    "DEGRADED",
                    "degraded",
                    f"latest status is {status}{note}",
                )
            )
        elif now > fresh_until:
            results.append(
                HealthResult(
                    f"service.freshness.{service}",
                    "DEGRADED",
                    "degraded",
                    f"stale since {fresh_until.isoformat()}{note}",
                )
            )
        else:
            results.append(
                HealthResult(
                    f"service.freshness.{service}",
                    "PASS",
                    "degraded",
                    f"fresh until {fresh_until.isoformat()}{note}",
                )
            )
    return results


def _backup_result(backup_root: Path, *, now: datetime) -> HealthResult:
    try:
        evidence = backup_service.check_freshness(backup_root, now=now)
    except (OSError, ValueError) as error:
        return HealthResult(
            "backup.freshness",
            "FAIL",
            "required",
            f"backup freshness evaluation failed: {error}",
        )
    return HealthResult("backup.freshness", str(evidence["status"]), "required", str(evidence["message"]))


def collect_health(
    database: Path,
    records_path: Path,
    *,
    now: datetime,
    stale_after_seconds: int,
    backup_root: Path | None = None,
) -> list[HealthResult]:
    results = [
        HealthResult(check.name, check.status, "required", check.message)
        for check in run_checks(database)
    ]
    results.extend(
        _service_results(
            records_path,
            now=now,
            stale_after_seconds=stale_after_seconds,
        )
    )
    results.append(
        HealthResult(
            "database.foreign_key_enforcement",
            "UNAVAILABLE",
            "unavailable",
            "requires DB-002",
        )
    )
    results.append(_backup_result(backup_root or Path.home() / ".gmv_backups", now=now))
    return results


def overall_state(results: list[HealthResult]) -> str:
    if any(result.status == "FAIL" for result in results):
        return "failed"
    if any(result.status in {"DEGRADED", "UNAVAILABLE"} for result in results):
        return "degraded"
    return "ready"


def run_with_timeout(function: Callable[[], list[HealthResult]], seconds: float) -> list[HealthResult]:
    if seconds <= 0:
        raise ValueError("timeout must be greater than zero")

    def timeout(_signal_number: int, _frame: FrameType | None) -> None:
        raise HealthTimeoutError(f"health run exceeded {seconds:g} seconds")

    previous = signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return function()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _payload(results: list[HealthResult], observed_at: datetime) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at": observed_at.astimezone(UTC).isoformat(),
        "overall": overall_state(results),
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
            lambda: collect_health(
                options.database,
                options.records,
                now=observed_at,
                stale_after_seconds=options.stale_after_seconds,
                backup_root=options.backup_root,
            ),
            options.timeout_seconds,
        )
    except (HealthTimeoutError, ValueError) as error:
        results = [HealthResult("health.execution", "FAIL", "required", str(error))]
        exit_code = EXIT_TIMEOUT
    else:
        exit_code = EXIT_FAILED if overall_state(results) == "failed" else 0

    payload = _payload(results, observed_at)
    if options.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        for result in results:
            print(
                f"{result.status}|{result.classification}|"
                f"{result.name}|{result.message}"
            )
        print(f"OVERALL|{payload['overall'].upper()}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
