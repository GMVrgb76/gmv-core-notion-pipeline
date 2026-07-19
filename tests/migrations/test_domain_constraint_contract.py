"""Isolated tests for the accepted non-queue DB-003 domain scope."""

from __future__ import annotations

import pytest

from gmv_core.domain_constraints import (
    SERVICE_RUN_STATUSES,
    validate_compatibility_mode,
    validate_confidence,
    validate_non_self_relation,
    validate_oid_grammar,
    validate_service_run_status,
)


@pytest.mark.parametrize("oid", ["SYS-000001", "RES-999999", "ZZZ-000001"])
def test_oid_grammar_accepts_exact_shape_without_claiming_prefix_authority(oid: str) -> None:
    assert validate_oid_grammar(oid) == oid


@pytest.mark.parametrize(
    "oid",
    [
        "SYS-000000",
        "sys-000001",
        "SY-000001",
        "SYS-00001",
        "SYS_000001",
        " SYS-000001",
        "SYS-000001 ",
        1,
    ],
)
def test_oid_grammar_rejects_noncanonical_values(oid: object) -> None:
    with pytest.raises(ValueError, match="OID"):
        validate_oid_grammar(oid)


def test_service_run_outcome_vocabulary_is_exact() -> None:
    assert SERVICE_RUN_STATUSES == {"OK", "ERROR", "TIMEOUT", "CANCELLED"}
    for status in SERVICE_RUN_STATUSES:
        assert validate_service_run_status(status) == status
    for status in ("ok", "FAILED", "active", "", None):
        with pytest.raises(ValueError, match="Service Run status"):
            validate_service_run_status(status)


@pytest.mark.parametrize("mode", [0, 1])
def test_compatibility_mode_accepts_only_integer_boolean(mode: int) -> None:
    assert validate_compatibility_mode(mode) == mode


@pytest.mark.parametrize("mode", [-1, 2, "0", "1", False, True, None])
def test_compatibility_mode_rejects_non_integer_boolean_domain(mode: object) -> None:
    with pytest.raises(ValueError, match="compatibility mode"):
        validate_compatibility_mode(mode)


@pytest.mark.parametrize("confidence", [None, 0, 0.25, 1])
def test_confidence_accepts_nullable_closed_unit_interval(confidence: float | None) -> None:
    assert validate_confidence(confidence) == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("inf"), float("nan"), True, "1"])
def test_confidence_rejects_values_outside_scalar_domain(confidence: object) -> None:
    with pytest.raises(ValueError, match="confidence"):
        validate_confidence(confidence)


def test_relation_endpoints_must_differ() -> None:
    assert validate_non_self_relation("SYS-000001", "RES-000001") == (
        "SYS-000001",
        "RES-000001",
    )
    with pytest.raises(ValueError, match="must differ"):
        validate_non_self_relation("SYS-000001", "SYS-000001")
    with pytest.raises(ValueError, match="OID strings"):
        validate_non_self_relation("SYS-000001", None)
