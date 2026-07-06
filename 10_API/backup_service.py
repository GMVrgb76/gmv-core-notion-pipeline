#!/usr/bin/env python3
"""Create and verify atomic GMV full-system recovery sets."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from secure_storage import atomic_write_text, require_private, secure_directory
from audit_integrity import append as append_audit

SCHEMA_VERSION = 1
POLICY_VERSION = "GMV Recovery Policy v1"
ROLLING_DAYS = 90
BACKUP_ID = re.compile(r"^BKP-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _entry(root: Path, path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed Git executable and argv
        ["/usr/bin/git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _sqlite_backup(source: Path, target: Path) -> None:
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as source_connection:
        with sqlite3.connect(target) as target_connection:
            source_connection.backup(target_connection)
    os.chmod(target, 0o600)


def _resource_evidence(database: Path) -> list[dict[str, object]]:
    uri = f"{database.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute("SELECT oid,path,sha256 FROM resources ORDER BY oid")
        evidence = []
        for oid, raw_path, expected_hash in rows:
            path = Path(str(raw_path))
            available = path.is_file()
            actual_hash = _sha256(path) if available else None
            evidence.append(
                {
                    "oid": str(oid),
                    "path": str(path),
                    "availability": "available" if available else "unavailable",
                    "expected_sha256": str(expected_hash),
                    "actual_sha256": actual_hash,
                    "matches": available and actual_hash == str(expected_hash),
                }
            )
    return evidence


def verify_backup(backup: Path) -> dict[str, Any]:
    require_private(backup, 0o700)
    manifest_path = backup / "manifest.json"
    require_private(manifest_path, 0o600)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported backup manifest schema")
    if not BACKUP_ID.fullmatch(str(manifest.get("backup_id", ""))):
        raise ValueError("invalid backup identity")
    for entry in manifest.get("entries", []):
        path = backup / str(entry["path"])
        if not path.is_file():
            raise ValueError(f"missing backup entry: {entry['path']}")
        if path.stat().st_size != entry["size"] or _sha256(path) != entry["sha256"]:
            raise ValueError(f"backup entry verification failed: {entry['path']}")
    database = backup / "database" / "GMV.db"
    uri = f"{database.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = list(connection.execute("PRAGMA foreign_key_check"))
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        object_count = int(connection.execute("SELECT COUNT(*) FROM objects").fetchone()[0])
        event_count = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
    if integrity != "ok" or foreign_keys:
        raise ValueError("restored database integrity verification failed")
    return {
        "backup_id": manifest["backup_id"],
        "integrity": integrity,
        "foreign_key_violations": len(foreign_keys),
        "user_version": user_version,
        "object_count": object_count,
        "event_count": event_count,
    }


def _audit(root: Path, event: dict[str, object]) -> None:
    audit_dir = root / "audit"
    secure_directory(audit_dir)
    append_audit(audit_dir / "backup_events.v2.jsonl", event)


def create_backup(
    core: Path,
    root: Path,
    *,
    kind: str = "rolling",
    milestone: str | None = None,
    now: datetime | None = None,
) -> Path:
    if kind not in {"rolling", "milestone"}:
        raise ValueError("backup kind must be rolling or milestone")
    if kind == "milestone" and not milestone:
        raise ValueError("milestone backup requires a label")
    observed = (now or datetime.now(UTC)).astimezone(UTC)
    backup_id = f"BKP-{observed.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    secure_directory(root)
    sets = root / "sets"
    secure_directory(sets)
    lock_descriptor = os.open(root / ".backup.lock", os.O_CREAT | os.O_RDWR, 0o600)
    staging = sets / f".{backup_id}.partial"
    final = sets / backup_id
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        staging.mkdir(mode=0o700)
        database_dir = staging / "database"
        database_dir.mkdir(mode=0o700)
        database_copy = database_dir / "GMV.db"
        _sqlite_backup(core / "09_DATABASE" / "GMV.db", database_copy)
        archive = staging / "repository.tar"
        subprocess.run(  # noqa: S603 - fixed Git executable and argv
            ["/usr/bin/git", "archive", "--format=tar", f"--output={archive}", "HEAD"],
            cwd=core,
            check=True,
        )
        os.chmod(archive, 0o600)
        entries = [_entry(staging, database_copy), _entry(staging, archive)]
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "policy": POLICY_VERSION,
            "backup_id": backup_id,
            "created_at": observed.isoformat(),
            "kind": kind,
            "milestone": milestone,
            "source_commit": _git(core, "rev-parse", "HEAD"),
            "entries": entries,
            "resource_evidence": _resource_evidence(database_copy),
            "excluded": ["runtime", "cache", "temporary outputs", "generated indexes"],
            "automatic_restore_authority": False,
        }
        atomic_write_text(staging / "manifest.json", json.dumps(manifest, sort_keys=True, indent=2))
        verify_backup(staging)
        os.replace(staging, final)
        _audit(
            root,
            {
                "action": "backup.create",
                "backup_id": backup_id,
                "at": observed.isoformat(),
                "kind": kind,
                "outcome": "verified",
                "source_commit": manifest["source_commit"],
            },
        )
        return final
    except BaseException as error:
        if staging.exists():
            shutil.rmtree(staging)
        _audit(
            root,
            {
                "action": "backup.create",
                "backup_id": backup_id,
                "at": observed.isoformat(),
                "kind": kind,
                "outcome": "failed",
                "error": type(error).__name__,
            },
        )
        raise
    finally:
        os.close(lock_descriptor)


def retention_candidates(root: Path, *, now: datetime | None = None) -> list[Path]:
    cutoff = (now or datetime.now(UTC)).astimezone(UTC) - timedelta(days=ROLLING_DAYS)
    candidates = []
    for backup in sorted((root / "sets").glob("BKP-*")):
        manifest = json.loads((backup / "manifest.json").read_text())
        created = datetime.fromisoformat(str(manifest["created_at"]))
        if manifest["kind"] == "rolling" and created < cutoff:
            candidates.append(backup)
    return candidates


def restore_check(backup: Path, target: Path) -> dict[str, Any]:
    if target.exists():
        raise FileExistsError("restore-check target already exists")
    evidence = verify_backup(backup)
    target.mkdir(mode=0o700)
    database_dir = target / "09_DATABASE"
    database_dir.mkdir(mode=0o700)
    shutil.copyfile(backup / "database" / "GMV.db", database_dir / "GMV.db")
    os.chmod(database_dir / "GMV.db", 0o600)
    evidence["target"] = str(target)
    evidence["canonical_overwrite"] = False
    return evidence


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--core", type=Path, default=Path.home() / ".gmv_core")
    create.add_argument("--root", type=Path, default=Path.home() / ".gmv_backups")
    create.add_argument("--kind", choices=("rolling", "milestone"), default="rolling")
    create.add_argument("--milestone")
    verify = subparsers.add_parser("verify")
    verify.add_argument("backup", type=Path)
    options = parser.parse_args(arguments)
    try:
        if options.command == "create":
            result = create_backup(
                options.core,
                options.root,
                kind=options.kind,
                milestone=options.milestone,
            )
            print(result)
        else:
            print(json.dumps(verify_backup(options.backup), sort_keys=True))
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
