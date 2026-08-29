"""Hash-chained append-only operational audit journal."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path

GENESIS = "0" * 64


def _hash(record: dict[str, object]) -> str:
    body = {key: value for key, value in record.items() if key != "record_hash"}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate(path: Path) -> list[dict[str, object]]:
    records = []
    previous = GENESIS
    if not path.exists():
        return records
    for number, line in enumerate(path.read_text().splitlines(), 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid audit JSON at line {number}") from error
        valid = (
            record.get("sequence") == number
            and record.get("previous_hash") == previous
            and record.get("record_hash") == _hash(record)
        )
        if not valid:
            raise ValueError(f"audit chain failure at line {number}")
        records.append(record)
        previous = str(record["record_hash"])
    return records


def append(path: Path, event: dict[str, object]) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    lock_path = path.with_suffix(path.suffix + ".lock")
    descriptor = os.open(lock_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        records = validate(path)
        previous = str(records[-1]["record_hash"]) if records else GENESIS
        record = {"sequence": len(records) + 1, "previous_hash": previous, **event}
        record["record_hash"] = _hash(record)
        output = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            os.write(output, line.encode())
            os.fsync(output)
        finally:
            os.close(output)
    return record
