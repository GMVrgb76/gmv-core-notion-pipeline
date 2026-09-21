#!/usr/bin/env python3
"""GMV Crawler — Document type classification.

New pipeline stage, added 2026-09-21. Real-archive audit found that
different Area35 document types (contracts, price lists, biographies,
technical sheets, press releases, invitations, certificates) need
fundamentally different extraction schemas -- not just different predicate
mappings in `00_CONFIG/crawler_predicate_text_mapping.json` -- and that
folder-name-based typing is not reliable enough to route on: of
`09_TEMP_IMPORT`'s 181 real documents (the largest single category, over a
third of the whole archive), only about 55% could be typed from filename
keywords alone even after two rounds of fixing the matching regex; the rest
have free-form names (`"de profundis progetto.pdf"`, `"3 totale 6 pezzi piu
2 grandi 40x45cm - lou qi-2.pdf"`) with no reliable signal at all. This
stage asks the model "what kind of document is this" from real *content*,
before any entity/claim extraction is attempted -- so a caller can route to
the right downstream schema (this module does not build one itself yet;
see `DOCUMENT_TYPES` below for what's classified, `gmv_crawler_candidate_
extractor.py` for the one schema that exists so far, biography/press
material).

Deliberately minimal duplication of `gmv_evidence_pipeline.py`'s HTTP-calling
shape (same /api/chat + template-role request, same format-constrained JSON)
rather than generalizing `ollama_extract()` itself -- that function is
already tested/reviewed/shipped for the entities/claims contract, and
widening its schema parameter to cover classification too is a separate,
larger change this module does not need to force through just to answer
"what kind of document is this."
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_evidence_pipeline import EvidenceError, OllamaResponseError, canonical  # noqa: E402 -- reused, not reimplemented

DOCUMENT_TYPES = [
    "biography", "contract", "price_list", "technical_sheet",
    "press_release", "invitation", "certificate", "other",
]

# NuExtract-style template: field names + type hints, not real values --
# same convention as gmv_evidence_pipeline.py's NUEXTRACT_CHAT_TEMPLATE.
CLASSIFICATION_TEMPLATE = {"document_type": "string", "confidence": "string"}

CLASSIFICATION_INSTRUCTIONS = (
    "Classify this document into exactly one of: " + ", ".join(DOCUMENT_TYPES) + ". "
    "'biography' covers CVs, artist statements, critical texts, and press releases "
    "about an artist's career or work. 'contract' covers any legal agreement between "
    "parties. 'price_list' covers listings of artworks with prices. 'technical_sheet' "
    "covers artwork material/dimension specifications. 'certificate' covers "
    "certificates of authenticity. 'press_release' covers exhibition/event "
    "announcements distinct from a career biography. 'invitation' covers event or "
    "exhibition invitations and flyers. Use 'other' only if none of these fit. "
    "Report your confidence as high, medium, or low."
)

CLASSIFICATION_SCHEMA = {
    "type": "object", "required": ["document_type"],
    "properties": {
        "document_type": {"type": "string", "enum": DOCUMENT_TYPES},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
}


def classify_document(text: str, *, endpoint: str, model: str, max_chars: int = 4000,
                      timeout: int = 60, num_ctx: int = 8192, num_predict: int = 256) -> dict:
    """Ask the model what kind of document `text` is, via the same NuExtract
    /api/chat + template-role shape `gmv_crawler_candidate_extractor.py`
    already uses for extraction. Only the first `max_chars` are sent --
    classifying a document's type needs far less context than full
    extraction (the type is normally obvious from the opening section), and
    keeping this call small keeps classification fast relative to the much
    more expensive extraction step it's meant to gate.

    Raises `OllamaResponseError`/`EvidenceError` on any real failure -- not
    swallowed here, matching `extract_candidates()`'s own stated principle
    that an LLM/network failure is the caller's problem to handle, not this
    stage's to hide."""
    snippet = text[:max_chars]
    messages = [
        {"role": "template", "content": canonical(CLASSIFICATION_TEMPLATE)},
        {"role": "instructions", "content": CLASSIFICATION_INSTRUCTIONS},
        {"role": "user", "content": snippet},
    ]
    payload = json.dumps({"model": model, "messages": messages, "stream": False,
                          "format": CLASSIFICATION_SCHEMA, "think": False,
                          "options": {"num_ctx": num_ctx, "num_predict": num_predict}}).encode()
    request = urllib.request.Request(endpoint.rstrip("/") + "/api/chat", data=payload, headers={"Content-Type": "application/json"})  # noqa: S310 - endpoint is the caller-supplied local Ollama config, never user/remote input
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 -- same fixed local Ollama endpoint
            envelope = json.load(response)
            raw_output = (envelope.get("message") or {}).get("content", "")
            if envelope.get("done_reason") in {"length", "max_tokens"}:
                raise OllamaResponseError("OLLAMA_OUTPUT_TRUNCATED", runtime={}, raw_output=raw_output)
            try:
                parsed = json.loads(raw_output)
            except json.JSONDecodeError as exc:
                raise OllamaResponseError("OLLAMA_INVALID_JSON", raw_output=raw_output) from exc
    except urllib.error.URLError as exc:
        raise EvidenceError("OLLAMA_UNAVAILABLE") from exc
    except TimeoutError as exc:
        raise EvidenceError("TIMEOUT") from exc
    document_type = parsed.get("document_type")
    if document_type not in DOCUMENT_TYPES:
        raise OllamaResponseError("OLLAMA_SCHEMA_INVALID", raw_output=raw_output)
    return {"document_type": document_type, "confidence": parsed.get("confidence", "unknown")}
