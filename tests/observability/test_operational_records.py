"""Structured operational record contract and append behavior."""

from __future__ import annotations

import concurrent.futures
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "operational_records",
    ROOT / "10_API" / "operational_records.py",
)
assert SPEC is not None and SPEC.loader is not None
RECORDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECORDS)
SCHEMA = json.loads(
    (ROOT / "00_CONFIG" / "OPERATIONAL_RUN_RECORD_SCHEMA.json").read_text()
)


def _record(tmp_path: Path, **overrides: object) -> dict[str, object]:
    values = {
        "service": "test_service",
        "status": "OK",
        "error_code": "none",
        "started_at": datetime(2026, 1, 1, tzinfo=UTC),
        "ended_at": datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        "return_code": 0,
        "command": ["tool", "argument"],
        "summary": "completed",
        "artifact_paths": [tmp_path / "missing.log"],
    }
    values.update(overrides)
    return RECORDS.build_record(**values)


def test_record_matches_required_schema_fields(tmp_path: Path) -> None:
    record = _record(tmp_path)

    assert set(record) == set(SCHEMA["required"])
    assert record["schema_version"] == 1
    assert str(record["run_id"]).startswith("RUN-")
    assert str(record["correlation_id"]).startswith("COR-")
    RECORDS.validate_record(record)


def test_missing_and_present_artifacts_are_explicit(tmp_path: Path) -> None:
    present = tmp_path / "present.log"
    present.write_text("evidence", encoding="utf-8")

    record = _record(tmp_path, artifact_paths=[present, tmp_path / "missing.log"])

    available, unavailable = record["artifacts"]
    assert available["availability"] == "available"
    assert available["sha256"]
    assert unavailable == {
        "path": str(tmp_path / "missing.log"),
        "availability": "unavailable",
    }


def test_sensitive_and_oversized_fields_are_redacted_and_bounded(tmp_path: Path) -> None:
    record = _record(
        tmp_path,
        command=["tool", "password=visible", "token:visible", "x" * 5000],
        summary="secret=visible",
    )

    encoded = json.dumps(record)
    assert "visible" not in encoded
    assert "[REDACTED]" in encoded
    assert len(record["command"][-1]) == RECORDS.MAX_FIELD_LENGTH


def test_append_is_concurrent_and_run_ids_are_unique(tmp_path: Path) -> None:
    target = tmp_path / "operations.jsonl"

    def append_one(_index: int) -> str:
        record = _record(tmp_path)
        RECORDS.append_record(target, record)
        return record["run_id"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        run_ids = list(executor.map(append_one, range(40)))

    stored = RECORDS.read_records(target)
    assert len(set(run_ids)) == 40
    assert len(stored) == 40
    assert target.stat().st_mode & 0o777 == 0o600


def test_rotation_preserves_previous_append_log(tmp_path: Path) -> None:
    target = tmp_path / "operations.jsonl"
    first = _record(tmp_path, summary="first")
    second = _record(tmp_path, summary="second")
    RECORDS.append_record(target, first)

    RECORDS.append_record(target, second, rotation_bytes=target.stat().st_size + 1)

    rotated = target.with_suffix(".jsonl.1")
    assert RECORDS.read_records(rotated) == [first]
    assert RECORDS.read_records(target) == [second]


def test_invalid_status_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="status"):
        _record(tmp_path, status="UNKNOWN")
