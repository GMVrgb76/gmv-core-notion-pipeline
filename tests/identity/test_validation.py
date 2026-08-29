"""Canonical OID contract acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gmv_core.errors import OIDValidationError
from gmv_core.identity import (
    OID_CONTRACT_VERSION,
    PREFIX_TO_TYPE,
    validate_oid,
)

OID_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "oids.json"


def _fixture() -> dict[str, object]:
    return json.loads(OID_FIXTURE.read_text(encoding="utf-8"))


def test_current_typed_objects_validate() -> None:
    fixture = _fixture()

    assert fixture["contract_version"] == OID_CONTRACT_VERSION
    assert fixture["prefixes"] == PREFIX_TO_TYPE
    for value, object_type in fixture["current_typed_oids"]:
        parsed = validate_oid(value, expected_type=object_type)
        assert parsed.value == value
        assert parsed.object_type == object_type


@pytest.mark.parametrize(
    "value",
    [
        "res-000001",
        "RES-1",
        "RES-0000001",
        "RES_000001",
        "RES-000000",
        "RES-000001 ",
        " RES-000001",
        "RÉS-000001",
        "ABC-000001",
        "",
        None,
    ],
)
def test_malformed_or_unsupported_oids_fail(value: object) -> None:
    with pytest.raises(OIDValidationError):
        validate_oid(value)


def test_prefix_must_match_object_type() -> None:
    with pytest.raises(OIDValidationError, match="does not match"):
        validate_oid("RES-000001", expected_type="Service")


def test_unsupported_object_type_fails() -> None:
    with pytest.raises(OIDValidationError, match="unsupported Object type"):
        validate_oid("RES-000001", expected_type="Document")
