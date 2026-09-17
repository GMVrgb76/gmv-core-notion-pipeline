"""GMV Crawler — Task 10: BUILD ATOMS for RELATION predicates (located_at slice).

Pins build_relation_atoms() end-to-end on the two real Garibaldi cases
("was held at" / "was presented at" -> located_at), the Task 8 pipeline
connection (ONE classify_entity_types() call per batch, network behavior
propagated, never swallowed), the prefix-link object->entity rules
(longest wins, exact-length tie is ambiguous -> None), and the critical
rejection: a model returning entity_type="EXHIBITION" for a PLACE-range
object MUST produce VALIDATION_FAILED -- which required the disclosed
deviation from the brief's letter (A-SCHEMA05 is MAJOR in the real
validator, so the fatal set is BLOCKER + A-SCHEMA05-by-codice; see the
module docstring and the Task 10 commit).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

import gmv_crawler_relation_atom_builder as relation_builder  # noqa: E402
from gmv_crawler_candidate_extractor import (  # noqa: E402
    CandidateEntity,
    CandidateProposition,
)
from gmv_crawler_entity_proposal_queue import append_entity_proposals  # noqa: E402 -- reused, not reimplemented, for the chain test
from gmv_crawler_entity_resolver import EntityTypeProposal  # noqa: E402
from gmv_crawler_relation_atom_builder import (  # noqa: E402
    BuiltRelationAtom,
    build_relation_atoms,
)
from gmv_evidence_pipeline import EvidenceError  # noqa: E402

ONTO = json.loads(
    (ROOT / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_v0.1.json").read_text(encoding="utf-8")
)
LOCATED_AT_CLASS = next(
    entry["predicate_class"]
    for entry in ONTO["predicates"]
    if entry["predicate_id"] == "located_at"
)
LOCATED_AT_RANGE = next(
    entry["range"]
    for entry in ONTO["predicates"]
    if entry["predicate_id"] == "located_at"
)

NOW = "2026-09-17T09:00:00Z"
CLAIM_A = "CLAIM-AttraversaMenti-1"
CLAIM_B = "CLAIM-BlueShores-1"


def make_entity(name: str) -> CandidateEntity:
    return CandidateEntity(
        name=name,
        evidence_excerpt="a real biography mentions this entity",
        status="DOCUMENTATO",
        source_id="SRC-GARIBALDI",
        evidence_id=("EV-1",),
    )


def make_proposition(
    subject_raw: str, predicate: str, object_raw: str, *, ref: str
) -> CandidateProposition:
    return CandidateProposition(
        subject_raw=subject_raw,
        predicate=predicate,
        object_raw=object_raw,
        evidence_excerpt=f"the biography states {subject_raw} {predicate} {object_raw}",
        status="DOCUMENTATO",
        source_id="SRC-GARIBALDI",
        evidence_id=("EV-1",),
        truncated_source=False,
        extraction_claim_ref=ref,
    )


def make_classifier(entity_type: str = "PLACE"):
    def _fake(
        entities, *, known_artists=None, known_institutions=None, endpoint=None,
        model=None, timeout=None, temperature=None, seed=None,
    ):
        return tuple(
            EntityTypeProposal(
                entity_name=entity.name,
                entity_type=entity_type,
                confidence="HIGH",
                source="MODEL_INFERENCE",
                needs_verification=True,
            )
            for entity in entities
        )

    return _fake


HOLD_PROPS = (
    make_proposition(
        "AttraversaMenti",
        "was held at",
        "Le Stanze della Fotografia, Venice (2025)",
        ref=CLAIM_A,
    ),
    make_proposition(
        "BlueShores",
        "was presented at",
        "UniCredit Pavilion, Milan in 2016",
        ref=CLAIM_B,
    ),
)
HOLD_ENTITIES = (make_entity("Le Stanze della Fotografia"), make_entity("UniCredit Pavilion"))
HOLD_EXPECTED_OBJECTS = (
    "Le Stanze della Fotografia, Venice (2025)",
    "UniCredit Pavilion, Milan in 2016",
)


# --- the two real Garibaldi cases: atom built, every field pinned ---

def test_real_garibaldi_cases_build_atoms_all_18_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(relation_builder, "classify_entity_types", make_classifier("PLACE"))
    built, rejected = build_relation_atoms(
        HOLD_PROPS, HOLD_ENTITIES, now=NOW, known_artists=frozenset()
    )
    assert rejected == ()
    assert len(built) == 2
    for i, entry in enumerate(built):
        assert isinstance(entry, BuiltRelationAtom)
        atom = entry.atom
        assert atom.atom_id == "ATOM-" + hashlib.sha256(
            f"SRC-GARIBALDI|{HOLD_PROPS[i].extraction_claim_ref}".encode("utf-8")
        ).hexdigest()[:16]
        assert atom.subject == HOLD_PROPS[i].subject_raw  # verbatim, no normalization
        assert atom.predicate == "located_at"
        assert atom.predicate_class == LOCATED_AT_CLASS == "RELATION"
        assert atom.object == HOLD_EXPECTED_OBJECTS[i]
        assert atom.object_type == "PLACE"
        assert atom.source == "SRC-GARIBALDI"
        assert atom.status == "UNVERIFIED"
        assert atom.valid_from is None and atom.valid_to is None
        assert atom.asserted_at == NOW and atom.ingested_at == NOW
        assert atom.asserted_by == "crawler_llm_extraction"
        assert atom.confidence == 0.5
        assert atom.visibility == "INTERNAL"
        assert atom.end_reason is None and atom.supersedes is None and atom.superseded_by is None
        assert entry.object_type_proposal.entity_type == "PLACE"
        assert entry.object_type_proposal.needs_verification is True


# --- the critical test: wrong object type must be mechanically rejected ---

def test_exhibition_object_type_rejected_validation_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reproduces the real probe failure this session observed: model
    classifies a venue as EXHIBITION instead of PLACE/INSTITUTION.
    validate_atom() reports this as A-SCHEMA05 MAJOR; this module's fatal
    set (BLOCKER or A-SCHEMA05 by codice, see disclosed deviation) must
    turn it into a rejection -- the brief's most-important test.

    2026-09-17: GMV_ONTOLOGY_REGISTRY_v0.1.json's located_at range was
    widened from ["PLACE"] to ["PLACE", "INSTITUTION"] (see that file's
    own "notes" on the entry) after a live run on this exact real data
    showed real venues (Le Stanze della Fotografia, Area35 Art Gallery)
    correctly typed INSTITUTION by the model, then wrongly rejected by
    the too-narrow range. EXHIBITION is still outside the range either
    way, so this test's own claim is unaffected -- only the grounding
    assertion on the range's exact value is updated to match; see the
    sibling test below for the now-accepted INSTITUTION case."""
    monkeypatch.setattr(relation_builder, "classify_entity_types", make_classifier("EXHIBITION"))
    built, rejected = build_relation_atoms(HOLD_PROPS, HOLD_ENTITIES, now=NOW)
    assert built == ()
    assert len(rejected) == 2
    for entry in rejected:
        assert entry.reason_code == "VALIDATION_FAILED"
        assert "A-SCHEMA05" in entry.detail
        assert "range" in entry.detail
    assert LOCATED_AT_RANGE == ["PLACE", "INSTITUTION"]
    assert "EXHIBITION" not in LOCATED_AT_RANGE


def test_institution_object_type_now_accepted_after_range_widening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Positive-path counterpart to the test above: since 2026-09-17,
    INSTITUTION is a valid located_at object_type (real venues like
    Area35 Art Gallery are institutions, not generic PLACE) -- an atom
    classified INSTITUTION must build successfully now, not be rejected
    the way it was on the live run that motivated the range widening."""
    monkeypatch.setattr(relation_builder, "classify_entity_types", make_classifier("INSTITUTION"))
    built, rejected = build_relation_atoms(HOLD_PROPS, HOLD_ENTITIES, now=NOW)
    assert rejected == ()
    assert len(built) == 2
    for entry in built:
        assert entry.atom.object_type == "INSTITUTION"


# --- pass-1 rejections, with classify never called ---

def test_unmapped_predicate_rejected_without_any_classify_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(relation_builder, "classify_entity_types", _fail_if_called)
    prop = make_proposition("Federico Garibaldi", "was born in", "Venice, Italy", ref="CLAIM-X")
    built, rejected = build_relation_atoms((prop,), HOLD_ENTITIES, now=NOW)
    assert built == ()
    assert [entry.reason_code for entry in rejected] == ["PREDICATE_TEXT_NOT_MAPPED"]
    assert rejected[0].raw_predicate == "was born in"


def test_unmapped_predicate_case_and_whitespace_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(relation_builder, "classify_entity_types", make_classifier("PLACE"))
    prop = make_proposition("AttraversaMenti", "  WAS HELD AT ", "le stanze della fotografia", ref=CLAIM_A)
    built, rejected = build_relation_atoms((prop,), HOLD_ENTITIES, now=NOW)
    assert rejected == () and len(built) == 1
    assert built[0].atom.predicate == "located_at"


def test_object_not_linked_to_any_entity_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(relation_builder, "classify_entity_types", _fail_if_called)
    prop = make_proposition(
        "AttraversaMenti", "was held at", "a place not mentioned as entity", ref="CLAIM-X"
    )
    built, rejected = build_relation_atoms((prop,), HOLD_ENTITIES, now=NOW)
    assert built == ()
    assert [entry.reason_code for entry in rejected] == ["OBJECT_NOT_LINKED_TO_KNOWN_ENTITY"]


# --- prefix-link rules (pure function + through the builder) ---

def test_longest_prefix_wins_most_specific_match(monkeypatch: pytest.MonkeyPatch) -> None:
    entities = (
        make_entity("Galleria Nazionale"),
        make_entity("Galleria Nazionale d'Arte"),
    )
    linked = relation_builder._link_object_to_entity(
        "Galleria Nazionale d'Arte Moderna in 2024", entities
    )
    assert linked is not None
    assert linked.name == "Galleria Nazionale d'Arte"  # longest prefix wins
    monkeypatch.setattr(relation_builder, "classify_entity_types", make_classifier("PLACE"))
    prop = make_proposition(
        "Quadriennale 2024", "was held at", "Galleria Nazionale d'Arte Moderna in 2024", ref="CLAIM-X"
    )
    built, rejected = build_relation_atoms((prop,), entities, now=NOW)
    assert rejected == () and len(built) == 1
    # the proposal rides with the LINKED entity's name -- observable proof of which entity won
    assert built[0].object_type_proposal.entity_name == "Galleria Nazionale d'Arte"


def test_exact_length_tie_is_ambiguous_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    entities = (
        make_entity("La Fenice"),
        make_entity("la fenice"),
    )
    assert relation_builder._link_object_to_entity("la fenice, venezia (1752)", entities) is None
    monkeypatch.setattr(relation_builder, "classify_entity_types", _fail_if_called)
    prop = make_proposition("Il Barbiere di Siviglia", "was held at", "La Fenice, Venice (1816)", ref="CLAIM-X")
    built, rejected = build_relation_atoms((prop,), entities, now=NOW)
    assert built == ()
    assert [entry.reason_code for entry in rejected] == ["OBJECT_NOT_LINKED_TO_KNOWN_ENTITY"]


def test_link_object_to_entity_no_match_returns_none() -> None:
    assert (
        relation_builder._link_object_to_entity(
            "completely unrelated string", (make_entity("Le Stanze della Fotografia"),)
        )
        is None
    )


# --- batch behavior: one classify call, order preserved ---

def test_shared_entity_classified_once_per_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[dict]] = []
    fake_classifier = make_classifier("PLACE")

    def counting(
        entities, *, known_artists=None, known_institutions=None, endpoint=None,
        model=None, timeout=None, temperature=None, seed=None,
    ):
        calls.append([{"name": e.name} for e in entities])
        return fake_classifier(entities, known_artists=known_artists, endpoint=endpoint, model=model, timeout=timeout)

    monkeypatch.setattr(relation_builder, "classify_entity_types", counting)
    props = (
        make_proposition("A", "was held at", "Le Stanze della Fotografia, Venice (2025)", ref="CLAIM-1"),
        make_proposition("B", "was held at", "Le Stanze della Fotografia (other show)", ref="CLAIM-2"),
        make_proposition("C", "was presented at", "UniCredit Pavilion, Milan in 2016", ref="CLAIM-3"),
    )
    built, rejected = build_relation_atoms(
        props, HOLD_ENTITIES, now=NOW, known_artists=frozenset()
    )
    assert rejected == ()
    assert len(built) == 3
    assert len(calls) == 1  # one Ollama call per batch -- the brief's non-negotiable
    assert [entry["name"] for entry in calls[0]] == ["Le Stanze della Fotografia", "UniCredit Pavilion"]
    assert [e.atom.subject for e in built] == ["A", "B", "C"]


def test_network_failure_propagates_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    def booms(*_args, **_kwargs):
        raise EvidenceError("OLLAMA_UNAVAILABLE")

    monkeypatch.setattr(relation_builder, "classify_entity_types", booms)
    with pytest.raises(EvidenceError, match="OLLAMA_UNAVAILABLE"):
        build_relation_atoms(HOLD_PROPS, HOLD_ENTITIES, now=NOW)


# --- the Task 8 -> Task 9chain contract stays decoupled but interoperable ---

def test_built_relation_atom_proposal_feeds_task9_queue_directly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(relation_builder, "classify_entity_types", make_classifier("PLACE"))
    built, rejected = build_relation_atoms(HOLD_PROPS, HOLD_ENTITIES, now=NOW)
    assert rejected == () and len(built) == 2
    unverified = [entry.object_type_proposal for entry in built]
    queue_path = tmp_path / "proposal-queue.jsonl"
    appended = append_entity_proposals(unverified, queue_path, now=NOW)
    assert appended == 2
    from gmv_crawler_entity_proposal_queue import summarize_entity_proposal_queue

    summary = summarize_entity_proposal_queue(queue_path)
    assert [entry.entity_name for entry in summary] == [
        "Le Stanze della Fotografia", "UniCredit Pavilion",
    ]  # count 1 each -> (name, type) asc


def _fail_if_called(*_args, **_kwargs):
    pytest.fail("classify_entity_types must not be called on the pass-1-only paths")