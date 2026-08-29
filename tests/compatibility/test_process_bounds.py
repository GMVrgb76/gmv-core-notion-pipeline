"""Process bounds for disposable legacy compatibility executions."""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY = ROOT / "10_API" / "gmv_compatibility.py"


def _write_program(path: Path, body: str) -> None:
    path.write_text(f"#!{sys.executable}\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _command(home: Path, helper: Path) -> tuple[list[str], dict[str, str]]:
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    return (
        [
            sys.executable,
            str(COMPATIBILITY),
            "daily_log",
            "--",
            str(helper),
        ],
        environment,
    )


def _latest_run(home: Path) -> tuple[str, str, str]:
    database = home / ".gmv_core" / "09_DATABASE" / "GMV.db"
    with sqlite3.connect(database) as connection:
        return connection.execute(
            "SELECT status,stdout_path,stderr_path "
            "FROM service_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()


def test_child_receives_only_allowlisted_environment(tmp_path: Path) -> None:
    helper = tmp_path / "environment.py"
    _write_program(
        helper,
        "import json, os; print(json.dumps(dict(os.environ), sort_keys=True))",
    )
    command, environment = _command(tmp_path, helper)
    environment["GMV_TEST_SECRET"] = str(tmp_path / "must-not-leak")

    result = subprocess.run(
        command,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    status, stdout_path, _stderr_path = _latest_run(tmp_path)
    child_environment = json.loads(Path(stdout_path).read_text(encoding="utf-8"))
    assert status == "OK"
    assert child_environment["HOME"] == str(tmp_path)
    assert "PATH" in child_environment
    assert "GMV_TEST_SECRET" not in child_environment


def test_oversized_stdout_and_stderr_are_bounded(tmp_path: Path) -> None:
    helper = tmp_path / "large-output.py"
    _write_program(
        helper,
        "import sys; print('o' * 10000); print('e' * 10000, file=sys.stderr)",
    )
    command, environment = _command(tmp_path, helper)
    environment["GMV_COMPAT_MAX_OUTPUT_BYTES"] = "128"

    result = subprocess.run(
        command,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    status, stdout_path, stderr_path = _latest_run(tmp_path)
    assert status == "OK"
    for path in (stdout_path, stderr_path):
        captured = Path(path).read_text(encoding="utf-8")
        assert len(captured.encode()) <= 128 + len(b"\n...[output truncated]\n")
        assert captured.endswith("...[output truncated]\n")


def test_timeout_terminates_parent_and_child_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "child-survived"
    helper = tmp_path / "hangs-with-child.py"
    _write_program(
        helper,
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', \"import time; from pathlib import Path; "
        f"time.sleep(0.8); Path({str(marker)!r}).touch()\"]); time.sleep(30)",
    )
    command, environment = _command(tmp_path, helper)
    environment["GMV_COMPAT_TIMEOUT_SECONDS"] = "0.1"

    result = subprocess.run(
        command,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 124
    status, _stdout_path, _stderr_path = _latest_run(tmp_path)
    assert status == "TIMEOUT"
    time.sleep(1)
    assert not marker.exists()


def test_sigterm_cancels_parent_and_child_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "cancelled-child-survived"
    helper = tmp_path / "cancel-with-child.py"
    _write_program(
        helper,
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', \"import time; from pathlib import Path; "
        f"time.sleep(0.8); Path({str(marker)!r}).touch()\"]); time.sleep(30)",
    )
    command, environment = _command(tmp_path, helper)
    process = subprocess.Popen(  # noqa: S603 - disposable test process
        command,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.2)
    process.send_signal(signal.SIGTERM)

    _stdout, _stderr = process.communicate(timeout=5)

    assert process.returncode == 128 + signal.SIGTERM
    status, _stdout_path, _stderr_path = _latest_run(tmp_path)
    assert status == "CANCELLED"
    time.sleep(1)
    assert not marker.exists()
