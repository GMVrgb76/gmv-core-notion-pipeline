import copy
import hashlib
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "10_API"))

from gmv_crawler_candidate_extractor import CandidateEntity, CandidateProposition  # noqa: E402
from gmv_crawler_entity_resolver import EntityIdentityProposal, EntityTypeProposal, _forma  # noqa: E402
from gmv_crawler_extractor import ExtractionDocument  # noqa: E402
from gmv_crawler_orchestrator import ProcessDocumentResult, process_document  # noqa: E402

import gmv_crawler_orchestrator as orchestrator  # noqa: E402

GOOD_HASH = "sha256:" + "a" * 64
NOW = "2026-09-17T12:00:00Z"


@pytest.fixture(autouse=True)
def _stub_classify_document(monkeypatch: pytest.MonkeyPatch):
    """classify_document() (added 2026-09-21) runs first in process_document()
    now -- default every test to document_type="biography" (the original,
    only, path before this change) so they stay pure/fast/deterministic (no
    real Ollama call) unless a test explicitly overrides this stub itself
    for a price_list/contract-routing test."""
    monkeypatch.setattr(orchestrator, "classify_document", lambda *a, **k: {"document_type": "biography", "confidence": "high"})


def make_document(text: str = "some real-looking text") -> ExtractionDocument:
    return ExtractionDocument(
        source_id="SRC-1", source_hash=GOOD_HASH, status="SUCCESS",
        extractor="text", text=text,
    )


def make_entity(
    name: str, *, source_id: str = "SRC-1", excerpt: str = "excerpt",
) -> CandidateEntity:
    return CandidateEntity(
        name=name, evidence_excerpt=excerpt, status="DOCUMENTATO",
        source_id=source_id, evidence_id=("EV-1",),
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


# --- document-type routing (2026-09-21) ---

def test_price_list_routes_to_price_extractor_not_entities_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    """A price_list-classified document must never call extract_candidates()
    at all -- see gmv_crawler_document_classifier.py's own docstring for why
    entities/claims produces unmappable noise on this document type."""
    from gmv_crawler_price_extractor import CandidateArtworkPrice

    monkeypatch.setattr(orchestrator, "classify_document", lambda *a, **k: {"document_type": "price_list", "confidence": "high"})

    def _fail_extract(*a, **k):
        raise AssertionError("extract_candidates() must not be called for a price_list document")

    price_entry = CandidateArtworkPrice(
        title="Don Quijote", price=7500, evidence_excerpt="Prezzo: 7500",
        source_id="SRC-1", evidence_id=("EV-1",), extraction_claim_ref="SRC-1#0",
    )

    def _fake_price_extract(*a, **k):
        return (price_entry,), ()

    def _fail_registry(*a, **k):
        raise AssertionError(
            "_load_entity_registry() must not be called for a price_list document: the "
            "branch returns before extract_candidates(), so no entity name ever exists "
            "to propose an identity for"
        )

    monkeypatch.setattr(orchestrator, "extract_candidates", _fail_extract)
    monkeypatch.setattr(orchestrator, "extract_price_entries", _fake_price_extract)
    monkeypatch.setattr(orchestrator, "_load_entity_registry", _fail_registry)

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert result.document_type == "price_list"
    assert result.price_entries == (price_entry,)
    assert result.price_rejected == ()
    assert result.atoms == ()
    assert result.all_entities == ()
    assert result.contract_summary is None
    # Identity proposals are declared in that construction explicitly, not left
    # to a dataclass default that would silently keep covering this branch if a
    # future edit moved the load above the early return.
    assert result.entity_identity_proposals == ()


def test_contract_runs_both_entities_claims_and_contract_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """A contract-classified document must run BOTH extract_candidates()
    (parties as entities, obligations as claims) AND
    extract_contract_summary() (structured commission/obligations) -- see
    ProcessDocumentResult's own docstring for the live finding neither
    alone is as complete as both together."""
    from gmv_crawler_contract_extractor import CandidateContractSummary

    monkeypatch.setattr(orchestrator, "classify_document", lambda *a, **k: {"document_type": "contract", "confidence": "high"})

    entities = (make_entity("Area35 Art Factory"),)
    propositions = (make_proposition("Area35 Art Factory", "edition_size", "5", ref="CLAIM-1"),)

    def _fake_extract(*a, **k):
        return entities, propositions, ()

    summary = CandidateContractSummary(
        evidence_excerpt="ACCORDO TRA ARTISTA E GALLERIA",
        source_id="SRC-1", evidence_id=("EV-1",), extraction_claim_ref="SRC-1#0",
        commission_percentage="50%",
    )
    calls = []

    def _fake_contract_summary(*a, **k):
        calls.append(True)
        return summary

    monkeypatch.setattr(orchestrator, "extract_candidates", _fake_extract)
    monkeypatch.setattr(orchestrator, "extract_contract_summary", _fake_contract_summary)

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert result.document_type == "contract"
    assert len(calls) == 1
    assert result.contract_summary == summary
    assert result.all_entities == entities
    assert len(result.atoms) == 1  # the entities/claims -> atoms path still ran


def test_contract_summary_failure_keeps_the_already_extracted_atoms(monkeypatch: pytest.MonkeyPatch) -> None:
    """Live, reproduced 2026-09-23 (nightly crawler run, real Garibaldi
    "accordo di rappresentanza"): extract_contract_summary() is
    deliberately NOT chunked (a contract's terms don't merge sensibly
    across independent halves), so a long real contract can overflow
    num_predict and raise OLLAMA_OUTPUT_TRUNCATED. That exception used to
    propagate straight out of process_document(), discarding the atoms/
    entities extract_candidates() had ALREADY extracted successfully just
    above. Now a genuine failure here just leaves contract_summary=None
    instead of losing everything."""
    from gmv_evidence_pipeline import OllamaResponseError

    monkeypatch.setattr(orchestrator, "classify_document", lambda *a, **k: {"document_type": "contract", "confidence": "high"})

    entities = (make_entity("Federico Garibaldi"),)
    propositions = (make_proposition("Federico Garibaldi", "edition_size", "5", ref="CLAIM-1"),)

    def _fake_extract(*a, **k):
        return entities, propositions, ()

    def _fake_contract_summary_fails(*a, **k):
        raise OllamaResponseError("OLLAMA_OUTPUT_TRUNCATED", runtime={}, raw_output="")

    monkeypatch.setattr(orchestrator, "extract_candidates", _fake_extract)
    monkeypatch.setattr(orchestrator, "extract_contract_summary", _fake_contract_summary_fails)

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert result.document_type == "contract"
    assert result.contract_summary is None
    assert result.all_entities == entities
    assert len(result.atoms) == 1  # the entities/claims -> atoms path still ran


def test_biography_never_calls_price_or_contract_extractors(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*a, **k):
        raise AssertionError("must not be called for a biography document")

    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: ((), (), ()))
    monkeypatch.setattr(orchestrator, "extract_price_entries", _fail)
    monkeypatch.setattr(orchestrator, "extract_contract_summary", _fail)

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert result.document_type == "biography"
    assert result.price_entries == ()
    assert result.contract_summary is None


def test_document_type_always_populated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator, "classify_document", lambda *a, **k: {"document_type": "press_release", "confidence": "medium"})
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: ((), (), ()))
    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert result.document_type == "press_release"


# --- unresolved-identity proposals (2026-09-26) ---
#
# The guarantees this section tries to BREAK, deliberately:
#   I1 "a name the registry resolves produces no proposal; an unresolved
#       one produces exactly one, carrying the CandidateEntity's own
#       name/source_id/evidence_excerpt verbatim"
#       -> test_identity_proposal_only_for_names_the_registry_cannot_resolve
#   I2 "price_list is unaffected" (the field is (), and the registry is
#       never even read on that path)
#       -> test_price_list_routes_to_price_extractor_not_entities_claims
#   I3 "no deduplication, no grouping, no did-you-mean" -- the same raw
#       name twice in one document is TWO proposals
#       -> test_identity_proposals_are_not_deduplicated_within_a_document
#   I4 "the registry is read fresh per document, never cached across a
#       run" -- a human confirming an entity between two documents of one
#       run must be visible to the second
#       -> test_identity_proposals_see_a_registry_edit_made_between_documents
#
# Every test here patches `_load_entity_registry` rather than relying on
# 00_CONFIG/gmv_entity_registry.json's current contents, for the reason
# tests/test_gmv_crawler_entity_resolver.py's institution-list test states
# about area35_known_institutions.json: that file grows through human
# confirmation, and a test that depends on what it happens to contain
# starts failing the next time someone uses the product. The registry
# file's own contents are pinned where they belong -- by
# test_committed_entity_registry_file_resolves_its_own_entity.
#
# NOT re-tested here, on purpose, because an existing test already pins it
# in the module that owns the guarantee:
# test_no_production_module_calls_a_registry_write_function (Task 13, A7)
# statically scans 10_API/ and automation/ and fails if this module ever
# calls confirm_new_entity()/confirm_entity_alias() -- i.e. the
# human-gate boundary this section most needs protecting is already
# enforced by a test that would break loudly if a future edit crossed it.

_KNOWN_ENTITY = {
    "gmv_id": "GMV-000001",
    "entity_type": "ARTIST",
    "canonical_name": "Federico Garibaldi",
    "aliases": ["Garibaldi"],
    "status": "ACTIVE",
}


def test_identity_proposal_only_for_names_the_registry_cannot_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I1, both halves in one document: the known name yields nothing, the
    unknown one yields exactly one proposal, and the proposal carries the
    CandidateEntity's own provenance fields byte-for-byte (a locator
    trimmed to look tidier would point at a file that does not exist)."""
    resolvable = make_entity("Federico Garibaldi", source_id="SRC-DOC-A")
    unresolved = make_entity(
        "Danilo Bucchi", source_id="/real/dropbox/locator.md",
        excerpt="testo citato:  e' stato esposto da Danilo Bucchi",
    )
    monkeypatch.setattr(
        orchestrator, "_load_entity_registry",
        lambda: {"note": "test fixture", "entities": [dict(_KNOWN_ENTITY)]},
    )
    monkeypatch.setattr(
        orchestrator, "extract_candidates", lambda *a, **k: ((resolvable, unresolved), (), ()),
    )

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert result.entity_identity_proposals == (
        EntityIdentityProposal(
            raw_name="Danilo Bucchi",
            # Never computed here: classify_entity_types() stays
            # build_relation_atoms()'s scoped job, so an unattended run
            # never spends a model call on a path whose whole contract is
            # "cheap, mechanical, no network".
            suggested_entity_type="",
            source_id="/real/dropbox/locator.md",
            evidence_excerpt="testo citato:  e' stato esposto da Danilo Bucchi",
        ),
    )
    # Orthogonal to atom-building: the alias "Garibaldi" in the test
    # registry must suppress the proposal too, without changing what the
    # document produced above.
    monkeypatch.setattr(
        orchestrator, "extract_candidates", lambda *a, **k: ((make_entity("Garibaldi"),), (), ()),
    )
    from_alias = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert from_alias.entity_identity_proposals == ()
    # Nothing about the atom side of the result moved: no propositions
    # above means no atoms either way, and the entities themselves are
    # still returned verbatim for whatever the caller does with them.
    assert result.atoms == ()
    assert result.all_entities == (resolvable, unresolved)


def test_identity_proposals_are_not_deduplicated_within_a_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I3, the direct attack. Two CandidateEntity rows carrying the SAME
    unresolved name -- which is what a real extraction produces when a
    document mentions someone twice -- must produce TWO proposals, not
    one. A "helpfully" deduplicating pipeline would be making the call
    that these are one entity, which is precisely the judgement
    gmv_crawler_entity_identity_proposal_queue.py's own module docstring
    assigns to a human reading the queue."""
    monkeypatch.setattr(
        orchestrator, "_load_entity_registry",
        lambda: {"note": "test fixture", "entities": [dict(_KNOWN_ENTITY)]},
    )
    first = make_entity("Danilo Bucchi", source_id="SRC-DOC-A", excerpt="first mention")
    second = make_entity("Danilo Bucchi", source_id="SRC-DOC-B", excerpt="second mention")
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: ((first, second), (), ()))

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert len(result.entity_identity_proposals) == 2
    assert [p.raw_name for p in result.entity_identity_proposals] == ["Danilo Bucchi"] * 2
    # Not collapsed even down to the provenance: the two rows point at two
    # different places in the document, and a human reviewing the queue
    # needs to see both, not one arbitrarily-chosen citation.
    assert [p.source_id for p in result.entity_identity_proposals] == ["SRC-DOC-A", "SRC-DOC-B"]
    assert [p.evidence_excerpt for p in result.entity_identity_proposals] == [
        "first mention", "second mention",
    ]


def test_identity_proposals_see_a_registry_edit_made_between_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """I4, in the shape that actually breaks. The same unknown name is
    processed twice in one process, with a human confirming it in
    between (the registry's own documented maintenance model: a person
    edits the file). The second document must produce NO proposal. A
    module-level cache, an lru_cache, or a registry loaded once per run
    would keep proposing a name the human has already answered, and the
    queue would stop being a truthful list of what is actually unknown.

    The fake loader hands back a FRESH deep copy on every call, not the
    live dict, so a cache of the first return value really does go stale
    and this test really does fail on one."""
    registry = {"note": "test fixture", "entities": [dict(_KNOWN_ENTITY)]}
    reads: list[int] = []

    def _fake_load() -> dict:
        reads.append(1)
        return copy.deepcopy(registry)

    monkeypatch.setattr(orchestrator, "_load_entity_registry", _fake_load)
    entity = make_entity("Danilo Bucchi", source_id="SRC-DOC-A", excerpt="cited")
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: ((entity,), (), ()))

    first = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert [p.raw_name for p in first.entity_identity_proposals] == ["Danilo Bucchi"]

    # The human confirms it, mid-run, through the real write path's shape.
    registry["entities"].append({
        "gmv_id": "GMV-000002", "entity_type": "ARTIST",
        "canonical_name": "Danilo Bucchi", "aliases": [], "status": "ACTIVE",
    })

    second = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert second.entity_identity_proposals == ()
    # One load per document, not one per run and not one per entity.
    assert len(reads) == 2, reads


# --- "technique, WxH cm" caption rescue + WORK identity proposals ---
#
# 2026-09-27, opencode task brief opencode_task_17.md. The guarantees this
# section tries to BREAK, deliberately:
#   W1 "a real caption-shaped claim becomes exactly two atoms
#       (medium + dimensions), verbatim, is not also reported as a
#       rejection, and yields WORK identity proposals for the work's title"
#       -> test_caption_claim_builds_two_atoms_and_work_identity_proposals
#   W2 "a rescued claim never reaches build_relation_atoms(), so it is not
#       logged a second time as PREDICATE_TEXT_NOT_MAPPED"
#       -> test_rescued_caption_claim_never_reaches_the_relation_builder
#   W3 "ProcessDocumentResult.rejected is STILL ONLY
#       build_relation_atoms()'s final rejections, for every proposition
#       the rescue did not touch" (task constraint 4)
#       -> test_rejected_is_still_only_relation_rejections_alongside_a_rescue
#       -> test_non_caption_dimension_shaped_claim_is_still_rejected_once
#   W4 "no deduplication: two WORK-domain propositions about one subject
#       are two proposals"
#       -> test_two_work_propositions_on_one_subject_are_not_deduplicated
#   W5 "the WORK set comes from the real registry's declared `domain`,
#       not a hardcoded id list"
#       -> test_work_domain_set_matches_the_real_registry_entry_by_entry
#   W6 "a subject the entity registry already resolves produces no
#       proposal at all"
#       -> test_a_resolvable_work_subject_produces_no_identity_proposal
#
# As with the section above, every test patches `_load_entity_registry`
# rather than relying on the real registry file's current contents.


# One of the 5 real caption rows in the live rejection queue, verbatim
# (source_id/claim-ref shape included, the claim index really is "0:1").
REAL_CAPTION_SOURCE = (
    "/gmv_master_system/01_area35_master/01_artists/genna_davide/10_md_processed_files/"
    "07_career__05_monographs__cataloghi__2025_03_21_davide genna_portfolio lavori al 2025.pdf.md"
)
REAL_CAPTION_CLAIM = (
    "Il bacio",
    "smalto, unghie, alluminio e carta su tavola",
    "90 x 60 x 5 cm",
    "***Il bacio*** – 2020 smalto, unghie, alluminio e carta su tavola 90 x 60 x 5 cm",
)


@pytest.fixture
def _empty_entity_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """A registry holding only one known ARTIST, so "Il bacio" and every
    other test subject below is genuinely unresolved and produces a
    proposal."""
    monkeypatch.setattr(
        orchestrator, "_load_entity_registry",
        lambda: {"note": "test fixture", "entities": [dict(_KNOWN_ENTITY)]},
    )


def test_caption_claim_builds_two_atoms_and_work_identity_proposals(
    monkeypatch: pytest.MonkeyPatch, _empty_entity_registry: None,
) -> None:
    """W1, the whole rescue end to end through the real orchestrator. The
    real claim shape is reproduced verbatim (including its long real
    locator, which is what the atom_id is derived from)."""
    subject, predicate, obj, excerpt = REAL_CAPTION_CLAIM
    claim_ref = f"{REAL_CAPTION_SOURCE}#0:1"
    proposition = CandidateProposition(
        subject_raw=subject, predicate=predicate, object_raw=obj,
        evidence_excerpt=excerpt, status="DOCUMENTATO", source_id=REAL_CAPTION_SOURCE,
        evidence_id=("EV-1",), truncated_source=False, extraction_claim_ref=claim_ref,
    )
    monkeypatch.setattr(
        orchestrator, "extract_candidates", lambda *a, **k: ((), (proposition,), ()),
    )

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)

    # Two atoms, one per governed predicate, both carrying the real work's
    # title as subject and the real text verbatim as object.
    assert [(a.predicate, a.subject, a.object, a.object_type) for a in result.atoms] == [
        ("medium", "Il bacio", "smalto, unghie, alluminio e carta su tavola", "string"),
        ("dimensions", "Il bacio", "90 x 60 x 5 cm", "string"),
    ]
    # The ids come from the SYNTHETIC refs, one per fact, so the two atoms
    # of one caption can never collide on a single atom_id.
    assert [a.atom_id for a in result.atoms] == [
        "ATOM-" + hashlib.sha256(f"{REAL_CAPTION_SOURCE}|{claim_ref}#medium".encode()).hexdigest()[:16],
        "ATOM-" + hashlib.sha256(f"{REAL_CAPTION_SOURCE}|{claim_ref}#dimensions".encode()).hexdigest()[:16],
    ]
    # Rescued: the claim produced atoms, so it is NOT also reported as a
    # rejection (a second PREDICATE_TEXT_NOT_MAPPED would misdescribe it).
    assert result.rejected == ()
    # And the work's TITLE gets WORK identity proposals carrying the
    # proposition's own real provenance -- TWO of them, not one: the
    # rescue produces a `medium` and a `dimensions` proposition about that
    # one subject, and identity proposals are deliberately never
    # deduplicated (see W4's own test for the reasoning).
    assert result.entity_identity_proposals == (
        EntityIdentityProposal(
            raw_name="Il bacio", suggested_entity_type="WORK",
            source_id=REAL_CAPTION_SOURCE, evidence_excerpt=excerpt,
        ),
        EntityIdentityProposal(
            raw_name="Il bacio", suggested_entity_type="WORK",
            source_id=REAL_CAPTION_SOURCE, evidence_excerpt=excerpt,
        ),
    )


def test_rescued_caption_claim_never_reaches_the_relation_builder(
    monkeypatch: pytest.MonkeyPatch, _empty_entity_registry: None,
) -> None:
    """W2 in the shape that actually breaks it: if the rescued claim were
    still handed to build_relation_atoms(), that call would (a) need a
    classify_entity_types() model call for nothing and (b) emit a stale
    duplicate rejection. Failing the call outright is stronger than
    asserting on its arguments."""
    subject, predicate, obj, excerpt = REAL_CAPTION_CLAIM
    proposition = CandidateProposition(
        subject_raw=subject, predicate=predicate, object_raw=obj,
        evidence_excerpt=excerpt, status="DOCUMENTATO", source_id=REAL_CAPTION_SOURCE,
        evidence_id=("EV-1",), truncated_source=False,
        extraction_claim_ref=f"{REAL_CAPTION_SOURCE}#0:1",
    )

    def _fail_relation(*a, **k):
        raise AssertionError(
            "build_relation_atoms() must not see a claim the caption rescue already built"
        )

    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: ((), (proposition,), ()))
    monkeypatch.setattr(orchestrator, "build_relation_atoms", _fail_relation)

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert [a.predicate for a in result.atoms] == ["medium", "dimensions"]


def test_rejected_is_still_only_relation_rejections_alongside_a_rescue(
    monkeypatch: pytest.MonkeyPatch, _empty_entity_registry: None,
) -> None:
    """W3, the task's constraint 4, verified with a real run rather than by
    inspection: one document carrying BOTH a rescued caption claim and a
    genuinely unmapped, non-caption-shaped claim. The second must still
    come out of build_relation_atoms() as PREDICATE_TEXT_NOT_MAPPED, once,
    and the rescued one must not appear in `rejected` at all."""
    subject, predicate, obj, excerpt = REAL_CAPTION_CLAIM
    propositions = (
        CandidateProposition(
            subject_raw=subject, predicate=predicate, object_raw=obj,
            evidence_excerpt=excerpt, status="DOCUMENTATO", source_id=REAL_CAPTION_SOURCE,
            evidence_id=("EV-1",), truncated_source=False,
            extraction_claim_ref=f"{REAL_CAPTION_SOURCE}#0:1",
        ),
        make_proposition("Federico Garibaldi", "was born in", "Chiavari, Italy", ref="CLAIM-9"),
    )
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: ((), propositions, ()))

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)

    assert [a.predicate for a in result.atoms] == ["medium", "dimensions"]
    assert [r.extraction_claim_ref for r in result.rejected] == ["CLAIM-9"]
    assert [r.reason_code for r in result.rejected] == ["PREDICATE_TEXT_NOT_MAPPED"]
    # "was born in" resolves to no predicate at all, so it contributes no
    # WORK identity proposal either; only the rescued work's title does --
    # twice, one per synthetic proposition, for the no-dedup reason above.
    assert [p.raw_name for p in result.entity_identity_proposals] == ["Il bacio", "Il bacio"]


def test_non_caption_dimension_shaped_claim_is_still_rejected_once(
    monkeypatch: pytest.MonkeyPatch, _empty_entity_registry: None,
) -> None:
    """W3's other half, and the guard against over-rescuing: the real
    multi-panel row ("45 x 55, 45 x 60 cm" -- "cm" on the last part only)
    must produce NO atoms and the usual single PREDICATE_TEXT_NOT_MAPPED
    rejection, exactly as before this feature existed. A loosened pattern
    that started accepting it would fail here."""
    proposition = make_proposition(
        "Vocazione sognante", "tessuti e carta su tavola", "45 x 55, 45 x 60 cm", ref="CLAIM-10",
    )
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: ((), (proposition,), ()))

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert result.atoms == ()
    assert [r.reason_code for r in result.rejected] == ["PREDICATE_TEXT_NOT_MAPPED"]
    assert [r.extraction_claim_ref for r in result.rejected] == ["CLAIM-10"]
    assert result.entity_identity_proposals == ()


def test_two_work_propositions_on_one_subject_are_not_deduplicated(
    monkeypatch: pytest.MonkeyPatch, _empty_entity_registry: None,
) -> None:
    """W4, the direct attack, and the exact real shape the caption rescue
    produces: ONE work with BOTH a `dimensions` and a `medium` fact about
    it. Two proposals, not one -- collapsing them would be this function
    deciding the two facts are about one entity, which is the human's call
    at the identity queue's gate."""
    propositions = (
        make_proposition("Il bacio", "dimensions", "90 x 60 x 5 cm", ref="CLAIM-11"),
        make_proposition("Il bacio", "medium", "smalto e acrilico su tavola", ref="CLAIM-12"),
    )
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: ((), propositions, ()))

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert [p.raw_name for p in result.entity_identity_proposals] == ["Il bacio", "Il bacio"]
    assert {p.suggested_entity_type for p in result.entity_identity_proposals} == {"WORK"}
    assert [p.source_id for p in result.entity_identity_proposals] == ["SRC-1", "SRC-1"]


def test_work_domain_set_matches_the_real_registry_entry_by_entry(
    monkeypatch: pytest.MonkeyPatch, _empty_entity_registry: None,
) -> None:
    """W5, cross-checked against the real registry file rather than a second
    hardcoded list (this repo's recurring review finding: a duplicated
    literal list passes its own tautological test and drifts silently).

    For EVERY predicate the real registry declares with `domain ==
    ["WORK"]`, a proposition using it must produce a WORK identity
    proposal; for every other predicate -- including `edition_number`,
    whose domain is `["ARTWORK_INSTANCE"]`, and the two RELATION
    predicates that also accept a WORK subject but declare a
    MULTI-element domain -- it must not. Both directions are driven from
    the file, so adding a WORK-domain predicate to the registry makes this
    test demand the new behaviour rather than let the orchestrator quietly
    stop covering it."""
    from gmv_atom_validator import _load_ontology_registry

    registry = _load_ontology_registry()
    work_ids = {e["predicate_id"] for e in registry["predicates"] if e.get("domain") == ["WORK"]}
    # Sanity: the real set today, so a registry edit that empties or
    # explodes this cannot make the assertions below vacuous.
    assert work_ids == {"edition_size", "dimensions", "medium", "creation_year"}
    other_ids = [e["predicate_id"] for e in registry["predicates"] if e["predicate_id"] not in work_ids]

    for predicate_id in sorted(work_ids):
        propositions = (make_proposition("Il bacio", predicate_id, "90 x 60 x 5 cm", ref="C-W"),)
        monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, _p=propositions, **k: ((), _p, ()))
        result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
        assert [(p.raw_name, p.suggested_entity_type) for p in result.entity_identity_proposals] == [
            ("Il bacio", "WORK"),
        ], predicate_id

    for predicate_id in other_ids:
        propositions = (make_proposition("Il bacio", predicate_id, "a value", ref="C-X"),)
        monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, _p=propositions, **k: ((), _p, ()))
        result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
        assert result.entity_identity_proposals == (), predicate_id

    # And a raw, unmapped predicate TEXT never proposes anything, even
    # though the ontology registry has no entry for it at all: resolution
    # goes through the registry's own map, never through a string prefix
    # or a heuristic. The object here is deliberately NOT a dimension
    # expression, so the caption rescue does not convert this claim into
    # two governed WORK propositions first -- otherwise this would be
    # testing the rescue twice, not the resolution.
    propositions = (make_proposition("Il bacio", "smalto, unghie, alluminio e carta su tavola", "tessuto", ref="C-R"),)
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: ((), propositions, ()))
    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert result.entity_identity_proposals == ()


def test_a_resolvable_work_subject_produces_no_identity_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W6. A `dimensions` fact about a work the entity registry already
    knows resolves to exactly one gmv_id: no proposal, and nothing else
    about the document changes. The `None` return is filtered, not
    converted into a proposal for a name that needs no decision."""
    monkeypatch.setattr(
        orchestrator, "_load_entity_registry",
        lambda: {"note": "test fixture", "entities": [dict(_KNOWN_ENTITY)]},
    )
    propositions = (
        make_proposition("Federico Garibaldi", "dimensions", "90 x 60 x 5 cm", ref="CLAIM-13"),
    )
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: ((), propositions, ()))

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert result.entity_identity_proposals == ()
    assert [a.predicate for a in result.atoms] == ["dimensions"]

def test_process_document_does_not_propose_identity_for_known_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bare geographic name in 00_CONFIG/area35_known_places.json ("Roma")
    must never reach propose_entity_identity(), even though it does not
    resolve against the entity registry -- mirrors
    test_a_resolvable_work_subject_produces_no_identity_proposal's mocking
    convention (extract_candidates() stubbed, no real Ollama call) rather
    than exercising the real extractor."""
    monkeypatch.setattr(
        orchestrator, "_load_entity_registry",
        lambda: {"note": "test fixture", "entities": []},
    )
    entities = (make_entity("Roma"),)
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: (entities, (), ()))

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert result.entity_identity_proposals == ()


def test_process_document_unaffected_for_unresolved_institution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real, unresolved institution name NOT in area35_known_places.json
    must still produce an identity proposal -- proves the places filter
    only blocks what it's meant to, not every unresolved name."""
    monkeypatch.setattr(
        orchestrator, "_load_entity_registry",
        lambda: {"note": "test fixture", "entities": []},
    )
    entities = (make_entity("Accademia di Belle Arti"),)
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: (entities, (), ()))

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert [p.raw_name for p in result.entity_identity_proposals] == ["Accademia di Belle Arti"]


def test_process_document_does_not_propose_identity_for_country_not_in_curated_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 29's end-to-end country filter, at the filter point Task 26/27
    built. "Bulgaria" is a real bare country name from the live run and is
    deliberately NOT in 00_CONFIG/area35_known_places.json -- asserted here
    against the real loader so this test cannot become vacuous if a human
    curates it by hand later. The city case below is what keeps the
    hand-curated file load-bearing."""
    curated = orchestrator._load_known_places()
    for name in ("Bulgaria", "Montenegro", "ROMANIA"):
        assert _forma(name) not in curated, name
        monkeypatch.setattr(
            orchestrator, "_load_entity_registry",
            lambda: {"note": "test fixture", "entities": []},
        )
        entities = (make_entity(name),)
        monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: (entities, (), ()))

        result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
        assert result.entity_identity_proposals == (), name


def test_process_document_still_proposes_uncurated_city(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the guarantee: a real CITY that is neither a country
    nor in the hand-curated list must still be proposed. If the new check ever
    degraded into "not a known curated place", this real unresolved name would
    be silently dropped."""
    name = "Trieste"
    assert _forma(name) not in orchestrator._load_known_places()
    assert not orchestrator._is_known_country(name)
    monkeypatch.setattr(
        orchestrator, "_load_entity_registry",
        lambda: {"note": "test fixture", "entities": []},
    )
    entities = (make_entity(name),)
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: (entities, (), ()))

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert [p.raw_name for p in result.entity_identity_proposals] == [name]


def test_process_document_still_proposes_institution_naming_a_country(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adversarial test of the exact-match guarantee, through the real
    orchestrator. "Biennale di Venezia, Padiglione Italia" contains a
    country name and is a real string from the corpus; it has a real
    institutional identity for a human to verify, so a substring or
    partial-name rule would have discarded it."""
    name = "Biennale di Venezia, Padiglione Italia"
    assert not orchestrator._is_known_country(name)
    monkeypatch.setattr(
        orchestrator, "_load_entity_registry",
        lambda: {"note": "test fixture", "entities": []},
    )
    entities = (make_entity(name),)
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: (entities, (), ()))

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    assert [p.raw_name for p in result.entity_identity_proposals] == [name]


def test_process_document_country_filter_also_covers_the_work_subject_loop(
    monkeypatch: pytest.MonkeyPatch, _empty_entity_registry: None,
) -> None:
    """The SECOND filter point, which the first test above cannot reach: a
    WORK-domain proposition whose subject is a country name. `dimensions` is
    a real WORK-domain predicate per the real ontology registry, so this
    drives the same ontology lookup the orchestrator itself uses rather than
    hardcoding a belief about it."""
    propositions = (
        make_proposition("Montenegro", "dimensions", "90 x 60 x 5 cm", ref="CLAIM-CTY-1"),
        make_proposition("Il bacio", "dimensions", "90 x 60 x 5 cm", ref="CLAIM-CTY-2"),
    )
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: ((), propositions, ()))

    result = process_document(make_document(), evidence_ids=("EV-1",), now=NOW)
    # "Montenegro" dropped from the identity queue, "Il bacio" kept: same
    # loop, same predicate, only the subject differs.
    assert [p.raw_name for p in result.entity_identity_proposals] == ["Il bacio"]
    # And the atom is still built for the dropped subject -- this is an
    # identity-queue filter, not a proposition filter. Asserted on the
    # subject, because AtomCandidate (the frozen 18-field schema) carries no
    # claim ref; the two claims differ only by claim_ref, so identical
    # subjects here would mean the atoms collided.
    assert [(a.predicate, a.subject) for a in result.atoms] == [
        ("dimensions", "Montenegro"),
        ("dimensions", "Il bacio"),
    ]


# ---------------------------------------------------------------------------
# The pre-extraction non-prose gate (2026-10-05, opencode_task_35.md).
#
# Follows the same mocking convention already established above:
# monkeypatch.setattr(orchestrator, "<stage>", <raiser>) for the stages
# that must NEVER run, so "was it called" is proven by a loud failure
# rather than by an assertion about an empty result (which an unrelated
# bug could produce just as well).
# ---------------------------------------------------------------------------

# Real locators, verbatim from the live 01_RUNTIME/gmv_crawler/registry.db,
# not invented for the test. ALL SIX real CSV-sourced locators in that
# registry (3513 rows total) -- three distinct source files, each present
# both as the original and as its real AnyDoc `.md` conversion, which is
# why the conversion shape is half the list. The first two files are the
# ones that produced the 672 MOVE_CANONICAL/MOVE_TEMP_IMPORT/MOVE_DUPLICATE
# rows in the live rejection_queue.jsonl; their completeness here is
# checked against the real DB by
# test_detector_gates_every_real_csv_locator_and_no_real_prose_one.
REAL_CSV_LOCATORS = (
    "/gmv_master_system/01_area35_master/01_artists/geranzani_pietro/00_master/source_manifest.csv",
    "/gmv_master_system/01_area35_master/01_artists/nazeraj_erjon/00_master/source_manifest.csv",
    # Same two files, as their real AnyDoc conversions -- half the real
    # non-prose locators are this shape, and reading only the outer ".md"
    # would let every one of them through.
    "/gmv_master_system/01_area35_master/01_artists/geranzani_pietro/10_md_processed_files/00_master__source_manifest.csv.md",
    "/gmv_master_system/01_area35_master/01_artists/nazeraj_erjon/10_md_processed_files/00_master__source_manifest.csv.md",
    # The one non-manifest CSV (a contacts table -- still not prose), again
    # in both its two real shapes.
    "/gmv_master_system/01_area35_master/01_artists/gasparini_gian_piero/09_temp_import/gp contact.csv",
    "/gmv_master_system/01_area35_master/01_artists/gasparini_gian_piero/10_md_processed_files/09_temp_import__gp contact.csv.md",
)


def _make_document_for(source_id: str, text: str = "colonna;MOVE_CANONICAL;target") -> ExtractionDocument:
    return ExtractionDocument(
        source_id=source_id, source_hash=GOOD_HASH, status="SUCCESS",
        extractor="text", text=text,
    )


@pytest.mark.parametrize("locator", REAL_CSV_LOCATORS)
def test_real_csv_manifest_never_reaches_classification_or_extraction(
    locator: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE guarantee of this gate, for each of the 5 real locators:
    neither classify_document() nor extract_candidates() is ever called.
    Both are stubbed to raise, so a regression that lets a manifest
    through fails the test instead of silently re-queueing the same
    MOVE_CANONICAL noise it exists to remove."""
    def _fail(*a, **k):
        raise AssertionError(f"non-prose source {locator!r} must never reach classification/extraction")

    monkeypatch.setattr(orchestrator, "classify_document", _fail)
    monkeypatch.setattr(orchestrator, "extract_candidates", _fail)
    monkeypatch.setattr(orchestrator, "extract_contract_summary", _fail)
    monkeypatch.setattr(orchestrator, "extract_price_entries", _fail)

    result = process_document(_make_document_for(locator), evidence_ids=("EV-1",), now=NOW)

    assert result.document_type == orchestrator.NON_PROSE_DOCUMENT_TYPE
    # Every payload empty: nothing to extract means nothing to propose,
    # reject, price or contract-summarize.
    assert result.atoms == ()
    assert result.rejected == ()
    assert result.extraction_rejected == ()
    assert result.all_entities == ()
    assert result.entity_type_proposals_needing_verification == ()
    assert result.entity_identity_proposals == ()
    assert result.price_entries == ()
    assert result.price_rejected == ()
    assert result.contract_summary is None


def test_non_prose_verdict_is_not_one_of_the_real_document_types() -> None:
    """Asserted against the REAL classify_document().DOCUMENT_TYPES list,
    not against a copy of it, so a future edit there can never silently
    make this verdict ambiguous -- which would break the one-field answer
    to "was this document ever classified?"."""
    from gmv_crawler_document_classifier import DOCUMENT_TYPES

    assert orchestrator.NON_PROSE_DOCUMENT_TYPE not in DOCUMENT_TYPES


def test_real_prose_documents_are_completely_unaffected(
    monkeypatch: pytest.MonkeyPatch, _empty_entity_registry: None,
) -> None:
    """The other half of the guarantee: real prose locators, in the exact
    three shapes the real registry holds (original, AnyDoc `.md`
    conversion, plain text), still go through classification and
    extraction untouched. If the gate ever degraded into "anything in
    10_md_processed_files" or "anything without a recognised prose
    extension", these would silently produce nothing."""
    seen: list[str] = []
    entities = (make_entity("Some Institution"),)
    propositions = (make_proposition("Some Show", "was held at", "Some Institution", ref="CLAIM-P1"),)

    def _record_classify(text, **k):
        seen.append(text)
        return {"document_type": "biography", "confidence": "high"}

    # Same convention as the relation tests above: a `located_at`-shaped
    # proposition would otherwise reach the real classify_entity_types()
    # and try a real network call (caught live below as a 60s TIMEOUT).
    def _fake_classify(batch_entities, **k):
        return tuple(
            EntityTypeProposal(
                entity_name=e.name, entity_type="INSTITUTION",
                confidence="HIGH", source="MODEL_INFERENCE", needs_verification=True,
            )
            for e in batch_entities
        )

    monkeypatch.setattr(orchestrator, "classify_document", _record_classify)
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: (entities, propositions, ()))
    monkeypatch.setattr("gmv_crawler_relation_atom_builder.classify_entity_types", _fake_classify)

    prose_locators = (
        # Real shapes from the registry. The AnyDoc one is the adversarial
        # case: its name ends in ".csv" one segment BEFORE the ".md", so
        # only a correct `_original_file_name()` unwrap leaves it prose.
        "/gmv_master_system/01_area35_master/01_artists/bonfanti_manuel/10_md_processed_files/09_temp_import__2026_04_not what it seems.docx.md",
        "/gmv_master_system/01_area35_master/01_artists/bertola_francesco/10_md_processed_files/09_temp_import__francesco bertola intima listino.pdf.md",
        "/gmv_master_system/01_area35_master/01_artists/dawson_dennis/object.yaml",
        "/gmv_master_system/01_area35_master/01_artists/dawson_dennis/99_ai_working/project_2026_07_29/work/dawson-scenari-preview.html",
        "/gmv_master_system/01_area35_master/99_exports/mutualart_2026/01_federico_garibaldi/federico garibaldi/federico garibaldi.md",
    )
    for locator in prose_locators:
        result = process_document(
            _make_document_for(locator, text="prose about an artist"),
            evidence_ids=("EV-1",), now=NOW,
        )
        assert result.document_type == "biography", locator
        assert len(seen) == prose_locators.index(locator) + 1, locator

    # Underscored by the real ontology registry's own WORK-domain lookup
    # downstream, so this is not merely "it did not crash".
    assert len(seen) == len(prose_locators)


def test_gate_is_extension_only_and_never_reads_the_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deterministic-only guarantee (hard constraint 1 of the task
    brief), proven adversarially: the gate's verdict for a real CSV
    locator is byte-identical whatever the document text says, INCLUDING
    text that is pure, well-formed prose. A content-sensitive rule would
    pass this only if it ignored content entirely, which is the claim
    under test -- a `.csv` is gated for what it IS, not what it says."""
    locator = REAL_CSV_LOCATORS[0]
    monkeypatch.setattr(orchestrator, "extract_candidates", lambda *a, **k: ((), (), ()))

    prose_text = (
        "Federico Garibaldi nacque a Chiavari nel 1807. Il suo primo "
        "esilio ebbe fine a Montevideo. Poi torno in Italia e si "
        "dedico alla guerra."
    )
    assert orchestrator._is_non_prose_source(locator) is True
    result = process_document(
        _make_document_for(locator, text=prose_text), evidence_ids=("EV-1",), now=NOW,
    )
    assert result.document_type == orchestrator.NON_PROSE_DOCUMENT_TYPE
    assert result.atoms == ()


@pytest.mark.parametrize("source_id,expected", [
    # (real CSV, gated)
    (REAL_CSV_LOCATORS[0], True),
    (REAL_CSV_LOCATORS[2], True),
    # Real prose shapes, never gated -- including a `.md` whose name
    # contains dots, which is where a naive `split(".")[-1]` would break.
    ("/a/b/federico garibaldi.md", False),
    ("/a/10_md_processed_files/09_temp_import__x.docx.md", False),
    ("/a/10_md_processed_files/09_temp_import__x.pdf.md", False),
    # A ".csv" appearing mid-name is not an extension.
    ("/a/10_md_processed_files/09_temp_import__notes.csv di ricerca.txt.md", False),
    # Upper-cased real locator shape (the registry really holds both
    # cases, from different connector sweeps).
    ("/GMV_MASTER_SYSTEM/01_AREA35_MASTER/01_ARTISTS/GERANZANI_PIETRO/00_MASTER/SOURCE_MANIFEST.CSV", True),
    ("/A/10_MD_PROCESSED_FILES/00_MASTER__SOURCE_MANIFEST.CSV.MD", True),
    # Fail-open: an odd name shape must never gate, not even by accident.
    ("/a/b/manifest", False),
    ("", False),
])
def test_is_non_prose_source_cases(source_id: str, expected: bool) -> None:
    """Unit-level truth table for the detector, including the adversarial
    near-miss shapes (a `.csv` that is not the extension; an empty and a
    dotless source_id). The mid-name case is the real one to get right:
    `split(".")[-1]` on `notes.csv di ricerca.txt.md` unwrapped by
    `_original_file_name()` gives `notes.csv di ricerca.txt` -> not
    gated, while a substring check on ".csv" anywhere would wrongly gate
    it and lose a real text."""
    assert orchestrator._is_non_prose_source(source_id) is expected


def test_detector_gates_every_real_csv_locator_and_no_real_prose_one() -> None:
    """Keeps REAL_CSV_LOCATORS honest against the REAL registry instead of
    against a hand-maintained list of extensions: every `.csv`-sourced
    locator the live registry actually holds is gated, and NO locator
    whose underlying file is prose (.pdf/.docx/.doc/.txt/.md/.html) is.

    Read-only: opens the committed registry.db with `mode=ro` so this test
    cannot itself create the sqlite file the write-authorization and
    sqlite-connection boundary tests police elsewhere.
    """
    db = Path(__file__).resolve().parents[1] / "01_RUNTIME" / "gmv_crawler" / "registry.db"
    if not db.is_file():
        pytest.skip(f"real registry not present at {db}")
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
        locators = [row[0] for row in con.execute("SELECT canonical_locator FROM crawler_source_registry")]
    assert locators, "real registry returned no locators at all"

    real_csv = {
        loc for loc in locators
        if orchestrator._original_file_name(loc).lower().endswith(".csv")
    }
    assert real_csv, "no real CSV locator found -- the gate's premise is unverified"
    for loc in real_csv:
        assert orchestrator._is_non_prose_source(loc), loc
    # The list the parametrized test above drives is exactly this set, so
    # a NEW real CSV manifest appearing in the archive cannot slip past
    # this gate untested.
    assert set(REAL_CSV_LOCATORS) == real_csv

    for loc in locators:
        underlying = orchestrator._original_file_name(loc).lower()
        if underlying.endswith((".pdf", ".docx", ".doc", ".txt", ".md", ".html")):
            assert not orchestrator._is_non_prose_source(loc), loc
