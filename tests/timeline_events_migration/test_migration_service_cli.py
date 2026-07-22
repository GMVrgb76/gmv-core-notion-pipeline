"""timeline_events_migration_service.py CLI -- isolated, never against the live database.

Covers plan (always read-only), apply (requires --confirm and a verified
milestone backup reference), and reconcile (fills missing/partial evidence
without duplicating, including a simulated crash-after-COMMIT scenario).
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from gmv_core.timeline_events_migration import apply_migration
from tests.characterization.conftest import SCHEMA_FIXTURE

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "10_API" / "timeline_events_migration_service.py"
sys.path.insert(0, str(ROOT / "10_API"))
import backup_service as BACKUP  # noqa: E402

NOW = "2026-01-01T00:00:00"
EVIDENCE_RELATIVE = Path("04_LOGS") / "timeline_events_migration.v1.jsonl"

_INSERT_TIMELINE = (
    "INSERT INTO timeline (oid,event_at,event_type,description,source) VALUES (?,?,?,?,?)"
)
_INSERT_EVENTS = (
    "INSERT INTO events (oid,event_at,event_type,description,source) VALUES (?,?,?,?,?)"
)


def _core(tmp_path: Path, *, name: str = "core") -> Path:
    core = tmp_path / name
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
        connection.executescript(SCHEMA_FIXTURE.read_text(encoding="utf-8"))
        # Clear the fixture's own pre-seeded timeline/events rows (including
        # its intentional id=1 divergence) so this file's tests control exact,
        # predictable counts.
        connection.execute("DELETE FROM timeline")
        connection.execute("DELETE FROM events")
    database.chmod(0o600)
    return core


def _insert(database: Path, table: str, rows: list[tuple]) -> None:
    statement = _INSERT_TIMELINE if table == "timeline" else _INSERT_EVENTS
    with sqlite3.connect(database) as connection:
        connection.executemany(statement, rows)


def _seed_divergence(database: Path) -> None:
    identical = ("SYS-000001", NOW, "identical", "same content", "src")
    _insert(database, "timeline", [identical])
    _insert(database, "events", [identical])
    _insert(database, "timeline", [("SYS-000001", NOW, "collision", "timeline-only-A", "src")])
    _insert(database, "timeline", [("SYS-000001", NOW, "extra", "timeline-only-B", "src")])


def _milestone_backup(core: Path, backups_root: Path) -> Path:
    return BACKUP.create_backup(
        core, backups_root, kind="milestone", milestone="test-slice", now=datetime(2026, 1, 1, tzinfo=UTC)
    )


def _rolling_backup(core: Path, backups_root: Path) -> Path:
    return BACKUP.create_backup(core, backups_root, kind="rolling", now=datetime(2026, 1, 1, tzinfo=UTC))


def _run(core: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["HOME"] = str(core.parent)
    return subprocess.run(
        [
            sys.executable,
            str(SERVICE),
            "--database",
            str(core / "09_DATABASE" / "GMV.db"),
            "--home",
            str(core),
            *arguments,
        ],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _counts(database: Path) -> dict[str, int]:
    with sqlite3.connect(database) as connection:
        return {
            "timeline": int(connection.execute("SELECT COUNT(*) FROM timeline").fetchone()[0]),
            "events": int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]),
        }


# --- plan -------------------------------------------------------------------


def test_plan_is_read_only_and_reports_pending_rows(tmp_path: Path) -> None:
    core = _core(tmp_path)
    database = core / "09_DATABASE" / "GMV.db"
    _seed_divergence(database)
    before = _counts(database)

    result = _run(core, "plan", "--json")

    assert result.returncode == 0
    pending = json.loads(result.stdout)
    assert len(pending) == 2
    assert {row["description"] for row in pending} == {"timeline-only-A", "timeline-only-B"}
    assert _counts(database) == before
    assert not (core / EVIDENCE_RELATIVE).exists()


def test_plan_reports_nothing_pending_when_already_reconciled(tmp_path: Path) -> None:
    core = _core(tmp_path)
    database = core / "09_DATABASE" / "GMV.db"
    identical = ("SYS-000001", NOW, "identical", "same content", "src")
    _insert(database, "timeline", [identical])
    _insert(database, "events", [identical])

    result = _run(core, "plan", "--json")

    assert result.returncode == 0
    assert json.loads(result.stdout) == []


# --- apply: pre-flight validation -------------------------------------------


def test_apply_fails_without_confirm(tmp_path: Path) -> None:
    core = _core(tmp_path)
    _seed_divergence(core / "09_DATABASE" / "GMV.db")

    result = _run(core, "apply", "--backup", str(tmp_path))

    assert result.returncode == 2
    assert "--confirm" in result.stderr
    assert _counts(core / "09_DATABASE" / "GMV.db")["events"] == 1


def test_apply_fails_without_backup_reference(tmp_path: Path) -> None:
    core = _core(tmp_path)
    _seed_divergence(core / "09_DATABASE" / "GMV.db")

    result = _run(core, "apply", "--confirm")

    assert result.returncode == 2
    assert "--backup" in result.stderr
    assert _counts(core / "09_DATABASE" / "GMV.db")["events"] == 1


def test_apply_fails_with_a_rolling_not_milestone_backup(tmp_path: Path) -> None:
    core = _core(tmp_path)
    _seed_divergence(core / "09_DATABASE" / "GMV.db")
    backup = _rolling_backup(core, tmp_path / "backups")

    result = _run(core, "apply", "--confirm", "--backup", str(backup))

    assert result.returncode == 2
    assert "milestone" in result.stderr
    assert _counts(core / "09_DATABASE" / "GMV.db")["events"] == 1


def test_apply_fails_with_a_corrupt_backup_reference(tmp_path: Path) -> None:
    core = _core(tmp_path)
    _seed_divergence(core / "09_DATABASE" / "GMV.db")
    backup = _milestone_backup(core, tmp_path / "backups")
    (backup / "database" / "GMV.db").write_bytes(b"corrupt")

    result = _run(core, "apply", "--confirm", "--backup", str(backup))

    assert result.returncode == 2
    assert "backup reference failed verification" in result.stderr
    assert _counts(core / "09_DATABASE" / "GMV.db")["events"] == 1


# --- apply: success path -----------------------------------------------------


def test_apply_is_blocked_after_db005_write_capability_revocation(tmp_path: Path) -> None:
    core = _core(tmp_path)
    database = core / "09_DATABASE" / "GMV.db"
    _seed_divergence(database)
    backup = _milestone_backup(core, tmp_path / "backups")
    timeline_before = _counts(database)["timeline"]

    result = _run(core, "apply", "--confirm", "--backup", str(backup))

    assert result.returncode == 1
    assert "UnauthorizedWriteError" in result.stderr
    assert "timeline_events_migration.py" in result.stderr
    assert _counts(database) == {"timeline": timeline_before, "events": 1}
    assert not (core / EVIDENCE_RELATIVE).exists()


def test_repeated_apply_attempts_remain_blocked_and_non_mutating(tmp_path: Path) -> None:
    core = _core(tmp_path)
    database = core / "09_DATABASE" / "GMV.db"
    _seed_divergence(database)
    backup = _milestone_backup(core, tmp_path / "backups")

    first = _run(core, "apply", "--confirm", "--backup", str(backup))
    second = _run(core, "apply", "--confirm", "--backup", str(backup))
    assert first.returncode == 1
    assert second.returncode == 1
    assert "UnauthorizedWriteError" in first.stderr
    assert "UnauthorizedWriteError" in second.stderr
    assert _counts(database) == {"timeline": 3, "events": 1}
    assert not (core / EVIDENCE_RELATIVE).exists()


# --- reconcile: crash recovery and partial-log backfill ----------------------


def test_reconcile_recovers_from_a_crash_between_commit_and_audit(tmp_path: Path) -> None:
    """Simulate apply_migration's INSERT+COMMIT having already happened, with
    no evidence ever written (the exact crash window this design defends
    against). reconcile must recover the full, correct mapping with no CLI
    help beyond the DB and timeline/events content."""
    core = _core(tmp_path)
    database = core / "09_DATABASE" / "GMV.db"
    identical = ("SYS-000001", NOW, "identical", "same content", "src")
    migrated_but_unlogged = ("SYS-000001", NOW, "crashed", "no evidence yet", "src")
    _insert(database, "timeline", [identical, migrated_but_unlogged])
    _insert(database, "events", [identical, migrated_but_unlogged])
    assert not (core / EVIDENCE_RELATIVE).exists()

    result = _run(core, "reconcile", "--json")

    assert result.returncode == 0, result.stderr
    reconciled = json.loads(result.stdout)
    assert len(reconciled) == 2  # both pairs backfilled, log started from nothing
    assert _counts(database) == {"timeline": 2, "events": 2}  # untouched by reconcile

    evidence = core / EVIDENCE_RELATIVE
    records = [json.loads(line) for line in evidence.read_text().splitlines() if line]
    assert len(records) == 2
    assert {record["action"] for record in records} == {"timeline_row.reconciled"}


def test_reconcile_backfills_only_the_gap_in_a_partial_log(tmp_path: Path) -> None:
    core = _core(tmp_path)
    database = core / "09_DATABASE" / "GMV.db"
    _seed_divergence(database)
    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        migrated = apply_migration(connection)
        connection.commit()
    assert len(migrated) == 2

    # `apply` only logs the rows it actually inserted (2). The pre-existing
    # "identical" row was never touched by apply and is therefore not yet in
    # the log either; run reconcile once to establish a complete baseline
    # (3 records: the 2 migrated + the 1 always-identical row) before
    # simulating partial loss.
    baseline = _run(core, "reconcile", "--json")
    assert baseline.returncode == 0, baseline.stderr
    evidence = core / EVIDENCE_RELATIVE
    full_log_lines = evidence.read_text().splitlines()
    assert len(full_log_lines) == 3

    # Truncate the evidence log to its first two records, simulating a
    # partial write (the third record never made it to disk).
    evidence.write_text("\n".join(full_log_lines[:2]) + "\n")

    result = _run(core, "reconcile", "--json")

    assert result.returncode == 0, result.stderr
    gap = json.loads(result.stdout)
    assert len(gap) == 1  # only the missing third row is backfilled

    records = [json.loads(line) for line in evidence.read_text().splitlines() if line]
    assert len(records) == 3
    pairs = [(record["timeline_id"], record["events_id"]) for record in records]
    assert len(pairs) == len(set(pairs))  # no duplicate pair logged


def test_reconcile_never_writes_to_timeline_or_events(tmp_path: Path) -> None:
    core = _core(tmp_path)
    database = core / "09_DATABASE" / "GMV.db"
    _seed_divergence(database)
    before = _counts(database)

    result = _run(core, "reconcile", "--json")

    assert result.returncode == 0, result.stderr
    assert _counts(database) == before


def test_reconcile_fails_closed_on_a_corrupted_evidence_log(tmp_path: Path) -> None:
    core = _core(tmp_path)
    database = core / "09_DATABASE" / "GMV.db"
    _seed_divergence(database)
    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        apply_migration(connection)
        connection.commit()
    baseline = _run(core, "reconcile", "--json")
    assert baseline.returncode == 0, baseline.stderr

    evidence = core / EVIDENCE_RELATIVE
    record = json.loads(evidence.read_text().splitlines()[0])
    record["record_hash"] = "0" * 64
    evidence.write_text(json.dumps(record) + "\n")

    result = _run(core, "reconcile", "--json")

    assert result.returncode == 1
    assert "audit chain failure" in result.stderr
