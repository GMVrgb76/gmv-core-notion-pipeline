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

## The third piece: the human-confirmed WRITE (added 2026-09-26)

The paragraph above is scoped to the LOOKUP, and stays true of it. This
module now also contains the only code in the repository that writes to
`00_CONFIG/gmv_entity_registry.json`, and the boundary between the two
is drawn deliberately, because a lookup that mints an id would silently
make a real editorial decision as a side effect of a read.

- The READ half never writes: `resolve_entity_gmv_id()` above, plus
  `propose_entity_identity()`, which only builds an in-memory
  `EntityIdentityProposal` and does not even queue it -- appending stays
  the caller's explicit decision, the same decoupling
  `gmv_crawler_entity_proposal_queue.py`'s own module docstring already
  declares for the type question ("nothing in `classify_entity_types()`
  calls it: appending stays the caller's decision, by design").
- The WRITE half is exactly two functions, `confirm_new_entity()` and
  `confirm_entity_alias()`, and they exist to be CALLED BY A HUMAN. Both
  read the JSON file, check for an existing match, append, and write it
  back -- the exact read-check-append-write shape of
  `automation/gmv_crawler_review_tool.py::confirm_institution()` /
  `confirm_predicate_mapping()`, and of `area35_known_institutions.json`
  / `crawler_predicate_text_mapping.json` generally. No pipeline stage
  calls them today and none is wired to: the human-in-the-loop entry
  point (the OpenWebUI review chat, the same place
  `confirm_institution()` is triggered from) is a separate, later step,
  deliberately not built here.
- `next_sequential_gmv_id()` sits on this side of the line even though it
  is pure arithmetic over a dict: it is reachable only from
  `confirm_new_entity()`, and computing a candidate id is not the same
  act as assigning one.
- **No LLM, no similarity, no merge.** Nothing in this half decides
  that two names are the same entity, and nothing merges two existing
  entries. Design decision 2 of
  `GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md` §2 (2026-09-26) records
  the merge/split-suggestion layer as deliberately NOT built; a
  confirmed write can only ever CREATE one new entry or ADD one alias a
  human typed. That is why "propose a new entity for this name" and
  "add this name as an alias of GMV-x" are two separate functions
  rather than one function with a flag: the choice between them is the
  editorial decision, and this module only performs the one the human
  picked.
"""

from __future__ import annotations

import json
import re
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

#: The exact shape `next_sequential_gmv_id()` mints and therefore the exact
#: shape it is willing to count toward the next number: "GMV-" + at least six
#: digits and nothing else. Anchored with fullmatch() rather than a loose
#: search, so a legacy/content-derived id ("GMV-ARTIST-FEDERICO-GARIBALDI",
#: or a "GMV-000001-extra" with a trailing suffix) contributes nothing instead
#: of being partially parsed into a number that could collide with a real id.
#: The digit run is a MINIMUM width, not a fixed one, so a hand-written
#: over-long id is respected and the sequence continues past it rather than
#: wrapping or being clamped. This mirrors migration 010's own CHECK
#: (`gmv_id GLOB 'GMV-*' AND length(gmv_id) > length('GMV-')`) on the one
#: point where they can be compared: 010 constrains shape only, not the
#: algorithm, and this is where the decided algorithm (audit §2 Q1) lives.
_SEQUENTIAL_GMV_ID_RE = re.compile(r"GMV-(?P<number>\d{6,})")

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
        (Partially acted on 2026-09-26, and the half that was NOT taken
        is a real decision, not an oversight: `propose_entity_identity()`
        below consumes this `None` and is documented there as
        "propose when the name did not resolve to EXACTLY ONE id", so an
        ambiguous name CAN reach a human-review queue. What it does not
        do is tell the human WHICH case it is. Distinguishing them
        belongs to the deliberately-unbuilt Layer 2 of
        `GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md` §2 Q2 (periodic
        `status=MERGE_CANDIDATE` suggestions), which already has a
        governed status for the ambiguous case; re-deciding it here would
        have duplicated that design, not avoided it.)

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
    6. **No `gmv_id` is ever generated, minted, or auto-registered BY
       THIS FUNCTION.** A name with no registry entry returns `None` and
       stays that way. Two separate reasons, both real:
       (a) auto-creating an id HERE would silently make a real editorial
       decision -- that this string is a new, distinct entity -- as a
       side effect of a lookup, in a file the project classifies as
       "human-curated... never auto-populated" (its own `note` field).
       (b) The generation scheme, undecided when this was written, is
       now DECIDED (2026-09-26, `GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md`
       §2 Q1) as sequential `GMV-000001`, `GMV-000002`, ... , implemented
       by `next_sequential_gmv_id()` in this same file -- but
       deliberately reachable only from `confirm_new_entity()`, a
       human-confirmed write. Deciding the scheme is not the same as
       lifting the human gate, and migration 010's own header
       ("gmv_id generation algorithm ... NOT decided by this migration")
       is still accurate about the SQL, which is schema-only. `None` is a
       first-class outcome, not an error: callers must treat it as
       "unresolved / type-neutral" and carry on.
    7. **Reads the registry, writes nothing, and caches nothing.** No
       sqlite, no JSON write, no registry mutation -- the same
       "proposals live in memory only" boundary
       `classify_entity_types()`'s module section already declares for
       the type question, and the guarantee is stated per-function
       because this module (unlike when this was written) does contain
       writers, further down, behind the human-confirmed boundary the
       module docstring now describes. The scan is also deliberately
       per-call rather than memoized at module level: this file is
       hand-curated and
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


# ---------------------------------------------------------------------------
# The "stop and ask" half: propose, then (human-confirmed) write.
# See the module docstring's third section for the read/write boundary.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EntityIdentityProposal:
    """A name `resolve_entity_gmv_id()` could not resolve, worth a human's
    attention -- NEVER a decision. Mirrors `EntityTypeProposal`'s own
    contract in this same file, for the identity question instead of the
    type question: the same "proposal, never a fact" discipline, the same
    "a `False`/absent field is the human's cue to look" ergonomics, and
    the same refusal to touch sqlite or to write anything anywhere.

    Deliberately NOT a `gmv_id` field: this class is produced before any
    id exists, and adding a "suggested id" field would invite a caller to
    pre-compute one and treat the proposal as a pending assignment. The
    id is minted only by `confirm_new_entity()`, after a human has
    decided this name IS a new entity."""

    raw_name: str
    suggested_entity_type: str  # from classify_entity_types(), "" if unavailable
    source_id: str
    evidence_excerpt: str


def propose_entity_identity(
    name: str, registry: dict, *, source_id: str, evidence_excerpt: str,
    suggested_entity_type: str = "",
) -> EntityIdentityProposal | None:
    """`None` if `name` already resolves via `resolve_entity_gmv_id()` --
    nothing to propose. Otherwise a real `EntityIdentityProposal`.

    Does NOT queue anything itself -- queueing stays the caller's
    explicit decision, the same principle
    `gmv_crawler_entity_proposal_queue.py`'s own docstring already states
    for the type-proposal case ("nothing in `classify_entity_types()`
    calls it: appending stays the caller's decision, by design").

    Design decisions, each traceable to something real:

    1. **`None` means "did not resolve to EXACTLY ONE id", which is
       deliberately broader than "is not in the registry".**
       `resolve_entity_gmv_id()`'s own point 3 returns `None` for a name
       claimed by TWO entities, and that function's docstring states the
       consequence honestly: it cannot tell the caller which of the two
       happened. This function does not paper over that -- it reuses the
       value as given, and the honest consequence is spelled out here
       rather than hidden: **a name that already exists as a homonym will
       produce a "consider a new entity" proposal, which is misleading
       on its face.** The alternatives were weighed and rejected: (a)
       widening `resolve_entity_gmv_id()`'s signature to
       `str | None | AMBIGUOUS` re-opens a decision its own docstring
       explicitly hands to "whoever builds that queue" and would change
       a function this task must not modify; (b) re-scanning the
       registry here to count matches duplicates the exact-match logic
       in a second place, where it can drift. The cost left standing is
       that the human reviewing the queue must check the registry before
       confirming -- acceptable because the queue's whole purpose is
       that a human is looking, and NOT acceptable if this is ever
       surfaced without the registry beside it. The distinguishing layer
       is the deliberately-unbuilt Layer 2 of
       `GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md` §2 Q2, which already
       owns the homonym case through the governed
       `status=MERGE_CANDIDATE`.
    2. **A blank/whitespace-only `name` still returns a proposal, it is
       not silently dropped.** `resolve_entity_gmv_id()` returns `None`
       for a blank name, and "returns None because the caller passed
       nothing" is indistinguishable from "returns None because the name
       is unknown" -- so a filter on the resolver's output alone would
       have to drop blank names, and dropping them silently is how a real
       extraction bug (a model emitting an empty `subject_raw`) becomes
       invisible. An `EntityIdentityProposal` with an empty `raw_name` is
       legible garbage that a human can see in the queue; a silently
       discarded one is not. `CandidateEntity` already refuses an empty
       `name` at construction (`__post_init__`), so this is not a
       reachable path from the real extractor today.
    3. **`suggested_entity_type` is passed in, never computed here.** No
       Ollama call is made by this function, deliberately: the type
       question already has its own two-source principle
       (`classify_entity_types()`, above), whose whole point is that a
       roster hit is a fact and a model inference is not. Calling it here
       would give one name two independent, unreconcilable type answers,
       and would make generating an identity proposal cost a model call
       on a code path whose entire contract is "cheap, mechanical, no
       network" -- the same reason `resolve_entity_gmv_id()`'s point 1
       keeps a model out of identity. The default `""` means "no type
       available", which `EntityTypeProposal` has no equivalent of
       because it is never produced without one; a human confirming a
       new entity therefore still has to supply the type, via
       `confirm_new_entity()`.
    4. **`source_id` and `evidence_excerpt` are recorded verbatim, not
       validated or normalized.** Both are the crawler's own provenance
       fields (`CandidateEntity.source_id` is the Dropbox locator,
       `audit`'s §1.3 finding), and the queue line is a record of what
       was actually seen. Trimming a locator to make it prettier would
       make the queue point at a file that does not exist.
    5. **Reads the registry, writes nothing, and touches no network** --
       the same per-function guarantee as `resolve_entity_gmv_id()`'s
       point 7, restated because this module is no longer uniformly
       write-free and the reader should not have to infer which half
       they are in.
    """
    if resolve_entity_gmv_id(name, registry) is not None:
        return None
    return EntityIdentityProposal(
        raw_name=name,
        suggested_entity_type=suggested_entity_type,
        source_id=source_id,
        evidence_excerpt=evidence_excerpt,
    )


def next_sequential_gmv_id(registry: dict) -> str:
    """max(existing numeric `GMV-NNNNNN` ids in `registry`) + 1, formatted
    6-digit zero-padded. Returns `"GMV-000001"` if the registry has no
    numeric-format ids yet.

    The scheme itself is decided, not chosen here: sequential, per
    `GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md` §2 Q1 (2026-09-26),
    because the crawler spec v0.2 §11-§12 requires a `gmv_id` to be
    "stabile e indipendente dal nome corrente" and a content-derived id
    cannot be -- correcting a name would either move the id (breaking
    stability) or silently desynchronize it from the entity it was
    derived from. The committed registry entry was retrofitted from the
    rejected content-derived format to `GMV-000001` for exactly this
    reason.

    1. **No stored counter, ever.** The next number is recomputed from
       the ids actually present, every call. A `"next_sequence"` field
       would be a second source of truth that drifts the moment someone
       hand-edits the file without updating it -- and hand-editing this
       file is its documented maintenance model
       (`note_on_maintenance`), not an edge case. The same reasoning
       already recorded in the audit for
       `confirm_institution()`/`confirm_predicate_mapping()`: those
       read-check-append-write one file and keep no parallel counter
       either.
    2. **Only the exact `GMV-` + digits shape counts toward the max.** A
       legacy/non-numeric id is IGNORED, not an error, and not parsed
       leniently: matching the WHOLE id with one anchored pattern means
       "GMV-000001-extra" or "GMV-00000A" contributes nothing rather
       than being partially read as a number. Ignoring is safe precisely
       because an ignored id can never be re-issued: it does not have the
       format this function mints.
    3. **A hand-written id that is already past the 6-digit width is
       respected, not clamped.** `GMV-1234567` yields
       `GMV-1234568`: the format is a minimum width, so a longer id
       never silently becomes a duplicate of a shorter one. Clamping
       would be the collision bug this function exists to prevent.
    4. **A malformed entry raises, exactly as in
       `resolve_entity_gmv_id()`'s point 5.** `entry["gmv_id"]` lets a
       non-dict entry or a missing key propagate, and a non-`str` id
       raises `TypeError` here rather than being skipped: it is a broken
       hand-curated governance file, and quietly ignoring it while
       handing back an id derived from the entries that happened to
       parse is how a real entity stops being resolvable without anyone
       being told.
    5. **This is arithmetic, not assignment.** It says which id the NEXT
       confirmed entity would get; only `confirm_new_entity()` actually
       uses that answer to write one. Nothing here reads or writes a
       file, and nothing here can be reached by a pipeline stage.
    """
    highest = 0
    for entry in registry["entities"]:
        gmv_id = entry["gmv_id"]
        if not isinstance(gmv_id, str):
            raise TypeError(
                f"entities[].gmv_id must be a string, got {type(gmv_id).__name__}: {gmv_id!r}"
            )
        match = _SEQUENTIAL_GMV_ID_RE.fullmatch(gmv_id)
        if match is None:
            continue
        highest = max(highest, int(match.group("number")))
    return f"GMV-{highest + 1:06d}"


def _entries_claiming_name(name: str, registry: dict) -> list[dict]:
    """Every entity in `registry` whose `canonical_name` or any `alias`
    matches `name` under `resolve_entity_gmv_id()`'s own rules.

    Exists because `resolve_entity_gmv_id()` cannot answer this question
    itself: its declared return type carries one value, so "matched
    nothing" and "matched two entities" BOTH arrive as `None` (its
    docstring, point 3, states this outright). `confirm_new_entity()`
    needs to tell them apart -- treating a homonym as an unknown name
    would write a third record for a name two entities already own, and
    that bug was in this module's first draft of that function, caught by
    `test_confirm_new_entity_refuses_an_ambiguous_name`.

    The one-entry-sub-registry loop is the fix that adds no second copy of
    the matching rules: each candidate entry is handed to the real
    `resolve_entity_gmv_id()` as a complete one-entity registry, so
    `.strip().lower()` comparison, the empty-name skips, the
    empty-`gmv_id` skip and the malformed-entry raises are all the SAME
    code, by construction, and cannot drift from it. A hand-written
    "does any entry contain this string" scan here would be a second
    implementation of the same decision -- exactly the duplication
    discipline #2 in this project's AGENTS.md forbids.

    Cost is one full scan per entry (O(entries^2) overall), which is
    irrelevant for a hand-curated file of this size and irrelevant still
    for a write that happens once per human confirmation, not per
    document. Returned in file order, so the caller's error messages are
    deterministic.
    """
    claimants: list[dict] = []
    for entry in registry["entities"]:
        if resolve_entity_gmv_id(name, {"entities": [entry]}) is not None:
            claimants.append(entry)
    return claimants


def confirm_new_entity(canonical_name: str, entity_type: str, registry_path: Path) -> str:
    """Reads `registry_path`, computes `next_sequential_gmv_id()`, appends a
    new entity (`{"gmv_id": ..., "entity_type": entity_type,
    "canonical_name": canonical_name, "aliases": [], "status": "ACTIVE"}`),
    writes the file back. Mirrors `confirm_institution()`'s exact
    read-check-append-write shape
    (`automation/gmv_crawler_review_tool.py`). Returns the new `gmv_id`.

    The one function in the repository that can bring a new `gmv_id`
    into existence, which is why every check below is here rather than
    left to the caller:

    1. **It is meant to be called by a human, on a name a human has
       looked at.** No pipeline stage calls it (none is wired to), and
       nothing in the crawler calls it automatically. This mirrors
       `confirm_institution()`'s own docstring instruction ("Usa questa
       funzione SOLO quando l'utente ha confermato esplicitamente...
       non decidere da solo") -- the trigger lives in the OpenWebUI
       review chat, which is a separate later step, not here.
    2. **`entity_type` must be one of the 12 governed values**
       (`VALID_ENTITY_TYPES`, cross-checked against migration 010's own
       `CHECK` by an existing test in
       `tests/test_gmv_crawler_entity_resolver.py`). Without this check a
       typo would be written straight into a governance file and would
       only surface later, if ever, when the entry is compared against
       the schema. Reusing the module's own constant rather than
       re-listing the vocabulary keeps the two from drifting.
    3. **A blank `canonical_name` is rejected.** `resolve_entity_gmv_id()`
       skips empty names on both sides, so an entry created with one
       would be permanently invisible to the resolver -- written,
       counted in the sequence, and resolving nothing. That is the worst
       possible outcome for a write: it looks like success.
    4. **A name that ALREADY resolves is an error, not a silent second
       entry.** `confirm_institution()`'s shape returns "'name' era gia'
       nell'elenco" in that case; here the same situation must instead
       RAISE, because this function's return value is the new `gmv_id`
       and there is no honest id to return -- a duplicate entity would
       split one real entity into two records (the exact eager-splitting
       risk §2 Q1 of the audit explicitly accepts) while looking like a
       successful confirmation to whoever called it. The error message
       names the existing `gmv_id` and points at
       `confirm_entity_alias()`, which is the other real action a human
       might have meant.

       There are THREE cases, not two, and the third is why this uses
       `_entries_claiming_name()` rather than a single
       `resolve_entity_gmv_id()` call. Zero claimants -> create. One
       -> the duplicate error above. Two or more -> a homonym: the
       resolver already answers `None` for that name, and a
       `if resolve(...) is None: create` check would read that as
       "unknown" and write a third record for a name two entities
       already own. That was a real bug in this function's first
       version, caught by
       `test_confirm_new_entity_refuses_an_ambiguous_name` in
       `tests/test_gmv_crawler_entity_resolver.py`; the homonym case now
       raises with both `gmv_id`s named. The distinction is re-derived
       per call from the file, never cached, for the reason
       `resolve_entity_gmv_id()`'s point 7 gives.
    5. **`status` is hard-coded `"ACTIVE"`, matching migration 010's own
       `DEFAULT 'ACTIVE'`.** `MERGE_CANDIDATE`/`MERGED` are the human
       merge-repair vocabulary of the deliberately-unbuilt Layer 2, and
       a write that could set them would be able to assert a merge
       decision nobody made. `merged_into` is not written at all for
       the same reason; note this JSON file is not the SQL table, so
       010's `merged_into` triggers do not apply here -- the constraint
       that matters is the human gate above.
    6. **The file is rewritten in full, in
       `json.dumps(..., indent=2, ensure_ascii=False)` form, exactly as
       `confirm_institution()` does.** Real, stated consequence: the
       first confirm re-formats any hand-layout in the file (the
       committed registry's one-line `"aliases": ["Garibaldi"]` becomes
       multi-line). That is a cosmetic diff, not data loss -- the
       alternative, preserving hand formatting, means a hand-rolled JSON
       editor, which is a worse trade for a file a human curates by
       reading it. The path is supplied by the caller, not defaulted
       here, for the same reason `gmv_crawler_entity_proposal_queue.py`
       takes no default path.
    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise ValueError(
            f"{entity_type!r} is not a governed entity_type; not writing to "
            f"{registry_path}. Valid values are exactly the 12 in "
            "gmv_core/migration_sql/010_entity_registry.sql."
        )
    if not canonical_name.strip():
        raise ValueError(
            f"canonical_name is blank; not writing to {registry_path}. An entry "
            "with no name resolves to nothing and would be invisible forever."
        )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    claimants = _entries_claiming_name(canonical_name, registry)
    if len(claimants) == 1:
        raise ValueError(
            f"{canonical_name!r} already resolves to {claimants[0]['gmv_id']!r} in "
            f"{registry_path} -- no new entity written. If this is a name variant "
            "of that entity, use confirm_entity_alias() instead."
        )
    if len(claimants) > 1:
        raise ValueError(
            f"{canonical_name!r} is already claimed by {len(claimants)} entities in "
            f"{registry_path} -- {sorted(c['gmv_id'] for c in claimants)!r} -- so "
            "resolve_entity_gmv_id() answers None for it (the documented "
            "homonym outcome). Writing a new entity here would add a third "
            "record to a name two entities already own. Resolve the homonym "
            "first: use confirm_entity_alias() to attach the variant to the "
            "right one, or fix the registry by hand."
        )
    gmv_id = next_sequential_gmv_id(registry)
    registry["entities"].append(
        {
            "gmv_id": gmv_id,
            "entity_type": entity_type,
            "canonical_name": canonical_name,
            "aliases": [],
            "status": "ACTIVE",
        }
    )
    registry_path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return gmv_id


def confirm_entity_alias(gmv_id: str, new_alias: str, registry_path: Path) -> str:
    """Reads `registry_path`, finds the entity with this EXACT `gmv_id`
    (raising a clear error if none exists -- never a silent no-op),
    appends `new_alias` to its `aliases` list if not already present (a
    no-op with a clear return message if it is already there, mirroring
    `confirm_institution()`'s "era gia' nell'elenco" case), writes the
    file back. Returns a short human-readable confirmation string.

    The counterpart to `confirm_new_entity()`, and deliberately a
    SEPARATE function rather than a flag on it: "this is a new entity"
    and "this is another name for GMV-x" are two different editorial
    facts, and the only one that can safely link two strings is the one
    the human explicitly chose.

    1. **The `gmv_id` match is EXACT, and a miss raises.** Not
       case-folded, not prefix-matched, not "the only entity", not
       "created if absent". A near-miss id writing an alias onto the
       wrong entity is a silent corruption of a governance file, and an
       auto-create here would be the auto-registration the whole
       human-confirmed half of this module exists to prevent. The error
       message lists the ids actually present, because the realistic
       failure is a human typing `GMV-00001` instead of `GMV-000001`.
    2. **Alias membership is EXACT string membership, no normalization**
       -- the same case-sensitive, no-normalization rule migration 010's
       own comment states for `UNIQUE(entity_gmv_id, alias)`, and for
       the same reason: that schema deliberately keeps "F. Garibaldi"
       and "f. garibaldi" as distinct rows. Note the two normalizations
       are NOT the same, and the gap is intentional: the resolver
       compares with `.strip().lower()`, so an alias added here as
       `" Garibaldi "` WOULD resolve, while an exact-membership check
       here would let both `"Garibaldi"` and `" Garibaldi "` be stored.
       That redundancy is harmless (same entity, so no ambiguity is
       created) and folding it away would mean inventing a
       normalization the SQL comment explicitly defers to the
       application layer without specifying it.
    3. **A blank/whitespace-only alias is rejected**, same reason as
       `confirm_new_entity()`'s blank `canonical_name`: the resolver
       skips empty strings, so it would be an alias that resolves
       nothing.
    4. **It never changes `gmv_id`, `entity_type`, `canonical_name` or
       `status`** -- read-modify-write of the `aliases` list only. An
       alias must never be able to move an entity, since the id is
       required to be "stabile e indipendente dal nome corrente" and
       the audit's Q1 rejection of content-derived ids rests on exactly
       that.
    """
    if not gmv_id.strip():
        raise ValueError(f"gmv_id is blank; nothing to add an alias to ({registry_path}).")
    if not new_alias.strip():
        raise ValueError(f"new_alias is blank; not writing to {registry_path}.")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for entry in registry["entities"]:
        if entry["gmv_id"] != gmv_id:
            continue
        aliases = entry.get("aliases")
        if aliases is None:
            # The READ half of this same module reads aliases with
            # `entry.get("aliases", ())` (see resolve_entity_gmv_id), because
            # the key is OPTIONAL in a hand-curated file -- a human who
            # typed a new entity by hand and left the key out produced a
            # perfectly resolvable record. Indexing it directly here would
            # turn that same hand-curated file into a bare `KeyError:
            # 'aliases'` at the moment a human asked for the one thing they
            # wanted, and it would contradict the read half in the very
            # module that is supposed to agree with itself. So: materialize
            # the empty list the schema's DEFAULT implies, and let the
            # normal append path run. The key is always present in the file
            # we write back, which also means the value stays a list.
            aliases = entry["aliases"] = []
        if new_alias in aliases:
            return f"'{new_alias}' was already an alias of {gmv_id} in {registry_path} -- nothing written."
        aliases.append(new_alias)
        registry_path.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return f"Confirmed: '{new_alias}' added as an alias of {gmv_id} in {registry_path}."
    present = sorted(entry["gmv_id"] for entry in registry["entities"])
    raise ValueError(
        f"No entity with gmv_id {gmv_id!r} in {registry_path} -- nothing written. "
        f"Ids actually present: {present!r}. To register a brand-new entity use "
        "confirm_new_entity(), which mints the next sequential id itself."
    )
