"""Crawler preplan step 11: Candidate extraction (spec v0.2 §10).

No real Ollama/network calls: `ollama_extract` is monkeypatched at the
module level (same technique `tests/test_gmv_evidence_pipeline.py` already
uses on the real function).

Two rounds of adversarial review found and fixed the same underlying
pattern at two different trigger points:

1. `status` validated against a closed vocabulary (`STATUS_PRECEDENCE`)
   -- reproduced crashing the whole batch on a realistic out-of-vocabulary
   LLM status value. Fixed by not validating status against any closed
   set (see `test_extract_candidates_mixed_batch_survives_one_unusual_status_value`).
2. Even after (1), a narrower trigger survived: an explicitly empty-string
   `status` (legal per `SEMANTIC_OUTPUT_SCHEMA`, no `minLength`/`required`)
   still crashed the whole batch via the same all-or-nothing tuple
   comprehension. Fixed by isolating per-item construction failures --
   `extract_candidates()` now returns a third `rejected` tuple instead of
   raising (see `test_extract_candidates_rejects_only_the_malformed_item_not_the_whole_batch`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

import gmv_crawler_candidate_extractor as candidate_extractor  # noqa: E402
from gmv_crawler_candidate_extractor import (  # noqa: E402
    CandidateEntity,
    CandidateProposition,
    extract_candidates,
)
from gmv_crawler_extractor import ExtractionDocument  # noqa: E402


def make_document(**overrides) -> ExtractionDocument:
    fields = {
        "source_id": "sha256:" + "a" * 64,
        "source_hash": "sha256:" + "a" * 64,
        "status": "SUCCESS",
        "extractor": "pdf",
        "text": "Federico Garibaldi nacque a Nizza nel 1807.",
    }
    fields.update(overrides)
    return ExtractionDocument(**fields)


def make_claim(**overrides) -> dict:
    claim = {
        "subject_raw": "Federico Garibaldi", "predicate": "nato a", "object_raw": "Nizza",
        "evidence_excerpt": "nacque a Nizza nel 1807", "status": "SUPPORTED_BY_ARCHIVE",
        "truncated_source": False, "extraction_claim_ref": "sha256:" + "a" * 64 + "#0",
    }
    claim.update(overrides)
    return claim


def fake_ollama_result(entities=None, claims=None):
    def _fake(record, **kwargs):
        return {
            "file_id": record["file_id"],
            "entities": entities if entities is not None else [
                {"name": "Federico Garibaldi", "evidence_excerpt": "Federico Garibaldi nacque", "status": "SUPPORTED_BY_ARCHIVE"}
            ],
            "claims": claims if claims is not None else [make_claim()],
        }
    return _fake


# --- CandidateEntity / CandidateProposition dataclass invariants ---

def test_candidate_entity_requires_evidence_id() -> None:
    with pytest.raises(ValueError, match="evidence_id must not be empty"):
        CandidateEntity(
            name="X", evidence_excerpt="x", status="SUPPORTED_BY_ARCHIVE",
            source_id="sha256:" + "a" * 64, evidence_id=(),
        )


def test_candidate_entity_rejects_empty_status() -> None:
    with pytest.raises(ValueError, match="status must not be empty"):
        CandidateEntity(
            name="X", evidence_excerpt="x", status="",
            source_id="sha256:" + "a" * 64, evidence_id=("ev-1",),
        )


def test_candidate_entity_accepts_free_text_status_not_in_any_closed_vocabulary() -> None:
    """The core regression this dataclass must allow: an LLM can legitimately
    emit a status string that is not one of gmv_evidence_pipeline.STATUS_PRECEDENCE's
    10 literals (that list is a ranking aid for a later stage, not an enum)."""
    CandidateEntity(
        name="X", evidence_excerpt="x", status="DOCUMENTATO",
        source_id="sha256:" + "a" * 64, evidence_id=("ev-1",),
    )


def test_candidate_proposition_requires_evidence_id() -> None:
    with pytest.raises(ValueError, match="evidence_id must not be empty"):
        CandidateProposition(**{**make_claim(), "source_id": "sha256:" + "a" * 64, "evidence_id": ()})


def test_candidate_proposition_accepts_free_text_status() -> None:
    CandidateProposition(**{
        **make_claim(status="ATTESTATO"), "source_id": "sha256:" + "a" * 64, "evidence_id": ("ev-1",),
    })


@pytest.mark.parametrize(
    "field", ["subject_raw", "predicate", "object_raw", "evidence_excerpt", "source_id", "status", "extraction_claim_ref"]
)
def test_candidate_proposition_rejects_empty_required_fields(field: str) -> None:
    kwargs = {**make_claim(), "source_id": "sha256:" + "a" * 64, "evidence_id": ("ev-1",)}
    kwargs[field] = ""
    with pytest.raises(ValueError, match=f"{field} must not be empty"):
        CandidateProposition(**kwargs)


# --- extract_candidates() ---

def test_extract_candidates_maps_real_ollama_extract_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate_extractor, "ollama_extract", fake_ollama_result())
    document = make_document()
    entities, propositions, rejected = extract_candidates(document, evidence_ids=("ev-1", "ev-2"))
    assert entities == (
        CandidateEntity(
            name="Federico Garibaldi", evidence_excerpt="Federico Garibaldi nacque",
            status="SUPPORTED_BY_ARCHIVE", source_id=document.source_id, evidence_id=("ev-1", "ev-2"),
        ),
    )
    assert propositions == (
        CandidateProposition(
            subject_raw="Federico Garibaldi", predicate="nato a", object_raw="Nizza",
            evidence_excerpt="nacque a Nizza nel 1807", status="SUPPORTED_BY_ARCHIVE",
            source_id=document.source_id, evidence_id=("ev-1", "ev-2"),
            truncated_source=False, extraction_claim_ref="sha256:" + "a" * 64 + "#0",
        ),
    )
    assert rejected == ()


def test_extract_candidates_propagates_truncated_source_and_claim_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        candidate_extractor, "ollama_extract",
        fake_ollama_result(claims=[make_claim(truncated_source=True, extraction_claim_ref="sha256:" + "b" * 64 + "#3")]),
    )
    _, propositions, _ = extract_candidates(make_document(), evidence_ids=("ev-1",))
    assert propositions[0].truncated_source is True
    assert propositions[0].extraction_claim_ref == "sha256:" + "b" * 64 + "#3"


def test_extract_candidates_mixed_batch_survives_one_unusual_status_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test for the first review-reported blocker: one
    out-of-vocabulary status value in a batch must not destroy every
    other valid candidate from the same document."""
    monkeypatch.setattr(
        candidate_extractor, "ollama_extract",
        fake_ollama_result(
            entities=[
                {"name": "Entity A", "evidence_excerpt": "excerpt A", "status": "SUPPORTED_BY_ARCHIVE"},
                {"name": "Entity B", "evidence_excerpt": "excerpt B", "status": "DOCUMENTATO"},
            ],
            claims=[make_claim()],
        ),
    )
    entities, propositions, rejected = extract_candidates(make_document(), evidence_ids=("ev-1",))
    assert [e.name for e in entities] == ["Entity A", "Entity B"]
    assert entities[1].status == "DOCUMENTATO"
    assert len(propositions) == 1
    assert rejected == ()


def test_extract_candidates_rejects_only_the_malformed_item_not_the_whole_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test for the residual gap the re-review found: an
    explicitly empty-string status (legal per SEMANTIC_OUTPUT_SCHEMA,
    which has no minLength and does not require `status`) must reject
    only that one candidate, not the entire document's batch."""
    monkeypatch.setattr(
        candidate_extractor, "ollama_extract",
        fake_ollama_result(
            entities=[
                {"name": "Good Entity", "evidence_excerpt": "excerpt", "status": "SUPPORTED_BY_ARCHIVE"},
                {"name": "Bad Entity", "evidence_excerpt": "excerpt", "status": ""},
            ],
            claims=[make_claim(), make_claim(status="", extraction_claim_ref="sha256:" + "c" * 64 + "#1")],
        ),
    )
    entities, propositions, rejected = extract_candidates(make_document(), evidence_ids=("ev-1",))
    assert [e.name for e in entities] == ["Good Entity"]
    assert len(propositions) == 1
    assert len(rejected) == 2
    assert any("Bad Entity" in reason for reason in rejected)
    assert any("#1" in reason for reason in rejected)


def test_extract_candidates_empty_lists_produce_empty_tuples(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate_extractor, "ollama_extract", fake_ollama_result(entities=[], claims=[]))
    document = make_document()
    entities, propositions, rejected = extract_candidates(document, evidence_ids=("ev-1",))
    assert entities == ()
    assert propositions == ()
    assert rejected == ()


def test_extract_candidates_rejects_empty_evidence_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(candidate_extractor, "ollama_extract", fake_ollama_result())
    with pytest.raises(ValueError, match="evidence_id must not be empty"):
        extract_candidates(make_document(), evidence_ids=())


def test_extract_candidates_rejects_document_not_successfully_extracted(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("ollama_extract must not be called for a non-SUCCESS document")
    monkeypatch.setattr(candidate_extractor, "ollama_extract", fail_if_called)
    document = make_document(status="EXTRACTION_FAILED", extractor="", text="", error_detail="OSError")
    with pytest.raises(ValueError, match="EXTRACTION_FAILED"):
        extract_candidates(document, evidence_ids=("ev-1",))


def test_extract_candidates_passes_document_text_and_source_id_to_ollama_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def spy(record, **kwargs):
        captured.update(record)
        captured.update(kwargs)
        return {"file_id": record["file_id"], "entities": [], "claims": []}

    monkeypatch.setattr(candidate_extractor, "ollama_extract", spy)
    document = make_document(text="testo specifico di prova")
    extract_candidates(document, evidence_ids=("ev-1",), endpoint="http://example:1234", model="qwen3:8b")
    assert captured["file_id"] == document.source_id
    assert captured["text"] == "testo specifico di prova"
    assert captured["extraction_status"] == "SUCCESS"
    assert captured["endpoint"] == "http://example:1234"
    assert captured["model"] == "qwen3:8b"


def test_extract_candidates_default_model_and_endpoint_match_repo_precedent(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def spy(record, **kwargs):
        captured.update(kwargs)
        return {"file_id": record["file_id"], "entities": [], "claims": []}

    monkeypatch.setattr(candidate_extractor, "ollama_extract", spy)
    extract_candidates(make_document(), evidence_ids=("ev-1",))
    # gemma4:12b -> qwen2.5-coder:7b -> deepseek-coder-v2:16b (all
    # 2026-09-19) -> numind/nuextract3:q4_k_m (2026-09-20). deepseek-coder-v2
    # was the only one of the first three with zero failures across every
    # real document tested THAT session -- but the real nightly batch run of
    # 2026-09-20T01:00:05Z (01_RUNTIME/gmv_crawler/run_log.jsonl) shows it
    # failed on 100% of documents (OLLAMA_SCHEMA_INVALID/
    # OLLAMA_OUTPUT_TRUNCATED), so it was never actually the safe default its
    # own history suggested. nuextract3:q4_k_m + api_style="chat_template"
    # beat gemma4:12b on speed and hallucination rate in a 4-document A/B
    # (see DEFAULT_MODEL's own comment) -- not yet validated at this
    # crawler's own batch scale the way the first three swaps were.
    assert captured["model"] == "numind/nuextract3:q4_k_m"
    assert captured["endpoint"] == "http://localhost:11434"
    assert captured["api_style"] == "chat_template"


def test_extract_candidates_api_style_override_reaches_ollama_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    """A caller that explicitly wants the old /api/generate shape (e.g. to
    use a non-NuExtract model) must be able to override the new default."""
    captured = {}

    def spy(record, **kwargs):
        captured.update(kwargs)
        return {"file_id": record["file_id"], "entities": [], "claims": []}

    monkeypatch.setattr(candidate_extractor, "ollama_extract", spy)
    extract_candidates(make_document(), evidence_ids=("ev-1",), api_style="generate")
    assert captured["api_style"] == "generate"
