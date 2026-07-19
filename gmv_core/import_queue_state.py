"""Executable prototype of the accepted Import Queue state contract.

This module has no persistence side effects and is intentionally not wired to
production writers before the separately authorized DB-010 implementation.
"""

from __future__ import annotations

import math
from enum import StrEnum


class ImportQueueState(StrEnum):
    NEW = "new"
    PROCESSING = "processing"
    CLASSIFIED = "classified"
    APPROVED = "approved"
    RETRYABLE_ERROR = "retryable_error"
    REJECTED = "rejected"
    FAILED = "failed"
    ARCHIVED = "archived"


INITIAL_STATE = ImportQueueState.NEW
TERMINAL_STATES = frozenset(
    {
        ImportQueueState.REJECTED,
        ImportQueueState.FAILED,
        ImportQueueState.ARCHIVED,
    }
)
ACTIONABLE_STATES = frozenset(
    {
        ImportQueueState.NEW,
        ImportQueueState.CLASSIFIED,
        ImportQueueState.APPROVED,
        ImportQueueState.RETRYABLE_ERROR,
    }
)
ERROR_STATES = frozenset(
    {
        ImportQueueState.RETRYABLE_ERROR,
        ImportQueueState.FAILED,
    }
)
DESTINATION_REQUIRED_STATES = frozenset(
    {
        ImportQueueState.APPROVED,
        ImportQueueState.ARCHIVED,
    }
)
ALLOWED_TRANSITIONS = frozenset(
    {
        (ImportQueueState.NEW, ImportQueueState.PROCESSING),
        (ImportQueueState.PROCESSING, ImportQueueState.CLASSIFIED),
        (ImportQueueState.PROCESSING, ImportQueueState.RETRYABLE_ERROR),
        (ImportQueueState.PROCESSING, ImportQueueState.FAILED),
        (ImportQueueState.RETRYABLE_ERROR, ImportQueueState.PROCESSING),
        (ImportQueueState.CLASSIFIED, ImportQueueState.APPROVED),
        (ImportQueueState.CLASSIFIED, ImportQueueState.REJECTED),
        (ImportQueueState.APPROVED, ImportQueueState.ARCHIVED),
    }
)


def parse_state(value: object) -> ImportQueueState:
    if not isinstance(value, str):
        raise ValueError("Import Queue state must be an exact string")
    try:
        return ImportQueueState(value)
    except ValueError as error:
        raise ValueError(f"unsupported Import Queue state: {value}") from error


def require_initial_state(value: object) -> ImportQueueState:
    parsed = parse_state(value)
    if parsed is not INITIAL_STATE:
        raise ValueError(f"Import Queue rows must be created in {INITIAL_STATE}")
    return parsed


def require_transition(current: object, target: object) -> tuple[ImportQueueState, ImportQueueState]:
    source_state = parse_state(current)
    target_state = parse_state(target)
    if (source_state, target_state) not in ALLOWED_TRANSITIONS:
        raise ValueError(
            f"forbidden Import Queue transition: {source_state} -> {target_state}"
        )
    return source_state, target_state


def validate_state_payload(
    state: object,
    *,
    error: object = None,
    confidence: object = None,
    proposed_destination: object = None,
) -> ImportQueueState:
    parsed = parse_state(state)
    has_error = isinstance(error, str) and bool(error.strip())
    if parsed in ERROR_STATES:
        if not has_error:
            raise ValueError(f"{parsed} requires a non-empty error")
    elif error is not None:
        raise ValueError(f"{parsed} requires error to be null")

    if confidence is not None:
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("confidence must be null or a finite number between 0 and 1")

    if parsed in DESTINATION_REQUIRED_STATES and (
        not isinstance(proposed_destination, str) or not proposed_destination.strip()
    ):
        raise ValueError(f"{parsed} requires a non-empty proposed destination")
    return parsed
