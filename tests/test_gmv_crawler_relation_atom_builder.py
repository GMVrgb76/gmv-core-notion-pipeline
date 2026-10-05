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


def make_entity(name: str, *, source_id: str = "SRC-GARIBALDI") -> CandidateEntity:
    return CandidateEntity(
        name=name,
        evidence_excerpt="a real biography mentions this entity",
        status="DOCUMENTATO",
        source_id=source_id,
        evidence_id=("EV-1",),
    )


def make_proposition(
    subject_raw: str, predicate: str, object_raw: str, *, ref: str,
    source_id: str = "SRC-GARIBALDI",
) -> CandidateProposition:
    return CandidateProposition(
        subject_raw=subject_raw,
        predicate=predicate,
        object_raw=object_raw,
        evidence_excerpt=f"the biography states {subject_raw} {predicate} {object_raw}",
        status="DOCUMENTATO",
        source_id=source_id,
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


# =====================================================================
# Task 36 -- the "held at" -> located_at mapping, on REAL data
# =====================================================================
#
# Every fixture below is a verbatim real case, re-extracted for Task 36 from
#   01_artists/morales_ernesto/10_md_processed_files/
#     07_career__01_biography__bio completa en - ernesto morales.doc.md
# (local Dropbox-synced copy; the Dropbox OAuth file is deliberately not read,
# per the gmv-core-safety rule -- see the Task 36 report for how that deviation
# is disclosed). subject_raw / predicate / object_raw / evidence_excerpt are
# copied out of the extraction output unchanged; only source_id, status and
# evidence_id are fixture boilerplate.
#
# Domain/range grounding for these cases, read fresh from
# 00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json in Task 36:
#   located_at domain=[EXHIBITION,EVENT,ORGANIZATION] range=[PLACE,INSTITUTION]
# Every one of the 4 real subjects below is an exhibition title (never a
# person) and every object is a gallery/cultural centre (never a place that
# could be a person), which is what makes this text safe to map.

MORALES_SRC = (
    "/gmv_master_system/01_area35_master/01_artists/morales_ernesto/"
    "10_md_processed_files/07_career__01_biography__bio completa en - ernesto morales.doc.md"
)

# (subject_raw, object_raw, evidence_excerpt) -- all four verbatim from the
# real extraction; each one's object_raw prefix-matches a real extracted entity.
REAL_HELD_AT_CASES = (
    (
        "Equinox –",
        "William Holman Art Gallery",
        "2016\n**Equinox –** William Holman Art Gallery (New York, USA)",
        ":0:26",
    ),
    (
        "En el sueño de Polifilo",
        "Galleria Raffaella De Chirico Arte Contemporanea",
        "2012\n**En el sueño de Polifilo** – testo critico di Roberto Mastroianni – "
        "Galleria Raffaella De Chirico Arte Contemporanea (Torino, Italia)",
        ":0:44",
    ),
    (
        "Le città dell’esilio",
        "Galleria Il Sole Arte Contemporanea",
        "2008\n**Le città dell’esilio** – testo critico di Lorenzo Canova – "
        "Galleria Il Sole Arte Contemporanea (Roma, Italia)",
        ":0:56",
    ),
    (
        "Identidades",
        "Centro Cultural Recoleta",
        "2002\n**Identidades** – Centro Cultural Recoleta (Buenos Aires, Argentina)",
        ":0:90",
    ),
)


def _real_morales_props() -> tuple[CandidateProposition, ...]:
    return tuple(
        CandidateProposition(
            subject_raw=subject,
            predicate="held at",
            object_raw=obj,
            evidence_excerpt=excerpt,
            status="CONFIRMED",
            source_id=MORALES_SRC,
            evidence_id=("EV-TASK36",),
            truncated_source=False,
            extraction_claim_ref=f"{MORALES_SRC}#{ref}",
        )
        for subject, obj, excerpt, ref in REAL_HELD_AT_CASES
    )


def _real_morales_entities() -> tuple[CandidateEntity, ...]:
    return tuple(
        CandidateEntity(
            name=obj,
            evidence_excerpt=excerpt,
            status="CONFIRMED",
            source_id=MORALES_SRC,
            evidence_id=("EV-TASK36",),
        )
        for _subject, obj, excerpt, _ref in REAL_HELD_AT_CASES
    )


def test_real_morales_held_at_cases_build_located_at_atoms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POSITIVE, real data: the 4 verbatim real "held at" cases above each build
    one correctly-shaped located_at atom. Before Task 36 these were rejected as
    PREDICATE_TEXT_NOT_MAPPED; the pinned predicate/predicate_class/shape is the
    whole point of the new mapping entry."""
    monkeypatch.setattr(relation_builder, "classify_entity_types", make_classifier("INSTITUTION"))
    props = _real_morales_props()
    built, rejected = build_relation_atoms(props, _real_morales_entities(), now=NOW)
    assert rejected == ()
    assert len(built) == 4
    for i, entry in enumerate(built):
        subject, obj, _excerpt, _ref = REAL_HELD_AT_CASES[i]
        atom = entry.atom
        assert atom.predicate == "located_at"
        assert atom.predicate_class == "RELATION"
        assert atom.subject == subject  # verbatim exhibition title, no normalization
        assert atom.object == obj  # verbatim venue
        assert atom.object_type == "INSTITUTION"  # in located_at's real range
        assert atom.source == MORALES_SRC
        assert atom.atom_id == "ATOM-" + hashlib.sha256(
            f"{MORALES_SRC}|{props[i].extraction_claim_ref}".encode("utf-8")
        ).hexdigest()[:16]
        assert atom.status == "UNVERIFIED" and atom.confidence == 0.5
        assert atom.visibility == "INTERNAL"
        assert entry.object_type_proposal.needs_verification is True


def test_real_morales_held_at_batch_makes_exactly_one_classify_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The batch-level non-negotiable, re-pinned on the NEW mapping's real
    data: 4 real propositions, 4 distinct venues, exactly ONE
    classify_entity_types() call for the whole batch."""
    calls: list[list[str]] = []
    inner = make_classifier("INSTITUTION")

    def counting(
        entities, *, known_artists=None, known_institutions=None, endpoint=None,
        model=None, timeout=None, temperature=None, seed=None,
    ):
        calls.append([e.name for e in entities])
        return inner(entities, known_artists=known_artists, endpoint=endpoint)

    monkeypatch.setattr(relation_builder, "classify_entity_types", counting)
    built, rejected = build_relation_atoms(
        _real_morales_props(), _real_morales_entities(), now=NOW
    )
    assert rejected == ()
    assert len(built) == 4
    assert len(calls) == 1
    assert calls[0] == [obj for _s, obj, _e, _r in REAL_HELD_AT_CASES]


# --- NEGATIVE: a wrong-shaped use of the SAME raw text must still be rejected ---

def test_held_at_homonym_use_rejected_not_silently_atomified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NEGATIVE #1 -- homonym. "held at" outside the exhibition sense (e.g. "the
    artist held at Fort Knox", or any non-exhibition sentence a future extractor
    might emit with this same text) must NOT become an atom just because the raw
    text matches. The object here is a plausible-looking but un-extracted string,
    so the pass-1 link gate is what catches it -- and classify_entity_types must
    never even be reached."""
    monkeypatch.setattr(relation_builder, "classify_entity_types", _fail_if_called)
    prop = CandidateProposition(
        subject_raw="Ernesto Morales",
        predicate="held at",
        object_raw="Fort Knox, New York",
        evidence_excerpt="he held at Fort Knox for two years",
        status="CONFIRMED",
        source_id=MORALES_SRC,
        evidence_id=("EV-TASK36",),
        truncated_source=False,
        extraction_claim_ref=f"{MORALES_SRC}#homonym:1",
    )
    built, rejected = build_relation_atoms((prop,), _real_morales_entities(), now=NOW)
    assert built == ()
    assert [e.reason_code for e in rejected] == ["OBJECT_NOT_LINKED_TO_KNOWN_ENTITY"]
    assert rejected[0].raw_predicate == "held at"


@pytest.mark.parametrize("wrong_type", ["EXHIBITION", "EVENT", "PERSON", "PROJECT"])
def test_held_at_object_typed_outside_located_at_range_rejected(
    monkeypatch: pytest.MonkeyPatch, wrong_type: str,
) -> None:
    """NEGATIVE #2 -- wrong shape on the OBJECT side, which is the side the real
    validator actually checks. Any object_type outside located_at's real range
    ["PLACE", "INSTITUTION"] must produce VALIDATION_FAILED, never an atom, even
    though "held at" now maps."""
    assert wrong_type not in LOCATED_AT_RANGE
    monkeypatch.setattr(relation_builder, "classify_entity_types", make_classifier(wrong_type))
    built, rejected = build_relation_atoms(
        _real_morales_props(), _real_morales_entities(), now=NOW
    )
    assert built == ()
    assert len(rejected) == 4
    for entry in rejected:
        assert entry.reason_code == "VALIDATION_FAILED"
        assert "A-SCHEMA05" in entry.detail


def test_held_at_person_subject_is_not_mechanically_rejected_documents_domain_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DOCUMENTS A KNOWN, DELIBERATELY UNFIXED LIMITATION -- this test asserts
    the CURRENT (undesirable) behavior so it can never be mistaken for
    correctness or quietly forgotten.

    `validate_atom()` checks only `object_type` against the predicate's range
    and never checks the subject against the domain (gmv_atom_validator.py has
    no reference to "domain" at all; see the Task 10 module docstring). So the
    "person as subject of held at" counter-shape -- the shape that really occurs
    for 'exhibited at' on Davide Genna's CV and that the Task 22 Garibaldi
    finding was exactly -- is NOT caught by any mechanical check: given a real
    linked venue object it builds an atom.

    That is why 'held at' was only mapped after a human confirmed 0/76 real
    occurrences have a person subject. The same gap already applies to the
    pre-existing 'was held at'/'was presented at'/'presente in' entries; fixing
    it means teaching validate_atom() about domains, which is out of scope for
    this task and is NOT attempted here."""
    monkeypatch.setattr(relation_builder, "classify_entity_types", make_classifier("INSTITUTION"))
    entities = _real_morales_entities()
    prop = make_proposition(
        "Ernesto Morales", "held at", "Centro Cultural Recoleta",
        ref=f"{MORALES_SRC}#person-subject:1", source_id=MORALES_SRC,
    )
    built, rejected = build_relation_atoms((prop,), entities, now=NOW)
    assert rejected == ()
    assert len(built) == 1
    assert built[0].atom.subject == "Ernesto Morales"  # a PERSON...
    assert built[0].atom.object_type == "INSTITUTION"
    assert "PERSON" not in _domain_of("located_at")  # ...outside located_at's domain
    # deliberately NOT asserted as correct: see the docstring above.


def _domain_of(predicate_id: str) -> list[str]:
    return next(
        entry["domain"]
        for entry in ONTO["predicates"]
        if entry["predicate_id"] == predicate_id
    )


# --- regression guard: the six EXCLUDED candidates must stay unmapped ---

#: Raw texts Task 36 examined against real source documents and deliberately did
#: NOT map. Each was rejected for a concrete, recorded real reason -- the point of
#: this guard is that a future session reading the rejection queue's frequency
#: counts cannot quietly add one of these back on name-similarity alone, which is
#: the exact failure mode this project has already shipped twice.
TASK36_EXCLUDED = {
    "held": (
        "SPLIT across two real documents of the SAME biography into incompatible "
        "shapes: the 80 cases in 'Bio completa EN - Ernesto Morales.pdf.md' have "
        "subject=Ernesto Morales (a PERSON) -> show title (participated_in-shaped), "
        "while the 52 cases in 'Bio completa EN - IT Ernesto Morales.doc.md' have "
        "subject=exhibition title -> venue (located_at-shaped). The pipeline cannot "
        "tell which is which from the raw text. Independently: 0/132 of those "
        "objects link to an entity from the same extraction, so it would build 0 "
        "atoms whichever predicate it were mapped to."
    ),
    "present": (
        "Split, per constraint 3: 36 of 210 real cases in the Geranzani "
        "dossier are OCR garbage with subject_raw == object_raw (e.g. "
        "'LJJP'|'present'|'LJJP'), i.e. not a relation at all; the remaining "
        "real cases (e.g. 32 in Bio Evangelisti EN.pdf.md) are located_at-shaped."
    ),
    "exhibited": (
        "Split, per constraint 3: on both real sources the object is sometimes "
        "an exhibition title (participated_in-shaped) and sometimes a gallery "
        "(e.g. 'Giovanni Cerri'|'exhibited'|'Galleria Cortina'), and INSTITUTION "
        "is not in participated_in's range [EVENT,EXHIBITION,PROJECT]."
    ),
    "exhibited at": (
        "Split, per constraint 3: 49 real cases in Bio Evangelisti EN.doc.md are "
        "located_at-shaped (exhibition title -> venue), but all 7 in "
        "cv_davide_genna.docx have subject=Davide Genna (a PERSON) -> venue, "
        "which is exactly the Task 22 Garibaldi located_at mis-application. "
        "located_at's domain does not include PERSON and nothing enforces it."
    ),
    "mostra": (
        "Not one shape: 6 real cases in the Emanuela Volpe PDF have subjects "
        "that are variously the literal word 'Mostra', a venue "
        "('Arte Sacra Bergamo'), and a show title, with objects that are "
        "cities, venues and bare media."
    ),
    "presente": (
        "Not a relation at all in its only real source: the 12 fresh cases in "
        "absolute BARBARA COLOMBO. Web version.pdf all have object_raw == the "
        "word 'presente' itself -- it is used as a caption/label, not a verb."
    ),
}


@pytest.mark.parametrize("raw_text", sorted(TASK36_EXCLUDED))
def test_task36_excluded_raw_texts_stay_unmapped(raw_text: str) -> None:
    """Pins the Task 36 exclusions. Each is a real editorial decision recorded
    with a real reason in crawler_predicate_text_mapping.json's sibling
    'held at' entry and in the Task 36 report -- this test only makes sure the
    decision is not silently reversed."""
    mapping = relation_builder._load_predicate_mapping()
    assert raw_text not in mapping, (
        f"{raw_text!r} was deliberately excluded by Task 36 and must not be "
        f"re-added without a fresh real-document domain/range review: "
        f"{TASK36_EXCLUDED[raw_text]}"
    )


def test_task36_exclusions_all_documented_in_mapping_file_notes() -> None:
    """The exclusion reasons above must be discoverable from the mapping file
    itself, not only from a test or a report -- a reader editing that file is
    the person most likely to add 'present'/'held' back on frequency alone."""
    data = json.loads(
        (ROOT / "00_CONFIG" / "crawler_predicate_text_mapping.json").read_text(encoding="utf-8")
    )
    blob = str(data.get("note_on_task36_exclusions", ""))
    assert blob, "crawler_predicate_text_mapping.json must carry note_on_task36_exclusions"
    for raw_text in sorted(TASK36_EXCLUDED):
        assert f"'{raw_text}'" in blob, (
            f"exclusion reason for {raw_text!r} is not recorded in the mapping file"
        )