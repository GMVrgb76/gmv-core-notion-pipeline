from __future__ import annotations

import concurrent.futures
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "10_API"))
import audit_integrity as AUDIT  # noqa: E402


def test_concurrent_chain_and_permissions(tmp_path: Path) -> None:
    path = tmp_path / "audit" / "events.jsonl"
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: AUDIT.append(path, {"value": index}), range(30)))
    assert len(AUDIT.validate(path)) == 30
    assert path.stat().st_mode & 0o777 == 0o600


def test_tamper_and_truncated_write_fail(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    AUDIT.append(path, {"value": "original"})
    path.write_text(path.read_text().replace("original", "changed"))
    with pytest.raises(ValueError, match="chain failure"):
        AUDIT.validate(path)
    path.write_text('{"partial":')
    with pytest.raises(ValueError, match="invalid audit JSON"):
        AUDIT.validate(path)
