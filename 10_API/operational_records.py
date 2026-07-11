"""Append-only, bounded operational run records for compatibility services."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc

SCHEMA_VERSION = 1
MAX_FIELD_LENGTH = 4096
DEFAULT_FRESHNESS_SECONDS = 86400
DEFAULT_ROTATION_BYTES = 1024 * 1024
STATUSES = {"OK", "ERROR", "TIMEOUT", "CANCELLED"}
ERROR_CODES = {
    "none",
    "validation",
    "dependency",
    "process_exit",
    "timeout",
    "cancelled",
    "internal",
}
ID_PATTERN = re.compile(r"^(?:RUN|COR)-[0-9a-f]{32}$")
SENSITIVE_PATTERN = re.compile(
    r"(?i)(password|passwd|token|secret|authorization)(\s*[=:]\s*)([^\s]+)"
)


def _bounded(value: object) -> str:
    redacted = SENSITIVE_PATTERN.sub(r"\1\2[REDACTED]", str(value))
    return redacted[:MAX_FIELD_LENGTH]


def _artifact(path: str | Path) -> dict[str, object]:
    artifact = Path(path)
    if not artifact.is_file():
        return {"path": str(artifact), "availability": "unavailable"}
    payload = artifact.read_bytes()
    return {
        "path": str(artifact),
        "availability": "available",
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def build_record(
    *,
    service: str,
    status: str,
    error_code: str,
    started_at: datetime,
    ended_at: datetime,
    return_code: int,
    command: list[str],
    summary: str,
    artifact_paths: list[str | Path],
    correlation_id: str | None = None,
    freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS,
) -> dict[str, object]:
    record = {
        "schema_version": SCHEMA_VERSION,
        "run_id": f"RUN-{uuid.uuid4().hex}",
        "correlation_id": correlation_id or f"COR-{uuid.uuid4().hex}",
        "service": _bounded(service),
        "status": status,
        "error_code": error_code,
        "started_at": started_at.astimezone(UTC).isoformat(),
        "ended_at": ended_at.astimezone(UTC).isoformat(),
        "fresh_until": (ended_at.astimezone(UTC) + timedelta(seconds=freshness_seconds)).isoformat(),
        "return_code": return_code,
        "command": [_bounded(argument) for argument in command],
        "summary": _bounded(summary),
        "artifacts": [_artifact(path) for path in artifact_paths],
        "runbook": "RUNBOOK-NONE" if status == "OK" else "RUNBOOK-COMPATIBILITY-FAILURE",
    }
    validate_record(record)
    return record


def validate_record(record: dict[str, object]) -> None:
    required = {
        "schema_version", "run_id", "correlation_id", "service", "status",
        "error_code", "started_at", "ended_at", "fresh_until", "return_code",
        "command", "summary", "artifacts", "runbook",
    }
    if set(record) != required:
        raise ValueError("operational record fields do not match schema v1")
    if record["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported operational record schema")
    if record["status"] not in STATUSES or record["error_code"] not in ERROR_CODES:
        raise ValueError("invalid operational status or error code")
    for key in ("run_id", "correlation_id"):
        if not isinstance(record[key], str) or ID_PATTERN.fullmatch(record[key]) is None:
            raise ValueError(f"invalid {key}")
    for key in ("service", "summary", "runbook"):
        if not isinstance(record[key], str) or len(record[key]) > MAX_FIELD_LENGTH:
            raise ValueError(f"invalid {key}")
    if not isinstance(record["command"], list) or not isinstance(record["artifacts"], list):
        raise ValueError("command and artifacts must be arrays")


def append_record(
    path: str | Path,
    record: dict[str, object],
    *,
    rotation_bytes: int = DEFAULT_ROTATION_BYTES,
) -> None:
    validate_record(record)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_suffix(target.suffix + ".lock")
    encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with lock_path.open("a+b") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if target.exists() and target.stat().st_size + len(encoded) > rotation_bytes:
            rotated = target.with_suffix(target.suffix + ".1")
            os.replace(target, rotated)
            os.chmod(rotated, 0o600)
        descriptor = os.open(target, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def read_records(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text().splitlines() if line]
