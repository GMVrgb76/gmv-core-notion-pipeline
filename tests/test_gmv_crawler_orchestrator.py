import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "10_API"))

from gmv_crawler_candidate_extractor import CandidateEntity, CandidateProposition  # noqa: E402
from gmv_crawler_entity_resolver import EntityTypeProposal  # noqa: E402
from gmv_crawler_extractor import ExtractionDocument  # noqa: E402
from gmv_crawler_orchestrator import ProcessDocumentResult, process_document  # noqa: E402

import gmv_crawler_orchestrator as orchestrator  # noqa: E402

GOOD_HASH = "sha256:" + "a" * 64
NOW = "2026-09-17T12:00:00Z"


def make_document(text: str = "some real-looking text") -> ExtractionDocument:
    return ExtractionDocument(
        source_id="SRC-1", source_hash=GOOD_HASH, status="SUCCESS",
        extractor="text", text=text,
    )


def make_entity(name: str) -> CandidateEntity:
    return CandidateEntity(
        name=name, evidence_excerpt="excerpt", status="DOCUMENTATO",
        source_id="SRC-1", evidence_id=("EV-1",),
    )


def make_proposition(
    subject_raw: str, predicate: str, object_raw: str, *, ref: str
) -> CandidateProposition:
    return CandidateProposition(
        subject_raw=subject_raw, predicate=predicate, object_raw=object_raw,
        evidence_excerpt="excerpt", status="DOCUMENTATO", source_id="SRC-1",
        evidence_id=("EV-1",), truncated_source=False, extraction_claim_ref=ref,
    )


def test_attribute_only_proposition_builds_via_task6_no_relation_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pure ATTRIBUTE case (edition_size) must build via build_atoms()
    alone -- build_relation_atoms() (and therefore classify_entity_types())
    must never even be invoked for it."""
    entities = (make_entity("Some Work"),)
    propositions = (make_proposition("Some Work", "edition_size", "12", ref="CLAIM-1"),)

    def _fail_extract(*a, **k):
        return entities, propositions, ()

    def _fail_relation(*a, **k):
        raise AssertionError("build_relation_atoms() must not be called for an ATTRIBUTE-only batch")

    monkeypatch.setattr(orchestrator, "extract_candidates", _fail_extract)
    monkeypatch.setattr(orchestrator, "build_relation_atoms", _fail_relation)

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert isinstance(result, ProcessDocumentResult)
    assert len(result.atoms) == 1
    assert result.atoms[0].object_type == "integer"
    assert result.rejected == ()
    assert result.entity_type_proposals_needing_verification == ()


def test_relation_only_proposition_builds_via_task10_after_task6_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A located_at-shaped proposition must be rejected by build_atoms()
    (UNKNOWN_PREDICATE, real free text never matches the ontology
    registry's predicate ids) and then picked up by build_relation_atoms()
    -- proving the hand-off, not just that each builder works alone."""
    entities = (make_entity("Area35 Art Gallery"),)
    propositions = (
        make_proposition("Some Show", "was held at", "Area35 Art Gallery in 2019", ref="CLAIM-2"),
    )

    def _fake_extract(*a, **k):
        return entities, propositions, ()

    def _fake_classify(batch_entities, **k):
        return tuple(
            EntityTypeProposal(
                entity_name=e.name, entity_type="INSTITUTION",
                confidence="HIGH", source="MODEL_INFERENCE", needs_verification=True,
            )
            for e in batch_entities
        )

    monkeypatch.setattr(orchestrator, "extract_candidates", _fake_extract)
    monkeypatch.setattr("gmv_crawler_relation_atom_builder.classify_entity_types", _fake_classify)

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert len(result.atoms) == 1
    atom = result.atoms[0]
    assert atom.predicate == "located_at"
    assert atom.object_type == "INSTITUTION"
    assert atom.atom_id == "ATOM-" + hashlib.sha256(b"SRC-1|CLAIM-2").hexdigest()[:16]
    assert result.rejected == ()
    assert len(result.entity_type_proposals_needing_verification) == 1
    assert result.entity_type_proposals_needing_verification[0].entity_name == "Area35 Art Gallery"


def test_proposition_rejected_by_both_builders_appears_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The double-processing bug this module exists to avoid: a
    proposition neither builder can handle must appear in `rejected`
    EXACTLY ONCE (from build_relation_atoms(), the second/final builder
    tried), never twice."""
    entities = ()
    propositions = (
        make_proposition("Federico Garibaldi", "was born in", "Chiavari, Italy", ref="CLAIM-3"),
    )

    def _fake_extract(*a, **k):
        return entities, propositions, ()

    monkeypatch.setattr(orchestrator, "extract_candidates", _fake_extract)

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert result.atoms == ()
    assert len(result.rejected) == 1
    assert result.rejected[0].reason_code == "PREDICATE_TEXT_NOT_MAPPED"
    assert result.rejected[0].extraction_claim_ref == "CLAIM-3"


def test_mixed_batch_attribute_and_relation_together(monkeypatch: pytest.MonkeyPatch) -> None:
    entities = (make_entity("UniCredit Pavilion"),)
    propositions = (
        make_proposition("Some Work", "edition_size", "5", ref="CLAIM-4"),
        make_proposition("BlueShores", "was presented at", "UniCredit Pavilion, Milan", ref="CLAIM-5"),
        make_proposition("Federico Garibaldi", "explores", "landscape", ref="CLAIM-6"),
    )

    def _fake_extract(*a, **k):
        return entities, propositions, ()

    def _fake_classify(batch_entities, **k):
        return tuple(
            EntityTypeProposal(
                entity_name=e.name, entity_type="PLACE",
                confidence="HIGH", source="MODEL_INFERENCE", needs_verification=True,
            )
            for e in batch_entities
        )

    monkeypatch.setattr(orchestrator, "extract_candidates", _fake_extract)
    monkeypatch.setattr("gmv_crawler_relation_atom_builder.classify_entity_types", _fake_classify)

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert len(result.atoms) == 2
    predicates = {atom.predicate for atom in result.atoms}
    assert predicates == {"edition_size", "located_at"}
    assert len(result.rejected) == 1
    assert result.rejected[0].raw_predicate == "explores"


def test_extraction_level_rejects_kept_separate_from_atom_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_extract(*a, **k):
        return (), (), ("malformed entity: missing name",)

    monkeypatch.setattr(orchestrator, "extract_candidates", _fake_extract)

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert result.extraction_rejected == ("malformed entity: missing name",)
    assert result.rejected == ()
    assert result.atoms == ()


def test_network_failure_in_extraction_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_extract(*a, **k):
        raise RuntimeError("OLLAMA_UNAVAILABLE")

    monkeypatch.setattr(orchestrator, "extract_candidates", _raise_extract)
    with pytest.raises(RuntimeError, match="OLLAMA_UNAVAILABLE"):
        process_document(make_document(), evidence_ids=("EV-1",), now=NOW)


def test_all_entities_returned_verbatim_even_when_no_atom_uses_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entities = (make_entity("Some Entity Never Referenced"),)

    def _fake_extract(*a, **k):
        return entities, (), ()

    monkeypatch.setattr(orchestrator, "extract_candidates", _fake_extract)
    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert result.all_entities == entities
