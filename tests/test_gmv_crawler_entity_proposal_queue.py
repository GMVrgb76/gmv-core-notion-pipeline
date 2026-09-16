"""GMV Crawler — Task 9: review queue for MODEL_INFERENCE entity type proposals.

Pins the Task 8 -> Task 9 chain on the REAL output of
`classify_entity_types()` (network mocked exactly like
tests/test_gmv_crawler_entity_resolver.py, urllib.request.urlopen
patched, FakeUrlResponse helper): only |needs_verification| proposals
reach the queue; the already-verified roster facts are filtered BEFORE
any filesystem side effect; the file is created iff something was
actually written (mirroring the authorization log, the same
documented choice the module's docstring makes); repeated calls
accumulate instead of overwrite; and the summary groups by the exact
(entity_name, entity_type) pair, with confidence_counts ordered by
count then the HIGH/MEDIUM/LOW importance RANK -- never alphabetical
(a LOW=2/MEDIUM=2/HIGH=1 case is pinned so alphabetical secondary
ordering would fail).
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

from gmv_crawler_candidate_extractor import CandidateEntity  # noqa: E402
from gmv_crawler_entity_proposal_queue import (  # noqa: E402
    EntityProposalQueueSummaryEntry,
    append_entity_proposals,
    summarize_entity_proposal_queue,
)
from gmv_crawler_entity_resolver import (  # noqa: E402
    EntityTypeProposal,
    classify_entity_types,
)

NOW_1 = "2026-09-17T09:00:00Z"
NOW_2 = "2026-09-17T10:30:00Z"
NOW_3 = "2026-09-17T11:59:00Z"

KNOWN_NAME = "Federico Garibaldi"  # literal row in 00_CONFIG/area35_known_artists.json
UNKNOWN_NAME = "Ugo Dossi"  # invented: guaranteed not in the 46-name roster


class FakeUrlResponse:
    """Minimal urllib response: context-managed, JSON-serializable read()."""

    def __init__(self, envelope: dict):
        self._envelope = envelope

    def __enter__(self) -> FakeUrlResponse:
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def read(self) -> bytes:
        return json.dumps(self._envelope).encode()


def classification_envelope(items: list[dict]) -> dict:
    return {
        "model": "gemma4:12b",
        "response": json.dumps({"classifications": items}),
        "done_reason": "stop",
    }


def make_urlopen(envelope: dict | None = None) -> object:
    def _fake(request, timeout=None):
        return FakeUrlResponse(envelope or classification_envelope([]))

    return _fake


def make_entity(name: str) -> CandidateEntity:
    return CandidateEntity(
        name=name,
        evidence_excerpt="a real biography mentions this entity",
        status="DOCUMENTATO",
        source_id="SRC-EVID-42",
        evidence_id=("EV-1",),
    )


def make_proposal(
    entity_name: str,
    entity_type: str,
    confidence: str,
    *,
    needs_verification: bool = True,
) -> EntityTypeProposal:
    return EntityTypeProposal(
        entity_name=entity_name,
        entity_type=entity_type,
        confidence=confidence,
        source="MODEL_INFERENCE" if needs_verification else "MATCHED_KNOWN_ARTIST_ROSTER",
        needs_verification=needs_verification,
    )


# --- append: filters FIRST, returns the written count, file semantics ---

def test_mixed_list_filters_unverified_only_and_returns_written_count(
    tmp_path: Path,
) -> None:
    path = tmp_path / "queue.jsonl"
    proposals = (
        make_proposal(UNKNOWN_NAME, "ARTIST", "HIGH"),
        make_proposal("Altro Nome", "PERSON", "MEDIUM"),
        make_proposal(KNOWN_NAME, "ARTIST", "HIGH", needs_verification=False),
    )
    assert append_entity_proposals(proposals, path, now=NOW_1) == 2
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert [row["entity_name"] for row in rows] == [UNKNOWN_NAME, "Altro Nome"]
    for row in rows:
        assert set(row) == {"entity_name", "entity_type", "confidence", "source", "queued_at"}
        assert row["source"] == "MODEL_INFERENCE"
        assert row["queued_at"] == NOW_1


def test_all_verified_nothing_written_file_not_created(tmp_path: Path) -> None:
    path = tmp_path / "does" / "not" / "exist.jsonl"
    roster = make_proposal(KNOWN_NAME, "ARTIST", "HIGH", needs_verification=False)
    assert append_entity_proposals([roster], path, now=NOW_1) == 0
    assert not path.exists()
    assert not path.parent.exists()  # documented: "queue exists iff something was enqueued"


def test_all_verified_leaves_existing_file_completely_untouched(tmp_path: Path) -> None:
    path = tmp_path / "queue.jsonl"
    assert append_entity_proposals([make_proposal(UNKNOWN_NAME, "ARTIST", "HIGH")], path, now=NOW_1) == 1
    before = path.read_text(encoding="utf-8")
    roster = make_proposal(KNOWN_NAME, "ARTIST", "HIGH", needs_verification=False)
    assert append_entity_proposals([roster], path, now=NOW_2) == 0
    assert path.read_text(encoding="utf-8") == before


def test_empty_sequence_is_noop(tmp_path: Path) -> None:
    path = tmp_path / "queue.jsonl"
    assert append_entity_proposals([], path, now=NOW_1) == 0
    assert not path.exists()


def test_two_calls_accumulate_not_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "queue.jsonl"
    assert append_entity_proposals([make_proposal(UNKNOWN_NAME, "ARTIST", "HIGH")], path, now=NOW_1) == 1
    assert append_entity_proposals(
        [make_proposal("Seconda Entita", "PLACE", "LOW")], path, now=NOW_2
    ) == 1
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert [row["queued_at"] for row in rows] == [NOW_1, NOW_2]


# --- summarize: structure, ordering, determinism ---

def test_summarize_absent_path_returns_empty_tuple(tmp_path: Path) -> None:
    assert summarize_entity_proposal_queue(tmp_path / "does-not-exist.jsonl") == ()


def test_summarize_same_pair_confidences_counts_ordered_by_rank_not_alphabet(
    tmp_path: Path,
) -> None:
    path = tmp_path / "queue.jsonl"
    # HIGH once, MEDIUM twice, LOW twice; queued_at deliberately out of
    # chronological write order so first/last must come from min/max, not
    # from the order the rows were written in.
    assert append_entity_proposals([make_proposal(UNKNOWN_NAME, "ARTIST", "HIGH")], path, now=NOW_3) == 1
    assert append_entity_proposals(
        [
            make_proposal(UNKNOWN_NAME, "ARTIST", "MEDIUM"),
            make_proposal(UNKNOWN_NAME, "ARTIST", "LOW"),
            make_proposal(UNKNOWN_NAME, "ARTIST", "LOW"),
            make_proposal(UNKNOWN_NAME, "ARTIST", "MEDIUM"),
        ],
        path,
        now=NOW_1,
    ) == 4
    (summary,) = summarize_entity_proposal_queue(path)
    assert summary == EntityProposalQueueSummaryEntry(
        entity_name=UNKNOWN_NAME,
        entity_type="ARTIST",
        # MEDIUM and LOW both occur twice: correct order must put MEDIUM
        # before LOW by importance rank; alphabetical secondary ordering
        # would put LOW first and this test would fail.
        confidence_counts=(("MEDIUM", 2), ("LOW", 2), ("HIGH", 1)),
        count=5,
        first_queued_at=NOW_1,
        last_queued_at=NOW_3,
    )


def test_summarize_same_name_different_types_stay_separate_groups(
    tmp_path: Path,
) -> None:
    path = tmp_path / "queue.jsonl"
    assert append_entity_proposals(
        [make_proposal("Le Stanze della Fotografia", "EXHIBITION", "HIGH")],
        path,
        now=NOW_1,
    ) == 1
    assert append_entity_proposals(
        [make_proposal("Le Stanze della Fotografia", "INSTITUTION", "LOW")],
        path,
        now=NOW_2,
    ) == 1
    entries = summarize_entity_proposal_queue(path)
    assert len(entries) == 2
    assert {entry.entity_type for entry in entries} == {"EXHIBITION", "INSTITUTION"}
    assert all(entry.count == 1 for entry in entries)


def test_summary_sorted_by_count_desc_then_name_then_type_deterministic(
    tmp_path: Path,
) -> None:
    path = tmp_path / "queue.jsonl"
    asserts_and_calls = [
        ([make_proposal("Aaa", "Zzz-type", "HIGH")], NOW_1),
        ([make_proposal("Bbb", "Aaa-type", "LOW"), make_proposal("Bbb", "Bbb-type", "MEDIUM")], NOW_1),
        ([make_proposal("Aaa", "Zzz-type", "MEDIUM"), make_proposal("Aaa", "Zzz-type", "LOW")], NOW_2),
        ([make_proposal("Bbb", "Aaa-type", "HIGH"), make_proposal("Bbb", "Bbb-type", "LOW")], NOW_2),
        ([make_proposal("Ccc", "WORK", "HIGH")], NOW_3),
    ]
    for proposals, now in asserts_and_calls:
        append_entity_proposals(proposals, path, now=now)
    first = summarize_entity_proposal_queue(path)
    second = summarize_entity_proposal_queue(path)
    assert first == second  # deterministic across repeated calls
    assert [entry.count for entry in first] == [3, 2, 2, 1]
    assert first[1].entity_name == "Bbb" and first[1].entity_type == "Aaa-type"
    assert first[2].entity_name == "Bbb" and first[2].entity_type == "Bbb-type"


# --- end-to-end: Task 8 real output -> Task 9 queue ---

def test_e2e_classify_then_enqueue_only_model_inference_proposals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        make_urlopen(
            classification_envelope(
                [{"name": UNKNOWN_NAME, "entity_type": "ARTIST", "confidence": "HIGH"}]
            )
        ),
    )
    proposals = classify_entity_types((make_entity(KNOWN_NAME), make_entity(UNKNOWN_NAME)))
    assert proposals == (
        EntityTypeProposal(
            entity_name=KNOWN_NAME, entity_type="ARTIST",
            confidence="HIGH", source="MATCHED_KNOWN_ARTIST_ROSTER",
            needs_verification=False,
        ),
        EntityTypeProposal(
            entity_name=UNKNOWN_NAME, entity_type="ARTIST",
            confidence="HIGH", source="MODEL_INFERENCE",
            needs_verification=True,
        ),
    )
    queue_path = tmp_path / "queue.jsonl"
    written = append_entity_proposals(proposals, queue_path, now=NOW_1)
    assert written == 1
    rows = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["entity_name"] == UNKNOWN_NAME
    assert rows[0]["source"] == "MODEL_INFERENCE"
    (summary,) = summarize_entity_proposal_queue(queue_path)
    assert summary.entity_name == UNKNOWN_NAME
    assert summary.entity_type == "ARTIST"
    assert summary.count == 1