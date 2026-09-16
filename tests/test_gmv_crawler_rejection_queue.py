"""GMV Crawler — Task 7: rejection queue for BUILD ATOMS rejections.

Cross-checks the JSONL accumulation module
(10_API/gmv_crawler_rejection_queue.py) both with hand-built
`RejectedCandidate` values and -- end-to-end -- with REAL rejections
produced by `build_atoms()` (Task 6), proving the Task 6 -> Task 7 chain
works on real candidate data, not just on test fixtures.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

from gmv_crawler_atom_builder import RejectedCandidate, build_atoms  # noqa: E402
from gmv_crawler_candidate_extractor import CandidateProposition  # noqa: E402
from gmv_crawler_rejection_queue import (  # noqa: E402
    RejectionQueueSummaryEntry,
    append_rejected,
    summarize_rejection_queue,
)

QUEUE_FIELDS = {
    "source_id",
    "extraction_claim_ref",
    "raw_predicate",
    "reason_code",
    "detail",
    "queued_at",
}

T1 = "2026-09-16T00:01:00Z"
T2 = "2026-09-16T00:02:00Z"
T3 = "2026-09-16T00:03:00Z"
ATOM_NOW = "2026-09-16T00:00:00Z"


def rejected(
    reason_code: str = "UNKNOWN_PREDICATE",
    raw_predicate: str = "foo_bar_predicate",
    source_id: str = "SRC-EVID-42",
    extraction_claim_ref: str = "CLAIM-007",
) -> RejectedCandidate:
    return RejectedCandidate(
        source_id=source_id,
        extraction_claim_ref=extraction_claim_ref,
        raw_predicate=raw_predicate,
        reason_code=reason_code,
        detail=f"{reason_code} fixture detail",
    )


def make_proposition(**overrides) -> CandidateProposition:
    fields = {
        "subject_raw": "Federico Garibaldi",
        "predicate": "edition_size",
        "object_raw": "3",
        "evidence_excerpt": "evidenza",
        "status": "DOCUMENTATO",
        "source_id": "SRC-EVID-42",
        "evidence_id": ("EV-1",),
        "truncated_source": False,
        "extraction_claim_ref": "CLAIM-007",
    }
    fields.update(overrides)
    return CandidateProposition(**fields)


# --- append: creates file + parent dirs, exact lines, valid JSON ---

def test_append_rejected_creates_file_and_parent_dirs_with_exact_lines(tmp_path: Path) -> None:
    queue_path = tmp_path / "deep" / "nested" / "queue.jsonl"
    candidates = (
        rejected(),
        rejected(reason_code="OBJECT_NOT_INTEGER", raw_predicate="edition_size",
                 extraction_claim_ref="CLAIM-008"),
    )
    append_rejected(candidates, queue_path, now=T1)
    assert queue_path.exists()
    lines = queue_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line, candidate, now in zip(lines, candidates, (T1, T1), strict=True):
        record = json.loads(line)
        assert set(record) == QUEUE_FIELDS
        assert record["source_id"] == candidate.source_id
        assert record["extraction_claim_ref"] == candidate.extraction_claim_ref
        assert record["raw_predicate"] == candidate.raw_predicate
        assert record["reason_code"] == candidate.reason_code
        assert record["detail"] == candidate.detail
        assert record["queued_at"] == now


# --- two scans: second call appends, never overwrites ---

def test_two_append_calls_simulate_two_scans_and_accumulate(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.jsonl"
    append_rejected((rejected(extraction_claim_ref="SCAN1"),), queue_path, now=T1)
    append_rejected((rejected(extraction_claim_ref="SCAN2"),), queue_path, now=T2)
    records = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    assert [r["extraction_claim_ref"] for r in records] == ["SCAN1", "SCAN2"]
    assert [r["queued_at"] for r in records] == [T1, T2]  # appended after, not replaced


# --- absent file is an empty queue, not an error ---

def test_summarize_missing_path_returns_empty_tuple(tmp_path: Path) -> None:
    assert summarize_rejection_queue(tmp_path / "does-not-exist.jsonl") == ()


# --- grouping + first/last are true min/max, not first/last written ---

def test_repeated_rejections_group_and_min_max_ignores_write_order(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.jsonl"
    # deliberately written later with a SMALLER queued_at: first/last must
    # be a real min/max over queued_at, not "first/last row in the file".
    append_rejected((rejected(reason_code="OBJECT_NOT_INTEGER", raw_predicate="edition_size"),),
                    queue_path, now=T3)
    append_rejected((rejected(reason_code="OBJECT_NOT_INTEGER", raw_predicate="edition_size"),),
                    queue_path, now=T1)
    append_rejected((rejected(reason_code="OBJECT_NOT_INTEGER", raw_predicate="edition_size"),),
                    queue_path, now=T2)
    summary = summarize_rejection_queue(queue_path)
    assert summary == (
        RejectionQueueSummaryEntry(
            reason_code="OBJECT_NOT_INTEGER",
            raw_predicate="edition_size",
            count=3,
            first_queued_at=T1,
            last_queued_at=T3,
        ),
    )


# --- grouping key is the exact pair, not either field alone ---

def test_same_reason_different_predicate_and_vice_versa_stay_separate(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.jsonl"
    append_rejected(
        (
            rejected(reason_code="UNKNOWN_PREDICATE", raw_predicate="foo"),
            rejected(reason_code="UNKNOWN_PREDICATE", raw_predicate="bar"),
            rejected(reason_code="OBJECT_NOT_INTEGER", raw_predicate="foo"),
        ),
        queue_path,
        now=T1,
    )
    summary = summarize_rejection_queue(queue_path)
    assert len(summary) == 3  # (UNKNOWN, foo) (UNKNOWN, bar) (OBJECT_NOT_INTEGER, foo)
    assert {e.raw_predicate for e in summary} == {"foo", "bar"}
    assert {e.reason_code for e in summary} == {"UNKNOWN_PREDICATE", "OBJECT_NOT_INTEGER"}
    assert all(e.count == 1 for e in summary)


# --- ordering: count desc, then (reason_code, raw_predicate) asc, deterministic ---

def test_summary_sorts_by_count_desc_then_alpha_and_is_deterministic(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.jsonl"
    # appended deliberately NOT in sorted order, so any dependence on
    # insertion/dict order would surface as a different result
    append_rejected(
        (
            rejected(reason_code="PREDICATE_NOT_YET_SUPPORTED", raw_predicate="represented_by"),
            rejected(reason_code="UNKNOWN_PREDICATE", raw_predicate="partner_of"),
            rejected(reason_code="UNKNOWN_PREDICATE", raw_predicate="is the author of",
                     extraction_claim_ref="A"),
            rejected(reason_code="UNKNOWN_PREDICATE", raw_predicate="is the author of",
                     extraction_claim_ref="B"),
            rejected(reason_code="UNKNOWN_PREDICATE", raw_predicate="is the author of",
                     extraction_claim_ref="C"),
            rejected(reason_code="OBJECT_NOT_INTEGER", raw_predicate="edition_size"),
            rejected(reason_code="OBJECT_NOT_INTEGER", raw_predicate="edition_size"),
        ),
        queue_path,
        now=T1,
    )
    expected = (
        RejectionQueueSummaryEntry("UNKNOWN_PREDICATE", "is the author of", 3, T1, T1),
        RejectionQueueSummaryEntry("OBJECT_NOT_INTEGER", "edition_size", 2, T1, T1),
        RejectionQueueSummaryEntry("PREDICATE_NOT_YET_SUPPORTED", "represented_by", 1, T1, T1),
        RejectionQueueSummaryEntry("UNKNOWN_PREDICATE", "partner_of", 1, T1, T1),
    )  # count desc; both count-1 groups ordered "PREDICATE..." < "UNKNOWN..."
    assert summarize_rejection_queue(queue_path) == tuple(expected)
    # deterministic across calls: same input, identical order both times
    assert summarize_rejection_queue(queue_path) == summarize_rejection_queue(queue_path)


# --- end-to-end: real build_atoms() rejections through append + summarize ---

def test_end_to_end_real_rejections_from_build_atoms_accumulate(tmp_path: Path) -> None:
    queue_path = tmp_path / "rejected" / "queue.jsonl"
    _, scan1_rejected = build_atoms(
        (
            make_proposition(predicate="foo_bar_predicate"),      # UNKNOWN_PREDICATE
            make_proposition(predicate="evidences"),              # alias -> PREDICATE_NOT_YET_SUPPORTED
            make_proposition(predicate="edition_size", object_raw="tre"),  # OBJECT_NOT_INTEGER
        ),
        now=ATOM_NOW,
    )
    append_rejected(scan1_rejected, queue_path, now=T1)
    _, scan2_rejected = build_atoms(
        (make_proposition(predicate="foo_bar_predicate", extraction_claim_ref="CLAIM-OTH"),),
        now=ATOM_NOW,
    )
    # second scan: the same unknown predicate rejected again, plus a real
    # RELATION predicate rejection this time
    _, scan2b_rejected = build_atoms(
        (make_proposition(predicate="represented_by"),),
        now=ATOM_NOW,
    )
    append_rejected((*scan2_rejected, *scan2b_rejected), queue_path, now=T2)

    summary = summarize_rejection_queue(queue_path)
    assert len(summary) == 4
    assert summary[0] == RejectionQueueSummaryEntry(
        reason_code="UNKNOWN_PREDICATE", raw_predicate="foo_bar_predicate", count=2,
        first_queued_at=T1, last_queued_at=T2,  # accumulated across two scans
    )
    assert {e.raw_predicate for e in summary} == {
        "foo_bar_predicate", "evidences", "edition_size", "represented_by",
    }
    assert all(e.count == 1 for e in summary[1:])