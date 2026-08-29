"""Static DB-006 boundary: no tracked runtime writes Engine Runs."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _writers_of_engine_runs() -> set[str]:
    result = subprocess.run(
        ["/usr/bin/git", "grep", "-l", "INSERT INTO engine_runs", "--", "*.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 1), result.stderr
    return {
        line
        for line in result.stdout.splitlines()
        if line and not line.startswith("tests/")
    }


def test_no_tracked_writer_inserts_into_engine_runs() -> None:
    assert _writers_of_engine_runs() == set()
