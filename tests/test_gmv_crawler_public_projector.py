"""Crawler preplan step 15: PUBLIC projector (GMV_KNOWLEDGE_MONAD_SPEC_v1.0
§14; crawler spec v0.2 §15-20).

Cross-checks this module's two hardcoded literals against real,
already-committed precedent instead of trusting the module docstring's
own claims: `BLOCKED_EXTRACTION_STATUS` against the real "BLOCKED" run
status `gmv_evidence_pipeline.py` actually writes, and
`PUBLISHABLE_VISIBILITY` against the "PUBLIC" default every other
crawler-step test fixture on this branch already uses for
`AtomCandidate.visibility`. Same discipline steps 4/6/7/8/9/10/11/12/13/14
already used for their own governed-vocabulary claims.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

from gmv_atom_validator import AtomCandidate  # noqa: E402
from gmv_crawler_derived_views import CurrentStateEntry, derive_current_state  # noqa: E402
from gmv_crawler_extractor import STATUS_VALUES  # noqa: E402
from gmv_monad_materializer import SourceManifestEntry  # noqa: E402
import gmv_crawler_public_projector as pp  # noqa: E402
from gmv_crawler_public_projector import (  # noqa: E402
    project_public,
    render_public_text,
    select_public_atoms,
)

# Other test files whose AtomCandidate fixtures already default
# visibility to "PUBLIC" -- read below by
# test_publishable_visibility_matches_every_other_real_fixture_default(),
# not duplicated as a second hardcoded assumption.
SIBLING_FIXTURE_FILES = (
    "tests/test_gmv_atom_validator.py",
    "tests/test_gmv_crawler_reconciliation.py",
    "tests/test_gmv_crawler_fulltext_index.py",
    "tests/test_gmv_crawler_derived_views.py",
    "tests/test_gmv_monad_materializer.py",
)


def make_atom(**overrides) -> AtomCandidate:
    fields = {
        "atom_id": "GMV-ATOM-001",
        "subject": "Federico Garibaldi",
        "predicate": "participated_in",
        "predicate_class": "RELATION",
        "object": "Biennale di Venezia",
        "object_type": "EXHIBITION",
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


def make_source(**overrides) -> SourceManifestEntry:
    fields = {
        "source_id": "SRC-001",
        "path": "/GMV_MASTER_SYSTEM/.../file.pdf",
        "source_type": "PDF",
        "size": 1024,
        "modified": "2026-01-01",
        "hash_value": "sha256:" + "a" * 64,
        "epistemic_level": "PRIMARY",
        "extraction_status": "SUCCESS",
    }
    fields.update(overrides)
    return SourceManifestEntry(**fields)


# --- select_public_atoms(): the exclusion gates, one adversarial case per rule ---

def test_select_includes_valid_public_atom_with_unblocked_source() -> None:
    atom = make_atom()
    result = select_public_atoms((atom,), (make_source(),))
    assert result == (atom,)


def test_select_excludes_non_valid_status() -> None:
    """§14: 'claim UNVERIFIED non attribuite'. An UNVERIFIED atom, even
    with VISIBILITY=PUBLIC, must never reach PUBLIC."""
    unverified = make_atom(status="UNVERIFIED")
    assert select_public_atoms((unverified,)) == ()


def test_select_excludes_superseded_status() -> None:
    """§14: 'historical states presented as current'."""
    superseded = make_atom(status="SUPERSEDED")
    assert select_public_atoms((superseded,)) == ()


def test_select_excludes_non_public_visibility() -> None:
    """§14: 'fatti INTERNAL'."""
    internal = make_atom(visibility="INTERNAL")
    assert select_public_atoms((internal,)) == ()


def test_select_excludes_ambiguous_slot_entirely_not_either_candidate() -> None:
    """Adversarial case for this module's own core guarantee (module
    docstring point 2): two VALID, PUBLIC-visibility atoms competing for
    the same SUBJECT+PREDICATE slot with different OBJECTs must produce
    ZERO public lines, not one arbitrarily chosen one -- publishing
    either would present a contested/unresolved state as settled fact,
    exactly what §14 forbids. Tries to break the guarantee by picking
    atom_id ordering that would make the wrong 'obvious' choice look
    right if this module silently picked the first or last candidate."""
    first = make_atom(atom_id="A2", object="Biennale di Venezia")
    second = make_atom(atom_id="A1", object="Documenta Kassel")
    result = select_public_atoms((first, second))
    assert result == ()


def test_select_under_publishes_legitimately_multi_valued_relation_as_disclosed() -> None:
    """Demonstrates the known, disclosed trade-off inherited from step 14
    (module docstring point 2): an artist genuinely participating in two
    different exhibitions produces two VALID, non-contradictory
    participated_in atoms that nonetheless collide into one
    SUBJECT+PREDICATE slot and are suppressed from PUBLIC entirely,
    because derive_current_state() has no per-predicate policy for
    "this predicate may legitimately hold several simultaneous values".
    Not a bug this module introduces -- pinned here so a future step
    that does add such a policy has a failing regression test to guide
    it, the same way step 14's own AMBIGUOUS test pins its mechanism."""
    exhibition_a = make_atom(atom_id="A1", object="Biennale di Venezia")
    exhibition_b = make_atom(atom_id="A2", object="Documenta Kassel")
    result = select_public_atoms((exhibition_a, exhibition_b))
    assert result == ()  # both true facts, both currently unpublished


def test_select_excludes_atom_whose_source_extraction_failed() -> None:
    """§14: 'inferenze da fonti bloccate'. Uses "EXTRACTION_FAILED", a
    real value gmv_crawler_extractor.STATUS_VALUES actually contains and
    the real crawler pipeline can actually produce -- not the earlier
    draft's invented "BLOCKED" literal, which no real code in this
    repository ever writes to a per-source extraction_status field (see
    module docstring point 3 for the full account of that correction)."""
    atom = make_atom(source="SRC-FAILED")
    failed_source = make_source(source_id="SRC-FAILED", extraction_status="EXTRACTION_FAILED")
    assert select_public_atoms((atom,), (failed_source,)) == ()


def test_select_excludes_atom_whose_source_is_unsupported_format() -> None:
    atom = make_atom(source="SRC-UNSUPPORTED")
    unsupported_source = make_source(
        source_id="SRC-UNSUPPORTED", extraction_status="UNSUPPORTED_FORMAT",
    )
    assert select_public_atoms((atom,), (unsupported_source,)) == ()


def test_select_includes_atom_whose_source_extraction_succeeded() -> None:
    atom = make_atom(source="SRC-OK")
    ok_source = make_source(source_id="SRC-OK", extraction_status="SUCCESS")
    assert select_public_atoms((atom,), (ok_source,)) == (atom,)


def test_select_does_not_exclude_when_source_absent_from_manifest() -> None:
    """Absence of SOURCES information about atom.source is not itself
    evidence the source is blocked (EIC-02 discipline, not invented
    here) -- an atom referencing a source_id not present in the supplied
    manifest is not penalized for that absence alone."""
    atom = make_atom(source="SRC-NOT-IN-MANIFEST")
    result = select_public_atoms((atom,), (make_source(source_id="SRC-OTHER"),))
    assert result == (atom,)


def test_select_with_no_sources_argument_does_not_exclude_anything_on_that_basis() -> None:
    atom = make_atom()
    assert select_public_atoms((atom,)) == (atom,)


def test_select_excludes_atom_failing_every_gate_simultaneously() -> None:
    """Adversarial case: an atom that is simultaneously non-VALID,
    non-PUBLIC visibility, and sourced from a blocked source must still
    be excluded cleanly (no gate silently short-circuits and lets a
    doubly-disqualified atom slip through some unintended code path)."""
    atom = make_atom(status="UNVERIFIED", visibility="INTERNAL", source="SRC-FAILED")
    failed_source = make_source(source_id="SRC-FAILED", extraction_status="EXTRACTION_FAILED")
    assert select_public_atoms((atom,), (failed_source,)) == ()


def test_select_deduplicates_identical_atom_id_appearing_twice() -> None:
    """Reused guarantee (via derive_current_state()): the same atom
    object passed twice must not double-count."""
    atom = make_atom()
    assert select_public_atoms((atom, atom)) == (atom,)


def test_select_sorts_result_by_atom_id_regardless_of_input_order() -> None:
    a2 = make_atom(atom_id="A2", subject="X", predicate="born_in", object="Roma")
    a1 = make_atom(atom_id="A1", subject="Y", predicate="died_in", object="Milano")
    result = select_public_atoms((a2, a1))
    assert [a.atom_id for a in result] == ["A1", "A2"]


def test_select_reuses_caller_supplied_current_state_without_recomputing() -> None:
    """Grounds the injectable-but-defaulted `current_state` parameter:
    when supplied, this module trusts it rather than recomputing from
    `atoms` -- proven here by passing an `atoms` argument that would
    produce a *different* result than the supplied `current_state` if
    recomputation actually happened."""
    real_atom = make_atom(atom_id="A1")
    injected_state = (
        CurrentStateEntry(
            subject="Injected", predicate="born_in", resolution="RESOLVED",
            atom=real_atom, candidates=(real_atom,),
        ),
    )
    # atoms=() alone would recompute to an empty current_state if the
    # injected one were ignored.
    result = select_public_atoms((), current_state=injected_state)
    assert result == (real_atom,)


# --- render_public_text() ---

def test_render_produces_one_line_per_atom_sorted_by_atom_id() -> None:
    a2 = make_atom(atom_id="A2", subject="X", predicate="born_in", object="Roma")
    a1 = make_atom(atom_id="A1", subject="Y", predicate="died_in", object="Milano")
    text = render_public_text((a2, a1))
    lines = text.split("\n")
    assert lines == [
        "- Y — died_in — Milano",
        "- X — born_in — Roma",
    ]


def test_render_empty_input_returns_empty_string() -> None:
    assert render_public_text(()) == ""


def test_render_collapses_embedded_newlines_to_keep_one_line_per_atom() -> None:
    atom = make_atom(object="Multi\nline\rvalue")
    text = render_public_text((atom,))
    assert text.count("\n") == 0
    assert "Multi line value" in text


def test_render_collapses_windows_style_crlf_to_a_single_line() -> None:
    """\\r\\n (not just \\r or \\n separately) must still collapse to one
    rendered line -- a plausible real input from a Windows-authored
    source document."""
    atom = make_atom(object="Line one\r\nLine two")
    text = render_public_text((atom,))
    assert text.count("\n") == 0


# --- project_public() ---

def test_project_public_composes_selection_and_rendering() -> None:
    eligible = make_atom(atom_id="A1")
    excluded = make_atom(atom_id="A2", status="UNVERIFIED")
    text = project_public((eligible, excluded))
    assert text == render_public_text((eligible,))
    assert "A2" not in text  # excluded atom's content must not leak in


def test_project_public_empty_atoms_returns_empty_string() -> None:
    assert project_public(()) == ""


# --- grounding cross-checks against real, already-committed precedent ---

def test_blocked_extraction_statuses_is_status_values_minus_success() -> None:
    """Cross-checks BLOCKED_EXTRACTION_STATUSES against the real,
    already-grounded gmv_crawler_extractor.STATUS_VALUES set, imported
    here independently (not via gmv_crawler_public_projector's own
    import), not a second hardcoded assumption of what that set is.
    Regression test for the review-reported blocker: an earlier draft
    used a standalone "BLOCKED" literal that grep-matched an unrelated
    field (gmv_evidence_pipeline.py's whole-run SEMANTIC-stage `status`,
    not any per-source `extraction_status`) and that no real per-source
    extraction_status value in this repository's closed vocabulary can
    ever equal."""
    assert pp.BLOCKED_EXTRACTION_STATUSES == STATUS_VALUES - {"SUCCESS"}
    assert "SUCCESS" not in pp.BLOCKED_EXTRACTION_STATUSES
    assert "BLOCKED" not in STATUS_VALUES  # the corrected literal never existed here


def test_module_actually_imports_status_values_not_just_test_file() -> None:
    assert pp.STATUS_VALUES is STATUS_VALUES


def test_publishable_visibility_matches_every_other_real_fixture_default() -> None:
    """No governed VISIBILITY vocabulary exists anywhere in this
    repository (module docstring). This test grounds
    PUBLISHABLE_VISIBILITY against the one real, repo-wide precedent
    that does exist: every other crawler-step test file's own
    AtomCandidate fixture already defaults visibility to "PUBLIC"."""
    for relative_path in SIBLING_FIXTURE_FILES:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        assert '"visibility": "PUBLIC"' in text, (
            f"{relative_path} no longer defaults visibility to 'PUBLIC' -- "
            "PUBLISHABLE_VISIBILITY's grounding assumption needs re-checking"
        )
    assert pp.PUBLISHABLE_VISIBILITY == "PUBLIC"


def test_module_actually_imports_derive_current_state_not_just_test_file() -> None:
    """Regression guard for the review-reported overclaim pattern seen
    twice already this session (step 9 credentials.py, step 14
    FROZEN_PREDICATE_CLASSES): a docstring 'imported/reused' claim is
    only true if the real `from X import Y` line exists in the module
    itself, not just in this test file."""
    assert pp.derive_current_state is derive_current_state
    assert pp.CurrentStateEntry is CurrentStateEntry
    assert pp.AtomCandidate is AtomCandidate
    assert pp.SourceManifestEntry is SourceManifestEntry
