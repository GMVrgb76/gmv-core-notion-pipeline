"""Isolated executable checks for the DB-003/DB-010 state decision."""

from __future__ import annotations

import itertools

import pytest

from gmv_core.import_queue_state import (
    ACTIONABLE_STATES,
    ALLOWED_TRANSITIONS,
    INITIAL_STATE,
    TERMINAL_STATES,
    ImportQueueState,
    parse_state,
    require_initial_state,
    require_transition,
    validate_state_payload,
)


def test_exact_state_vocabulary_and_derived_sets() -> None:
    assert {state.value for state in ImportQueueState} == {
        "new",
        "processing",
        "classified",
        "approved",
        "retryable_error",
        "rejected",
        "failed",
        "archived",
    }
    assert INITIAL_STATE is ImportQueueState.NEW
    assert TERMINAL_STATES == {
        ImportQueueState.REJECTED,
        ImportQueueState.FAILED,
        ImportQueueState.ARCHIVED,
    }
    assert ACTIONABLE_STATES == {
        ImportQueueState.NEW,
        ImportQueueState.CLASSIFIED,
        ImportQueueState.APPROVED,
        ImportQueueState.RETRYABLE_ERROR,
    }


def test_exact_allowed_transition_graph() -> None:
    expected = {
        ("new", "processing"),
        ("processing", "classified"),
        ("processing", "retryable_error"),
        ("processing", "failed"),
        ("retryable_error", "processing"),
        ("classified", "approved"),
        ("classified", "rejected"),
        ("approved", "archived"),
    }
    assert {(source.value, target.value) for source, target in ALLOWED_TRANSITIONS} == expected
    for source, target in expected:
        assert require_transition(source, target) == (
            ImportQueueState(source),
            ImportQueueState(target),
        )


def test_new_is_the_only_initial_state() -> None:
    assert require_initial_state("new") is ImportQueueState.NEW
    for state in ImportQueueState:
        if state is ImportQueueState.NEW:
            continue
        with pytest.raises(ValueError, match="must be created in new"):
            require_initial_state(state)


def test_every_unlisted_transition_is_forbidden() -> None:
    for source, target in itertools.product(ImportQueueState, repeat=2):
        if (source, target) in ALLOWED_TRANSITIONS:
            continue
        with pytest.raises(ValueError, match="forbidden Import Queue transition"):
            require_transition(source, target)


@pytest.mark.parametrize("terminal", TERMINAL_STATES)
def test_terminal_states_have_no_exit(terminal: ImportQueueState) -> None:
    assert all(source is not terminal for source, _target in ALLOWED_TRANSITIONS)


@pytest.mark.parametrize("value", ["pending", "pending_review", "complete", "reviewed", "NEW", " new "])
def test_legacy_test_only_and_normalized_values_are_not_authority(value: str) -> None:
    with pytest.raises(ValueError, match="unsupported Import Queue state"):
        parse_state(value)


def test_error_states_require_error_and_other_states_reject_it() -> None:
    assert validate_state_payload("retryable_error", error="temporary failure")
    assert validate_state_payload("failed", error="policy rejection")
    with pytest.raises(ValueError, match="requires a non-empty error"):
        validate_state_payload("retryable_error", error=" ")
    with pytest.raises(ValueError, match="requires error to be null"):
        validate_state_payload("new", error="stale error")


@pytest.mark.parametrize("confidence", [0, 0.25, 1, None])
def test_confidence_accepts_only_nullable_closed_unit_interval(confidence: float | None) -> None:
    assert validate_state_payload("classified", confidence=confidence)


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("inf"), float("nan"), True, "1"])
def test_invalid_confidence_is_rejected(confidence: object) -> None:
    with pytest.raises(ValueError, match="confidence"):
        validate_state_payload("classified", confidence=confidence)


def test_approval_and_archive_require_destination() -> None:
    assert validate_state_payload("approved", proposed_destination="07_IMPORT/approved")
    assert validate_state_payload("archived", proposed_destination="98_ARCHIVE/item")
    with pytest.raises(ValueError, match="proposed destination"):
        validate_state_payload("approved", proposed_destination=None)
