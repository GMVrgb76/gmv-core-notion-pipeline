"""Crawler preplan step 12: Reconciliation engine (spec v0.2 §15-20).

Cross-checks against the real, already-committed `compute_atom_fingerprint()`
(step 7, `gmv_atom_validator.py`) -- reconcile() must key matching off that
real function, not a duplicated identity notion, and must inherit its
_forma()-based word-order-invariant normalization (proven here with a
same-person, different-word-order subject, mirroring the exact bug
compute_atom_fingerprint's own docstring documents fixing).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

from gmv_atom_validator import AtomCandidate  # noqa: E402
from gmv_crawler_reconciliation import (  # noqa: E402
    REACHABLE_OUTCOMES,
    ReconciliationOutcome,
    ReconciliationResult,
    reconcile,
)


def make_atom(**overrides) -> AtomCandidate:
    fields = {
        "atom_id": "GMV-ATOM-001",
        "subject": "Federico Garibaldi",
        "predicate": "born_in",
        "predicate_class": "EVENT",
        "object": "Nizza",
        "object_type": "PLACE",
        "source": "SRC-001",
        "status": "VALID",
        "valid_from": None,
        "valid_to": None,
        "asserted_at": "2026-01-01T00:00:00Z",
        "ingested_at": "2026-01-01T00:00:00Z",
        "asserted_by": "gemma4:12b",
        "confidence": 0.9,
        "visibility": "PUBLIC",
    }
    fields.update(overrides)
    return AtomCandidate(**fields)


# --- reconcile() ---

def test_no_existing_atoms_is_new() -> None:
    result = reconcile(make_atom(), existing_atoms=())
    assert result.outcome == "NEW"
    assert result.matched_atoms == ()


def test_existing_atom_with_different_object_is_new_not_matched() -> None:
    """Different OBJECT means a different fingerprint entirely -- this is
    the module docstring's central point: fingerprint-based matching
    cannot see a same-subject-predicate/different-object pair as related
    at all (that is exactly the gap CONFLICTING/SUPERSEDING would need a
    different, unbuilt 'slot' key to close)."""
    existing = make_atom(atom_id="GMV-ATOM-000", object="Genova")
    result = reconcile(make_atom(), existing_atoms=(existing,))
    assert result.outcome == "NEW"
    assert result.matched_atoms == ()


def test_same_fingerprint_same_source_is_identical() -> None:
    existing = make_atom(atom_id="GMV-ATOM-000", source="SRC-001")
    candidate = make_atom(atom_id="GMV-ATOM-001", source="SRC-001")
    result = reconcile(candidate, existing_atoms=(existing,))
    assert result.outcome == "IDENTICAL"
    assert result.matched_atoms == (existing,)


def test_same_fingerprint_different_source_is_supporting() -> None:
    existing = make_atom(atom_id="GMV-ATOM-000", source="SRC-999")
    candidate = make_atom(atom_id="GMV-ATOM-001", source="SRC-001")
    result = reconcile(candidate, existing_atoms=(existing,))
    assert result.outcome == "SUPPORTING"
    assert result.matched_atoms == (existing,)


def test_multiple_matches_all_different_sources_are_all_returned_as_supporting() -> None:
    existing_a = make_atom(atom_id="GMV-ATOM-000", source="SRC-A")
    existing_b = make_atom(atom_id="GMV-ATOM-002", source="SRC-B")
    candidate = make_atom(atom_id="GMV-ATOM-001", source="SRC-C")
    result = reconcile(candidate, existing_atoms=(existing_a, existing_b))
    assert result.outcome == "SUPPORTING"
    assert set(result.matched_atoms) == {existing_a, existing_b}


def test_same_source_match_takes_precedence_over_other_supporting_matches() -> None:
    """When one existing atom is a literal duplicate (same source) and
    another is independent corroboration (different source), the
    candidate is fully redundant against the same-source one -- IDENTICAL
    wins, not SUPPORTING."""
    duplicate = make_atom(atom_id="GMV-ATOM-000", source="SRC-001")
    corroborating = make_atom(atom_id="GMV-ATOM-002", source="SRC-999")
    candidate = make_atom(atom_id="GMV-ATOM-001", source="SRC-001")
    result = reconcile(candidate, existing_atoms=(duplicate, corroborating))
    assert result.outcome == "IDENTICAL"
    assert result.matched_atoms == (duplicate,)


def test_reconcile_uses_real_fingerprint_word_order_invariance() -> None:
    """Grounds reuse of compute_atom_fingerprint(): a subject written in a
    different word order (the same bug _forma() was adopted to fix in
    step 7) must still match, since reconcile() must inherit that
    behavior by reusing the real function, not a re-derived identity
    notion of its own."""
    existing = make_atom(atom_id="GMV-ATOM-000", subject="Garibaldi, Federico", source="SRC-999")
    candidate = make_atom(atom_id="GMV-ATOM-001", subject="Federico Garibaldi", source="SRC-001")
    result = reconcile(candidate, existing_atoms=(existing,))
    assert result.outcome == "SUPPORTING"


def test_status_of_existing_atoms_is_not_filtered_by_reconcile() -> None:
    """reconcile() does not look at STATUS at all -- an INVALIDATED atom
    still counts as a match if its fingerprint matches. Documented as a
    caller responsibility, not decided here; this test pins that current
    behavior so a future change is deliberate, not accidental."""
    invalidated = make_atom(atom_id="GMV-ATOM-000", source="SRC-001", status="INVALIDATED", end_reason="CORRECTED")
    candidate = make_atom(atom_id="GMV-ATOM-001", source="SRC-001")
    result = reconcile(candidate, existing_atoms=(invalidated,))
    assert result.outcome == "IDENTICAL"


# --- ReconciliationResult invariants ---

@pytest.mark.parametrize("outcome", ["CONFLICTING", "SUPERSEDING", "CORRECTING"])
def test_result_rejects_not_yet_reachable_outcomes(outcome: str) -> None:
    with pytest.raises(ValueError, match="does not yet compute"):
        ReconciliationResult(outcome=outcome, candidate=make_atom(), matched_atoms=())


def test_result_rejects_new_with_matched_atoms() -> None:
    with pytest.raises(ValueError, match="NEW must not carry"):
        ReconciliationResult(outcome="NEW", candidate=make_atom(), matched_atoms=(make_atom(atom_id="X"),))


def test_result_rejects_identical_with_no_matched_atoms() -> None:
    with pytest.raises(ValueError, match="must carry at least one"):
        ReconciliationResult(outcome="IDENTICAL", candidate=make_atom(), matched_atoms=())


def test_result_rejects_identical_with_more_than_one_matched_atom() -> None:
    with pytest.raises(ValueError, match="exactly one matched atom"):
        ReconciliationResult(
            outcome="IDENTICAL", candidate=make_atom(),
            matched_atoms=(make_atom(atom_id="X"), make_atom(atom_id="Y")),
        )


def test_reachable_outcomes_is_proper_subset_of_full_vocabulary() -> None:
    """Cross-check against the module's own real Literal type, not a
    second hardcoded set of the same six strings -- a drift between
    ReconciliationOutcome's real definition and REACHABLE_OUTCOMES would
    otherwise go undetected."""
    full_vocabulary = set(ReconciliationOutcome.__args__)
    assert full_vocabulary == {"NEW", "IDENTICAL", "SUPPORTING", "CONFLICTING", "SUPERSEDING", "CORRECTING"}
    assert REACHABLE_OUTCOMES < full_vocabulary


def test_multiple_existing_atoms_same_source_as_candidate_keeps_only_one_witness() -> None:
    """Pins current behavior deliberately: if existing_atoms already
    contains two atoms sharing both the candidate's fingerprint AND its
    SOURCE (possible since no atoms_runtime store enforces uniqueness
    yet), IDENTICAL's one-match invariant means only one of them survives
    into matched_atoms -- the other is silently not reported. Not fixed;
    pinned so a future change to this is deliberate, not accidental."""
    duplicate_a = make_atom(atom_id="GMV-ATOM-000", source="SRC-001")
    duplicate_b = make_atom(atom_id="GMV-ATOM-002", source="SRC-001")
    candidate = make_atom(atom_id="GMV-ATOM-001", source="SRC-001")
    result = reconcile(candidate, existing_atoms=(duplicate_a, duplicate_b))
    assert result.outcome == "IDENTICAL"
    assert len(result.matched_atoms) == 1
    assert result.matched_atoms[0] in (duplicate_a, duplicate_b)
