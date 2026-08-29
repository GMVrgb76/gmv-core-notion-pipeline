"""Shared, side-effect-free validation for command-line inputs."""

from __future__ import annotations

import re
from collections.abc import Collection
from pathlib import Path

from gmv_core.errors import CLIInputError, OIDValidationError
from gmv_core.identity import OID, validate_oid

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_cli_oid(value: object, *, expected_type: str | None = None) -> OID:
    """Validate an OID and expose identity failures through the CLI taxonomy."""
    try:
        return validate_oid(value, expected_type=expected_type)
    except OIDValidationError as error:
        raise CLIInputError("oid", str(error)) from error


def validate_positive_id(value: object, *, argument: str = "id") -> int:
    """Return a strictly positive base-10 identifier without normalization."""
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise CLIInputError(argument, "must be a positive decimal integer")

    parsed = int(value)
    if parsed < 1:
        raise CLIInputError(argument, "must be a positive decimal integer")
    return parsed


def validate_path(value: object, *, argument: str = "path") -> Path:
    """Validate path syntax without resolving or accessing the filesystem."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise CLIInputError(argument, "must be a non-empty path without NUL bytes")
    return Path(value)


def validate_status(
    value: object,
    *,
    allowed: Collection[str],
    argument: str = "status",
) -> str:
    """Require an exact status value from a caller-owned finite vocabulary."""
    if not isinstance(value, str) or value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise CLIInputError(argument, f"must be one of: {choices}")
    return value


def validate_slug(value: object, *, argument: str = "slug") -> str:
    """Require a lowercase ASCII slug without silently normalizing it."""
    if not isinstance(value, str) or SLUG_PATTERN.fullmatch(value) is None:
        raise CLIInputError(
            argument,
            "must contain lowercase ASCII letters or digits separated by hyphens",
        )
    return value
