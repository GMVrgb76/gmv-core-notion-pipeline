#!/usr/bin/env python3
"""GMV Crawler — Candidate extraction (crawler preplan step 11 / spec v0.2 §10).

EXTRACT CANDIDATES stage (§3): `ExtractionDocument` (step 10) -> raw,
pre-Monad candidates. §10 verbatim: "L'LLM produce solo candidati
(CandidateEntity/Proposition/Relation/Event/Measure), mai la Monade
direttamente. Ogni candidato richiede evidence_id[] obbligatorio -- se
assente, il candidato e' rifiutato."

Grounding, read in full before writing this module (per this session's own
established discipline): `gmv_evidence_pipeline.py::ollama_extract()`
already IS this stage's real, tested, production-used implementation --
it calls Ollama with a structured-output schema (`SEMANTIC_OUTPUT_SCHEMA`)
constraining the model to `{entities: [...], claims: [...]}`, each item
requiring an `evidence_excerpt`. This module wraps `ollama_extract()` by
import rather than reimplementing LLM-calling logic, the same reuse
discipline steps 3/6/7/8/10 already applied.

Two honest gaps against §10's literal text, not fixed here:

1. **Only two candidate shapes exist, not five.** §10 names
   `CandidateEntity/Proposition/Relation/Event/Measure`. The real
   `ollama_extract()` produces a flat `entities`/`claims` split --
   `claims` are raw `(subject_raw, predicate, object_raw)` triples with no
   Relation/Event/Measure sub-typing. That sub-typing requires knowing
   each claim's governed `predicate_class` (IDENTITY/ATTRIBUTE/RELATION/
   EVENT/MEASURE/EPISTEMIC, `GMV_ONTOLOGY_REGISTRY_v0.1.json`, step 2) --
   which in turn requires the raw `predicate` string to already be mapped
   to a registered predicate. That mapping is §3's NORMALIZE PREDICATES
   pipeline stage, which (like SEGMENT/BUILD EVIDENCE before it, already
   flagged as a gap in `gmv_crawler_extractor.py`) has no dedicated
   numbered step in §33's implementation order and has not been built.
   Classifying claims into Relation/Event/Measure/generic-Proposition
   *now* would mean inventing an unfounded heuristic, not implementing a
   real capability -- this module defines only `CandidateEntity` and a
   single generic `CandidateProposition` (§10's catch-all shape),
   deferring true sub-typing to whichever future step actually builds
   NORMALIZE PREDICATES.
2. **The "policy di routing che esclude Big Pickle da provenance/claims/
   Notion" §0 says remains binding here does not exist anywhere in this
   repository or its git history** (grepped: zero hits for "Big Pickle" /
   "big_pickle" in any form). Nothing in this module implements or
   enforces it -- there is nothing real to wrap. Surfaced here rather than
   silently invented or silently dropped; if this policy exists outside
   this repo (config elsewhere, a policy only in Ollama server routing),
   a future session needs to locate it before claiming this module
   honors it.

`DEFAULT_MODEL = "deepseek-coder-v2:16b"` (changed 2026-09-19, twice in
one day). History, not simplified, because each step was a real,
falsified hypothesis: (1) original default `"gemma4:12b"` traced back
to §0's "operational graft" citing a spec benchmark **no session had
ever independently verified**. (2) First empirical test (one real short
CV, this pipeline's own prompt/schema/temperature=0/seed=42):
qwen2.5-coder:7b beat gemma4 on that document (64.7s vs 111.2s, 11
claims vs 8) -- changed the default on that basis. (3) In the very next
real batch run, qwen2.5-coder repeatedly hit `OLLAMA_OUTPUT_TRUNCATED`
on documents gemma4 had handled fine -- traced to a documented Ollama/
llama.cpp bug where Qwen-family models enter a repetition loop during
constrained JSON generation and never terminate on their own (raising
num_ctx/num_predict cannot fix a loop, it just delays hitting the
ceiling). (4) Re-tested gemma4:12b specifically on the document that
had defeated qwen -- gemma4 TIMED OUT on it too (>280s), so it was
never actually a safe fallback either; a similar Ollama repetition-loop
report exists for gemma4:31b on constrained JSON with long free-text
fields (issue ollama/ollama#15502), suggesting the family isn't
inherently safe just because THIS session's first CV test happened not
to trigger it. (5) `deepseek-coder-v2:16b`, tested on both real
documents (the short CV and the one that defeated both other models),
completed both cleanly (`done_reason: "stop"`, no loop) -- the only
model of the three with zero failures across every real document
tested, at the cost of shallower extraction on the easy case (1 claim
vs gemma4's 8 on the CV). Chosen for reliability over completeness: a
document that fails outright yields zero atoms, one that extracts
fewer facts still yields some. `endpoint` defaults to
`http://localhost:11434`, the one real precedent for a default Ollama
endpoint in this repo (`gmv_evidence_pipeline.py`'s own `--endpoint` CLI
default).

`status` on both candidate dataclasses is deliberately **not** validated
against a closed vocabulary. An earlier draft of this module gated it on
membership in `gmv_evidence_pipeline.py`'s `STATUS_PRECEDENCE` list and
raised `ValueError` on anything else -- adversarial review caught that
this contradicts `STATUS_PRECEDENCE`'s own real semantics: its source
comment (`gmv_evidence_pipeline.py`, next to `_better_status()`) states
outright that "the semantic-extraction LLM's `status` field is free text,
not an enum" and that an unrecognized value should lose a ranking
comparison, never raise. Neither `ollama_extract()`'s prompt nor its
`SEMANTIC_OUTPUT_SCHEMA` (`"status": {"type": "string"}`, no `enum`)
constrains the model to a fixed set, so a realistic LLM response
(reproduced during review, e.g. `"DOCUMENTATO"`) previously crashed
`extract_candidates()` for an entire document over one out-of-vocabulary
item in a list comprehension -- destroying every other valid candidate
in the same batch, directly contradicting §10 ("il candidato è
rifiutato", singular, not "il documento"). Fixed: `status` here is only
checked non-empty, matching every other required string field on these
dataclasses. (Distinct in any case from the frozen Monad-level STATUS
enum VALID/UNVERIFIED/DISPUTED/SUPERSEDED/INVALIDATED, which only applies
after BUILD ATOMS -- a Candidate never carries that, per §10's "mai la
Monade direttamente".)

`evidence_id` is a crawler-layer concept (`EvidenceUnit.evidence_id`,
step 4) that `ollama_extract()` itself knows nothing about -- no
BUILD EVIDENCE engine exists yet to segment an `ExtractionDocument` into
real `EvidenceUnit` rows (the same gap `gmv_crawler_extractor.py`
documents for `structural_units`). `extract_candidates()` therefore takes
`evidence_ids` as an explicit, caller-supplied, non-empty tuple applied
uniformly to every candidate produced from one document -- not because
finer-grained per-passage linkage is undesirable, but because building
that linkage now would be inventing the missing SEGMENT/BUILD EVIDENCE
stage, not this one. `extract_document()`'s own `source_hash` parameter
(step 10) established the identical pattern: accept from the caller what
no upstream engine yet produces automatically.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_crawler_extractor import ExtractionDocument  # noqa: E402 -- reused, not reimplemented
from gmv_evidence_pipeline import ollama_extract  # noqa: E402 -- reused, not reimplemented

# `DEFAULT_MODEL = "numind/nuextract3:q4_k_m"` / `DEFAULT_API_STYLE =
# "chat_template"` (changed 2026-09-20, was `"deepseek-coder-v2:16b"` /
# "generate"). Evidence basis, stated plainly because it is NOT the same
# rigor as the qwen/gemma4/deepseek history above: an A/B benchmark on 4
# real Area35 documents from a DIFFERENT artist's archive (Federico
# Garibaldi -- this crawler's own empirical tests so far used a CV and one
# long document, not that corpus), comparing gemma4:12b against
# numind/nuextract3:q4_k_m called correctly (`ollama.com/numind/nuextract3`:
# NuExtract3 only enters its structured-extraction mode via Ollama's
# /api/chat with a "template" role message -- calling it with a flat
# /api/generate prompt, as this file did for every model until now, leaves
# it in a generic, unreliable mode). Result: nuextract3:q4_k_m was 2-3x
# faster and hallucinated less than gemma4:12b (measured as
# evidence_excerpt not being a verbatim substring of the source text: ~4.5%
# vs ~15.7% across the 4 documents) and extracted MORE total entities/
# claims. deepseek-coder-v2:16b was never part of that specific A/B (it was
# the crawler's own prior default, chosen for the different reason of
# zero-failure reliability on ITS two test documents) -- but the real
# nightly batch run of 2026-09-20T01:00:05Z (`01_RUNTIME/gmv_crawler/
# run_log.jsonl`) shows deepseek-coder-v2:16b failed on 100% of documents
# in that run (`OLLAMA_SCHEMA_INVALID`/`OLLAMA_OUTPUT_TRUNCATED`, 0 of
# however-many-were-attempted succeeded, 0 atoms), so it was not actually a
# safe incumbent to preserve by default either.
# THIS HAS NOT YET BEEN VALIDATED AT THIS CRAWLER'S OWN FULL-ROSTER BATCH
# SCALE the way qwen2.5-coder and deepseek-coder-v2 were (see history
# above, and the pattern that a small-sample win doesn't guarantee it) --
# the next real nightly run against the full 46-artist roster is the actual
# test. If it fails at scale the way qwen did, follow the same discipline:
# record the real failure mode here before changing the default again.
DEFAULT_MODEL = "numind/nuextract3:q4_k_m"
DEFAULT_API_STYLE = "chat_template"
DEFAULT_ENDPOINT = "http://localhost:11434"


def _validate_evidence_id(evidence_id: tuple[str, ...]) -> tuple[str, ...]:
    if not evidence_id:
        raise ValueError(
            "evidence_id must not be empty -- spec v0.2 §10: 'Ogni candidato "
            "richiede evidence_id[] obbligatorio -- se assente, il candidato "
            "e' rifiutato'"
        )
    return evidence_id


@dataclass(frozen=True, slots=True)
class CandidateEntity:
    """§10's `CandidateEntity`. Field names/shape taken verbatim from
    `ollama_extract()`'s real output (`name`, `evidence_excerpt`, `status`),
    plus the crawler's own provenance (`source_id`, `evidence_id`)."""

    name: str
    evidence_excerpt: str
    status: str
    source_id: str
    evidence_id: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must not be empty")
        if not self.evidence_excerpt:
            raise ValueError("evidence_excerpt must not be empty")
        if not self.source_id:
            raise ValueError("source_id must not be empty")
        if not self.status:
            raise ValueError("status must not be empty")
        _validate_evidence_id(self.evidence_id)


@dataclass(frozen=True, slots=True)
class CandidateProposition:
    """§10's generic `CandidateProposition` -- the catch-all shape used for
    every raw claim in v1, since Relation/Event/Measure sub-typing is not
    yet possible (see module docstring, gap 1). Field names (`subject_raw`,
    `predicate`, `object_raw`, `evidence_excerpt`) are taken verbatim from
    `ollama_extract()`'s real output, not renamed for cosmetic consistency
    with this module's own `_raw` naming intuition -- reuse fidelity over
    invented uniformity. `truncated_source`/`extraction_claim_ref` are also
    real `ollama_extract()` output fields (unconditionally attached to
    every claim it returns) -- caught by review as a silent provenance
    loss when an earlier draft omitted them from the mapping."""

    subject_raw: str
    predicate: str
    object_raw: str
    evidence_excerpt: str
    status: str
    source_id: str
    evidence_id: tuple[str, ...]
    truncated_source: bool
    extraction_claim_ref: str

    def __post_init__(self) -> None:
        if not self.subject_raw:
            raise ValueError("subject_raw must not be empty")
        if not self.predicate:
            raise ValueError("predicate must not be empty")
        if not self.object_raw:
            raise ValueError("object_raw must not be empty")
        if not self.evidence_excerpt:
            raise ValueError("evidence_excerpt must not be empty")
        if not self.source_id:
            raise ValueError("source_id must not be empty")
        if not self.status:
            raise ValueError("status must not be empty")
        if not self.extraction_claim_ref:
            raise ValueError("extraction_claim_ref must not be empty")
        _validate_evidence_id(self.evidence_id)


def extract_candidates(
    document: ExtractionDocument,
    *,
    evidence_ids: tuple[str, ...],
    endpoint: str = DEFAULT_ENDPOINT,
    model: str = DEFAULT_MODEL,
    max_prompt_chars: int = 24000,
    timeout: int = 60,
    temperature: float | None = None,
    seed: int | None = None,
    num_predict: int = 2048,
    num_ctx: int = 8192,
    api_style: str = DEFAULT_API_STYLE,
) -> tuple[tuple[CandidateEntity, ...], tuple[CandidateProposition, ...], tuple[str, ...]]:
    """Run `ollama_extract()` against `document.text` and map its raw
    output to this module's Candidate dataclasses. `temperature`/`seed`
    are passed straight through to `ollama_extract()` (default None,
    same as there -- no behavior change unless a caller opts in); see
    that function's own docstring for why they exist (a live, reproduced
    finding: re-extracting the same text with default sampling produces
    different predicate phrasing every call, which defeats any exact-
    text predicate mapping downstream). `api_style` defaults to
    `DEFAULT_API_STYLE` ("chat_template", matching `DEFAULT_MODEL` -- see
    that constant's own comment) rather than `ollama_extract()`'s own
    "generate" default, since calling THIS module's default model with
    the wrong api_style would defeat the whole point of choosing it.
    Raises `ValueError` for
    a caller bug (document not successfully extracted, no evidence_ids
    supplied) -- these are not extraction outcomes to report via a status
    field the way `extract_document()` (step 10) reports format failures;
    unlike that stage, this one has no "acceptable failure" outcome of its
    own to model (§10 draws no ExtractionDocument-style status vocabulary
    for candidate extraction) -- an LLM/network failure surfaces as
    whatever `ollama_extract()` itself raises (`EvidenceError`,
    `OllamaResponseError`), not swallowed here.

    A per-item `__post_init__` failure (e.g. an explicit empty-string
    `status` -- legal under `SEMANTIC_OUTPUT_SCHEMA`, which has no
    `minLength` and does not list `status` as `required`) rejects only
    that one candidate, per §10's own wording ("il candidato e'
    rifiutato", singular) -- it does not raise and does not discard the
    rest of the batch. This is a second-round fix: the first draft built
    `entities`/`propositions` via a `tuple(... for ... in ...)`
    comprehension, so one malformed item's `ValueError` propagated out
    and destroyed every other valid candidate from the same document --
    reproduced and confirmed by adversarial re-review after the first
    fix (which only removed the specific trigger that had been
    demonstrated, a closed-vocabulary status check, not this underlying
    all-or-nothing construction pattern). Rejected items are not silently
    dropped -- their reason is returned in `rejected`, not just logged
    nowhere, consistent with this session's general stance against silent
    loss (see Correction 6's `DELETED`-not-`del` fix elsewhere in this
    crawler).
    """
    _validate_evidence_id(evidence_ids)
    if document.status != "SUCCESS":
        raise ValueError(
            f"document must have status SUCCESS to extract candidates from, "
            f"got {document.status!r} (source_id={document.source_id!r})"
        )
    record = {
        "file_id": document.source_id,
        "text": document.text,
        "extraction_status": document.status,
    }
    result = ollama_extract(
        record, endpoint=endpoint, model=model,
        max_prompt_chars=max_prompt_chars, timeout=timeout,
        temperature=temperature, seed=seed, num_predict=num_predict, num_ctx=num_ctx,
        api_style=api_style,
    )
    entities: list[CandidateEntity] = []
    propositions: list[CandidateProposition] = []
    rejected: list[str] = []
    for entity in result["entities"]:
        try:
            entities.append(CandidateEntity(
                name=entity["name"],
                evidence_excerpt=entity["evidence_excerpt"],
                status=entity["status"],
                source_id=document.source_id,
                evidence_id=evidence_ids,
            ))
        except ValueError as exc:
            rejected.append(f"entity {entity.get('name', '<unnamed>')!r}: {exc}")
    for claim in result["claims"]:
        try:
            propositions.append(CandidateProposition(
                subject_raw=claim["subject_raw"],
                predicate=claim["predicate"],
                object_raw=claim["object_raw"],
                evidence_excerpt=claim["evidence_excerpt"],
                status=claim["status"],
                source_id=document.source_id,
                evidence_id=evidence_ids,
                truncated_source=claim["truncated_source"],
                extraction_claim_ref=claim["extraction_claim_ref"],
            ))
        except ValueError as exc:
            ref = claim.get("extraction_claim_ref", "<no-ref>")
            rejected.append(f"proposition {ref!r}: {exc}")
    return tuple(entities), tuple(propositions), tuple(rejected)
