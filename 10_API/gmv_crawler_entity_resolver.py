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

## The second, adjacent half: IDENTITY, not TYPE

`classify_entity_types()` above answers "what KIND of entity is this
name?". `resolve_entity_gmv_id()` (added at the end of this file, 2026-09-26)
answers the strictly narrower, strictly prior question: "does this name
already HAVE a stable identity, and which one?". They do not overlap and
neither subsumes the other -- a name can be typed without being resolved
(that is every `MODEL_INFERENCE` proposal above), and a name can be
resolved to an id without this module ever asserting a type -- and both
are proposals for a consumer to act on, never decisions recorded
anywhere. The two sit side by side in one module on purpose: this file is
already the crawler's home for "what do we know about an entity name", and
splitting identity into a second module for the sake of tidiness would
give the two halves different, divergent conventions for the same
job (both already share one convention: exact normalized comparison,
`.strip().lower()`, and an ambiguous match resolves to "no answer", never
to a silent pick -- see `resolve_entity_gmv_id()`'s own docstring and
`gmv_crawler_relation_atom_builder._link_object_to_entity()`, the existing
real precedent for exactly that rule in this subsystem).

Everything out-of-scope above stays out-of-scope here too, with the
`resolve_entity_gmv_id()` case stated explicitly since it is the more
tempting one: this function READS a plain human-curated JSON file
(`00_CONFIG/gmv_entity_registry.json`) and WRITES NOTHING -- not the
`entities`/`entity_aliases` tables of migration 010, not the JSON file
itself, not any sqlite connection of any kind. It does not generate,
mint, or auto-register a `gmv_id` for a name it does not recognize:
returning `None` is a legitimate, non-error outcome that the caller is
required to treat as "stays unresolved / type-neutral", which is the
Epistemic Ingestion Constitution v0.1 rule-8 shape (use a type-neutral
identifier and record the typing issue) that `classify_entity_types()`'s
`needs_verification=True` already implements for the type question.
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
KNOWN_INSTITUTIONS_PATH = REPO_ROOT / "00_CONFIG" / "area35_known_institutions.json"

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
    source: str  # "MATCHED_KNOWN_ARTIST_ROSTER" | "MATCHED_KNOWN_INSTITUTION_LIST" | "MODEL_INFERENCE"
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


def _load_known_institutions() -> frozenset[str]:
    """The real, human-confirmed institution list (00_CONFIG/area35_known_institutions.json),
    `_forma()`-normalized -- same pattern as `_load_known_artists()`. Starts
    empty (2026-09-17) and grows only through explicit human confirmation
    (e.g. the OpenWebUI review chat's `confirm_institution` tool), never
    auto-populated from model output -- same 'verified fact, not inference'
    principle as the artist roster."""
    data = json.loads(KNOWN_INSTITUTIONS_PATH.read_text(encoding="utf-8"))
    return frozenset(_forma(name) for name in data["institutions"])


def _classify_via_ollama(
    entity_names: Sequence[str], *, endpoint: str, model: str, timeout: int,
    temperature: float | None = None, seed: int | None = None,
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
    options: dict[str, object] = {}
    if temperature is not None: options["temperature"] = temperature
    if seed is not None: options["seed"] = seed
    payload = json.dumps(
        {"model": model, "prompt": prompt, "stream": False,
         "format": CLASSIFICATION_SCHEMA, "think": False, "options": options}
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
    known_institutions: frozenset[str] | None = None,
    endpoint: str = DEFAULT_ENDPOINT, model: str = DEFAULT_MODEL, timeout: int = 60,
    temperature: float | None = None, seed: int | None = None,
) -> tuple[EntityTypeProposal, ...]:
    """Classify every entity into a proposal, in the input order.

    `known_institutions` (2026-09-17) mirrors `known_artists` exactly, one
    list per governed entity_type instead of one shared list, because the
    two rosters have different real sources and different maintainers: the
    artist roster is a point-in-time Dropbox folder snapshot; the
    institution list starts empty and grows only through explicit human
    confirmation (the OpenWebUI review chat's `confirm_institution` tool).
    A name matching BOTH lists is treated as an artist (checked first) --
    not expected in practice (an institution and a person/artist sharing
    the exact same real name is not a real case this project has seen),
    but the order is fixed and documented rather than left to iteration
    order.

    `temperature`/`seed` (default None, passed straight through to
    `_classify_via_ollama()` -- no behavior change unless a caller opts
    in) exist for the same reason `ollama_extract()` gained them
    (2026-09-17, this session): re-classifying the SAME entity name with
    Ollama's default sampling can return a DIFFERENT `entity_type` on a
    separate call (reproduced live: "Le Stanze della Fotografia" was
    typed INSTITUTION in one run and EXHIBITION in another, with no
    change to the input). MATCHED_KNOWN_ARTIST_ROSTER hits are unaffected
    either way -- they never call the model at all.

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
    if known_institutions is None:
        known_institutions = _load_known_institutions()
    matched_names: dict[str, EntityTypeProposal] = {}
    to_classify: list[CandidateEntity] = []
    for entity in entities:
        normalized = _forma(entity.name)
        if normalized in known_artists:
            matched_names[entity.name] = EntityTypeProposal(
                entity_name=entity.name, entity_type="ARTIST",
                confidence="HIGH", source="MATCHED_KNOWN_ARTIST_ROSTER",
                needs_verification=False,
            )
        elif normalized in known_institutions:
            matched_names[entity.name] = EntityTypeProposal(
                entity_name=entity.name, entity_type="INSTITUTION",
                confidence="HIGH", source="MATCHED_KNOWN_INSTITUTION_LIST",
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
            temperature=temperature, seed=seed,
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


def resolve_entity_gmv_id(name: str, registry: dict) -> str | None:
    """The `gmv_id` already registered for `name`, or `None`.

    `registry` is the parsed `00_CONFIG/gmv_entity_registry.json` (the
    `{"entities": [...]}` shape, human-curated and human-verified, never
    auto-populated -- the same discipline as `area35_known_artists.json`).
    A name matches an entry's `canonical_name` or any of its `aliases`.

    Design decisions, each traceable to something real rather than
    preferred on its own:

    1. **Exact comparison after `.strip().lower()` on BOTH sides. No
       fuzzy matching, no embedding similarity, no LLM call, no
       `difflib`.** The rule this implements is already written into
       `gmv_core/migration_sql/010_entity_registry.sql`'s own header
       ("never fuzzy-match -> automatic merge") and into the crawler
       spec v0.2 §11-§12 it was derived from. The mechanical reason it
       is enforced HERE rather than left to review: the registry is a
       hand-curated file, so a fuzzy match is unauditable against it --
       there is no recorded reason attached to "87% similar", only to
       "the strings are equal". The one real precedent for exact
       normalized comparison in this subsystem is
       `gmv_crawler_relation_atom_builder._link_object_to_entity()` /
       `_load_predicate_mapping()` (`.strip().lower()`, equality, never
       similarity), and the reason a model is excluded is not
       performance: `classify_entity_types()`'s own docstring records two
       reproduced probes where a self-confident model call produced the
       wrong answer on real Garibaldi data, and there is no honest way to
       audit a proposed identity whose only justification is a
       temperature-0 generation that cannot be reproduced by a reviewer
       reading two files. Prove the exact match is sufficient before
       adding a model dependency to identity, not after.
    2. **`.strip().lower()`, NOT `area35_validator._forma()`.** Real
       tension, resolved deliberately: `_forma()` would usefully collapse
       "Garibaldi, Federico" onto "Federico Garibaldi" for free, and it
       is this subsystem's existing name normalizer
       (`compute_atom_fingerprint()`, `derive_current_state()`'s slot
       key, `r_duplicati`). It is not used here because `_forma()` sorts
       ALL tokens, and its own docstring in `compute_atom_fingerprint()`
       records the consequence with a real example: "Venice Biennale" and
       "Biennale Venice" fingerprint IDENTICALLY under it. That is an
       accepted trade-off for deduplication of PERSON/ARTIST names, where
       token order genuinely carries no meaning, and an unacceptable one
       for deciding that two strings are the same ENTITY -- a matcher
       that can only be trusted for people, silently applied to every
       name, is exactly the "fuzzy match -> automatic merge" the SQL
       header forbids. Name variants are the human-curated registry's
       job (`aliases` exists for that); a real "Garibaldi, Federico"
       variant failing to match is reportable evidence for a human to
       add the alias, not something the matcher should quietly decide.
    3. **An ambiguous name -- one appearing on two different entities --
       returns `None`, never the first match.** Same rule and the same
       real precedent as point 2 of `_link_object_to_entity()`'s own
       docstring ("an exact tie ... is a real ambiguity -> None (the
       caller rejects it, never an arbitrary pick)"). This is the
       migration-010 homonyms case, which its own comment on the absence
       of a `(entity_type, canonical_name)` UNIQUE constraint says is a
       real, expected situation to surface for human review rather than
       to resolve by picking one. Three properties of the scan below are
       deliberate, each one an attack this function has to survive:
       - It covers the WHOLE registry before answering, so the result
         cannot depend on the order a human happens to keep entries in.
         A "return the first matching entry" loop would make an identity
         function's answer change when the file is reformatted for
         readability -- a latent wrong-entity merge, not a cosmetic bug.
       - An entity listing its own `canonical_name` in its own `aliases`
         is ONE entity, not two: otherwise a harmless redundancy in a
         hand-curated file would silently un-resolve a real name.
       - A third entry claiming an already-ambiguous name cannot
         re-resolve it back to one of the first two.
       Honest limitation, stated rather than hidden: the declared return
       type carries one value, so "matched nothing" and "matched two
       things" both arrive as `None` and this function cannot tell the
       caller which happened. Both are the least-assertive outcome
       available (Constitution v0.1 rule 12: "when two interpretations
       are possible, choose the less assertive one"), but a future
       caller that needs to route only the ambiguous cases to a
       human-review queue will need a wider signature than this one -- a
       design decision for whoever builds that queue, not something
       this function guesses at by raising.
    4. **An empty/whitespace-only `name` never matches, even a registry
       entry whose own name is empty.** An entity with no name has not
       been identified by anything, so matching it would hand back an id
       for an unknown string. Symmetrically, an entry whose `gmv_id` is
       empty is skipped rather than matched: an entry with no id
       identifies nothing, and returning `""` would be worse than `None`
       -- `""` is falsy but not `None`, so a caller checking `is None`
       would let it through and materialize a Monad with an empty
       `gmv_id`, which `gmv_monad_materializer.gmv_id_is_well_formed()`
       would then reject as a BLOCKER far downstream, with the real
       cause (a broken registry entry) nowhere near the error.
    5. **A malformed entry is a caller bug and raises; it is never read
       as "no match".** An entry that is not a dict, or has no
       `canonical_name`, propagates a `KeyError`/`TypeError` out of here
       -- the same treatment a malformed `registry` argument gets in
       `validate_atom()`/`build_atoms()` elsewhere in this subsystem,
       and the same reason `_load_known_artists()`'s `data["artists"]`
       lets a `KeyError` propagate. Silently degrading a broken
       hand-curated governance file to "this name happens to be
       unknown" is how a real entity quietly stops resolving.
    6. **No `gmv_id` is ever generated, minted, or auto-registered.** A
       name with no registry entry returns `None` and stays that way.
       The generation scheme is explicitly undecided in migration 010
       ("NOT decided by this migration") and remains open in
       `GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md` §2 Q1; auto-creating
       an id here would silently make a real editorial decision (that
       this string is a new, distinct entity) as a side effect of a
       lookup. `None` is a first-class outcome, not an error: callers
       must treat it as "unresolved / type-neutral" and carry on.
    7. **Reads the registry, writes nothing, and caches nothing.** No
       sqlite, no JSON write, no registry mutation -- the same
       "proposals live in memory only" boundary
       `classify_entity_types()`'s module section already declares for
       the type question. The scan is also deliberately per-call rather
       than memoized at module level: this file is hand-curated and
       expected to be edited by a human between runs (that is its whole
       maintenance model, see its own `note_on_maintenance`), and a
       cached index would keep answering with the pre-edit contents for
       the rest of the process -- staleness in an identity lookup means
       confidently resolving to the wrong entity, which is materially
       worse than re-reading a one-entry file. Cost is O(entries) per
       name, negligible at this size and for the one-call pattern a
       caller has today; a caller that ever needs to resolve a very
       large name set should restructure for a batch, not have a stale
       cache appear for it.
    """
    normalized = name.strip().lower()
    if not normalized:
        return None
    resolved: str | None = None
    for entry in registry["entities"]:
        gmv_id = entry["gmv_id"]
        if not gmv_id:
            continue
        for raw_name in (entry["canonical_name"], *entry.get("aliases", ())):
            candidate = raw_name.strip().lower()
            if not candidate or candidate != normalized:
                continue
            if resolved is not None and resolved != gmv_id:
                return None
            resolved = gmv_id
    return resolved
