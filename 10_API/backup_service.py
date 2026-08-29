#!/usr/bin/env python3
"""Create and verify atomic GMV full-system recovery sets."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from secure_storage import atomic_write_text, require_private, secure_directory
from audit_integrity import append as append_audit
from audit_integrity import validate as validate_audit

CORE_ROOT = Path(__file__).resolve().parents[1]
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

database_module = importlib.import_module("gmv_core.database")

UTC = timezone.utc

SCHEMA_VERSION = 1
POLICY_VERSION = "GMV Recovery Policy v1"
ROLLING_DAYS = 90
BACKUP_ID = re.compile(r"^BKP-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
OID = re.compile(r"^(?P<prefix>[A-Z]{3})-(?P<sequence>[0-9]{6})$")

# Recovery Policy v1 (00_CONFIG/RECOVERY_OBJECTIVES.md), approved 2026-07-06.
RPO_SECONDS = 900
RESTORE_CADENCE_DAYS = 30


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
    with database_module.connect_path(source_uri, uri=True) as source_connection:
        with database_module.connect_path(target) as target_connection:
            source_connection.backup(target_connection)
    os.chmod(target, 0o600)


def _resource_evidence(database: Path) -> list[dict[str, object]]:
    uri = f"{database.resolve().as_uri()}?mode=ro"
    with database_module.connect_path(uri, uri=True) as connection:
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


def _oid_continuity(database: Path) -> dict[str, Any]:
    uri = f"{database.resolve().as_uri()}?mode=ro"
    with database_module.connect_path(uri, uri=True) as connection:
        oids = [str(row[0]) for row in connection.execute("SELECT oid FROM objects ORDER BY oid")]
    seen: set[str] = set()
    duplicates: list[str] = []
    malformed: list[str] = []
    sequences_by_prefix: dict[str, list[int]] = {}
    for oid in oids:
        if oid in seen:
            duplicates.append(oid)
        seen.add(oid)
        match = OID.fullmatch(oid)
        if match is None:
            malformed.append(oid)
            continue
        sequences_by_prefix.setdefault(match.group("prefix"), []).append(int(match.group("sequence")))
    by_prefix: dict[str, dict[str, Any]] = {}
    for prefix, sequences in sorted(sequences_by_prefix.items()):
        sequences.sort()
        low, high = sequences[0], sequences[-1]
        gaps = sorted(set(range(low, high + 1)) - set(sequences))
        by_prefix[prefix] = {"count": len(sequences), "min": low, "max": high, "gaps": gaps}
    return {
        "total": len(oids),
        "duplicates": sorted(set(duplicates)),
        "malformed": sorted(malformed),
        "by_prefix": by_prefix,
    }


def _oid_set(database: Path) -> set[str]:
    uri = f"{database.resolve().as_uri()}?mode=ro"
    with database_module.connect_path(uri, uri=True) as connection:
        return {str(row[0]) for row in connection.execute("SELECT oid FROM objects")}


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
    with database_module.connect_path(uri, uri=True) as connection:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = list(connection.execute("PRAGMA foreign_key_check"))
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        object_count = int(connection.execute("SELECT COUNT(*) FROM objects").fetchone()[0])
        event_count = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
    if integrity != "ok" or foreign_keys:
        raise ValueError("restored database integrity verification failed")
    continuity = _oid_continuity(database)
    if continuity["duplicates"] or continuity["malformed"]:
        raise ValueError(f"OID continuity verification failed: {continuity}")
    return {
        "backup_id": manifest["backup_id"],
        "integrity": integrity,
        "foreign_key_violations": len(foreign_keys),
        "user_version": user_version,
        "object_count": object_count,
        "event_count": event_count,
        "oid_continuity": continuity,
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


def apply_retention(root: Path, *, now: datetime | None = None) -> list[str]:
    candidates = retention_candidates(root, now=now)
    verified = [path for path in sorted((root / "sets").glob("BKP-*")) if path not in candidates]
    if not verified:
        raise ValueError("retention would remove the only recovery set")
    removed = []
    for path in candidates:
        shutil.rmtree(path)
        removed.append(path.name)
    return removed


def restore_check(
    backup: Path,
    target: Path,
    *,
    core: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if target.exists():
        raise FileExistsError("restore-check target already exists")
    root = backup.parent.parent
    backup_id = backup.name
    started = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        evidence = verify_backup(backup)
        target.mkdir(mode=0o700)
        database_dir = target / "09_DATABASE"
        database_dir.mkdir(mode=0o700)
        restored_database = database_dir / "GMV.db"
        shutil.copyfile(backup / "database" / "GMV.db", restored_database)
        os.chmod(restored_database, 0o600)
        restored_continuity = _oid_continuity(restored_database)
        if restored_continuity["duplicates"] or restored_continuity["malformed"]:
            raise ValueError(f"restored database OID continuity verification failed: {restored_continuity}")
        evidence["restored_oid_continuity"] = restored_continuity
        if core is not None:
            source_database = core / "09_DATABASE" / "GMV.db"
            missing_from_source = sorted(_oid_set(restored_database) - _oid_set(source_database))
            evidence["source_comparison"] = {"missing_from_source": missing_from_source}
            if missing_from_source:
                raise ValueError(
                    f"OID continuity mismatch: restored OIDs absent from source: {missing_from_source}"
                )
        evidence["target"] = str(target)
        evidence["canonical_overwrite"] = False
        _audit(
            root,
            {
                "action": "restore.check",
                "backup_id": backup_id,
                "at": started.isoformat(),
                "target": str(target),
                "outcome": "verified",
            },
        )
        return evidence
    except BaseException as error:
        _audit(
            root,
            {
                "action": "restore.check",
                "backup_id": backup_id,
                "at": started.isoformat(),
                "target": str(target),
                "outcome": "failed",
                "error": type(error).__name__,
            },
        )
        raise


def _parse_at(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def check_freshness(
    root: Path,
    *,
    now: datetime,
    rpo_seconds: int = RPO_SECONDS,
    restore_cadence_days: int = RESTORE_CADENCE_DAYS,
) -> dict[str, Any]:
    """Governed backup.freshness diagnostic. Fails closed on any unverifiable evidence."""
    audit_path = root / "audit" / "backup_events.v2.jsonl"
    try:
        records = validate_audit(audit_path)
    except (OSError, ValueError) as error:
        return {"status": "FAIL", "message": f"backup audit chain invalid: {error}"}
    if not records:
        return {"status": "FAIL", "message": "no backup audit evidence recorded"}

    backups = [
        record
        for record in records
        if record.get("action") == "backup.create" and record.get("outcome") == "verified"
    ]
    if not backups:
        return {"status": "FAIL", "message": "no verified backup recorded in audit trail"}
    latest_backup = max(backups, key=lambda record: str(record["at"]))
    age_seconds = (now - _parse_at(latest_backup["at"])).total_seconds()
    if age_seconds > rpo_seconds:
        return {
            "status": "FAIL",
            "message": (
                f"latest verified backup {latest_backup['backup_id']} is "
                f"{int(age_seconds)}s old, exceeds the {rpo_seconds}s approved RPO"
            ),
        }

    backup_path = root / "sets" / str(latest_backup["backup_id"])
    try:
        verify_backup(backup_path)
    except (OSError, ValueError, sqlite3.Error) as error:
        return {
            "status": "FAIL",
            "message": f"latest backup {latest_backup['backup_id']} failed re-verification: {error}",
        }

    restores = [
        record
        for record in records
        if record.get("action") == "restore.check" and record.get("outcome") == "verified"
    ]
    if not restores:
        return {
            "status": "DEGRADED",
            "message": (
                f"backup fresh ({int(age_seconds)}s old); no verified isolated restore test "
                f"on record; monthly restore cadence overdue"
            ),
        }
    latest_restore = max(restores, key=lambda record: str(record["at"]))
    restore_age_days = (now - _parse_at(latest_restore["at"])).total_seconds() / 86400
    if restore_age_days > restore_cadence_days:
        return {
            "status": "DEGRADED",
            "message": (
                f"backup fresh ({int(age_seconds)}s old); last verified restore test "
                f"{restore_age_days:.1f}d ago exceeds the {restore_cadence_days}d cadence (overdue)"
            ),
        }
    return {
        "status": "PASS",
        "message": (
            f"backup fresh ({int(age_seconds)}s old); last verified restore test "
            f"{restore_age_days:.1f}d ago, within the {restore_cadence_days}d cadence"
        ),
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--core", type=Path, default=Path.home() / ".gmv_core")
    create.add_argument("--root", type=Path, default=Path.home() / ".gmv_backups")
    create.add_argument("--kind", choices=("rolling", "milestone"), default="rolling")
    create.add_argument("--milestone")
    create.add_argument("--encrypt", action="store_true")
    verify = subparsers.add_parser("verify")
    verify.add_argument("backup", type=Path)
    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("backup", type=Path)
    restore = subparsers.add_parser("restore-check")
    restore.add_argument("backup", type=Path)
    restore.add_argument("target", type=Path)
    restore.add_argument("--core", type=Path, default=None)
    retention = subparsers.add_parser("retention")
    retention.add_argument("--root", type=Path, default=Path.home() / ".gmv_backups")
    retention.add_argument("--apply", action="store_true")
    options = parser.parse_args(arguments)
    try:
        if options.command == "create":
            if options.encrypt:
                raise ValueError("encryption key custody is not approved; refusing")
            result = create_backup(
                options.core,
                options.root,
                kind=options.kind,
                milestone=options.milestone,
            )
            print(result)
        elif options.command == "verify":
            print(json.dumps(verify_backup(options.backup), sort_keys=True))
        elif options.command == "inspect":
            manifest = json.loads((options.backup / "manifest.json").read_text())
            print(json.dumps(manifest, sort_keys=True))
        elif options.command == "restore-check":
            result = restore_check(options.backup, options.target, core=options.core)
            print(json.dumps(result, sort_keys=True))
        else:
            candidates = retention_candidates(options.root)
            result = apply_retention(options.root) if options.apply else [path.name for path in candidates]
            print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
