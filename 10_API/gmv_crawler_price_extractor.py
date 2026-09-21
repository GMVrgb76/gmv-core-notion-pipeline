#!/usr/bin/env python3
"""GMV Crawler — Price-list extraction (new schema, added 2026-09-21).

`gmv_crawler_candidate_extractor.py`'s entities/claims schema does not fit
real Area35 price-list documents: forcing a price list through it produces
"claims" like `subject="Giovanni Pasini Don Quijote, 2018" predicate="Prezzo"
object="7.500"` -- schema-valid but not a useful shape for the actual future
use case (tracking how a given artwork's price moves over time), and every
distinct price-list row generates its own one-off "predicate" that clutters
`00_CONFIG/crawler_predicate_text_mapping.json`'s rejection queue with noise
that will never repeat (see `gmv_crawler_document_classifier.py`'s own
docstring for the full audit that found this).

Two real Area35 price lists were read to shape this schema (Giovanni
Pasini's and Gaspare Manos's, both `09_TEMP_IMPORT`): both list, per
artwork, artist, title, year, medium, dimensions, and a price (often with
a currency symbol and a "tasse incluse"/"taxes included" qualifier). This
module's `CandidateArtworkPrice` mirrors exactly those fields, verbatim
where possible -- no fields invented beyond what both real documents
actually contained.

Reuses `gmv_evidence_pipeline.py`'s `deterministic_chunks()`/
`adaptive_split_chunk()` for the same reason `extract_candidates()` does:
a price list for an artist with many works, or a multi-artist gallery-wide
list, can in principle overflow `num_predict` the same way a long
biography's exhibition list did -- chunking now avoids rediscovering that
failure mode on a real long price list later.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_crawler_candidate_extractor import _validate_evidence_id  # noqa: E402 -- reused, not reimplemented
from gmv_evidence_pipeline import (  # noqa: E402 -- reused, not reimplemented
    EvidenceError,
    OllamaResponseError,
    adaptive_split_chunk,
    canonical,
    deterministic_chunks,
)

DEFAULT_MODEL = "numind/nuextract3:q4_k_m"
DEFAULT_API_STYLE = "chat_template"
DEFAULT_ENDPOINT = "http://localhost:11434"

PRICE_LIST_TEMPLATE = {
    "artworks": [{
        "artist_name": "verbatim-string", "title": "verbatim-string", "year": "integer",
        "medium": "verbatim-string", "dimensions": "verbatim-string", "price": "number",
        "currency": "verbatim-string", "evidence_excerpt": "verbatim-string",
    }],
}
PRICE_LIST_INSTRUCTIONS = (
    "Extract every artwork listed with a price. Only extract information explicitly "
    "present in the text. Do not infer a missing field -- omit it instead. "
    "'price' must be the numeric amount only (no currency symbol, no thousands "
    "separators). 'currency' should be the ISO-ish symbol or code as written "
    "(e.g. €, EUR, $, USD)."
)
PRICE_LIST_SCHEMA = {
    "type": "object", "required": ["artworks"],
    "properties": {
        "artworks": {"type": "array", "items": {
            "type": "object", "required": ["title", "price", "evidence_excerpt"],
            "properties": {
                "artist_name": {"type": "string"}, "title": {"type": "string"},
                "year": {"type": ["integer", "null"]}, "medium": {"type": "string"},
                "dimensions": {"type": "string"}, "price": {"type": "number"},
                "currency": {"type": "string"}, "evidence_excerpt": {"type": "string"},
            },
        }},
    },
}


@dataclass(frozen=True, slots=True)
class CandidateArtworkPrice:
    """One priced-artwork row from a real price list. `price`/`title`/
    `evidence_excerpt` are the only fields required non-empty -- the rest
    (artist_name/year/medium/dimensions/currency) are real fields seen in
    both source documents this schema was built from, but not every price
    list states all of them for every row."""
    title: str
    price: float
    evidence_excerpt: str
    source_id: str
    evidence_id: tuple[str, ...]
    extraction_claim_ref: str
    artist_name: str = ""
    year: int | None = None
    medium: str = ""
    dimensions: str = ""
    currency: str = ""

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("title must not be empty")
        if self.price is None:
            raise ValueError("price must not be empty")
        if not self.evidence_excerpt:
            raise ValueError("evidence_excerpt must not be empty")
        if not self.source_id:
            raise ValueError("source_id must not be empty")
        if not self.extraction_claim_ref:
            raise ValueError("extraction_claim_ref must not be empty")
        _validate_evidence_id(self.evidence_id)


def _chat_template_call(text: str, *, endpoint: str, model: str, timeout: int,
                        num_ctx: int, num_predict: int, temperature: float | None, seed: int | None) -> dict:
    messages = [
        {"role": "template", "content": canonical(PRICE_LIST_TEMPLATE)},
        {"role": "instructions", "content": PRICE_LIST_INSTRUCTIONS},
        {"role": "user", "content": text},
    ]
    options = {"num_ctx": num_ctx, "num_predict": num_predict}
    if temperature is not None: options["temperature"] = temperature
    if seed is not None: options["seed"] = seed
    payload = json.dumps({"model": model, "messages": messages, "stream": False,
                          "format": PRICE_LIST_SCHEMA, "think": False,
                          "options": options}).encode()
    request = urllib.request.Request(endpoint.rstrip("/") + "/api/chat", data=payload, headers={"Content-Type": "application/json"})  # noqa: S310 - endpoint is the caller-supplied local Ollama config, never user/remote input
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - same fixed local Ollama endpoint
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
    artworks = parsed.get("artworks")
    if not isinstance(artworks, list):
        raise OllamaResponseError("OLLAMA_SCHEMA_INVALID", raw_output=raw_output)
    return {"artworks": artworks}


def extract_price_entries(
    document_text: str, *, source_id: str, evidence_ids: tuple[str, ...],
    endpoint: str = DEFAULT_ENDPOINT, model: str = DEFAULT_MODEL,
    timeout: int = 60, num_predict: int = 2048, num_ctx: int = 8192,
    temperature: float | None = 0, seed: int | None = 42,
    max_chunk_chars: int = 8000, min_adaptive_chunk_chars: int = 500, max_adaptive_depth: int = 4,
) -> tuple[tuple[CandidateArtworkPrice, ...], tuple[str, ...]]:
    """Extract priced artworks from a real price-list document. Chunking/
    adaptive-retry mirrors `extract_candidates()` exactly (same
    `deterministic_chunks()`/`adaptive_split_chunk()` reuse, same
    `ADAPTIVE_CHUNK_MINIMUM_EXHAUSTED`/`ADAPTIVE_CHUNK_MAX_DEPTH` exhaustion
    errors) -- see that function's docstring for the live-reproduced reason
    this exists. Per-item construction failures reject only that one row,
    not the whole document, for the same reason `extract_candidates()`
    does this (spec v0.2 §10: "il candidato è rifiutato", singular)."""
    record = {"file_id": source_id, "text": document_text}

    def _extract_node(node: dict, depth: int = 0) -> list[dict]:
        try:
            result = _chat_template_call(node["text"], endpoint=endpoint, model=model,
                                          timeout=timeout, num_ctx=num_ctx, num_predict=num_predict,
                                          temperature=temperature, seed=seed)
        except OllamaResponseError as exc:
            if str(exc) != "OLLAMA_OUTPUT_TRUNCATED":
                raise
            if len(node.get("text", "")) <= min_adaptive_chunk_chars:
                raise EvidenceError("ADAPTIVE_CHUNK_MINIMUM_EXHAUSTED") from exc
            if depth >= max_adaptive_depth:
                raise EvidenceError("ADAPTIVE_CHUNK_MAX_DEPTH") from exc
            left, right = adaptive_split_chunk(node)
            return _extract_node(left, depth + 1) + _extract_node(right, depth + 1)
        return result["artworks"]

    all_rows: list[dict] = []
    for index, chunk in enumerate(deterministic_chunks(record, max_chunk_chars)):
        chunk["chunk_id"] = str(index)
        all_rows.extend(_extract_node(chunk))

    entries: list[CandidateArtworkPrice] = []
    rejected: list[str] = []
    for i, row in enumerate(all_rows):
        try:
            entries.append(CandidateArtworkPrice(
                title=row["title"], price=row["price"], evidence_excerpt=row["evidence_excerpt"],
                source_id=source_id, evidence_id=evidence_ids, extraction_claim_ref=f"{source_id}#{i}",
                artist_name=row.get("artist_name", ""), year=row.get("year"),
                medium=row.get("medium", ""), dimensions=row.get("dimensions", ""),
                currency=row.get("currency", ""),
            ))
        except (ValueError, KeyError) as exc:
            rejected.append(f"artwork {row.get('title', '<untitled>')!r}: {exc}")
    return tuple(entries), tuple(rejected)
