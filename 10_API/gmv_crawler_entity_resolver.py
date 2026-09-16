#!/usr/bin/env python3
"""GMV Crawler — entity type classification (RESOLVE ENTITIES, narrow slice).

`CandidateEntity` (10_API/gmv_crawler_candidate_extractor.py) carries
`name`/`evidence_excerpt`/`status`/`source_id`/`evidence_id` but NO type.
Building a real atom around a RELATION predicate (the 11 Task 6 does not
cover) requires knowing what *kind of entity* the subject/object is. This
module produces exactly that: a typed PROPOSAL, never a decision.

The design below was decided with the user after two REAL (not
hypothetical) probes against local `gemma4:12b` on entities extracted
from a real biography (see task brief opencode_task_8.md for the full
account; this session did not re-run the live probes -- verified via the
mocked network tests instead, and the directing session re-runs the real
cases at its next start):

1. Asking the model to classify a name from text context alone produced
   errors even at self-declared `HIGH` confidence (Federico Garibaldi ->
   PERSON despite the text literally saying "visual artist"). Self-
   reported LLM confidence is NOT a guarantee and must NEVER bypass a
   verification, at any value.
2. Given a real, verified list (the 47 artists actually represented by
   Area35, `00_CONFIG/area35_known_artists.json`, fetched from real
   Dropbox folders), the same case resolves correctly (ARTIST) because
   it is a CHECK against a true fact, not an inference.

Hence the categorical, non-negotiable two-source principle implemented
here -- two categories, NOT two points on one confidence scale:

- `MATCHED_KNOWN_ARTIST_ROSTER`: `_forma(entity.name)` is in the real
  roster -> a verified fact: `entity_type="ARTIST"`,
  `confidence="HIGH"`, `needs_verification=False`. No model call is made
  for these -- it is already verified; asking the model would be wasted
  work and could even corrupt a fact with an inference.
- `MODEL_INFERENCE`: no roster hit, type inferred by the model from
  context -> `needs_verification=True` ALWAYS, whatever confidence the
  model declares -- even `"HIGH"`. No confidence value turns an LLM
  inference into a verified fact; they are different categories.

Whoever consumes these proposals decides what `needs_verification=True`
means -- a human, or eventually the interactive-session web-verification
pattern already used by `gmv_artist_web_retrieve.py` (web research done
by the interactive session, never by a subprocess). NOT BUILT HERE.

Explicit out-of-scope, mirrored in the code: no writes to the Entity
Registry (`entities`/`entity_aliases` in
gmv_core/migration_sql/010_entity_registry.sql) and no `sqlite3` at all
-- proposals live in memory only; no persistent review queue for these
(the Task 7 JSONL queue is a different concern); no external web lookup;
no editing of `area35_known_artists.json` (a future editorial choice);
no modification of any existing module -- error classes and defaults are
REUSED, not reimplemented:
`EvidenceError`/`OllamaResponseError` come from `gmv_evidence_pipeline`
(the same family `ollama_extract()` raises), `DEFAULT_ENDPOINT`/
`DEFAULT_MODEL` from `gmv_crawler_candidate_extractor`, and `_forma()`
via the exact `from area35_validator import ...` root import pattern
already used at `gmv_atom_validator.py:106`.

The one Ollama call reuses `ollama_extract()`'s proven HTTP envelope
style (same `/api/generate` path, same `"format"` schema constraint,
same `"think"` handling, same `done_reason` truncation check, same
`urllib.request` error mapping) -- reimplemented here rather than
imported because the payload schema and record shape differ; the control
flow is intentionally the same shape.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from area35_validator import _forma  # noqa: E402 -- root-module import, exact pattern of gmv_atom_validator.py:106
from gmv_crawler_candidate_extractor import (  # noqa: E402 -- reuse, not redefine (task brief Task 8)
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    CandidateEntity,
)
from gmv_evidence_pipeline import EvidenceError, OllamaResponseError  # noqa: E402 -- same error family as ollama_extract(), reused not reimplemented

KNOWN_ARTISTS_PATH = REPO_ROOT / "00_CONFIG" / "area35_known_artists.json"

#: The 12 valid entity_type values, verbatim from the `entity_type IN (...)` CHECK
#: in gmv_core/migration_sql/010_entity_registry.sql (cross-checked by a test in
#: tests/test_gmv_crawler_entity_resolver.py so this constant cannot silently drift
#: from the schema). ARTIST, WORK and friends are CORE/DOMAIN-status class_ids there;
#: ARTWORK is deliberately absent (DEPRECATED).
VALID_ENTITY_TYPES = frozenset(
    {
        "PERSON", "ORGANIZATION", "INSTITUTION", "PLACE", "EVENT", "DOCUMENT",
        "ARTIST", "EXHIBITION", "PROJECT", "COLLECTION", "WORK", "ARTWORK_INSTANCE",
    }
)
VALID_CONFIDENCES = frozenset({"HIGH", "MEDIUM", "LOW"})

#: The JSON-schema "format" constraint passed to Ollama with the classification call,
#: the same mechanism SEMANTIC_OUTPUT_SCHEMA uses for ollama_extract(). Built from
#: VALID_ENTITY_TYPES/VALID_CONFIDENCES so schema and validation set cannot drift
#: apart inside this module.
CLASSIFICATION_SCHEMA: dict = {
    "type": "object",
    "required": ["classifications"],
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "entity_type", "confidence"],
                "properties": {
                    "name": {"type": "string"},
                    "entity_type": {"type": "string", "enum": sorted(VALID_ENTITY_TYPES)},
                    "confidence": {"type": "string", "enum": sorted(VALID_CONFIDENCES)},
                },
            },
        }
    },
}


@dataclass(frozen=True, slots=True)
class EntityTypeProposal:
    """One entity's proposed type. A PROPOSAL, never a decision: nothing
    here registers the type anywhere, and `needs_verification=True` is the
    contractual signal that a human (or the interactive-session pattern)
    must confirm before this type can be acted upon."""

    entity_name: str
    entity_type: str  # one of the 12 values in 010_entity_registry.sql
    confidence: str  # "HIGH" | "MEDIUM" | "LOW"
    source: str  # "MATCHED_KNOWN_ARTIST_ROSTER" | "MODEL_INFERENCE"
    needs_verification: bool


def _load_known_artists() -> frozenset[str]:
    """The real Area35 represented-artist roster, `_forma()`-normalized for
    O(1) membership checks. Reads `area35_known_artists.json` field
    `"artists"` (47 real names, fetched from Dropbox folder names -- a
    point-in-time snapshot, see that file's own note). Normalizing with
    `_forma()` (area35_validator.py, the same function the duplicate
    detector already uses) makes "Garibaldi, Federico" and "Federico
    Garibaldi" the same key without inventing a new normalization -- the
    roster's own shape is Firstname Surname."""
    data = json.loads(KNOWN_ARTISTS_PATH.read_text(encoding="utf-8"))
    return frozenset(_forma(name) for name in data["artists"])


def _classify_via_ollama(
    entity_names: Sequence[str], *, endpoint: str, model: str, timeout: int
) -> list[dict]:
    """One Ollama classification call for the whole batch of unmatched
    names (a document, one call -- the `ollama_extract()` principle, not
    one call per entity). Deliberately the SAME envelope shape as
    `ollama_extract()` (10_API/gmv_evidence_pipeline.py): `/api/generate`,
    structured `"format"` constraint, explicit `"think": False` (a real
    probe in this session showed omitting it yields truncated/empty
    responses -- it is not optional), `done_reason in {"length",
    "max_tokens"}` -> `OLLAMA_OUTPUT_TRUNCATED`, unparseable raw output ->
    `OLLAMA_INVALID_JSON`, missing/schema-invalid `classifications` ->
    `OLLAMA_SCHEMA_INVALID`, `URLError` -> `EvidenceError
    ("OLLAMA_UNAVAILABLE")`, `TimeoutError` -> `EvidenceError("TIMEOUT")`.
    A call-level failure propagates -- it is never swallowed into a fake
    proposal."""
    prompt = (
        "Classify each entity name below into exactly one of these entity "
        "types: " + ", ".join(sorted(VALID_ENTITY_TYPES)) + ". "
        "Return ONLY JSON with a field 'classifications': an array with one "
        "item per name, each item an object with name (the exact name you "
        "were given, verbatim), entity_type (exactly one of the types "
        "listed above), confidence (one of HIGH, MEDIUM, LOW). Do not omit "
        "any name and do not reorder.\nNAMES:\n"
        + "\n".join(f"- {name}" for name in entity_names)
    )
    payload = json.dumps(
        {"model": model, "prompt": prompt, "stream": False,
         "format": CLASSIFICATION_SCHEMA, "think": False}
    ).encode()
    request = urllib.request.Request(  # noqa: S310 - caller-supplied local Ollama endpoint, same form and rationale as ollama_extract()
        endpoint.rstrip("/") + "/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - same fixed local Ollama endpoint
            envelope = json.load(response)
            raw_output = envelope.get("response", "")
            runtime = {k: envelope.get(k) for k in ("done_reason", "eval_count", "prompt_eval_count")}
            if envelope.get("done_reason") in {"length", "max_tokens"}:
                raise OllamaResponseError("OLLAMA_OUTPUT_TRUNCATED", runtime=runtime, raw_output=raw_output)
            try:
                parsed = json.loads(raw_output)
            except json.JSONDecodeError as exc:
                raise OllamaResponseError("OLLAMA_INVALID_JSON", runtime=runtime, raw_output=raw_output) from exc
            classifications = parsed.get("classifications")
            if not isinstance(classifications, list):
                raise OllamaResponseError("OLLAMA_SCHEMA_INVALID", runtime=runtime, raw_output=raw_output)
            return classifications
    except urllib.error.URLError as exc:
        raise EvidenceError("OLLAMA_UNAVAILABLE") from exc
    except TimeoutError as exc:
        raise EvidenceError("TIMEOUT") from exc
    except KeyError as exc:
        raise OllamaResponseError("OLLAMA_INVALID_JSON") from exc


def classify_entity_types(
    entities: Sequence[CandidateEntity], *,
    known_artists: frozenset[str] | None = None,
    endpoint: str = DEFAULT_ENDPOINT, model: str = DEFAULT_MODEL, timeout: int = 60,
) -> tuple[EntityTypeProposal, ...]:
    """Classify every entity into a proposal, in the input order.

    1. `known_artists` None -> `_load_known_artists()` (the accept-from-
       caller / load-by-default pattern `validate_atom()`/
       `derive_current_state()` already use for `registry`).
    2. `_forma(entity.name) in known_artists` -> `MATCHED_KNOWN_ARTIST_ROSTER`,
       `entity_type="ARTIST"`, `confidence="HIGH"`,
       `needs_verification=False`. No model call for these.
    3. Unmatched entities go to ONE `_classify_via_ollama()` call for the
       whole sub-batch. Each response item is matched to a requested
       entity by EXACT `name` -- never by position/order (the model may
       reorder). Item-level contract checks mirror `ollama_extract()`:
       a `name`/`entity_type`/`confidence` outside the schema vocabularies
       raises `OLLAMA_SCHEMA_INVALID`.
    4. A requested entity ABSENT from the response is never silently
       dropped and never gets an invented proposal -- this raises
       `EvidenceError("CLASSIFICATION_MISSING_ENTITY")` with the missing
       names in `detail`. This exact handling is the decision documented
       in the commit for the task-brief's open point (no reason_code was
       prescribed); the whole batch fails because the model demonstrably
       violated its one contract (classify every given name).
    5. Every model-classified proposal gets `source="MODEL_INFERENCE"`,
       `needs_verification=True` -- unconditionally, whatever `confidence`
       the model returned (HIGH included). Not a threshold; a category.
    """
    if known_artists is None:
        known_artists = _load_known_artists()
    matched_names: dict[str, EntityTypeProposal] = {}
    to_classify: list[CandidateEntity] = []
    for entity in entities:
        if _forma(entity.name) in known_artists:
            matched_names[entity.name] = EntityTypeProposal(
                entity_name=entity.name, entity_type="ARTIST",
                confidence="HIGH", source="MATCHED_KNOWN_ARTIST_ROSTER",
                needs_verification=False,
            )
        else:
            to_classify.append(entity)
    classified: dict[str, EntityTypeProposal] = {}
    if to_classify:
        requested_names = {entity.name for entity in to_classify}
        for item in _classify_via_ollama(
            [entity.name for entity in to_classify],
            endpoint=endpoint, model=model, timeout=timeout,
        ):
            name = item.get("name")
            entity_type = item.get("entity_type")
            confidence = item.get("confidence")
            if name is None or entity_type not in VALID_ENTITY_TYPES or confidence not in VALID_CONFIDENCES:
                raise OllamaResponseError("OLLAMA_SCHEMA_INVALID")
            if name not in requested_names:
                # an entity the model invented (not in the request): well-formed
                # but not ours, ignored -- it cannot leak into the proposals
                continue
            classified[name] = EntityTypeProposal(
                entity_name=name, entity_type=entity_type, confidence=confidence,
                source="MODEL_INFERENCE", needs_verification=True,
            )
        missing = requested_names - set(classified)
        if missing:
            raise EvidenceError(
                "CLASSIFICATION_MISSING_ENTITY",
                detail=(
                    "model response did not classify every requested name; "
                    f"missing: {sorted(missing)!r}"
                ),
            )
    return tuple(
        matched_names[entity.name] if entity.name in matched_names else classified[entity.name]
        for entity in entities
    )