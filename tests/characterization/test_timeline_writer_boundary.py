"""Static boundary test: only the two known writers may INSERT INTO timeline.

Temporary allow-list, DB-005/AUTO-003 first slice (test-only, no production
code). Fails if any tracked Python file outside this list writes directly to
the legacy `timeline` table. This allow-list is expected to shrink to empty
once DB-005 migrates both listed writers to Events -- at that point this
test should assert no writers remain, not that these two specifically do.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_TIMELINE_WRITERS = frozenset(
    {
        "01_RUNTIME/knowledge_engine.py",
        "10_API/gmv_compatibility.py",
    }
)


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


def test_only_known_writers_insert_into_timeline() -> None:
    assert _writers_of_timeline() == set(ALLOWED_TIMELINE_WRITERS)
