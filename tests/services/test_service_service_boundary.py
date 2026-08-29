"""Static persistence-boundary check for service_service.py.

Scoped to this one file only, per ADR_CORE_PERSISTENCE_BOUNDARY.md — this is
not the deferred ARC-002 repo-wide enforcement check.
"""

from __future__ import annotations

from pathlib import Path

SERVICE_SERVICE = Path(__file__).resolve().parents[2] / "10_API" / "service_service.py"


def test_service_service_does_not_reference_sqlite3() -> None:
    source = SERVICE_SERVICE.read_text(encoding="utf-8")
    assert "sqlite3" not in source
