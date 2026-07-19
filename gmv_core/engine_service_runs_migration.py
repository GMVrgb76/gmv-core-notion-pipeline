"""Deterministic Engine Runs -> Service Runs reconciliation for DB-006."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass

SERVICE_IDENTITIES = {
    "knowledge_engine": ("SRV-000001", "Knowledge Engine"),
    "morning_brief": ("SRV-000002", "Morning Brief"),
    "daily_log": ("SRV-000003", "Daily Log"),
    "market_engine": ("SRV-000004", "Market Engine"),
}

# The one Project Owner-approved exclusion is deliberately exact. Any changed
# field or additional unmapped Engine Run is a new reconciliation decision and
# must fail closed rather than being silently classified as historical.
APPROVED_EXCLUDED_ENGINE_RUN = (
    23,
    "gmv_core",
    "2026-07-11T14:13:49",
    "OK",
    0.074014,
    "./11_CLI/gmv constitution check",
    "/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/"
    "2026_07_11_141349_gmv_core.out.log",
    "/Users/giacomomarcovalerio/.gmv_core/05_OUTPUT/compatibility/"
    "2026_07_11_141349_gmv_core.err.log",
    "gmv_core compatibility run completed with status OK, return code 0",
)

RECORDED_GATE_COUNTS = {(5, 25, 1), (30, 0, 1)}

RunPayload = tuple[
    str,
    str,
    float | None,
    str | None,
    str | None,
    str | None,
    str | None,
]
ServiceContent = tuple[str, str, *RunPayload]


@dataclass(frozen=True, slots=True)
class PendingRun:
    engine_run_id: int
    engine: str
    service_oid: str
    service_name: str
    run_at: str
    status: str
    duration_seconds: float | None
    command: str | None
    stdout_path: str | None
    stderr_path: str | None
    summary: str | None
    content_sha256: str


@dataclass(frozen=True, slots=True)
class MatchedRun(PendingRun):
    service_run_id: int


@dataclass(frozen=True, slots=True)
class ExcludedRun:
    engine_run_id: int
    engine: str
    run_at: str
    status: str
    duration_seconds: float | None
    command: str | None
    stdout_path: str | None
    stderr_path: str | None
    summary: str | None
    content_sha256: str
    reason: str = "frozen_unapproved_constitution_cli"


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    matched: tuple[MatchedRun, ...]
    pending: tuple[PendingRun, ...]
    excluded: tuple[ExcludedRun, ...]

    @property
    def counts(self) -> tuple[int, int, int]:
        return len(self.matched), len(self.pending), len(self.excluded)


@dataclass(frozen=True, slots=True)
class MigrationResult:
    migrated: tuple[MatchedRun, ...]
    excluded: tuple[ExcludedRun, ...]


def _content_hash(values: tuple[object, ...]) -> str:
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _engine_rows(connection: sqlite3.Connection) -> list[tuple]:
    return list(
        connection.execute(
            """
            SELECT id,engine,run_at,status,duration_seconds,command,
                   stdout_path,stderr_path,summary
            FROM engine_runs
            ORDER BY id
            """
        )
    )


def _service_rows(connection: sqlite3.Connection) -> list[tuple]:
    return list(
        connection.execute(
            """
            SELECT id,service_oid,service_name,run_at,status,duration_seconds,
                   command,stdout_path,stderr_path,summary
            FROM service_runs
            ORDER BY id
            """
        )
    )


def _pending_run(row: tuple, service_oid: str, service_name: str) -> PendingRun:
    (
        engine_run_id,
        engine,
        run_at,
        status,
        duration_seconds,
        command,
        stdout_path,
        stderr_path,
        summary,
    ) = row
    values = (
        engine,
        service_oid,
        service_name,
        run_at,
        status,
        duration_seconds,
        command,
        stdout_path,
        stderr_path,
        summary,
    )
    return PendingRun(
        engine_run_id=int(engine_run_id),
        engine=str(engine),
        service_oid=service_oid,
        service_name=service_name,
        run_at=str(run_at),
        status=str(status),
        duration_seconds=duration_seconds,
        command=command,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        summary=summary,
        content_sha256=_content_hash(values),
    )


def _excluded_run(row: tuple) -> ExcludedRun:
    return ExcludedRun(
        engine_run_id=int(row[0]),
        engine=str(row[1]),
        run_at=str(row[2]),
        status=str(row[3]),
        duration_seconds=row[4],
        command=row[5],
        stdout_path=row[6],
        stderr_path=row[7],
        summary=row[8],
        content_sha256=_content_hash(tuple(row[1:])),
    )


def _service_content(run: PendingRun) -> ServiceContent:
    return (
        run.service_oid,
        run.service_name,
        run.run_at,
        run.status,
        run.duration_seconds,
        run.command,
        run.stdout_path,
        run.stderr_path,
        run.summary,
    )


def plan_migration(connection: sqlite3.Connection) -> MigrationPlan:
    """Classify every Engine Run by exact, one-to-one payload matching."""
    available: dict[ServiceContent, deque[int]] = defaultdict(deque)
    for service_row in _service_rows(connection):
        available[tuple(service_row[1:])].append(int(service_row[0]))

    matched: list[MatchedRun] = []
    pending: list[PendingRun] = []
    excluded: list[ExcludedRun] = []
    for row in _engine_rows(connection):
        engine = str(row[1])
        identity = SERVICE_IDENTITIES.get(engine)
        if identity is None:
            if tuple(row) != APPROVED_EXCLUDED_ENGINE_RUN:
                raise ValueError(
                    f"unapproved unmapped Engine Run: id={row[0]} engine={engine}"
                )
            excluded.append(_excluded_run(row))
            continue

        candidate = _pending_run(row, *identity)
        bucket = available.get(_service_content(candidate))
        if bucket:
            matched.append(
                MatchedRun(
                    **{
                        field: getattr(candidate, field)
                        for field in candidate.__dataclass_fields__
                    },
                    service_run_id=bucket.popleft(),
                )
            )
        else:
            pending.append(candidate)

    return MigrationPlan(tuple(matched), tuple(pending), tuple(excluded))


def apply_migration(
    connection: sqlite3.Connection,
    *,
    allowed_gate_counts: set[tuple[int, int, int]] | None = None,
) -> MigrationResult:
    """Insert pending mapped runs inside the caller's active transaction."""
    if not connection.in_transaction:
        raise ValueError("Engine-to-Service migration requires an active transaction")

    plan = plan_migration(connection)
    if allowed_gate_counts is not None and plan.counts not in allowed_gate_counts:
        raise ValueError(
            "Engine-to-Service reconciliation gate mismatch: "
            f"matched={plan.counts[0]} pending={plan.counts[1]} "
            f"excluded={plan.counts[2]}"
        )

    migrated: list[MatchedRun] = []
    for run in plan.pending:
        cursor = connection.execute(
            """
            INSERT INTO service_runs
            (service_oid,service_name,run_at,status,duration_seconds,
             command,stdout_path,stderr_path,summary)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            _service_content(run),
        )
        migrated.append(
            MatchedRun(
                **{
                    field: getattr(run, field)
                    for field in run.__dataclass_fields__
                },
                service_run_id=int(cursor.lastrowid),
            )
        )
    return MigrationResult(tuple(migrated), plan.excluded)


def reconcile_evidence(connection: sqlite3.Connection) -> MigrationPlan:
    """Reconstruct current mapped pairs and the approved exclusion from data."""
    return plan_migration(connection)
