"""Executable prototype of the accepted DB-003 scalar domain contracts.

The functions are side-effect free and intentionally not wired to production
writers before a separately authorized persistence-enforcement slice.
"""

from __future__ import annotations

import math

from gmv_core.identity import OID_PATTERN

SERVICE_RUN_STATUSES = frozenset({"OK", "ERROR", "TIMEOUT", "CANCELLED"})


def validate_oid_grammar(value: object) -> str:
    if not isinstance(value, str) or OID_PATTERN.fullmatch(value) is None:
        raise ValueError("OID must match AAA-000001 with uppercase ASCII letters")
    if value.endswith("-000000"):
        raise ValueError("OID sequence must be between 000001 and 999999")
    return value


def validate_service_run_status(value: object) -> str:
    if not isinstance(value, str) or value not in SERVICE_RUN_STATUSES:
        choices = ", ".join(sorted(SERVICE_RUN_STATUSES))
        raise ValueError(f"Service Run status must be one of: {choices}")
    return value


def validate_compatibility_mode(value: object) -> int:
    if type(value) is not int or value not in {0, 1}:
        raise ValueError("compatibility mode must be integer 0 or 1")
    return value


def validate_confidence(value: object) -> int | float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError("confidence must be null or a finite number between 0 and 1")
    return value


def validate_non_self_relation(source_oid: object, target_oid: object) -> tuple[str, str]:
    if not isinstance(source_oid, str) or not isinstance(target_oid, str):
        raise ValueError("Relation endpoints must be OID strings")
    if source_oid == target_oid:
        raise ValueError("Relation source and target must differ")
    return source_oid, target_oid
