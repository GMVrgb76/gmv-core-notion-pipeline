"""Verified full-system backup and isolated restore contract."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.characterization.conftest import SCHEMA_FIXTURE

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "10_API"))
import backup_service as BACKUP  # noqa: E402


def _core(tmp_path: Path) -> Path:
    core = tmp_path / "core"
    core.mkdir()
    subprocess.run(["/usr/bin/git", "init", "-q"], cwd=core, check=True)
    subprocess.run(["/usr/bin/git", "config", "user.email", "test@example.invalid"], cwd=core, check=True)
    subprocess.run(["/usr/bin/git", "config", "user.name", "Test"], cwd=core, check=True)
    (core / "source.txt").write_text("source")
    subprocess.run(["/usr/bin/git", "add", "source.txt"], cwd=core, check=True)
    subprocess.run(["/usr/bin/git", "commit", "-qm", "fixture"], cwd=core, check=True)
    database = core / "09_DATABASE" / "GMV.db"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA_FIXTURE.read_text())
    return core


def test_create_verify_and_isolated_restore(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    backup = BACKUP.create_backup(core, root, now=datetime(2026, 7, 6, tzinfo=UTC))
    evidence = BACKUP.verify_backup(backup)
    restored = tmp_path / "restored"
    restore = BACKUP.restore_check(backup, restored)
    assert evidence["integrity"] == "ok"
    assert restore["canonical_overwrite"] is False
    assert (restored / "09_DATABASE" / "GMV.db").stat().st_mode & 0o777 == 0o600
    assert backup.stat().st_mode & 0o777 == 0o700
    assert (backup / "manifest.json").stat().st_mode & 0o777 == 0o600


def test_corruption_fails_verification(tmp_path: Path) -> None:
    backup = BACKUP.create_backup(_core(tmp_path), tmp_path / "backups")
    (backup / "database" / "GMV.db").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="verification failed"):
        BACKUP.verify_backup(backup)


def test_interrupted_creation_leaves_no_partial_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    monkeypatch.setattr(BACKUP, "verify_backup", lambda _path: (_ for _ in ()).throw(ValueError("stop")))
    with pytest.raises(ValueError, match="stop"):
        BACKUP.create_backup(core, root)
    assert list((root / "sets").iterdir()) == []
    assert "failed" in (root / "audit" / "backup_events.jsonl").read_text()


def test_milestones_are_never_retention_candidates(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    old = datetime(2025, 1, 1, tzinfo=UTC)
    rolling = BACKUP.create_backup(core, root, now=old)
    BACKUP.create_backup(core, root, kind="milestone", milestone="Sprint 002", now=old + timedelta(seconds=1))
    assert BACKUP.retention_candidates(root, now=datetime(2026, 7, 6, tzinfo=UTC)) == [rolling]


def test_restore_refuses_existing_target(tmp_path: Path) -> None:
    backup = BACKUP.create_backup(_core(tmp_path), tmp_path / "backups")
    target = tmp_path / "canonical"
    target.mkdir()
    with pytest.raises(FileExistsError):
        BACKUP.restore_check(backup, target)


def test_manifest_disables_automatic_restore(tmp_path: Path) -> None:
    backup = BACKUP.create_backup(_core(tmp_path), tmp_path / "backups")
    manifest = json.loads((backup / "manifest.json").read_text())
    assert manifest["automatic_restore_authority"] is False
    assert manifest["policy"] == "GMV Recovery Policy v1"
    assert os.path.basename(manifest["entries"][0]["path"]) == "GMV.db"


def test_scheduler_uses_pinned_python_and_private_umask() -> None:
    script = (ROOT / "12_SCHEDULER" / "run_backup.sh").read_text()
    plist = (ROOT / "12_SCHEDULER" / "com.gmv.backup.plist.template").read_text()
    assert ".venv/bin/python" in script
    assert "<key>StartInterval</key>\n  <integer>900</integer>" in plist
    assert "<key>Umask</key>\n  <integer>63</integer>" in plist
