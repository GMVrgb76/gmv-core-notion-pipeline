"""GMV Crawler — Task 11: DRAFT predicate-mapping proposals (never decisions).

Mechanically guards the proposals file
(00_CONFIG/crawler_predicate_mapping_proposals_DRAFT.json):

- it exists, is valid JSON, and names exactly the 7 raw predicates seen in
  the real rejection-queue snapshot with reason_code=PREDICATE_TEXT_NOT_MAPPED;
- every non-null proposed_predicate_id is a REAL predicate_id loaded from
  GMV_ONTOLOGY_REGISTRY_v0.1.json (no hardcoded second list), and is of
  predicate_class RELATION (none of the 7 sentences is an ATTRIBUTE/IDENTITY
  candidate);
- no entry pairs a non-null direction_note with a non-null proposal (the
  consumer code does not invert subject/object, per opencode_task_11.md and
  Task 10);
- the real governance file crawler_predicate_text_mapping.json still holds
  exactly its 2 original entries (located_at) -- proof this task did not
  silently touch governance.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

from gmv_crawler_rejection_queue import summarize_rejection_queue  # noqa: E402

DRAFT_PATH = ROOT / "00_CONFIG" / "crawler_predicate_mapping_proposals_DRAFT.json"
REGISTRY_PATH = ROOT / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_v0.1.json"
GOVERNANCE_PATH = ROOT / "00_CONFIG" / "crawler_predicate_text_mapping.json"
SNAPSHOT_PATH = ROOT / "00_CONFIG" / "crawler_snapshots" / "rejection_queue_2026-09-17_garibaldi.jsonl"

EXPECTED_RAW_PREDICATES = {
    "was born in",
    "is an",
    "explores",
    "presented",
    "was featured in",
    "acquired",
    "earned",
}

PROPOSAL_FIELDS = {
    "raw_predicate_text",
    "example_sentence",
    "proposed_predicate_id",
    "verification",
    "direction_note",
    "confidence",
}


def _load_draft() -> list[dict]:
    return json.loads(DRAFT_PATH.read_text(encoding="utf-8"))["proposals"]


def _load_registry_predicates() -> dict[str, dict]:
    predicates = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["predicates"]
    return {p["predicate_id"]: p for p in predicates}


def _proposals_with_id(draft: list[dict]) -> list[dict]:
    return [p for p in draft if p["proposed_predicate_id"] is not None]


def test_draft_exists_is_valid_json_with_exactly_seven_proposals() -> None:
    assert DRAFT_PATH.exists(), "DRAFT proposals file must exist"
    drafts = _load_draft()
    assert len(drafts) == 7, f"expected exactly 7 proposals, got {len(drafts)}"


def test_draft_covers_exactly_the_seven_snapshot_unmapped_predicates() -> None:
    raw_texts = {p["raw_predicate_text"] for p in _load_draft()}
    assert len(raw_texts) == 7, "raw_predicate_text must be unique across proposals"
    assert raw_texts == EXPECTED_RAW_PREDICATES

    snapshot_unmapped = {
        e.raw_predicate
        for e in summarize_rejection_queue(SNAPSHOT_PATH)
        if e.reason_code == "PREDICATE_TEXT_NOT_MAPPED"
    }
    assert snapshot_unmapped == EXPECTED_RAW_PREDICATES, (
        "proposals must be grounded in the real snapshot's unmapped predicates"
    )
    assert "was held at" not in raw_texts, (
        "'was held at' is already mapped (VALIDATION_FAILED row) -- out of this task's scope"
    )


def test_draft_entries_match_required_schema() -> None:
    for proposal in _load_draft():
        assert set(proposal) == PROPOSAL_FIELDS, (
            f"unexpected fields for {proposal.get('raw_predicate_text')!r}"
        )
        assert isinstance(proposal["raw_predicate_text"], str)
        assert isinstance(proposal["example_sentence"], str)
        assert isinstance(proposal["verification"], str)
        assert proposal["proposed_predicate_id"] is None or isinstance(
            proposal["proposed_predicate_id"], str
        )
        assert proposal["direction_note"] is None or isinstance(
            proposal["direction_note"], str
        )
        assert proposal["confidence"] in {"HIGH", "MEDIUM", "LOW"}, (
            f"bad confidence for {proposal['raw_predicate_text']!r}"
        )


def test_proposed_predicate_ids_are_registered_in_the_real_registry() -> None:
    registry = _load_registry_predicates()
    for proposal in _proposals_with_id(_load_draft()):
        proposed = proposal["proposed_predicate_id"]
        assert proposed in registry, (
            f"{proposed!r} for {proposal['raw_predicate_text']!r} is not a real "
            "predicate_id in GMV_ONTOLOGY_REGISTRY_v0.1.json"
        )


def test_proposed_predicate_ids_are_all_relation_class() -> None:
    registry = _load_registry_predicates()
    for proposal in _proposals_with_id(_load_draft()):
        proposed = proposal["proposed_predicate_id"]
        assert registry[proposed]["predicate_class"] == "RELATION", (
            f"{proposed!r} for {proposal['raw_predicate_text']!r} is not RELATION "
            "class -- none of the 7 sentences is an ATTRIBUTE/IDENTITY candidate"
        )


def test_no_direction_note_paired_with_a_proposal() -> None:
    for proposal in _load_draft():
        if proposal["direction_note"] is not None:
            assert proposal["proposed_predicate_id"] is None, (
                f"{proposal['raw_predicate_text']!r} has both a direction_note and a "
                "proposed_predicate_id -- the consumer does not invert subject/object"
            )


def test_governance_mapping_file_still_has_only_the_known_verified_entries() -> None:
    """This test originally pinned the file to exactly the 2 entries that
    existed when Task 11 ran, to prove Task 11 (an OpenCode delegation)
    never touched governance. 2026-09-17: a human (the directing session)
    deliberately added a 3rd entry ('was a solo exhibition at', same
    located_at mapping, verified against two separate live re-extractions
    of the same real sentence) -- a legitimate governance edit by the
    party this file's own "note_on_maintenance" says is allowed to make
    one. 2026-09-21: a 4th entry ('ha esposto' -> participated_in) was
    added via the new confirm_predicate_mapping Open WebUI tool -- and
    caught, on review, having FIRST been confirmed as exhibited_at (wrong:
    that predicate's domain is ARTWORK_INSTANCE, but the real example's
    subject was the artist "Giovanni Cerri", a PERSON -- participated_in's
    domain=[PERSON,ARTIST] is what actually matches), corrected before
    this test was updated. 2026-09-22: a 5th entry ('partecipa' ->
    participated_in) was added, verified against two real Bucchi cases
    with the same domain/range shape as 'ha esposto'. 2026-09-25: a 6th
    entry ('presente in' -> located_at) was added, verified against 20
    distinct real cases across multiple artist biographies, all sharing
    the same exhibition/show-title -> gallery/museum shape already
    verified for 'was held at'. 2026-09-25 (same session): the registry
    itself (GMV_ONTOLOGY_REGISTRY_v0.1.json) was widened with 3 new
    CANDIDATE predicates (curated_by, critical_text_by, resided_in) after
    confirming no existing predicate fit 3 real, frequent, clean-shaped
    raw predicates ('a cura di', 'testo critico di', 'moved to') --
    entries 7-9 map those. The real invariant this test protects is
    unchanged: every raw_predicate_text here is one that was actually
    verified against real data (even if the first proposed predicate_id
    was itself wrong and had to be corrected), never silently multiplying
    beyond what a human checked."""
    governance = json.loads(GOVERNANCE_PATH.read_text(encoding="utf-8"))
    mappings = governance["mappings"]
    assert len(mappings) == 9, f"expected exactly the 9 known-verified entries, got {len(mappings)}"
    by_text = {m["raw_predicate_text"]: m["predicate_id"] for m in mappings}
    assert by_text == {
        "was held at": "located_at",
        "was presented at": "located_at",
        "was a solo exhibition at": "located_at",
        "ha esposto": "participated_in",
        "partecipa": "participated_in",
        "presente in": "located_at",
        "a cura di": "curated_by",
        "testo critico di": "critical_text_by",
        "moved to": "resided_in",
    }