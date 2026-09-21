"""Price-list extraction (new schema, 2026-09-21).

No real Ollama/network calls: `urllib.request.urlopen` is monkeypatched at
the module level, same technique the sibling extractor tests already use.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))

import gmv_crawler_price_extractor as price_extractor  # noqa: E402
from gmv_crawler_price_extractor import CandidateArtworkPrice, extract_price_entries  # noqa: E402


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *a, **k):
        return self._data


def _fake_artworks(artworks, done_reason="stop"):
    def _fake(request, timeout):
        return _FakeHTTPResponse({"message": {"content": json.dumps({"artworks": artworks})}, "done_reason": done_reason})
    return _fake


REAL_ROW = {
    "artist_name": "Giovanni Pasini", "title": "Don Quijote", "year": 2018,
    "medium": "olio e sabbia su tela", "dimensions": "h. 200 x 180 x 5 cm",
    "price": 7500, "currency": "€", "evidence_excerpt": "Prezzo: € 7.500 tasse incluse",
}


def test_extract_price_entries_hits_chat_endpoint_with_template_role(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        return _FakeHTTPResponse({"message": {"content": json.dumps({"artworks": [REAL_ROW]})}, "done_reason": "stop"})

    monkeypatch.setattr(price_extractor.urllib.request, "urlopen", fake_urlopen)
    entries, rejected = extract_price_entries("some price list text", source_id="sha256:" + "a" * 64, evidence_ids=("ev-1",))
    assert captured["url"].endswith("/api/chat")
    roles = {m["role"] for m in captured["body"]["messages"]}
    assert roles == {"template", "instructions", "user"}
    template_message = next(m for m in captured["body"]["messages"] if m["role"] == "template")
    assert json.loads(template_message["content"]) == price_extractor.PRICE_LIST_TEMPLATE
    assert rejected == ()
    assert entries == (
        CandidateArtworkPrice(
            title="Don Quijote", price=7500, evidence_excerpt="Prezzo: € 7.500 tasse incluse",
            source_id="sha256:" + "a" * 64, evidence_id=("ev-1",), extraction_claim_ref="sha256:" + "a" * 64 + "#0",
            artist_name="Giovanni Pasini", year=2018, medium="olio e sabbia su tela",
            dimensions="h. 200 x 180 x 5 cm", currency="€",
        ),
    )


def test_extract_price_entries_rejects_only_the_malformed_row(monkeypatch: pytest.MonkeyPatch) -> None:
    bad_row = {"title": "Untitled", "evidence_excerpt": "e"}  # missing required 'price'
    monkeypatch.setattr(price_extractor.urllib.request, "urlopen", _fake_artworks([REAL_ROW, bad_row]))
    entries, rejected = extract_price_entries("text", source_id="sha256:" + "a" * 64, evidence_ids=("ev-1",))
    assert len(entries) == 1
    assert len(rejected) == 1
    assert "Untitled" in rejected[0]


def test_extract_price_entries_chunks_long_document(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(json.loads(request.data))
        i = len(calls) - 1
        row = dict(REAL_ROW, title=f"Work{i}")
        return _FakeHTTPResponse({"message": {"content": json.dumps({"artworks": [row]})}, "done_reason": "stop"})

    monkeypatch.setattr(price_extractor.urllib.request, "urlopen", fake_urlopen)
    long_text = "Prezzo opera. " * 500  # well over a small max_chunk_chars
    entries, rejected = extract_price_entries(
        long_text, source_id="sha256:" + "a" * 64, evidence_ids=("ev-1",), max_chunk_chars=100,
    )
    assert len(calls) >= 2
    assert len(entries) == len(calls)
    refs = [e.extraction_claim_ref for e in entries]
    assert len(set(refs)) == len(refs)


def test_extract_price_entries_retries_truncated_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(True)
        if len(calls) == 1:
            raise price_extractor.OllamaResponseError("OLLAMA_OUTPUT_TRUNCATED", runtime={}, raw_output="{incomplete")
        return _FakeHTTPResponse({"message": {"content": json.dumps({"artworks": [REAL_ROW]})}, "done_reason": "stop"})

    monkeypatch.setattr(price_extractor.urllib.request, "urlopen", fake_urlopen)
    entries, _ = extract_price_entries(
        "Federico Garibaldi price text here, reasonably long for splitting.",
        source_id="sha256:" + "a" * 64, evidence_ids=("ev-1",),
        max_chunk_chars=1000, min_adaptive_chunk_chars=5,
    )
    assert len(calls) == 3  # 1 failed whole-chunk call + 2 successful half-chunk calls
    assert len(entries) == 2


def test_extract_price_entries_adaptive_split_exhausted_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def always_truncated(request, timeout):
        raise price_extractor.OllamaResponseError("OLLAMA_OUTPUT_TRUNCATED", runtime={}, raw_output="{incomplete")

    monkeypatch.setattr(price_extractor.urllib.request, "urlopen", always_truncated)
    with pytest.raises(price_extractor.EvidenceError, match="ADAPTIVE_CHUNK_MINIMUM_EXHAUSTED"):
        extract_price_entries("short text", source_id="sha256:" + "a" * 64, evidence_ids=("ev-1",), min_adaptive_chunk_chars=1000)


def test_candidate_artwork_price_requires_evidence_id() -> None:
    with pytest.raises(ValueError, match="evidence_id must not be empty"):
        CandidateArtworkPrice(
            title="X", price=100, evidence_excerpt="e", source_id="sha256:" + "a" * 64,
            evidence_id=(), extraction_claim_ref="ref#0",
        )


def test_candidate_artwork_price_requires_title() -> None:
    with pytest.raises(ValueError, match="title must not be empty"):
        CandidateArtworkPrice(
            title="", price=100, evidence_excerpt="e", source_id="sha256:" + "a" * 64,
            evidence_id=("ev-1",), extraction_claim_ref="ref#0",
        )
