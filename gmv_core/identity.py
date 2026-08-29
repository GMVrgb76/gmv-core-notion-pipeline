"""Canonical, non-normalizing Object identifier validation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from gmv_core.errors import OIDValidationError

OID_CONTRACT_VERSION = "1.0.0"
OID_PATTERN = re.compile(r"^(?P<prefix>[A-Z]{3})-(?P<sequence>[0-9]{6})$")

PREFIX_TO_TYPE = {
    "COR": "Core",
    "PER": "Person",
    "PLG": "Plugin",
    "RES": "Resource",
    "SRV": "Service",
    "SYS": "System",
}
TYPE_TO_PREFIX = {object_type: prefix for prefix, object_type in PREFIX_TO_TYPE.items()}


@dataclass(frozen=True, slots=True)
class OID:
    value: str
    prefix: str
    object_type: str
    sequence: int


def validate_oid(value: object, *, expected_type: str | None = None) -> OID:
    """Validate an OID exactly as supplied; never trim or change case."""
    if not isinstance(value, str):
        raise OIDValidationError("OID must be a string")

    match = OID_PATTERN.fullmatch(value)
    if match is None:
        raise OIDValidationError("OID must match AAA-000001 with uppercase ASCII letters")

    prefix = match.group("prefix")
    object_type = PREFIX_TO_TYPE.get(prefix)
    if object_type is None:
        raise OIDValidationError(f"unsupported OID prefix: {prefix}")

    sequence = int(match.group("sequence"))
    if sequence == 0:
        raise OIDValidationError("OID sequence must be between 000001 and 999999")

    if expected_type is not None:
        expected_prefix = TYPE_TO_PREFIX.get(expected_type)
        if expected_prefix is None:
            raise OIDValidationError(f"unsupported Object type: {expected_type}")
        if expected_prefix != prefix:
            raise OIDValidationError(
                f"OID prefix {prefix} does not match Object type {expected_type}"
            )

    return OID(
        value=value,
        prefix=prefix,
        object_type=object_type,
        sequence=sequence,
    )
