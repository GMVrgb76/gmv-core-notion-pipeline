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


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "10_API" / "backup_service.py"), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


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
    assert "failed" in (root / "audit" / "backup_events.v2.jsonl").read_text()


def test_milestones_are_never_retention_candidates(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    old = datetime(2025, 1, 1, tzinfo=UTC)
    rolling = BACKUP.create_backup(core, root, now=old)
    BACKUP.create_backup(core, root, kind="milestone", milestone="Sprint 002", now=old + timedelta(seconds=1))
    assert BACKUP.retention_candidates(root, now=datetime(2026, 7, 6, tzinfo=UTC)) == [rolling]
    removed = BACKUP.apply_retention(root, now=datetime(2026, 7, 6, tzinfo=UTC))
    assert removed == [rolling.name]
    assert any((root / "sets").iterdir())


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


def test_cli_has_no_live_restore_surface() -> None:
    cli = (ROOT / "11_CLI" / "gmv").read_text()
    assert "restore-check" in cli
    assert "snapshot restore <" not in cli


def test_cli_inspect_verify_and_restore_check_are_stable(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    backup = BACKUP.create_backup(core, root, now=datetime(2026, 7, 6, tzinfo=UTC))
    target = tmp_path / "isolated"

    inspect = _run_cli("inspect", str(backup))
    verify = _run_cli("verify", str(backup))
    restore = _run_cli("restore-check", str(backup), str(target))

    assert inspect.returncode == 0
    manifest = json.loads(inspect.stdout)
    assert manifest["schema_version"] == 1
    assert manifest["policy"] == "GMV Recovery Policy v1"

    assert verify.returncode == 0
    evidence = json.loads(verify.stdout)
    assert evidence["integrity"] == "ok"
    assert evidence["backup_id"] == manifest["backup_id"]

    assert restore.returncode == 0
    restored = json.loads(restore.stdout)
    assert restored["canonical_overwrite"] is False
    assert restored["target"] == str(target)
    assert (target / "09_DATABASE" / "GMV.db").is_file()


def test_cli_create_rejects_encrypt_flag(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"

    result = _run_cli(
        "create",
        "--core",
        str(core),
        "--root",
        str(root),
        "--encrypt",
    )

    assert result.returncode == 1
    assert "key custody is not approved" in result.stderr
    assert not root.exists()


def test_cli_verify_rejects_missing_and_wrong_schema_manifest(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    backup = BACKUP.create_backup(core, root, now=datetime(2026, 7, 6, tzinfo=UTC))

    (backup / "manifest.json").unlink()
    missing = _run_cli("verify", str(backup))
    assert missing.returncode == 1
    assert missing.stderr.startswith("error:")

    backup = BACKUP.create_backup(core, root, now=datetime(2026, 7, 6, tzinfo=UTC))
    manifest_path = backup / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["schema_version"] = 999
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")

    wrong_schema = _run_cli("verify", str(backup))
    assert wrong_schema.returncode == 1
    assert "unsupported backup manifest schema" in wrong_schema.stderr


# --- S002-20 Sprint Review remediation: OID continuity ---------------------


def test_oid_continuity_detects_duplicates_and_malformed(tmp_path: Path) -> None:
    database = tmp_path / "oids.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE objects (oid TEXT)")
        connection.executemany(
            "INSERT INTO objects VALUES (?)",
            [("SRV-000001",), ("SRV-000001",), ("bad-oid",), ("SRV-000003",)],
        )
    continuity = BACKUP._oid_continuity(database)
    assert continuity["duplicates"] == ["SRV-000001"]
    assert continuity["malformed"] == ["bad-oid"]
    assert continuity["by_prefix"]["SRV"] == {"count": 3, "min": 1, "max": 3, "gaps": [2]}


def test_oid_continuity_clean_set_has_no_duplicates_or_gaps(tmp_path: Path) -> None:
    database = tmp_path / "oids.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE objects (oid TEXT)")
        connection.executemany(
            "INSERT INTO objects VALUES (?)", [("SRV-000001",), ("SRV-000002",)]
        )
    continuity = BACKUP._oid_continuity(database)
    assert continuity["duplicates"] == []
    assert continuity["malformed"] == []
    assert continuity["by_prefix"]["SRV"]["gaps"] == []


def test_verify_backup_fails_closed_on_oid_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup = BACKUP.create_backup(_core(tmp_path), tmp_path / "backups")
    monkeypatch.setattr(
        BACKUP,
        "_oid_continuity",
        lambda _database: {"total": 2, "duplicates": ["SRV-000001"], "malformed": [], "by_prefix": {}},
    )
    with pytest.raises(ValueError, match="OID continuity verification failed"):
        BACKUP.verify_backup(backup)


def test_restore_check_detects_oids_missing_from_source(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    backup = BACKUP.create_backup(core, root)
    with sqlite3.connect(core / "09_DATABASE" / "GMV.db") as connection:
        connection.execute("DELETE FROM objects WHERE oid = 'SRV-000001'")
    with pytest.raises(ValueError, match="OID continuity mismatch"):
        BACKUP.restore_check(backup, tmp_path / "restored", core=core)


def test_restore_check_passes_when_source_retains_backed_up_oids(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    backup = BACKUP.create_backup(core, root)
    evidence = BACKUP.restore_check(backup, tmp_path / "restored", core=core)
    assert evidence["source_comparison"]["missing_from_source"] == []
    assert "restored_oid_continuity" in evidence


# --- S002-20 Sprint Review remediation: restore-check audit trail ----------


def _audit_records(root: Path) -> list[dict[str, object]]:
    path = root / "audit" / "backup_events.v2.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_restore_check_records_verified_audit_event(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    backup = BACKUP.create_backup(core, root)
    BACKUP.restore_check(backup, tmp_path / "restored", core=core)
    records = _audit_records(root)
    restores = [record for record in records if record["action"] == "restore.check"]
    assert len(restores) == 1
    assert restores[0]["outcome"] == "verified"
    assert restores[0]["backup_id"] == backup.name
    assert restores[0]["target"] == str(tmp_path / "restored")


def test_restore_check_records_failed_audit_event_on_corruption(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    backup = BACKUP.create_backup(core, root)
    (backup / "database" / "GMV.db").write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        BACKUP.restore_check(backup, tmp_path / "restored", core=core)
    records = _audit_records(root)
    restores = [record for record in records if record["action"] == "restore.check"]
    assert len(restores) == 1
    assert restores[0]["outcome"] == "failed"
    assert restores[0]["error"] == "ValueError"


def test_restore_check_never_writes_live_database(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    backup = BACKUP.create_backup(core, root)
    live_database = core / "09_DATABASE" / "GMV.db"
    before = live_database.read_bytes()
    BACKUP.restore_check(backup, tmp_path / "restored", core=core)
    assert live_database.read_bytes() == before


# --- S002-20 Sprint Review remediation: governed backup.freshness ----------


def test_check_freshness_fails_with_no_evidence(tmp_path: Path) -> None:
    evidence = BACKUP.check_freshness(tmp_path / "backups", now=datetime(2026, 7, 6, tzinfo=UTC))
    assert evidence["status"] == "FAIL"
    assert evidence["message"] == "no backup audit evidence recorded"


def test_check_freshness_pass_when_backup_and_restore_are_current(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)
    backup = BACKUP.create_backup(core, root, now=now)
    BACKUP.restore_check(backup, tmp_path / "restored", core=core, now=now)
    evidence = BACKUP.check_freshness(root, now=now + timedelta(minutes=5))
    assert evidence["status"] == "PASS"
    assert "within the 30d cadence" in evidence["message"]


def test_check_freshness_fails_when_backup_is_stale(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)
    BACKUP.create_backup(core, root, now=now)
    evidence = BACKUP.check_freshness(root, now=now + timedelta(seconds=BACKUP.RPO_SECONDS + 1))
    assert evidence["status"] == "FAIL"
    assert "exceeds the 900s approved RPO" in evidence["message"]


def test_check_freshness_fails_on_broken_audit_chain(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)
    BACKUP.create_backup(core, root, now=now)
    audit_path = root / "audit" / "backup_events.v2.jsonl"
    lines = audit_path.read_text().splitlines()
    record = json.loads(lines[-1])
    record["record_hash"] = "0" * 64
    lines[-1] = json.dumps(record, sort_keys=True, separators=(",", ":"))
    audit_path.write_text("\n".join(lines) + "\n")
    evidence = BACKUP.check_freshness(root, now=now + timedelta(seconds=1))
    assert evidence["status"] == "FAIL"
    assert "backup audit chain invalid" in evidence["message"]


def test_check_freshness_fails_when_latest_backup_manifest_missing(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)
    backup = BACKUP.create_backup(core, root, now=now)
    (backup / "manifest.json").unlink()
    evidence = BACKUP.check_freshness(root, now=now + timedelta(seconds=1))
    assert evidence["status"] == "FAIL"
    assert "failed re-verification" in evidence["message"]


def test_check_freshness_degraded_when_restore_test_never_performed(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    now = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)
    BACKUP.create_backup(core, root, now=now)
    evidence = BACKUP.check_freshness(root, now=now + timedelta(seconds=1))
    assert evidence["status"] == "DEGRADED"
    assert "monthly restore cadence overdue" in evidence["message"]


def test_check_freshness_degraded_when_restore_test_overdue(tmp_path: Path) -> None:
    core = _core(tmp_path)
    root = tmp_path / "backups"
    old = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    old_backup = BACKUP.create_backup(core, root, now=old)
    BACKUP.restore_check(old_backup, tmp_path / "restored-old", core=core, now=old)
    now = old + timedelta(days=40)
    BACKUP.create_backup(core, root, now=now)
    evidence = BACKUP.check_freshness(root, now=now + timedelta(seconds=1))
    assert evidence["status"] == "DEGRADED"
    assert "exceeds the 30d cadence" in evidence["message"]
