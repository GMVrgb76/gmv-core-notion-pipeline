"""Crawler preplan step 14: Derived View Spec (GMV_KNOWLEDGE_MONAD_SPEC_v1.0
§11-12).

Cross-checks derive_relations()'s "RELATION" literal against the real,
already-committed FROZEN_PREDICATE_CLASSES set (gmv_atom_validator.py),
not a duplicated hardcoded assumption -- same discipline steps 4/6/7/8/
9/10/11/12/13 already used. Also cross-checks derive_current_state()'s
predicate-alias resolution against the real, already-committed
`source_for`/`evidences` alias pair in
00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json, not an invented alias.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

from gmv_atom_validator import AtomCandidate, FROZEN_PREDICATE_CLASSES  # noqa: E402
from gmv_crawler_derived_views import (  # noqa: E402
    CurrentStateEntry,
    derive_claims,
    derive_current_state,
    derive_ledger,
    derive_relations,
    derive_timeline,
    derive_views,
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


# --- derive_timeline() ---

def test_timeline_sorts_by_valid_from_ascending() -> None:
    early = make_atom(atom_id="A1", valid_from="2010-01-01")
    late = make_atom(atom_id="A2", valid_from="2020-01-01")
    mid = make_atom(atom_id="A3", valid_from="2015-01-01")
    result = derive_timeline((late, early, mid))
    assert [a.atom_id for a in result] == ["A1", "A3", "A2"]


def test_timeline_puts_undated_atoms_last_not_dropped() -> None:
    dated = make_atom(atom_id="A1", valid_from="2010-01-01")
    undated = make_atom(atom_id="A2", valid_from=None)
    result = derive_timeline((undated, dated))
    assert [a.atom_id for a in result] == ["A1", "A2"]
    assert len(result) == 2  # undated atom present, not silently dropped


# --- derive_ledger() ---

def test_ledger_sorts_by_ingested_at_ascending() -> None:
    old = make_atom(atom_id="A1", ingested_at="2026-01-01T00:00:00Z")
    new = make_atom(atom_id="A2", ingested_at="2026-06-01T00:00:00Z")
    result = derive_ledger((new, old))
    assert [a.atom_id for a in result] == ["A1", "A2"]


def test_ledger_ordering_is_independent_of_timeline_ordering() -> None:
    """Grounds the module docstring's distinction: an atom ingested later
    can describe an earlier real-world time, and the two views must be
    allowed to disagree on order."""
    early_event_late_ingest = make_atom(
        atom_id="A1", valid_from="2000-01-01", ingested_at="2026-06-01T00:00:00Z"
    )
    late_event_early_ingest = make_atom(
        atom_id="A2", valid_from="2020-01-01", ingested_at="2026-01-01T00:00:00Z"
    )
    timeline = derive_timeline((early_event_late_ingest, late_event_early_ingest))
    ledger = derive_ledger((early_event_late_ingest, late_event_early_ingest))
    assert [a.atom_id for a in timeline] == ["A1", "A2"]
    assert [a.atom_id for a in ledger] == ["A2", "A1"]


# --- derive_relations() ---

def test_relations_filters_to_relation_predicate_class_only() -> None:
    relation = make_atom(atom_id="A1", predicate_class="RELATION")
    attribute = make_atom(atom_id="A2", predicate_class="ATTRIBUTE")
    result = derive_relations((relation, attribute))
    assert [a.atom_id for a in result] == ["A1"]


def test_relation_literal_matches_real_frozen_predicate_classes() -> None:
    assert "RELATION" in FROZEN_PREDICATE_CLASSES


def test_module_actually_imports_frozen_predicate_classes_not_just_test_file() -> None:
    """Regression test for the review-reported overclaim: an earlier
    draft's docstring/comment claimed FROZEN_PREDICATE_CLASSES was
    imported into the module itself, but only this test file imported
    it -- the module's own guard is what makes the claim true now."""
    import gmv_crawler_derived_views as module

    assert module.FROZEN_PREDICATE_CLASSES is FROZEN_PREDICATE_CLASSES


# --- derive_claims() ---

def test_claims_is_the_full_atom_set() -> None:
    a1, a2 = make_atom(atom_id="A1"), make_atom(atom_id="A2", predicate_class="MEASURE")
    assert derive_claims((a1, a2)) == (a1, a2)


# --- derive_current_state() ---

def test_current_state_single_valid_atom_is_resolved() -> None:
    atom = make_atom()
    result = derive_current_state((atom,))
    assert len(result) == 1
    assert result[0].resolution == "RESOLVED"
    assert result[0].atom == atom
    assert result[0].candidates == (atom,)


def test_current_state_ignores_non_valid_atoms() -> None:
    valid = make_atom(atom_id="A1", status="VALID")
    unverified = make_atom(atom_id="A2", subject="Someone Else", status="UNVERIFIED")
    result = derive_current_state((valid, unverified))
    assert len(result) == 1
    assert result[0].atom.atom_id == "A1"


def test_current_state_multiple_valid_atoms_same_slot_is_ambiguous_not_silently_resolved() -> None:
    """Core regression this function must guard against: two VALID atoms
    for the same SUBJECT+PREDICATE slot with different OBJECTs must never
    be silently narrowed to one -- both surface in candidates."""
    first = make_atom(atom_id="A1", object="Nizza")
    second = make_atom(atom_id="A2", object="Genova")
    result = derive_current_state((first, second))
    assert len(result) == 1
    assert result[0].resolution == "AMBIGUOUS"
    assert result[0].atom is None
    assert set(a.atom_id for a in result[0].candidates) == {"A1", "A2"}


def test_current_state_groups_by_forma_normalized_subject() -> None:
    """Grounds reuse of _forma(): a subject written in a different word
    order (the same normalization compute_atom_fingerprint() already
    relies on, step 7) must still land in the same slot."""
    first = make_atom(atom_id="A1", subject="Federico Garibaldi", object="Nizza")
    second = make_atom(atom_id="A2", subject="Garibaldi, Federico", object="Genova")
    result = derive_current_state((first, second))
    assert len(result) == 1
    assert result[0].resolution == "AMBIGUOUS"


def test_current_state_groups_by_registry_resolved_predicate_alias() -> None:
    """Regression test for the review-reported blocker: two VALID atoms
    using different real, registered aliases of the same predicate
    (source_for/evidences, 00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json)
    must land in the same slot and be reported AMBIGUOUS, not treated as
    two unrelated facts."""
    via_canonical = make_atom(
        atom_id="A1", subject="Documento X", predicate="source_for",
        predicate_class="RELATION", object="Claim1",
    )
    via_alias = make_atom(
        atom_id="A2", subject="Documento X", predicate="evidences",
        predicate_class="RELATION", object="Claim2",
    )
    result = derive_current_state((via_canonical, via_alias))
    assert len(result) == 1
    assert result[0].resolution == "AMBIGUOUS"
    assert set(a.atom_id for a in result[0].candidates) == {"A1", "A2"}


def test_current_state_deduplicates_identical_atom_id_appearing_twice() -> None:
    """Regression test for the review-reported blocker: the same atom
    passed twice (a plausible caller bug, e.g. overlapping query results)
    must not be treated as two competing candidates."""
    atom = make_atom()
    result = derive_current_state((atom, atom))
    assert len(result) == 1
    assert result[0].resolution == "RESOLVED"
    assert result[0].candidates == (atom,)


def test_current_state_same_atom_id_different_content_last_wins_no_error() -> None:
    """Pins a known, disclosed limitation of the atom_id dedup -- NOT a
    desirable behavior to extend.  The dedup in derive_current_state()
    keys on the `atom_id` *string* (dict comprehension), not on content
    or Python object identity: two genuinely different atoms sharing an
    `atom_id` (an upstream bug -- no uniqueness guarantee exists before
    this function) are collapsed silently to whichever appears last in
    the input iteration order, with no error and no AMBIGUOUS.  What to
    do about a real atom_id collision (raise, or a third resolution
    state) is an open design question, out of scope here; this test only
    locks in the current real behavior so a future change cannot break
    silently."""
    first = make_atom(atom_id="DUPE", predicate="born_in", object="Nizza")
    second = make_atom(atom_id="DUPE", predicate="died_in", object="Roma")
    # Forward order: second appears last, second's predicate/object wins.
    result = derive_current_state((first, second))
    assert len(result) == 1
    assert result[0].resolution == "RESOLVED"
    assert result[0].atom == second
    assert result[0].atom.predicate == "died_in"
    assert result[0].atom.object == "Roma"
    # Reversed order: first now appears last, first's predicate/object wins --
    # proving the outcome is iteration-order-dependent, not semantically fixed.
    reversed_result = derive_current_state((second, first))
    assert reversed_result[0].atom == first
    assert reversed_result[0].atom.predicate == "born_in"
    assert reversed_result[0].atom.object == "Nizza"


def test_current_state_candidates_ordered_deterministically_by_atom_id() -> None:
    second = make_atom(atom_id="A2", object="Genova")
    first = make_atom(atom_id="A1", object="Nizza")
    result = derive_current_state((second, first))  # passed out of atom_id order
    assert [a.atom_id for a in result[0].candidates] == ["A1", "A2"]
    assert result[0].subject == first.subject  # display fields come from candidates[0]


def test_current_state_different_predicates_are_separate_slots() -> None:
    born = make_atom(atom_id="A1", predicate="born_in", object="Nizza")
    died = make_atom(atom_id="A2", predicate="died_in", object="Roma")
    result = derive_current_state((born, died))
    assert len(result) == 2
    assert all(entry.resolution == "RESOLVED" for entry in result)


def test_current_state_entry_rejects_resolved_without_atom() -> None:
    with pytest.raises(ValueError, match="RESOLVED must carry an atom"):
        CurrentStateEntry(
            subject="X", predicate="p", resolution="RESOLVED", atom=None, candidates=(make_atom(),),
        )


def test_current_state_entry_rejects_ambiguous_with_atom() -> None:
    a1, a2 = make_atom(atom_id="A1"), make_atom(atom_id="A2")
    with pytest.raises(ValueError, match="AMBIGUOUS must not carry a resolved atom"):
        CurrentStateEntry(
            subject="X", predicate="p", resolution="AMBIGUOUS", atom=a1, candidates=(a1, a2),
        )


def test_current_state_entry_rejects_ambiguous_with_fewer_than_two_candidates() -> None:
    with pytest.raises(ValueError, match="2 or more competing"):
        CurrentStateEntry(
            subject="X", predicate="p", resolution="AMBIGUOUS", atom=None, candidates=(make_atom(),),
        )


# --- derive_views() ---

def test_derive_views_computes_all_five_views() -> None:
    atom = make_atom()
    views = derive_views((atom,))
    assert views.timeline == (atom,)
    assert views.ledger == (atom,)
    assert views.claims == (atom,)
    assert views.relations == ()
    assert len(views.current_state) == 1


def test_derive_views_does_not_expose_public() -> None:
    """PUBLIC is step 15's job (PUBLIC projector), not this module's --
    see module docstring. DerivedViews must not have a public field."""
    from dataclasses import fields

    field_names = {f.name for f in fields(derive_views(()))}
    assert "public" not in field_names
