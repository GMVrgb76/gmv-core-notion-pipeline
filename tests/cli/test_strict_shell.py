"""Regression tests for the transitional strict Bash CLI contract."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.characterization.conftest import CLI, SCHEMA_FIXTURE

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "10_API"))
import backup_service  # noqa: E402


@pytest.fixture
def strict_cli_environment(
    isolated_gmv: object,
    tmp_path: Path,
) -> Iterator[dict[str, str]]:
    home = Path(getattr(isolated_gmv, "home"))
    database = Path(getattr(isolated_gmv, "database"))
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE test_sentinel")
        connection.executescript(SCHEMA_FIXTURE.read_text(encoding="utf-8"))
        connection.execute("DELETE FROM engine_runs")
    database.chmod(0o600)

    subprocess.run(["/usr/bin/git", "init", "-q"], cwd=home, check=True)
    subprocess.run(["/usr/bin/git", "config", "user.email", "test@example.invalid"], cwd=home, check=True)
    subprocess.run(["/usr/bin/git", "config", "user.name", "Test"], cwd=home, check=True)
    subprocess.run(["/usr/bin/git", "add", "-A"], cwd=home, check=True)
    subprocess.run(["/usr/bin/git", "commit", "-qm", "fixture"], cwd=home, check=True)
    backup_service.create_backup(home, tmp_path / ".gmv_backups", now=datetime.now(UTC))

    executable_directory = tmp_path / "test-bin"
    executable_directory.mkdir()
    _write_executable(executable_directory / "launchctl", "exit 0")

    environment = os.environ.copy()
    environment["PATH"] = f"{executable_directory}:{environment['PATH']}"
    yield environment


def _run_cli(
    environment: dict[str, str],
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), *arguments],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _write_executable(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def test_missing_python_dependency_fails_before_status(
    strict_cli_environment: dict[str, str],
    tmp_path: Path,
) -> None:
    isolated_bin = tmp_path / "missing-python-bin"
    isolated_bin.mkdir()
    (isolated_bin / "dirname").symlink_to("/usr/bin/dirname")
    environment = strict_cli_environment.copy()
    environment["PATH"] = str(isolated_bin)

    result = _run_cli(environment, "status")

    assert result.returncode == 127
    assert result.stdout == ""
    assert "python3" in result.stderr


def test_status_no_longer_executes_shell_sqlite(
    strict_cli_environment: dict[str, str],
    tmp_path: Path,
) -> None:
    failing_bin = tmp_path / "failing-sqlite-bin"
    failing_bin.mkdir()
    _write_executable(failing_bin / "sqlite3", "exit 19")
    environment = strict_cli_environment.copy()
    environment["PATH"] = f"{failing_bin}:{environment['PATH']}"

    result = _run_cli(environment, "status")

    assert result.returncode == 0
    assert "STATE|DEGRADED" in result.stdout
    assert "SYSTEM READY" not in result.stdout


def test_status_does_not_depend_on_optional_launchctl(
    strict_cli_environment: dict[str, str],
    tmp_path: Path,
) -> None:
    isolated_bin = tmp_path / "sqlite-only-bin"
    isolated_bin.mkdir()
    environment = strict_cli_environment.copy()
    environment["PATH"] = f"{isolated_bin}:{environment['PATH']}"

    result = _run_cli(environment, "status")

    assert result.returncode == 0
    assert "STATE|DEGRADED" in result.stdout
    assert result.stderr == ""


def test_failed_optional_launchctl_is_not_invoked_by_status(
    strict_cli_environment: dict[str, str],
) -> None:
    launchctl = Path(strict_cli_environment["PATH"].split(":", 1)[0]) / "launchctl"
    _write_executable(launchctl, "exit 31")

    result = _run_cli(strict_cli_environment, "status")

    assert result.returncode == 0
    assert "STATE|DEGRADED" in result.stdout
    assert result.stderr == ""


def test_child_command_failure_propagates(
    strict_cli_environment: dict[str, str],
    tmp_path: Path,
) -> None:
    service = tmp_path / ".gmv_core" / "10_API" / "object_service.py"
    service.parent.mkdir(parents=True)
    _write_executable(service, "exit 23")

    result = _run_cli(strict_cli_environment, "object", "list")

    assert result.returncode == 23


def test_no_arguments_remains_a_valid_help_request(
    strict_cli_environment: dict[str, str],
) -> None:
    result = _run_cli(strict_cli_environment)

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.startswith("GMV CLI\n")
