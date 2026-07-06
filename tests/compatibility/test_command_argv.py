"""Compatibility commands use validated argument vectors without a shell."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY = ROOT / "10_API" / "gmv_compatibility.py"


def _write_program(path: Path, body: str) -> None:
    path.write_text(f"#!{sys.executable}\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _run_compatibility(
    home: Path,
    engine: str,
    executable: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    return subprocess.run(
        [
            sys.executable,
            str(COMPATIBILITY),
            engine,
            "--",
            str(executable),
            *arguments,
        ],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _latest_run(home: Path) -> tuple[str, str, str, str]:
    database = home / ".gmv_core" / "09_DATABASE" / "GMV.db"
    with sqlite3.connect(database) as connection:
        return connection.execute(
            "SELECT status,command,stdout_path,stderr_path "
            "FROM engine_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()


def test_exact_arguments_preserve_spaces_unicode_and_metacharacters(
    tmp_path: Path,
) -> None:
    helper = tmp_path / "programma ü con spazi.py"
    _write_program(helper, "import json, sys; print(json.dumps(sys.argv[1:]))")
    marker = tmp_path / "must-not-exist"
    arguments = ("two words", "ü", f"$(touch {marker})", "; echo unsafe")

    result = _run_compatibility(tmp_path, "test_engine", helper, *arguments)

    assert result.returncode == 0
    status, command, stdout_path, stderr_path = _latest_run(tmp_path)
    assert status == "OK"
    assert json.loads(Path(stdout_path).read_text(encoding="utf-8")) == list(arguments)
    assert Path(stderr_path).read_text(encoding="utf-8") == ""
    assert "'two words'" in command
    assert not marker.exists()


def test_nonzero_child_exit_is_recorded_and_propagated(tmp_path: Path) -> None:
    helper = tmp_path / "fails.py"
    _write_program(helper, "import sys; print('failed', file=sys.stderr); sys.exit(17)")

    result = _run_compatibility(tmp_path, "test_engine", helper)

    assert result.returncode == 17
    status, _command, _stdout_path, stderr_path = _latest_run(tmp_path)
    assert status == "ERROR"
    assert Path(stderr_path).read_text(encoding="utf-8") == "failed\n"


@pytest.mark.parametrize("engine", ["Bad-Engine", "../escape", "two words"])
def test_invalid_engine_names_are_rejected_before_execution(
    tmp_path: Path,
    engine: str,
) -> None:
    helper = tmp_path / "must-not-run.py"
    marker = tmp_path / "ran"
    _write_program(helper, f"from pathlib import Path; Path({str(marker)!r}).touch()")

    result = _run_compatibility(tmp_path, engine, helper)

    assert result.returncode == 2
    assert result.stderr.startswith("error: invalid engine name:")
    assert not marker.exists()


def test_shell_command_string_contract_is_rejected(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["HOME"] = str(tmp_path)

    result = subprocess.run(
        [sys.executable, str(COMPATIBILITY), "test_engine", "echo unsafe"],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "ENGINE_NAME -- COMMAND" in result.stderr
    assert not (tmp_path / ".gmv_core" / "04_LOGS").exists()
    assert not (tmp_path / ".gmv_core" / "05_OUTPUT").exists()
