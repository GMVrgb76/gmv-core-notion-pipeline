#!/usr/bin/env python3
"""GMV Crawler — Contract-terms extraction (new schema, added 2026-09-21).

Shaped from a real Area35 contract (Giovanni Pasini's, `09_TEMP_IMPORT`):
a "conto-vendita" (consignment) agreement between an artist and the gallery
with an explicit date range, a gallery commission percentage, payment-terms
wording, and a handful of named obligation clauses. Forcing this through
`gmv_crawler_candidate_extractor.py`'s entities/claims schema previously
produced one-off "predicates" per legal clause (`"si impegna a promuovere
e vendere"`, `"potrà assegnare"`, `"regola la collaborazione"`) that could
never be usefully mapped to a governed predicate -- a contract's real future
value (cited in this session by the user) is as a structured reference
document for planning the *next* contract, not as a source of biographical
subject/predicate/object facts.

Deliberately NOT chunked, unlike `gmv_crawler_price_extractor.py`'s
per-artwork rows: a contract is one coherent agreement, and its terms
(payment terms defined in one clause can depend on the duration defined in
another) don't merge sensibly if extracted from two independent halves the
way independent price-list rows or independent claims do. If a real
contract turns out to be too long for one call, that's a `max_prompt_chars`/
`num_ctx` sizing question for the caller, not a case for adaptive splitting.
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
from gmv_evidence_pipeline import EvidenceError, OllamaResponseError, canonical  # noqa: E402 -- reused, not reimplemented

DEFAULT_MODEL = "numind/nuextract3:q4_k_m"
DEFAULT_API_STYLE = "chat_template"
DEFAULT_ENDPOINT = "http://localhost:11434"

CONTRACT_TEMPLATE = {
    "contract_type": "verbatim-string", "artist_name": "verbatim-string",
    "gallery_name": "verbatim-string", "start_date": "date-time", "end_date": "date-time",
    "commission_percentage": "verbatim-string", "payment_terms": "verbatim-string",
    "key_obligations": ["verbatim-string"], "evidence_excerpt": "verbatim-string",
}
CONTRACT_INSTRUCTIONS = (
    "Extract the contract's key structured terms. Do not invent facts that are not "
    "stated anywhere in the document, but DO identify fields even when the document "
    "does not use the exact field name as a label -- e.g. 'artist_name' and "
    "'gallery_name' are simply the two parties named in the agreement (often "
    "introduced by wording like 'TRA ... E ...' / 'between ... and ...'), not "
    "something that must be literally labeled 'artist' or 'gallery'. 'start_date'/"
    "'end_date' are the contract's validity period, often phrased as 'dal [date] al "
    "[date]' / 'from [date] to [date]'. 'contract_type' should describe the kind of "
    "agreement (e.g. consignment agreement, sales agreement). 'payment_terms' is a "
    "short phrase describing when/how payment happens. Only omit a field if it is "
    "genuinely not discoverable anywhere in the text. 'key_obligations' should be a "
    "short list of the main duties each party has under this contract, quoted or "
    "closely paraphrased from the text, not a full legal summary."
)
CONTRACT_SCHEMA = {
    "type": "object", "required": ["evidence_excerpt"],
    "properties": {
        "contract_type": {"type": "string"}, "artist_name": {"type": "string"},
        "gallery_name": {"type": "string"}, "start_date": {"type": "string"},
        "end_date": {"type": "string"}, "commission_percentage": {"type": "string"},
        "payment_terms": {"type": "string"},
        "key_obligations": {"type": "array", "items": {"type": "string"}},
        "evidence_excerpt": {"type": "string"},
    },
}


@dataclass(frozen=True, slots=True)
class CandidateContractSummary:
    """A single structured summary of one contract document. Only
    `evidence_excerpt` is required non-empty -- every other field is real
    but optional, since not every real Area35 contract states all of them
    (e.g. some early ones have no explicit end_date)."""
    evidence_excerpt: str
    source_id: str
    evidence_id: tuple[str, ...]
    extraction_claim_ref: str
    contract_type: str = ""
    artist_name: str = ""
    gallery_name: str = ""
    start_date: str = ""
    end_date: str = ""
    commission_percentage: str = ""
    payment_terms: str = ""
    key_obligations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.evidence_excerpt:
            raise ValueError("evidence_excerpt must not be empty")
        if not self.source_id:
            raise ValueError("source_id must not be empty")
        if not self.extraction_claim_ref:
            raise ValueError("extraction_claim_ref must not be empty")
        _validate_evidence_id(self.evidence_id)


def extract_contract_summary(
    document_text: str, *, source_id: str, evidence_ids: tuple[str, ...],
    endpoint: str = DEFAULT_ENDPOINT, model: str = DEFAULT_MODEL,
    max_prompt_chars: int = 24000, timeout: int = 60, num_predict: int = 2048, num_ctx: int = 8192,
    temperature: float | None = 0, seed: int | None = 42,
) -> CandidateContractSummary:
    """One call, no chunking -- see module docstring for why. Raises
    `OllamaResponseError`/`EvidenceError` on any real LLM/network failure,
    and `ValueError` (via `CandidateContractSummary.__post_init__`) only if
    the model returns a response missing the one truly required field
    (`evidence_excerpt`) -- not swallowed, matching `extract_candidates()`'s
    own stated principle."""
    text = document_text[:max_prompt_chars]
    messages = [
        {"role": "template", "content": canonical(CONTRACT_TEMPLATE)},
        {"role": "instructions", "content": CONTRACT_INSTRUCTIONS},
        {"role": "user", "content": text},
    ]
    options = {"num_ctx": num_ctx, "num_predict": num_predict}
    if temperature is not None: options["temperature"] = temperature
    if seed is not None: options["seed"] = seed
    payload = json.dumps({"model": model, "messages": messages, "stream": False,
                          "format": CONTRACT_SCHEMA, "think": False,
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
    return CandidateContractSummary(
        evidence_excerpt=parsed.get("evidence_excerpt", ""),
        source_id=source_id, evidence_id=evidence_ids, extraction_claim_ref=f"{source_id}#0",
        contract_type=parsed.get("contract_type", ""), artist_name=parsed.get("artist_name", ""),
        gallery_name=parsed.get("gallery_name", ""), start_date=parsed.get("start_date", ""),
        end_date=parsed.get("end_date", ""), commission_percentage=parsed.get("commission_percentage", ""),
        payment_terms=parsed.get("payment_terms", ""),
        key_obligations=tuple(parsed.get("key_obligations", []) or ()),
    )
