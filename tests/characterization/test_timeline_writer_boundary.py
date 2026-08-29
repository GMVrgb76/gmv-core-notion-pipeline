"""Static boundary test: no tracked writer may INSERT INTO timeline.

DB-005/AUTO-003. Both known writers (01_RUNTIME/knowledge_engine.py,
10_API/gmv_compatibility.py) have been migrated to Events. This is now a
permanent regression guard, not a temporary allow-list: any future direct
Timeline write must fail this test.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _writers_of_timeline() -> set[str]:
    result = subprocess.run(
        ["/usr/bin/git", "grep", "-l", "INSERT INTO timeline", "--", "*.py"],
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


def test_no_tracked_writer_inserts_into_timeline() -> None:
    assert _writers_of_timeline() == set()
