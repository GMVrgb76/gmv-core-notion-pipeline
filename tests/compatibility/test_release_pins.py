"""Pinned legacy releases fail closed on source drift."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY = ROOT / "10_API" / "gmv_compatibility.py"
MARKET_RELEASE = ROOT / "01_RUNTIME" / "legacy" / "market_engine_v2.py"
MARKET_WRAPPER = ROOT / "12_SCHEDULER" / "run_market_engine_compatibility.sh"
INVENTORY = ROOT / "00_CONFIG" / "LEGACY_ENGINE_INVENTORY.md"


def _write_program(path: Path) -> str:
    path.write_text(f"#!{sys.executable}\nprint('ok')\n", encoding="utf-8")
    path.chmod(0o755)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(home: Path, source: Path, expected_hash: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(home),
            "GMV_COMPAT_SOURCE": str(source),
            "GMV_COMPAT_EXPECTED_SHA256": expected_hash,
        }
    )
    return subprocess.run(
        [
            sys.executable,
            str(COMPATIBILITY),
            "release_test",
            "--",
            str(source),
        ],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_matching_release_pin_executes(tmp_path: Path) -> None:
    source = tmp_path / "release.py"
    expected_hash = _write_program(source)

    result = _run(tmp_path, source, expected_hash)

    assert result.returncode == 0
    assert "status OK" in result.stdout


def test_release_hash_drift_fails_before_runtime_writes(tmp_path: Path) -> None:
    source = tmp_path / "release.py"
    expected_hash = _write_program(source)
    source.write_text(source.read_text() + "# drift\n", encoding="utf-8")

    result = _run(tmp_path, source, expected_hash)

    assert result.returncode == 2
    assert "release hash mismatch" in result.stderr
    assert not (tmp_path / ".gmv_core" / "04_LOGS").exists()
    assert not (tmp_path / ".gmv_core" / "05_OUTPUT").exists()


def test_release_source_must_be_exact_command_argument(tmp_path: Path) -> None:
    source = tmp_path / "release.py"
    expected_hash = _write_program(source)
    other = tmp_path / "other.py"
    _write_program(other)
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(tmp_path),
            "GMV_COMPAT_SOURCE": str(source),
            "GMV_COMPAT_EXPECTED_SHA256": expected_hash,
        }
    )

    result = subprocess.run(
        [sys.executable, str(COMPATIBILITY), "release_test", "--", str(other)],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "release source is not present" in result.stderr


def test_market_release_is_local_and_matches_wrapper_and_inventory() -> None:
    wrapper = MARKET_WRAPPER.read_text(encoding="utf-8")
    inventory = INVENTORY.read_text(encoding="utf-8")
    match = re.search(r'GMV_COMPAT_EXPECTED_SHA256="([0-9a-f]{64})"', wrapper)

    assert match is not None
    release_hash = hashlib.sha256(MARKET_RELEASE.read_bytes()).hexdigest()
    assert match.group(1) == release_hash
    assert release_hash in inventory
    assert "01_RUNTIME/legacy/market_engine_v2.py" in wrapper
    assert "Library/CloudStorage/Dropbox" not in wrapper
