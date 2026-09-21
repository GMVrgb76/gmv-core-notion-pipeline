"""Document type classification (new pipeline stage, 2026-09-21).

No real Ollama/network calls: `urllib.request.urlopen` is monkeypatched at
the module level, same technique `tests/test_gmv_evidence_pipeline.py`
already uses on the real function.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))

import gmv_crawler_document_classifier as classifier  # noqa: E402
from gmv_crawler_document_classifier import classify_document  # noqa: E402


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *a, **k):
        return self._data


def _fake_chat(document_type="contract", confidence="high", done_reason="stop"):
    def _fake(request, timeout):
        return _FakeHTTPResponse({
            "message": {"content": json.dumps({"document_type": document_type, "confidence": confidence})},
            "done_reason": done_reason,
        })
    return _fake


def test_classify_document_hits_chat_endpoint_with_template_role(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        return _FakeHTTPResponse({"message": {"content": json.dumps({"document_type": "contract", "confidence": "high"})}, "done_reason": "stop"})

    monkeypatch.setattr(classifier.urllib.request, "urlopen", fake_urlopen)
    result = classify_document("Questo accordo è stipulato tra...", endpoint="http://localhost:11434", model="numind/nuextract3:q4_k_m")
    assert captured["url"].endswith("/api/chat")
    roles = {m["role"] for m in captured["body"]["messages"]}
    assert roles == {"template", "instructions", "user"}
    template_message = next(m for m in captured["body"]["messages"] if m["role"] == "template")
    assert json.loads(template_message["content"]) == classifier.CLASSIFICATION_TEMPLATE
    assert result == {"document_type": "contract", "confidence": "high"}


def test_classify_document_truncates_text_to_max_chars(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        return _FakeHTTPResponse({"message": {"content": json.dumps({"document_type": "biography"})}, "done_reason": "stop"})

    monkeypatch.setattr(classifier.urllib.request, "urlopen", fake_urlopen)
    long_text = "x" * 10000
    classify_document(long_text, endpoint="http://localhost:11434", model="m", max_chars=100)
    user_message = next(m for m in captured["body"]["messages"] if m["role"] == "user")
    assert len(user_message["content"]) == 100


@pytest.mark.parametrize("document_type", classifier.DOCUMENT_TYPES)
def test_classify_document_accepts_every_known_type(monkeypatch: pytest.MonkeyPatch, document_type: str) -> None:
    monkeypatch.setattr(classifier.urllib.request, "urlopen", _fake_chat(document_type=document_type))
    result = classify_document("text", endpoint="http://localhost:11434", model="m")
    assert result["document_type"] == document_type


def test_classify_document_rejects_unknown_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(classifier.urllib.request, "urlopen", _fake_chat(document_type="not_a_real_type"))
    with pytest.raises(classifier.OllamaResponseError, match="OLLAMA_SCHEMA_INVALID"):
        classify_document("text", endpoint="http://localhost:11434", model="m")


def test_classify_document_raises_on_truncated_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(classifier.urllib.request, "urlopen", _fake_chat(done_reason="length"))
    with pytest.raises(classifier.OllamaResponseError, match="OLLAMA_OUTPUT_TRUNCATED"):
        classify_document("text", endpoint="http://localhost:11434", model="m")


def test_classify_document_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout):
        return _FakeHTTPResponse({"message": {"content": "not json"}, "done_reason": "stop"})

    monkeypatch.setattr(classifier.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(classifier.OllamaResponseError, match="OLLAMA_INVALID_JSON"):
        classify_document("text", endpoint="http://localhost:11434", model="m")


def test_classify_document_confidence_defaults_to_unknown_if_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout):
        return _FakeHTTPResponse({"message": {"content": json.dumps({"document_type": "invitation"})}, "done_reason": "stop"})

    monkeypatch.setattr(classifier.urllib.request, "urlopen", fake_urlopen)
    result = classify_document("text", endpoint="http://localhost:11434", model="m")
    assert result == {"document_type": "invitation", "confidence": "unknown"}
