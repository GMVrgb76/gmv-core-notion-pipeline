"""GMV Crawler — BUILD ATOMS v0 (task brief opencode_task_6.md): the
narrow ATTRIBUTE-only slice of gmv_crawler_atom_builder.py.

Cross-checks the module's hardcoded ATTRIBUTE predicate set against the
real, already-committed GMV_ONTOLOGY_REGISTRY_v0.1.json (the import-time
guard and a direct registry read here, not a duplicated hardcoded list),
and reserves one alias-resolution case (evidences -> source_for) to make
sure a governed alias is not treated as an unrelated raw string.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

from gmv_atom_validator import validate_atom  # noqa: E402
from gmv_crawler_atom_builder import (  # noqa: E402
    RejectedCandidate,
    build_atom,
    build_atoms,
)
from gmv_crawler_candidate_extractor import CandidateProposition  # noqa: E402

ONTOLOGY_REGISTRY_PATH = ROOT / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_v0.1.json"

NOW = "2026-09-16T00:00:00Z"


def make_proposition(**overrides) -> CandidateProposition:
    fields = {
        "subject_raw": "Federico Garibaldi",
        "predicate": "edition_size",
        "object_raw": "3",
        "evidence_excerpt": "l'edition è di 3 esemplari",
        "status": "DOCUMENTATO",
        "source_id": "SRC-EVID-42",
        "evidence_id": ("EV-1",),
        "truncated_source": False,
        "extraction_claim_ref": "CLAIM-007",
    }
    fields.update(overrides)
    return CandidateProposition(**fields)


# --- registry grounding ---

def test_module_attribute_predicate_set_matches_real_registry() -> None:
    """The two predicates this module will ever build must be exactly the
    registry's ATTRIBUTE/integer predicate set -- an independent read
    here, plus the module's own import-time guard, not a duplicated
    list."""
    import json

    import gmv_crawler_atom_builder as module

    registry = json.loads(ONTOLOGY_REGISTRY_PATH.read_text(encoding="utf-8"))
    real = frozenset(
        e["predicate_id"] for e in registry["predicates"]
        if e["predicate_class"] == "ATTRIBUTE" and e.get("range") == ["integer"]
    )
    assert real == {"edition_size", "edition_number"}
    assert module._ATTRIBUTE_INTEGER_PREDICATE_IDS == real


# --- edition_size valid -> every field exact ---

def test_build_atom_edition_size_valid_all_fields_exact() -> None:
    atom = build_atom(
        make_proposition(object_raw=" 3 "), now=NOW,
    )
    assert isinstance(atom, RejectedCandidate) is False
    assert atom.predicate == "edition_size"
    assert atom.subject == "Federico Garibaldi"  # verbatim, no normalization
    assert atom.predicate_class == "ATTRIBUTE"
    assert atom.object == "3"  # stripped of surrounding whitespace
    assert atom.object_type == "integer"
    assert atom.source == "SRC-EVID-42"
    assert atom.status == "UNVERIFIED"
    assert atom.valid_from is None
    assert atom.valid_to is None
    assert atom.asserted_at == NOW
    assert atom.ingested_at == NOW
    assert atom.asserted_by == "crawler_llm_extraction"
    assert atom.confidence == 0.5
    assert atom.visibility == "INTERNAL"
    assert atom.end_reason is None
    assert atom.supersedes is None
    assert atom.superseded_by is None
    assert len(atom.atom_id) == 5 + 16  # "ATOM-" prefix + 16 hex chars


def test_build_atom_edition_number_valid_all_fields_exact() -> None:
    atom = build_atom(
        make_proposition(predicate="edition_number", object_raw="1", extraction_claim_ref="CLAIM-008"),
        now=NOW,
    )
    assert isinstance(atom, RejectedCandidate) is False
    assert atom.predicate == "edition_number"
    assert atom.subject == "Federico Garibaldi"
    assert atom.predicate_class == "ATTRIBUTE"
    assert atom.object == "1"
    assert atom.object_type == "integer"
    assert atom.source == "SRC-EVID-42"
    assert atom.status == "UNVERIFIED"
    assert atom.valid_from is None
    assert atom.valid_to is None
    assert atom.asserted_at == NOW
    assert atom.ingested_at == NOW
    assert atom.asserted_by == "crawler_llm_extraction"
    assert atom.confidence == 0.5
    assert atom.visibility == "INTERNAL"
    assert atom.end_reason is None
    assert atom.supersedes is None
    assert atom.superseded_by is None


# --- built atoms must be independently clean under validate_atom() ---

def test_built_atom_passes_validate_atom_with_zero_blockers() -> None:
    """Independent proof, not a trust of build_atom()'s own check: the
    atom it returns, re-validated here directly, produces zero BLOCKER
    issues."""
    atom = build_atom(make_proposition(), now=NOW)
    blockers = [i for i in validate_atom(atom) if i.severita == "BLOCKER"]
    assert blockers == []


# --- UNKNOWN_PREDICATE ---

def test_build_atom_unknown_predicate_rejects() -> None:
    result = build_atom(make_proposition(predicate="foo_bar_predicate"), now=NOW)
    assert isinstance(result, RejectedCandidate)
    assert result.reason_code == "UNKNOWN_PREDICATE"
    assert result.source_id == "SRC-EVID-42"
    assert result.extraction_claim_ref == "CLAIM-007"
    assert result.raw_predicate == "foo_bar_predicate"
    assert result.detail


# --- PREDICATE_NOT_YET_SUPPORTED (real RELATION + real alias) ---

def test_build_atom_relation_predicate_rejects_not_yet_supported() -> None:
    result = build_atom(make_proposition(predicate="represented_by"), now=NOW)
    assert isinstance(result, RejectedCandidate)
    assert result.reason_code == "PREDICATE_NOT_YET_SUPPORTED"


def test_build_atom_relation_predicate_alias_resolves_to_canonical_and_rejects() -> None:
    """'evidences' is a real registered alias of RELATION predicate
    'source_for' (GMV_ONTOLOGY_REGISTRY_v0.1.json) -- it must resolve
    through the registry like the canonical form, never be treated as an
    unrelated raw string, and reject as not-yet-supported exactly like
    the canonical id."""
    via_alias = build_atom(make_proposition(predicate="evidences"), now=NOW)
    via_canonical = build_atom(make_proposition(predicate="source_for"), now=NOW)
    assert isinstance(via_alias, RejectedCandidate) and isinstance(via_canonical, RejectedCandidate)
    assert via_alias.reason_code == "PREDICATE_NOT_YET_SUPPORTED"
    assert via_canonical.reason_code == "PREDICATE_NOT_YET_SUPPORTED"
    assert "source_for" in via_alias.detail  # canonical id named, not the alias spelling


# --- OBJECT_NOT_INTEGER: >= 3 distinct non-numeric variants ---

def test_build_atom_non_integer_object_rejects() -> None:
    for bad_object in ("tre", "3/10"):
        result = build_atom(make_proposition(object_raw=bad_object), now=NOW)
        assert isinstance(result, RejectedCandidate), bad_object
        assert result.reason_code == "OBJECT_NOT_INTEGER", bad_object


def test_build_atom_whitespace_only_object_rejects_as_not_integer() -> None:
    """The empty-after-strip case (the brief's `""` variant, which cannot
    reach this function through the CandidateProposition constructor --
    its __post_init__ rejects empty object_raw): a whitespace-only string
    is constructible and strips to empty, which is not decimal digits."""
    result = build_atom(make_proposition(object_raw="   "), now=NOW)
    assert isinstance(result, RejectedCandidate)
    assert result.reason_code == "OBJECT_NOT_INTEGER"


# --- determinism / uniqueness of atom_id ---

def test_build_atom_atom_id_is_deterministic_byte_for_byte() -> None:
    p = make_proposition()
    first = build_atom(p, now=NOW)
    second = build_atom(p, now=NOW)
    assert first.atom_id == second.atom_id


def test_build_atom_atom_id_differs_for_different_extraction_claim_ref() -> None:
    a = build_atom(make_proposition(extraction_claim_ref="CLAIM-007"), now=NOW)
    b = build_atom(make_proposition(extraction_claim_ref="CLAIM-008"), now=NOW)
    assert a.atom_id != b.atom_id


def test_build_atom_atom_id_binds_to_source_id_not_semantic_fact() -> None:
    """The same semantic fact extracted from two different sources must
    get two different ids, never collapse onto one (reconcile()'s
    SUPPORTING outcome premise)."""
    a = build_atom(make_proposition(source_id="SRC-EVID-42"), now=NOW)
    b = build_atom(make_proposition(source_id="SRC-EVID-99"), now=NOW)
    assert a.atom_id != b.atom_id
    assert a.predicate == b.predicate
    assert a.object == b.object  # same fact, different provenance


# --- batch: no propagation, no loss, no duplication ---

def test_build_atoms_mixed_batch_isolates_rejections() -> None:
    propositions = (
        make_proposition(extraction_claim_ref="OK-1"),                       # valid edition_size
        make_proposition(predicate="edition_number", object_raw="1",
                         extraction_claim_ref="OK-2"),                        # valid edition_number
        make_proposition(predicate="foo_bar_predicate", extraction_claim_ref="BAD-1"),  # UNKNOWN_PREDICATE
        make_proposition(object_raw="tre", extraction_claim_ref="BAD-2"),    # OBJECT_NOT_INTEGER
    )
    atoms, rejected = build_atoms(propositions, now=NOW)
    assert len(atoms) == 2 and len(rejected) == 2
    # exactly the two valid propositions built, nothing lost or duplicated
    assert {a.predicate for a in atoms} == {"edition_size", "edition_number"}
    assert {a.source for a in atoms} == {"SRC-EVID-42"}
    # exactly the two invalid propositions rejected, one reason each
    assert {r.reason_code for r in rejected} == {"UNKNOWN_PREDICATE", "OBJECT_NOT_INTEGER"}
    assert {r.extraction_claim_ref for r in rejected} == {"BAD-1", "BAD-2"}


# --- INTERNAL / UNVERIFIED pinned on every constructible atom ---

def test_every_built_atom_is_internal_and_unverified() -> None:
    """Pinned explicitly, not left to drift: no atom this module builds
    may ever carry status != UNVERIFIED or visibility == PUBLIC (step 15
    publishes only PUBLIC atoms; nothing here has passed epistemic
    verification)."""
    atoms, _ = build_atoms(
        (
            make_proposition(),
            make_proposition(predicate="edition_number", object_raw="2",
                             extraction_claim_ref="X-2"),
        ),
        now=NOW,
    )
    assert atoms
    for atom in atoms:
        assert atom.status == "UNVERIFIED"
        assert atom.visibility == "INTERNAL"