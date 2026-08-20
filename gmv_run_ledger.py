#!/usr/bin/env python3
"""GMV Run Ledger — reference implementation, contract v0.1.2.

Corrections applied against the first MVP draft are marked [C-n] and are
documented in CORRECTIONS.md.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


LEDGER_ROOT = Path("~/.gmv_core/runs").expanduser()

RUN_SCHEMA = "gmv.run-manifest.v0.1"
EVENT_SCHEMA = "gmv.run-event.v0.1"
ARTIFACT_SCHEMA = "gmv.artifact.v0.1"
STATE_SCHEMA = "gmv.run-state.v0.1"
CHECKPOINT_SCHEMA = "gmv.checkpoint.v0.1"

ACTORS = {"gmv_pipeline", "gmv_recovery", "GMV"}

RUN_TRANSITIONS = {
    (None, "RUN_CREATED"): "CREATED",
    ("CREATED", "RUN_STARTED"): "RUNNING",
    ("CREATED", "RUN_ABORTED"): "ABORTED",
    # [C-9] A crash between RUN_CREATED and RUN_STARTED left the Run
    # permanently unclassifiable: CREATED had no path to INTERRUPTED.
    ("CREATED", "RUN_INTERRUPTED"): "INTERRUPTED",

    ("RUNNING", "RUN_PAUSED"): "PAUSED",
    ("RUNNING", "RUN_FAILED"): "FAILED",
    ("RUNNING", "RUN_INTERRUPTED"): "INTERRUPTED",
    ("RUNNING", "RUN_COMPLETED"): "COMPLETED",
    ("RUNNING", "RUN_ABORTED"): "ABORTED",

    ("PAUSED", "RUN_RESUMED"): "RUNNING",
    ("PAUSED", "RUN_ABORTED"): "ABORTED",

    ("FAILED", "RUN_RESUMED"): "RUNNING",
    ("FAILED", "RUN_ABORTED"): "ABORTED",

    ("INTERRUPTED", "RUN_RESUMED"): "RUNNING",
    ("INTERRUPTED", "RUN_ABORTED"): "ABORTED",
}

STAGE_TRANSITIONS = {
    ("NOT_STARTED", "STAGE_STARTED"): "RUNNING",
    ("NOT_STARTED", "STAGE_SKIPPED"): "SKIPPED",
    ("RUNNING", "STAGE_COMPLETED"): "COMPLETED",
    ("RUNNING", "STAGE_FAILED"): "FAILED",
    ("FAILED", "STAGE_RESTARTED"): "RUNNING",
}

STATE_EVENTS = {
    "RUN_CREATED",
    "RUN_STARTED",
    "RUN_PAUSED",
    "RUN_RESUMED",
    "RUN_FAILED",
    "RUN_INTERRUPTED",
    "RUN_COMPLETED",
    "RUN_ABORTED",
}

STAGE_EVENTS = {
    "STAGE_STARTED",
    "STAGE_RESTARTED",
    "STAGE_COMPLETED",
    "STAGE_FAILED",
    "STAGE_SKIPPED",
}

NON_STATE_EVENTS = {
    "ARTIFACT_REGISTERED",
    "LEDGER_REPAIRED",
    "HUMAN_DECISION",
}

ALL_EVENT_TYPES = STATE_EVENTS | STAGE_EVENTS | NON_STATE_EVENTS

# A Stage boundary is "satisfied" if execution need not revisit it.
SATISFIED_STAGE_STATES = {"COMPLETED", "SKIPPED"}


class LedgerError(RuntimeError):
    pass


class LedgerCorrupt(LedgerError):
    pass


class EventRejected(LedgerError):
    pass


class LockUnavailable(LedgerError):
    pass


class SubstrateError(LedgerError):
    pass


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# Canonical JSON — restricted v0.1 profile
# ---------------------------------------------------------------------------

def _validate_canonical_value(value: Any) -> None:
    if isinstance(value, bool):
        return

    if isinstance(value, float):
        raise LedgerError("Canonical JSON v0.1 forbids floating-point values.")

    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise LedgerError("Canonical JSON object keys must be strings.")
            _validate_canonical_value(child)
        return

    if isinstance(value, list):
        for child in value:
            _validate_canonical_value(child)
        return

    if value is None or isinstance(value, (str, int)):
        return

    raise LedgerError(f"Unsupported canonical JSON value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    _validate_canonical_value(value)

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fsync_file(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        try:
            os.fsync(fd)
        except OSError:
            pass  # Some filesystems reject directory fsync.
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# Deterministic source-set hashing
# ---------------------------------------------------------------------------

def hash_source_set(repo_root: Path, relative_paths: Iterable[str]) -> str:
    """Length-prefixed, order-independent source-set digest.

    Encoding per member:  uint32 len(path) | path UTF-8 | 32 raw digest bytes
    """
    repo_root = repo_root.resolve()
    entries: list[bytes] = []

    for raw in sorted(set(relative_paths)):
        rel = Path(raw)

        if rel.is_absolute():
            raise LedgerError(f"Source path must be relative: {raw}")

        normalized = rel.as_posix()

        if any(ord(c) < 32 for c in normalized):
            raise LedgerError(f"Control character in source path: {normalized!r}")

        path = repo_root / rel

        if path.is_symlink():
            raise LedgerError(f"Symlink forbidden in source set: {path}")

        if not path.is_file():
            raise LedgerError(f"Source-set member is not a file: {path}")

        path_bytes = normalized.encode("utf-8")

        entries.append(
            len(path_bytes).to_bytes(4, "big")
            + path_bytes
            + bytes.fromhex(sha256_file(path))
        )

    digest = hashlib.sha256()
    for entry in entries:
        digest.update(entry)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Atomic JSON (derived caches only)
# ---------------------------------------------------------------------------

def atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(temp_name)

    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(
                json.dumps(
                    payload, ensure_ascii=False, indent=2, sort_keys=True
                ).encode("utf-8")
            )
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp, path)
        fsync_directory(path.parent)

    except Exception:
        temp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Storage substrate (§10.1)
# ---------------------------------------------------------------------------

SYNC_ROOTS = (
    Path("~/Dropbox").expanduser(),
    Path("~/Library/Mobile Documents").expanduser(),
    Path("~/Library/CloudStorage").expanduser(),
    Path("~/Google Drive").expanduser(),
    Path("~/OneDrive").expanduser(),
)

DARWIN_ALLOWED_FS = {"apfs", "hfs"}
LINUX_ALLOWED_FS = {"ext4", "xfs", "btrfs", "zfs", "tmpfs"}


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _nearest_existing(path: Path) -> Path:
    current = path
    while not current.exists():
        if current.parent == current:
            raise SubstrateError(f"No existing ancestor for {path}")
        current = current.parent
    return current.resolve()


def _mount_candidates(path: Path, pairs: Iterable[tuple[Path, str]]):
    best = None
    for mountpoint, fs_type in pairs:
        if not _path_is_within(path, mountpoint):
            continue
        length = len(str(mountpoint))
        if best is None or length > best[0]:
            best = (length, str(mountpoint), fs_type)
    return best


def _darwin_mounts() -> list[tuple[Path, str]]:
    result = subprocess.run(  # noqa: S603 - executable resolved via PATH
        [_required_executable("mount")],
        text=True,
        capture_output=True,
        check=True,
    )
    mounts = []
    for line in result.stdout.splitlines():
        match = re.search(r" on (.+?) \(([^,\s)]+)", line)
        if match:
            mounts.append((Path(match.group(1)), match.group(2)))
    return mounts


def _linux_mounts() -> list[tuple[Path, str]]:
    mounts = []
    with open("/proc/mounts", encoding="utf-8") as handle:
        for line in handle:
            fields = line.split()
            if len(fields) >= 3:
                mounts.append((Path(fields[1].replace("\\040", " ")), fields[2]))
    return mounts


def verify_substrate(root: Path = LEDGER_ROOT) -> dict:
    root = root.expanduser()

    # [C-10] Resolve the *intended* path, not only its nearest existing
    # ancestor: a not-yet-created runs/ under a sync root must still fail.
    intended = root.resolve()
    existing = _nearest_existing(root)

    for sync_root in SYNC_ROOTS:
        if not sync_root.exists():
            continue
        sync_resolved = sync_root.resolve()
        if _path_is_within(intended, sync_resolved) or _path_is_within(
            existing, sync_resolved
        ):
            raise SubstrateError(
                f"Ledger cannot reside under sync root: {sync_resolved}"
            )

    system = platform.system()

    if system == "Darwin":
        found = _mount_candidates(existing, _darwin_mounts())
        allowed = DARWIN_ALLOWED_FS
    elif system == "Linux":
        found = _mount_candidates(existing, _linux_mounts())
        allowed = LINUX_ALLOWED_FS
    else:
        raise SubstrateError(f"Unsupported operating system: {system}")

    if found is None:
        raise SubstrateError(f"Cannot identify mount point for {existing}")

    _, mountpoint, fs_type = found

    if fs_type.lower() not in allowed:
        raise SubstrateError(
            f"Unsupported Ledger filesystem: {fs_type} at {mountpoint}"
        )

    return {
        "resolved_path": str(intended),
        "mountpoint": mountpoint,
        "filesystem": fs_type,
    }


# ---------------------------------------------------------------------------
# Lock (§22, B2)
# ---------------------------------------------------------------------------

class RunLock:
    """Exclusive advisory lock on the Run.

    [C-1] CRITICAL. release() must NOT issue LOCK_UN. An flock is held by the
    open file description, which is shared with every child that inherited the
    descriptor. LOCK_UN releases the lock for all of them at once, which is
    precisely the guarantee B2 relies on. Closing the parent's descriptor
    leaves the lock held until the last inheriting child exits.
    """

    def __init__(self, path: Path):
        self.path = path
        self.fd: int | None = None

    def acquire(self, blocking: bool = False) -> None:
        if self.fd is not None:
            raise LedgerError(f"Lock already held: {self.path}")

        self.path.parent.mkdir(parents=True, exist_ok=True)

        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        os.set_inheritable(fd, True)

        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB

        try:
            fcntl.flock(fd, flags)
        except BlockingIOError:
            os.close(fd)
            raise LockUnavailable(str(self.path))
        except OSError:
            os.close(fd)
            raise

        self.fd = fd

    def release(self) -> None:
        if self.fd is None:
            return
        fd, self.fd = self.fd, None
        os.close(fd)  # [C-1] close only — never LOCK_UN.

    def __enter__(self) -> "RunLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


# ---------------------------------------------------------------------------
# Code identity
# ---------------------------------------------------------------------------

def git_commit(repo_root: Path) -> str:
    result = subprocess.run(  # noqa: S603 - executable resolved via PATH
        [_required_executable("git"), "rev-parse", "HEAD"],
        cwd=repo_root, text=True, capture_output=True, check=True,
    )
    return result.stdout.strip()


def git_dirty(repo_root: Path) -> bool:
    result = subprocess.run(  # noqa: S603 - executable resolved via PATH
        [
            _required_executable("git"),
            "status",
            "--porcelain",
            "--untracked-files=all",
        ],
        cwd=repo_root, text=True, capture_output=True, check=True,
    )
    return bool(result.stdout.strip())


@dataclass
class RunIdentity:
    """[C-6] Repository and configuration identity, captured once per Run.

    The draft recomputed git state and the configuration hash at every stage,
    so an edit made while the pipeline was running silently produced two
    different fingerprints inside one Run. Capturing once makes intra-run
    fingerprint comparison (§35 Rule 2) meaningful.
    """
    repo_root: Path
    git_commit: str
    git_dirty: bool
    config_hash: str
    source_hashes: dict[tuple[str, ...], str] = field(default_factory=dict)

    @classmethod
    def capture(
        cls,
        repo_root: Path,
        config_path: Path,
        component_source_sets: dict[str, list[str]] | None = None,
    ) -> "RunIdentity":
        repo_root = repo_root.resolve()
        commit = git_commit(repo_root)
        dirty = git_dirty(repo_root)
        source_hashes = {}
        if dirty:
            for source_set in (component_source_sets or {}).values():
                key = tuple(sorted(set(source_set)))
                source_hashes[key] = hash_source_set(repo_root, key)

        return cls(
            repo_root=repo_root,
            git_commit=commit,
            git_dirty=dirty,
            config_hash=sha256_file(config_path),
            source_hashes=source_hashes,
        )

    def fingerprint(
        self,
        *,
        component_name: str,
        source_set: Iterable[str],
        stage_contract_version: int,
    ) -> dict:
        source_key = tuple(sorted(set(source_set)))
        if self.git_dirty and source_key not in self.source_hashes:
            raise LedgerError(
                "Dirty component source set was not captured at Run creation: "
                f"{source_key!r}"
            )

        return {
            "name": component_name,
            "git_commit": self.git_commit,
            "git_dirty": self.git_dirty,
            "source_hash": (
                self.source_hashes[source_key]
                if self.git_dirty
                else None
            ),
            "configuration_hash": self.config_hash,
            "stage_contract_version": stage_contract_version,
        }


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

@dataclass
class ReplayResult:
    events: list[dict] = field(default_factory=list)
    valid_end: int = 0
    discarded_bytes: int = 0


def read_events(path: Path) -> ReplayResult:
    if not path.exists():
        return ReplayResult()

    data = path.read_bytes()
    if not data:
        return ReplayResult()

    # [C-2] split(b"\n") rather than splitlines(): bytes.splitlines() also
    # breaks on \r, which would silently reinterpret record boundaries.
    chunks = data.split(b"\n")
    trailing = chunks.pop()  # b"" when the file ends with a newline

    events: list[dict] = []
    valid_end = 0

    for index, raw in enumerate(chunks, start=1):
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise LedgerCorrupt(f"Malformed record at line {index}: {exc}") from exc
        valid_end += len(raw) + 1

    # [C-3] Validate the committed prefix in BOTH branches. The draft skipped
    # validation whenever the tail was truncated, so a corrupt ledger with a
    # partial last line replayed as clean.
    validate_event_sequence(events)

    return ReplayResult(events, valid_end, len(trailing))


def validate_event_sequence(events: list[dict]) -> None:
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise LedgerCorrupt(
                f"Record {index} must be a JSON object, got "
                f"{type(event).__name__}."
            )

        if event.get("schema") != EVENT_SCHEMA:
            raise LedgerCorrupt(f"Unsupported event schema: {event.get('schema')!r}")

        if event.get("seq") != index:
            raise LedgerCorrupt(
                f"Illegal seq: expected {index}, got {event.get('seq')!r}"
            )

        if event.get("actor") not in ACTORS:
            raise LedgerCorrupt(f"Illegal actor: {event.get('actor')!r}")

        if event.get("event_type") not in ALL_EVENT_TYPES:
            raise LedgerCorrupt(f"Unknown event type: {event.get('event_type')!r}")

        component = event.get("component")
        if component is not None and not isinstance(component, dict):
            raise LedgerCorrupt(
                f"Invalid component fingerprint at seq {index}: expected object."
            )
        if component and component.get("git_dirty") and not component.get("source_hash"):
            raise LedgerCorrupt("Dirty component fingerprint without source_hash.")


def reduce_recorded_state(events: list[dict]) -> dict:
    run_state: str | None = None
    stages: dict[str, str] = {}

    for event in events:
        event_type = event["event_type"]

        if event_type in STATE_EVENTS:
            key = (run_state, event_type)
            if key not in RUN_TRANSITIONS:
                raise LedgerCorrupt(
                    f"Illegal Run transition: {run_state} + {event_type}"
                )
            run_state = RUN_TRANSITIONS[key]

        elif event_type in STAGE_EVENTS:
            stage = event.get("stage")
            if not stage:
                raise LedgerCorrupt(f"{event_type} missing stage")

            previous = stages.get(stage, "NOT_STARTED")
            key = (previous, event_type)
            if key not in STAGE_TRANSITIONS:
                raise LedgerCorrupt(
                    f"Illegal Stage transition: {stage}: {previous} + {event_type}"
                )
            stages[stage] = STAGE_TRANSITIONS[key]

    return {"run_state": run_state, "stages": stages}


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

class RunLedger:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir.resolve()
        self.events_path = self.run_dir / "events.jsonl"
        self.manifest_path = self.run_dir / "run_manifest.json"
        self.state_path = self.run_dir / "run_state.json"
        self.artifacts_index_path = self.run_dir / "artifacts.jsonl"
        self.lock = RunLock(self.run_dir / "run.lock")

        self._manifest: dict | None = None
        self._replay: ReplayResult | None = None
        self._replay_size: int | None = None

    # -- manifest ----------------------------------------------------------

    @property
    def manifest(self) -> dict:
        # [C-4] The manifest is immutable after RUN_STARTED; the draft re-read
        # and re-parsed it on every append.
        if self._manifest is None:
            self._manifest = json.loads(
                self.manifest_path.read_text(encoding="utf-8")
            )
        return self._manifest

    # -- replay ------------------------------------------------------------

    def replay(self, *, force: bool = False) -> ReplayResult:
        """[C-5] Cached replay.

        The draft re-read and re-validated the whole ledger on every append and
        again inside refresh_state_cache(), making a Run quadratic in its own
        event count. The cache is keyed on file size and is only trusted while
        this process holds the lock, so it can never mask another writer.
        """
        size = self.events_path.stat().st_size if self.events_path.exists() else 0

        if (
            force
            or self._replay is None
            or self._replay_size != size
            or self.lock.fd is None
        ):
            self._replay = read_events(self.events_path)
            self._replay_size = size

        return self._replay

    def recorded_state(self) -> dict:
        return reduce_recorded_state(self.replay().events)

    # -- append ------------------------------------------------------------

    def append_event(self, *, actor: str, event_type: str, **fields) -> dict:
        if self.lock.fd is None:
            raise EventRejected("Run lock must be held before appending events.")

        if actor not in ACTORS:
            raise EventRejected(f"Invalid actor: {actor}")

        if event_type not in ALL_EVENT_TYPES:
            raise EventRejected(f"Invalid event type: {event_type}")

        replay = self.replay()

        if replay.discarded_bytes:
            raise EventRejected(
                "Ledger tail is truncated; repair required before append."
            )

        event = {
            "schema": EVENT_SCHEMA,
            "seq": len(replay.events) + 1,
            "run_id": self.manifest["run_id"],
            "timestamp": utc_now(),
            "event_type": event_type,
            "actor": actor,
            **fields,
        }

        # Reject an illegal transition before it reaches disk (§70).
        reduce_recorded_state(replay.events + [event])

        payload = canonical_json_bytes(event) + b"\n"

        with self.events_path.open("ab") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        # Commit point passed. Update the in-memory projection, then caches.
        replay.events.append(event)
        replay.valid_end += len(payload)
        self._replay_size = self.events_path.stat().st_size

        self._refresh_derived()
        return event

    def repair_truncated_tail(self) -> dict | None:
        if self.lock.fd is None:
            raise EventRejected("Run lock required for repair.")

        replay = self.replay(force=True)
        if not replay.discarded_bytes:
            return None

        original_size = self.events_path.stat().st_size
        discarded = original_size - replay.valid_end

        with self.events_path.open("r+b") as handle:
            handle.truncate(replay.valid_end)
            handle.flush()
            os.fsync(handle.fileno())

        fsync_directory(self.events_path.parent)

        self.replay(force=True)

        return self.append_event(
            actor="gmv_recovery",
            event_type="LEDGER_REPAIRED",
            discarded_bytes=discarded,
            truncated_at_offset=replay.valid_end,
            last_valid_seq=len(replay.events),
        )

    # -- derived caches ----------------------------------------------------

    def _refresh_derived(self) -> None:
        replay = self.replay()
        state = reduce_recorded_state(replay.events)
        requested = self.manifest.get("requested_stages", [])

        ordered = [s for s in requested if s in state["stages"]]

        completed = [s for s in ordered if state["stages"][s] == "COMPLETED"]
        running = [s for s in ordered if state["stages"][s] == "RUNNING"]

        atomic_json_write(
            self.state_path,
            {
                "schema": STATE_SCHEMA,
                "run_id": self.manifest["run_id"],
                "recorded_state": state["run_state"],
                "stages": state["stages"],
                "current_stage": running[-1] if running else None,
                "last_completed_stage": completed[-1] if completed else None,
                "last_event_seq": replay.events[-1]["seq"] if replay.events else 0,
                "updated_at": utc_now(),
            },
        )

        # artifacts.jsonl is a derived index (§11): rewritten wholesale, never
        # appended to independently of the event stream.
        lines = [
            canonical_json_bytes(e["artifact"]).decode("utf-8")
            for e in replay.events
            if e["event_type"] == "ARTIFACT_REGISTERED"
        ]
        tmp = self.artifacts_index_path.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
        os.replace(tmp, self.artifacts_index_path)

    # -- artifacts ---------------------------------------------------------

    def register_artifact(
        self,
        *,
        actor: str,
        stage: str,
        artifact_type: str,
        path: Path,
        component: dict,
        input_artifacts: list[str] | None = None,
        record_count: int | None = None,
    ) -> dict:
        path = path.resolve()

        if not path.is_file():
            raise LedgerError(f"Artifact does not exist: {path}")

        if not _path_is_within(path, self.run_dir):
            raise LedgerError(f"Artifact outside Run directory: {path}")

        # [C-7] The draft fsynced the file but not its directory entry, so a
        # crash could leave a committed ARTIFACT_REGISTERED event pointing at a
        # file that never became durable.
        fsync_file(path)
        fsync_directory(path.parent)

        artifact = {
            "schema": ARTIFACT_SCHEMA,
            "artifact_id": f"art_{len(self.artifacts()) + 1:06d}",
            "artifact_type": artifact_type,
            "path": path.relative_to(self.run_dir).as_posix(),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "input_artifacts": input_artifacts or [],
        }

        if record_count is not None:
            artifact["record_count"] = record_count

        self.append_event(
            actor=actor,
            event_type="ARTIFACT_REGISTERED",
            stage=stage,
            component=component,
            artifact=artifact,
        )

        return artifact

    def artifacts(self) -> list[dict]:
        return [
            event["artifact"]
            for event in self.replay().events
            if event["event_type"] == "ARTIFACT_REGISTERED"
        ]

    def artifact_by_id(self, artifact_id: str) -> dict:
        for artifact in self.artifacts():
            if artifact["artifact_id"] == artifact_id:
                return artifact
        raise LedgerError(f"Unknown artifact: {artifact_id}")

    def verify_artifact(self, artifact: dict) -> tuple[bool, str | None]:
        path = self.run_dir / artifact["path"]

        if not path.is_file():
            return False, "FILE_MISSING"

        if path.stat().st_size != artifact["size_bytes"]:
            return False, "SIZE_MISMATCH"

        if sha256_file(path) != artifact["sha256"]:
            return False, "HASH_MISMATCH"

        return True, None

    # -- checkpoints (derived projection, §37) -----------------------------

    def evaluate_checkpoint(self, stage: str) -> dict:
        events = self.replay().events
        state = reduce_recorded_state(events)
        stage_state = state["stages"].get(stage, "NOT_STARTED")

        requested = self.manifest["requested_stages"]
        failures: list[str] = []

        if stage in requested:
            index = requested.index(stage)
            resume_from = (
                requested[index + 1] if index + 1 < len(requested) else None
            )
        else:
            resume_from = None
            failures.append("STAGE_NOT_REQUESTED")

        # [C-8] A SKIPPED stage is a satisfied boundary. The draft treated it
        # as unsatisfied, so a Run started with --rows (10_EXTRACT skipped)
        # always reported resume_from = 10_EXTRACT and demanded a full rerun.
        if stage_state == "SKIPPED":
            return {
                "schema": CHECKPOINT_SCHEMA,
                "checkpoint_id": f"cp_{stage.lower()}_skipped",
                "run_id": self.manifest["run_id"],
                "stage": stage,
                "stage_state": "SKIPPED",
                "derived_from_seq": _last_seq_for(events, stage, "STAGE_SKIPPED"),
                "evaluated_at": utc_now(),
                "resume_from": resume_from,
                "input_artifacts": [],
                "output_artifacts": [],
                "valid": not failures,
                **({"failed_conditions": failures} if failures else {}),
            }

        completion = None
        for event in events:
            if event["event_type"] == "STAGE_COMPLETED" and event.get("stage") == stage:
                completion = event

        if completion is None:
            failures.append("STAGE_NOT_COMPLETED")
            derived_seq = 0
            inputs: list[str] = []
            outputs: list[str] = []
        else:
            derived_seq = completion["seq"]
            inputs = completion.get("input_artifacts", [])
            outputs = completion.get("output_artifacts", [])

            if not completion.get("component"):
                failures.append("COMPONENT_FINGERPRINT_MISSING")

            for role, ids in (("INPUT", inputs), ("OUTPUT", outputs)):
                for artifact_id in ids:
                    try:
                        artifact = self.artifact_by_id(artifact_id)
                    except LedgerError:
                        failures.append(f"{role}_NOT_REGISTERED:{artifact_id}")
                        continue

                    valid, reason = self.verify_artifact(artifact)
                    if not valid:
                        failures.append(f"{role}_{reason}:{artifact_id}")

        return {
            "schema": CHECKPOINT_SCHEMA,
            "checkpoint_id": f"cp_{stage.lower()}_complete",
            "run_id": self.manifest["run_id"],
            "stage": stage,
            "stage_state": stage_state,
            "derived_from_seq": derived_seq,
            "evaluated_at": utc_now(),
            "resume_from": resume_from,
            "input_artifacts": inputs,
            "output_artifacts": outputs,
            "valid": not failures,
            **({"failed_conditions": failures} if failures else {}),
        }


def _last_seq_for(events: list[dict], stage: str, event_type: str) -> int:
    seq = 0
    for event in events:
        if event["event_type"] == event_type and event.get("stage") == stage:
            seq = event["seq"]
    return seq


# ---------------------------------------------------------------------------
# Run creation
# ---------------------------------------------------------------------------

def create_run(
    *,
    identity: RunIdentity,
    requested_stages: list[str],
    source_identity: str,
    config_path: Path,
    component_source_sets: dict[str, list[str]],
    stage_contract_versions: dict[str, int],
    ledger_root: Path = LEDGER_ROOT,
) -> RunLedger:
    ledger_root = ledger_root.expanduser()
    verify_substrate(ledger_root)

    ledger_root.mkdir(parents=True, exist_ok=True)
    active_dir = ledger_root / "_active"
    active_dir.mkdir(exist_ok=True)

    run_uuid = str(uuid.uuid4())
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"GMV-{stamp}-{run_uuid[:4].upper()}"

    run_dir = ledger_root / run_id
    run_dir.mkdir(mode=0o700)

    for relative in (
        "artifacts/extract",
        "artifacts/adapted",
        "artifacts/audit",
        "artifacts/remediation",
        "logs",
        "errors",
        "checkpoints",
    ):
        (run_dir / relative).mkdir(parents=True, exist_ok=True)

    atomic_json_write(
        run_dir / "run_manifest.json",
        {
            "schema": RUN_SCHEMA,
            "run_id": run_id,
            "run_uuid": run_uuid,
            "created_at": utc_now(),
            "pipeline": {
                "name": "gmv-core-notion-pipeline",
                "git_commit": identity.git_commit,
                "git_dirty": identity.git_dirty,
            },
            "host": {
                "hostname": socket.gethostname(),
                "pid": os.getpid(),
                "boot_id": _boot_id(),
            },
            "source": {"type": "notion", "source_identity": source_identity},
            "configuration": {
                "sha256": identity.config_hash,
                "path": str(config_path.resolve()),
            },
            "component_source_sets": component_source_sets,
            "stage_contract_versions": stage_contract_versions,
            "requested_stages": requested_stages,
        },
    )

    # [C-11] Register in _active BEFORE the first event (§53). The draft
    # created the symlink after RUN_STARTED, so a crash in that window left an
    # interrupted Run undiscoverable by gmv_recovery.
    link = active_dir / run_id
    if not link.exists():
        link.symlink_to(run_dir)
    fsync_directory(active_dir)

    ledger = RunLedger(run_dir)
    ledger.lock.acquire()

    ledger.append_event(actor="gmv_pipeline", event_type="RUN_CREATED")
    ledger.append_event(actor="gmv_pipeline", event_type="RUN_STARTED")

    return ledger


def deactivate_run(run_id: str, ledger_root: Path = LEDGER_ROOT) -> None:
    active_dir = ledger_root.expanduser() / "_active"
    link = active_dir / run_id
    try:
        link.unlink()
    except FileNotFoundError:
        pass
    else:
        fsync_directory(active_dir)


def _required_executable(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise LedgerError(f"Required executable not found: {name}")
    return executable


def _boot_id() -> str | None:
    system = platform.system()

    if system == "Linux":
        path = Path("/proc/sys/kernel/random/boot_id")
        if path.exists():
            return path.read_text().strip()

    if system == "Darwin":
        try:
            sysctl = shutil.which("sysctl")
            if sysctl is None:
                return None
            result = subprocess.run(  # noqa: S603 - executable resolved via PATH
                [sysctl, "-n", "kern.boottime"],
                text=True, capture_output=True, check=True,
            )
            return result.stdout.strip()
        except Exception:
            return None

    return None
