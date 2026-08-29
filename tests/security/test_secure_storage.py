"""Restrictive protected-artifact creation behavior."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "10_API"))
import secure_storage as SECURE  # noqa: E402


def test_atomic_write_creates_private_directory_and_file(tmp_path: Path) -> None:
    target = tmp_path / "protected" / "manifest.json"
    SECURE.atomic_write_text(target, "evidence")
    assert target.read_text() == "evidence"
    assert SECURE.mode(target.parent) == 0o700
    assert SECURE.mode(target) == 0o600


def test_existing_unsafe_file_fails_without_overwrite(tmp_path: Path) -> None:
    directory = tmp_path / "protected"
    directory.mkdir(mode=0o700)
    target = directory / "database.db"
    target.write_bytes(b"canonical")
    target.chmod(0o644)
    with pytest.raises(PermissionError, match="unsafe mode"):
        SECURE.atomic_write_bytes(target, b"replacement")
    assert target.read_bytes() == b"canonical"


def test_existing_unsafe_directory_fails_closed(tmp_path: Path) -> None:
    directory = tmp_path / "protected"
    directory.mkdir(mode=0o755)
    with pytest.raises(PermissionError, match="unsafe mode"):
        SECURE.atomic_write_text(directory / "manifest.json", "data")


def test_process_umask_cannot_weaken_created_modes(tmp_path: Path) -> None:
    previous = os.umask(0)
    try:
        target = tmp_path / "protected" / "backup.db"
        SECURE.atomic_write_bytes(target, b"database")
    finally:
        os.umask(previous)
    assert SECURE.mode(target.parent) == 0o700
    assert SECURE.mode(target) == 0o600


def test_failed_replace_removes_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "protected" / "manifest.json"

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr(SECURE.os, "replace", fail_replace)
    with pytest.raises(OSError, match="interrupted"):
        SECURE.atomic_write_text(target, "data")
    assert list(target.parent.iterdir()) == []
