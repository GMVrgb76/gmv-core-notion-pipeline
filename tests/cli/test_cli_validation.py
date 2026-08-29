"""Tests for the Sprint 001 shared CLI input contract."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from gmv_core.errors import CLIInputError
from gmv_core.validation import (
    validate_cli_oid,
    validate_path,
    validate_positive_id,
    validate_slug,
    validate_status,
)

ROOT = Path(__file__).resolve().parents[2]


def test_shared_validators_accept_exact_valid_inputs() -> None:
    assert validate_cli_oid("RES-000001", expected_type="Resource").value == "RES-000001"
    assert validate_positive_id("12", argument="import_id") == 12
    assert validate_path("relative/source.pdf") == Path("relative/source.pdf")
    assert validate_status("pending", allowed={"pending", "complete"}) == "pending"
    assert validate_slug("area35-intelligence") == "area35-intelligence"


@pytest.mark.parametrize(
    ("validator", "expected"),
    [
        (lambda: validate_cli_oid("invalid"), "invalid oid:"),
        (
            lambda: validate_positive_id(" 1", argument="import_id"),
            "invalid import_id:",
        ),
        (lambda: validate_path("bad\x00path"), "invalid path:"),
        (
            lambda: validate_status("unknown", allowed={"pending", "complete"}),
            "invalid status:",
        ),
        (lambda: validate_slug("Not-A-Slug"), "invalid slug:"),
    ],
)
def test_shared_validators_use_stable_error_taxonomy(validator, expected: str) -> None:
    with pytest.raises(CLIInputError, match=f"^{expected}") as raised:
        validator()

    assert raised.value.exit_code == 2


def _run_adapter(tmp_path: Path, script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["HOME"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, str(ROOT / "10_API" / script), *arguments],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_object_show_rejects_invalid_oid_before_database_access(tmp_path: Path) -> None:
    result = _run_adapter(tmp_path, "object_service.py", "show", "INVALID-OID")

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("error: invalid oid:")


def test_queue_show_rejects_invalid_id_before_database_access(tmp_path: Path) -> None:
    result = _run_adapter(tmp_path, "queue_service.py", "show", "not-a-number")

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: invalid import_id: must be a positive decimal integer\n"
    )
