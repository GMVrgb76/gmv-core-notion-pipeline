"""Contract-terms extraction (new schema, 2026-09-21).

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

import gmv_crawler_contract_extractor as contract_extractor  # noqa: E402
from gmv_crawler_contract_extractor import CandidateContractSummary, extract_contract_summary  # noqa: E402


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *a, **k):
        return self._data


REAL_CONTRACT_FIELDS = {
    "contract_type": "conto-vendita", "artist_name": "Giovanni Pasini",
    "gallery_name": "Area35 Art Factory", "start_date": "2018-06-14", "end_date": "2019-06-14",
    "commission_percentage": "50%", "payment_terms": "entro 60 giorni dalla chiusura della vendita",
    "key_obligations": ["La Galleria deve vendere le opere al prezzo stabilito con l'Artista"],
    "evidence_excerpt": "Termini contratto: dal 14 giugno 2018 al 14 giugno 2019",
}


def test_extract_contract_summary_hits_chat_endpoint_with_template_role(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        return _FakeHTTPResponse({"message": {"content": json.dumps(REAL_CONTRACT_FIELDS)}, "done_reason": "stop"})

    monkeypatch.setattr(contract_extractor.urllib.request, "urlopen", fake_urlopen)
    result = extract_contract_summary("contract text", source_id="sha256:" + "a" * 64, evidence_ids=("ev-1",))
    assert captured["url"].endswith("/api/chat")
    roles = {m["role"] for m in captured["body"]["messages"]}
    assert roles == {"template", "instructions", "user"}
    template_message = next(m for m in captured["body"]["messages"] if m["role"] == "template")
    assert json.loads(template_message["content"]) == contract_extractor.CONTRACT_TEMPLATE
    assert result == CandidateContractSummary(
        evidence_excerpt="Termini contratto: dal 14 giugno 2018 al 14 giugno 2019",
        source_id="sha256:" + "a" * 64, evidence_id=("ev-1",), extraction_claim_ref="sha256:" + "a" * 64 + "#0",
        contract_type="conto-vendita", artist_name="Giovanni Pasini", gallery_name="Area35 Art Factory",
        start_date="2018-06-14", end_date="2019-06-14", commission_percentage="50%",
        payment_terms="entro 60 giorni dalla chiusura della vendita",
        key_obligations=("La Galleria deve vendere le opere al prezzo stabilito con l'Artista",),
    )


def test_extract_contract_summary_never_chunks_even_when_long(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unlike price lists/claims, a contract is one coherent agreement --
    this must always be exactly one call, regardless of document length."""
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(json.loads(request.data))
        return _FakeHTTPResponse({"message": {"content": json.dumps({"evidence_excerpt": "e"})}, "done_reason": "stop"})

    monkeypatch.setattr(contract_extractor.urllib.request, "urlopen", fake_urlopen)
    long_text = "Clausola contrattuale. " * 5000
    extract_contract_summary(long_text, source_id="sha256:" + "a" * 64, evidence_ids=("ev-1",), max_prompt_chars=500)
    assert len(calls) == 1
    user_message = next(m for m in calls[0]["messages"] if m["role"] == "user")
    assert len(user_message["content"]) == 500


def test_extract_contract_summary_missing_evidence_excerpt_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout):
        return _FakeHTTPResponse({"message": {"content": json.dumps({"contract_type": "sales"})}, "done_reason": "stop"})

    monkeypatch.setattr(contract_extractor.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ValueError, match="evidence_excerpt must not be empty"):
        extract_contract_summary("text", source_id="sha256:" + "a" * 64, evidence_ids=("ev-1",))


def test_extract_contract_summary_raises_on_truncated_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout):
        return _FakeHTTPResponse({"message": {"content": json.dumps(REAL_CONTRACT_FIELDS)}, "done_reason": "length"})

    monkeypatch.setattr(contract_extractor.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(contract_extractor.OllamaResponseError, match="OLLAMA_OUTPUT_TRUNCATED"):
        extract_contract_summary("text", source_id="sha256:" + "a" * 64, evidence_ids=("ev-1",))


def test_candidate_contract_summary_requires_evidence_id() -> None:
    with pytest.raises(ValueError, match="evidence_id must not be empty"):
        CandidateContractSummary(
            evidence_excerpt="e", source_id="sha256:" + "a" * 64, evidence_id=(),
            extraction_claim_ref="ref#0",
        )
