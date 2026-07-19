#!/usr/bin/env python3

import re
import os
import hashlib
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import importlib
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import BinaryIO

from operational_records import append_record, build_record

CORE_SOURCE = Path(__file__).resolve().parents[1]
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

database = importlib.import_module("gmv_core.database")
DatabaseConfigurationError = importlib.import_module(
    "gmv_core.errors"
).DatabaseConfigurationError

CORE = Path.home() / ".gmv_core"
DB = CORE / "09_DATABASE" / "GMV.db"
LOGDIR = CORE / "04_LOGS"
OUTDIR = CORE / "05_OUTPUT" / "compatibility"
ENGINE_PATTERN = re.compile(r"[a-z][a-z0-9_]*\Z")
SERVICE_IDENTITIES = {
    "morning_brief": ("SRV-000002", "Morning Brief"),
    "daily_log": ("SRV-000003", "Daily Log"),
    "market_engine": ("SRV-000004", "Market Engine"),
}
DEFAULT_TIMEOUT_SECONDS = 900.0
DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024
TERMINATION_GRACE_SECONDS = 1.0
ALLOWED_ENVIRONMENT_KEYS = {
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PATH",
    "TMPDIR",
    "TZ",
}
TRUNCATION_MARKER = b"\n...[output truncated]\n"


class ProcessCancelled(Exception):
    def __init__(self, signal_number: int) -> None:
        self.signal_number = signal_number
        super().__init__(f"process cancelled by signal {signal_number}")


class CapturedStream:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.content = bytearray()
        self.truncated = False

    def drain(self, stream: BinaryIO) -> None:
        while chunk := stream.read(65536):
            remaining = self.limit - len(self.content)
            if remaining > 0:
                self.content.extend(chunk[:remaining])
            if len(chunk) > remaining:
                self.truncated = True

    def text(self) -> str:
        payload = bytes(self.content)
        if self.truncated:
            payload += TRUNCATION_MARKER
        return payload.decode("utf-8", errors="replace")


def _positive_setting(name: str, default: float, *, maximum: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive number") from error
    if value <= 0 or value > maximum:
        raise ValueError(f"{name} must be greater than 0 and at most {maximum:g}")
    return value


def _clean_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key in ALLOWED_ENVIRONMENT_KEYS
    }


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait()


def run_bounded_process(
    command: list[str],
    *,
    timeout_seconds: float,
    max_output_bytes: int,
) -> tuple[int, str, str, str]:
    process = subprocess.Popen(  # noqa: S603 - validated argv, no shell
        command,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_clean_environment(),
        start_new_session=True,
    )
    if process.stdout is None or process.stderr is None:
        _terminate_process_group(process)
        raise RuntimeError("compatibility process pipes were not created")

    stdout = CapturedStream(max_output_bytes)
    stderr = CapturedStream(max_output_bytes)
    stdout_thread = threading.Thread(target=stdout.drain, args=(process.stdout,))
    stderr_thread = threading.Thread(target=stderr.drain, args=(process.stderr,))
    stdout_thread.start()
    stderr_thread.start()

    def cancel(signal_number: int, _frame: FrameType | None) -> None:
        _terminate_process_group(process)
        raise ProcessCancelled(signal_number)

    previous_handlers = {
        signal_number: signal.signal(signal_number, cancel)
        for signal_number in (signal.SIGINT, signal.SIGTERM)
    }
    outcome = "ERROR"
    try:
        return_code = process.wait(timeout=timeout_seconds)
        outcome = "OK" if return_code == 0 else "ERROR"
    except subprocess.TimeoutExpired:
        _terminate_process_group(process)
        return_code = 124
        outcome = "TIMEOUT"
    except ProcessCancelled as cancellation:
        return_code = 128 + cancellation.signal_number
        outcome = "CANCELLED"
    finally:
        for signal_number, handler in previous_handlers.items():
            signal.signal(signal_number, handler)
        stdout_thread.join()
        stderr_thread.join()

    return return_code, stdout.text(), stderr.text(), outcome

def init_db(service_oid: str):
    conn = database.enable_foreign_keys(sqlite3.connect(DB))
    try:
        database.require_object_identities(
            conn,
            {"SYS-000001": "System", service_oid: "Service"},
        )
    except Exception:
        conn.close()
        raise
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS service_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_oid TEXT NOT NULL,
        service_name TEXT NOT NULL,
        run_at TEXT NOT NULL,
        status TEXT NOT NULL,
        duration_seconds REAL,
        command TEXT,
        stdout_path TEXT,
        stderr_path TEXT,
        summary TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        oid TEXT NOT NULL,
        event_at TEXT NOT NULL,
        event_type TEXT NOT NULL,
        description TEXT,
        source TEXT
    )
    """)
    conn.commit()
    return conn

def validate_invocation(arguments: list[str]) -> tuple[str, list[str]]:
    if len(arguments) < 4 or arguments[2] != "--":
        raise ValueError("usage: gmv_compatibility.py ENGINE_NAME -- COMMAND [ARG ...]")

    engine = arguments[1]
    command = arguments[3:]
    if not ENGINE_PATTERN.fullmatch(engine):
        raise ValueError("invalid engine name: use lowercase letters, digits, and underscores")
    if engine not in SERVICE_IDENTITIES:
        raise ValueError(f"unregistered compatibility service: {engine}")

    executable = command[0]
    if "/" in executable:
        executable_path = Path(executable).expanduser()
        if not executable_path.is_file() or not executable_path.stat().st_mode & 0o111:
            raise ValueError(f"command is not executable: {executable}")
    elif shutil.which(executable) is None:
        raise ValueError(f"command not found: {executable}")

    return engine, command


def validate_release_pin(command: list[str]) -> None:
    source = os.environ.get("GMV_COMPAT_SOURCE")
    expected_hash = os.environ.get("GMV_COMPAT_EXPECTED_SHA256")
    if source is None and expected_hash is None:
        return
    if not source or not expected_hash:
        raise ValueError("release pin requires both source path and SHA-256")

    source_path = Path(source).expanduser()
    if str(source_path) not in command:
        raise ValueError("release source is not present in command argv")
    if not source_path.is_file():
        raise ValueError(f"release source not found: {source_path}")
    actual_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise ValueError("release SHA-256 is invalid")
    if actual_hash != expected_hash:
        raise ValueError(
            f"release hash mismatch: expected {expected_hash}, got {actual_hash}"
        )


def run_engine(engine: str, command: list[str]) -> int:
    service_oid, service_name = SERVICE_IDENTITIES[engine]
    conn = init_db(service_oid)
    LOGDIR.mkdir(parents=True, exist_ok=True)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    DB.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat(timespec="seconds")
    stamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    stdout_path = OUTDIR / f"{stamp}_{engine}.out.log"
    stderr_path = OUTDIR / f"{stamp}_{engine}.err.log"

    timeout_seconds = _positive_setting(
        "GMV_COMPAT_TIMEOUT_SECONDS",
        DEFAULT_TIMEOUT_SECONDS,
        maximum=86400.0,
    )
    max_output_bytes = int(
        _positive_setting(
            "GMV_COMPAT_MAX_OUTPUT_BYTES",
            float(DEFAULT_MAX_OUTPUT_BYTES),
            maximum=16 * 1024 * 1024,
        )
    )
    start = datetime.now().astimezone()
    return_code, stdout, stderr, status = run_bounded_process(
        command,
        timeout_seconds=timeout_seconds,
        max_output_bytes=max_output_bytes,
    )
    ended_at = datetime.now().astimezone()
    duration = (ended_at - start).total_seconds()

    stdout_path.write_text(stdout)
    stderr_path.write_text(stderr)

    summary = (
        f"{engine} compatibility run completed with status {status}, "
        f"return code {return_code}"
    )

    error_code = {
        "OK": "none",
        "ERROR": "process_exit",
        "TIMEOUT": "timeout",
        "CANCELLED": "cancelled",
    }[status]
    record = build_record(
        service=engine,
        status=status,
        error_code=error_code,
        started_at=start,
        ended_at=ended_at,
        return_code=return_code,
        command=command,
        summary=summary,
        artifact_paths=[stdout_path, stderr_path],
        correlation_id=os.environ.get("GMV_CORRELATION_ID"),
    )
    append_record(LOGDIR / "operations.jsonl", record)

    cur = conn.cursor()

    cur.execute("""
    INSERT INTO service_runs
    (service_oid, service_name, run_at, status, duration_seconds,
     command, stdout_path, stderr_path, summary)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        service_oid, service_name, now, status, duration, shlex.join(command),
        str(stdout_path), str(stderr_path), summary
    ))

    cur.execute("""
    INSERT INTO events
    (oid, event_at, event_type, description, source)
    VALUES (?, ?, ?, ?, ?)
    """, (
        "SYS-000001", now, "engine_run", summary, "gmv_compatibility.py"
    ))

    conn.commit()
    conn.close()

    print("=== GMV COMPATIBILITY LAYER ===")
    print(summary)
    print("run_id:", record["run_id"])
    print("stdout:", stdout_path)
    print("stderr:", stderr_path)

    return return_code

if __name__ == "__main__":
    try:
        engine_name, command_argv = validate_invocation(sys.argv)
        validate_release_pin(command_argv)
        return_code = run_engine(engine_name, command_argv)
    except (ValueError, DatabaseConfigurationError) as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(2)

    sys.exit(return_code)
