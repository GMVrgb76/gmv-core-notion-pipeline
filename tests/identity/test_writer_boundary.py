"""Static DB-008 boundary for canonical Object identity writers."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ROOTS = ("01_RUNTIME/", "10_API/", "gmv_core/")
IDENTITY_WRITER = "gmv_core/repositories/identity.py"
OBJECT_WRITE = re.compile(
    r"\b(?:INSERT(?:\s+OR\s+\w+)?|REPLACE)\s+INTO\s+objects\b"
    r"|\bUPDATE\s+objects\b",
    flags=re.IGNORECASE,
)
SEQUENCE_WRITE = re.compile(
    r"\b(?:INSERT(?:\s+OR\s+\w+)?|REPLACE)\s+INTO\s+oid_sequences\b"
    r"|\bUPDATE\s+oid_sequences\b",
    flags=re.IGNORECASE,
)


def _tracked_production_sources() -> tuple[str, ...]:
    result = subprocess.run(
        ["/usr/bin/git", "ls-files", "*.py", "*.sql"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(
        relative
        for relative in result.stdout.splitlines()
        if relative.startswith(PRODUCTION_ROOTS)
    )


def test_only_identity_repository_writes_the_objects_table_directly() -> None:
    hits = {
        relative: len(OBJECT_WRITE.findall((ROOT / relative).read_text(encoding="utf-8")))
        for relative in _tracked_production_sources()
        if OBJECT_WRITE.search((ROOT / relative).read_text(encoding="utf-8"))
    }

    assert hits == {IDENTITY_WRITER: 1}


def test_identity_repository_validates_exact_type_before_insert() -> None:
    source = (ROOT / IDENTITY_WRITER).read_text(encoding="utf-8")

    validation = source.index("validate_oid(candidate, expected_type=object_type)")
    insertion = source.index("INSERT INTO objects")
    assert validation < insertion
    assert "if not connection.in_transaction" in source


def test_only_identity_repository_advances_oid_sequences_at_runtime() -> None:
    hits = {
        relative: len(
            SEQUENCE_WRITE.findall((ROOT / relative).read_text(encoding="utf-8"))
        )
        for relative in _tracked_production_sources()
        if relative.endswith(".py")
        and SEQUENCE_WRITE.search((ROOT / relative).read_text(encoding="utf-8"))
    }

    assert hits == {IDENTITY_WRITER: 1}
