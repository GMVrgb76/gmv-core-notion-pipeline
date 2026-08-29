"""Static persistence-boundary check for resource_service.py.

Scoped to this one file only, per ADR_CORE_PERSISTENCE_BOUNDARY.md — this is
not the deferred ARC-002 repo-wide enforcement check.
"""

from __future__ import annotations

from pathlib import Path

RESOURCE_SERVICE = Path(__file__).resolve().parents[2] / "10_API" / "resource_service.py"


def test_resource_service_does_not_reference_sqlite3() -> None:
    source = RESOURCE_SERVICE.read_text(encoding="utf-8")
    assert "sqlite3" not in source
