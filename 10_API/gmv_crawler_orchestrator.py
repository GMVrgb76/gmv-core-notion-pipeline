#!/usr/bin/env python3
"""GMV Crawler — single entry point wiring EXTRACT CANDIDATES -> BUILD ATOMS
(ATTRIBUTE, Task 6, and RELATION/located_at, Task 10) into one call.

Before this module, running the real pipeline on one document required
four separate manual script invocations (extract_candidates(), then
build_atoms(), then build_relation_atoms() on the propositions build_atoms()
couldn't use, then manually routing the leftovers to the two review
queues) -- verified this way, by hand, multiple times this session on
the real Federico Garibaldi biography. This module is exactly that
sequence, made callable once, nothing new invented: it composes four
already-verified functions (extract_candidates, build_atoms,
build_relation_atoms, and the two queue writers left to the caller, see
below) in the one order that avoids double-processing a proposition.

The one real design point, not obvious from any single function's own
docs: `build_atoms()` (Task 6) and `build_relation_atoms()` (Task 10)
both accept the SAME kind of input (`CandidateProposition`), but check
against DIFFERENT vocabularies (the registry's ATTRIBUTE predicates vs.
the curated RELATION text mapping) -- calling both on the FULL
proposition list would double-count every proposition neither one
builds (it would appear in both rejected tuples). This module runs
`build_atoms()` first, then runs `build_relation_atoms()` ONLY on the
propositions `build_atoms()` rejected (by identity, via
`extraction_claim_ref`, never by re-deriving from raw text) -- so every
proposition produces exactly one atom or exactly one final rejection,
never two.

Explicit non-goals, matching every task brief so far: does not write
to the two review queues itself (Task 7's `append_rejected()`/Task 9's
`append_entity_proposals()` remain the caller's explicit choice, same
decoupling principle every task brief in this project has kept); does
not persist anything; does not loop over multiple documents (one
`ExtractionDocument` per call, matching `extract_candidates()`'s own
one-document shape); does not touch any existing module.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_atom_validator import AtomCandidate  # noqa: E402 -- reused, not reimplemented
from gmv_crawler_atom_builder import (  # noqa: E402 -- reused, not reimplemented
    RejectedCandidate,
    build_atoms,
)
from gmv_crawler_candidate_extractor import (  # noqa: E402 -- reused, not reimplemented
    DEFAULT_API_STYLE,
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    CandidateEntity,
    extract_candidates,
)
from gmv_crawler_contract_extractor import (  # noqa: E402 -- reused, not reimplemented
    CandidateContractSummary,
    extract_contract_summary,
)
from gmv_crawler_document_classifier import classify_document  # noqa: E402 -- reused, not reimplemented
from gmv_crawler_entity_resolver import EntityTypeProposal  # noqa: E402 -- reused, not reimplemented
from gmv_crawler_extractor import ExtractionDocument  # noqa: E402 -- reused, not reimplemented
from gmv_crawler_price_extractor import (  # noqa: E402 -- reused, not reimplemented
    CandidateArtworkPrice,
    extract_price_entries,
)
from gmv_crawler_relation_atom_builder import (  # noqa: E402 -- reused, not reimplemented
    build_relation_atoms,
)


@dataclass(frozen=True, slots=True)
class ProcessDocumentResult:
    """Everything one document produced, already routed -- no field here
    requires the caller to re-derive which builder produced what.

    `document_type` (added 2026-09-21) is `classify_document()`'s own
    verdict, always populated regardless of which extraction path ran --
    a caller inspecting a stored result later should never have to
    re-classify a document just to know why it went through the price/
    contract/entities-claims path it did.

    `price_entries`/`price_rejected` are populated only for
    `document_type == "price_list"`, and `atoms`/`rejected`/
    `entity_type_proposals_needing_verification`/`all_entities` are empty
    for that document_type -- a price list does not go through
    `extract_candidates()`/`build_atoms()` at all (see `process_document()`'s
    own docstring for why: entities/claims produced one-off,
    unmappable "predicates" per price-list row).

    `contract_summary` is populated only for `document_type == "contract"`,
    ADDITIONALLY to (not instead of) the normal `atoms`/`all_entities`
    fields -- a contract runs through BOTH `extract_candidates()` (reliably
    identifies the contract's parties as entities and its obligations as
    claim text, verified live) AND `extract_contract_summary()`
    (reliably extracts commission_percentage/key_obligations as clean
    structured fields, verified live) because neither alone was as
    complete as both together; see `gmv_crawler_contract_extractor.py`'s
    own module docstring for the live-reproduced finding this is based on."""

    document_type: str
    atoms: tuple[AtomCandidate, ...]
    rejected: tuple[RejectedCandidate, ...]
    entity_type_proposals_needing_verification: tuple[EntityTypeProposal, ...]
    extraction_rejected: tuple[str, ...]
    all_entities: tuple[CandidateEntity, ...]
    price_entries: tuple[CandidateArtworkPrice, ...] = ()
    price_rejected: tuple[str, ...] = ()
    contract_summary: CandidateContractSummary | None = None


def process_document(
    document: ExtractionDocument,
    *,
    evidence_ids: tuple[str, ...],
    now: str,
    endpoint: str = DEFAULT_ENDPOINT,
    model: str = DEFAULT_MODEL,
    max_prompt_chars: int = 24000,
    timeout: int = 60,
    temperature: float | None = 0,
    seed: int | None = 42,
    num_predict: int = 2048,
    num_ctx: int = 8192,
    api_style: str = DEFAULT_API_STYLE,
) -> ProcessDocumentResult:
    """CLASSIFY -> EXTRACT CANDIDATES -> BUILD ATOMS (ATTRIBUTE then RELATION)
    for one document, in the one order that avoids double-processing.

    `classify_document()` (added 2026-09-21) runs FIRST and decides which
    extraction path the rest of this function takes -- see
    `ProcessDocumentResult`'s own docstring for exactly what each
    `document_type` produces. This branch exists because forcing every real
    Area35 document through the entities/claims schema regardless of its
    real type was producing schema-valid but useless one-off "predicates"
    for price lists and contracts (see `gmv_crawler_document_classifier.py`'s
    module docstring for the full audit). `technical_sheet`/`press_release`/
    `invitation`/`certificate`/`other`/`biography` all still fall through to
    the original entities/claims path unchanged -- only `price_list` and
    `contract` have a dedicated schema built so far.

    `api_style` defaults to `DEFAULT_API_STYLE` (currently "chat_template",
    matching `DEFAULT_MODEL` -- see that constant's own comment in
    gmv_crawler_candidate_extractor.py) and is passed straight through to
    `extract_candidates()`/`ollama_extract()`. It only affects candidate
    extraction, not `build_relation_atoms()`'s `classify_entity_types()`
    call below, which uses its own separate request shape.

    `temperature`/`seed` default to `0`/`42` HERE (unlike
    `extract_candidates()`/`ollama_extract()`, which both default to
    `None` -- no behavior change for their other callers). This
    orchestrator is exactly the layer that should hold that opinion: a
    live, reproduced finding this session showed the SAME document
    re-extracted with Ollama's default sampling produces DIFFERENT
    predicate phrasing every call ("was held at" / "was a solo
    exhibition at" / "held the solo exhibition" -- three different
    surface forms of one real fact across three real runs), which
    defeats `crawler_predicate_text_mapping.json`'s exact-text matching
    even when the mapping itself is correct. `temperature=0` with a
    fixed `seed` made two separate live calls on the same text produce
    byte-identical predicate lists (verified before this default was
    set, not assumed). Pass `temperature=None` explicitly to restore
    Ollama's own default sampling if a caller wants that instead.

    `num_predict`/`num_ctx` default to `2048`/`8192` HERE too (matching
    `ollama_extract()`'s own defaults, so still no behavior change for
    existing callers of THAT function -- only for callers of this
    orchestrator that pass higher values explicitly). Both raised by the
    nightly crawler script after a live investigation 2026-09-19 into
    frequent `OLLAMA_OUTPUT_TRUNCATED` failures: the FIRST hypothesis
    (num_predict too low) was tested and found WRONG for the actual
    failing documents -- raising num_predict alone (2048 -> 4096) on a
    real 25KB document that had failed live changed nothing (identical
    `eval_count`, still `done_reason: "length"`), because
    `prompt_eval_count + eval_count` was already hitting `num_ctx`
    itself (6331 prompt tokens + 1861 response tokens = 8192, the
    context ceiling, not the predict ceiling -- a long real document's
    prompt alone was consuming most of the budget). Doubling num_ctx to
    16384 (with num_predict raised to 8192 to match) let that same
    document complete normally: `done_reason: "stop"`, 37 entities, 9
    claims, valid JSON. A short (731-char) document was unaffected
    either way -- it already completed correctly with the original
    2048/8192 defaults (`done_reason: "stop"`, full 8-claim extraction)
    since its prompt was small enough to leave room.

    1. `extract_candidates(document, ...)` -- real LLM call, real
       envelope/error behavior unchanged (a network/LLM failure
       propagates here exactly as it always has, never swallowed).
    2. `build_atoms(propositions, now=now)` -- Task 6, ATTRIBUTE-only.
    3. Every proposition `build_atoms()` rejected (matched by
       `extraction_claim_ref`, the one field `RejectedCandidate`
       reliably carries back to its source proposition) is retried
       through `build_relation_atoms()` (Task 10, `located_at` only) --
       NOT the full proposition list again, so nothing is processed by
       both builders.
    4. `atoms` = every ATTRIBUTE atom plus every RELATION atom built.
       `rejected` = ONLY `build_relation_atoms()`'s final rejections
       (a proposition `build_atoms()` accepted never reaches step 3, so
       it can never appear here; one that `build_relation_atoms()`
       also rejects appears exactly once, not twice).
       `entity_type_proposals_needing_verification` = the
       `object_type_proposal` of every `BuiltRelationAtom` where
       `needs_verification` is True (ATTRIBUTE atoms carry no entity
       type proposal at all -- `object_type` is always the literal
       `"integer"`, nothing to verify).
       `extraction_rejected` = `extract_candidates()`'s own third
       return value verbatim (malformed-candidate strings, a different
       shape than `RejectedCandidate` -- kept separate, never merged
       into `rejected`, since it describes a different stage's
       failures with a different contract).
    """
    classification = classify_document(document.text, endpoint=endpoint, model=model, timeout=timeout)
    document_type = classification["document_type"]

    if document_type == "price_list":
        price_entries, price_rejected = extract_price_entries(
            document.text, source_id=document.source_id, evidence_ids=evidence_ids,
            endpoint=endpoint, model=model, timeout=timeout,
            temperature=temperature, seed=seed, num_predict=num_predict, num_ctx=num_ctx,
        )
        return ProcessDocumentResult(
            document_type=document_type,
            atoms=(), rejected=(), entity_type_proposals_needing_verification=(),
            extraction_rejected=(), all_entities=(),
            price_entries=price_entries, price_rejected=price_rejected,
        )

    entities, propositions, extraction_rejected = extract_candidates(
        document,
        evidence_ids=evidence_ids,
        endpoint=endpoint,
        model=model,
        max_prompt_chars=max_prompt_chars,
        timeout=timeout,
        temperature=temperature,
        seed=seed,
        num_predict=num_predict,
        num_ctx=num_ctx,
        api_style=api_style,
    )

    attr_atoms, attr_rejected = build_atoms(propositions, now=now)

    rejected_refs = {rejected.extraction_claim_ref for rejected in attr_rejected}
    leftover_propositions = tuple(
        proposition for proposition in propositions
        if proposition.extraction_claim_ref in rejected_refs
    )

    if leftover_propositions:
        rel_built, rel_rejected = build_relation_atoms(
            leftover_propositions, entities, now=now,
            endpoint=endpoint, model=model, timeout=timeout,
            temperature=temperature, seed=seed,
        )
    else:
        # Nothing left for the RELATION builder -- skip the call entirely
        # rather than invoking it on an empty batch: avoids a pointless
        # function call and keeps this branch free of any chance of an
        # unexpected classify_entity_types() call when there is
        # structurally nothing that could trigger one.
        rel_built, rel_rejected = (), ()

    atoms = attr_atoms + tuple(built.atom for built in rel_built)
    proposals_needing_verification = tuple(
        built.object_type_proposal for built in rel_built
        if built.object_type_proposal.needs_verification
    )

    contract_summary = None
    if document_type == "contract":
        contract_summary = extract_contract_summary(
            document.text, source_id=document.source_id, evidence_ids=evidence_ids,
            endpoint=endpoint, model=model, max_prompt_chars=max_prompt_chars, timeout=timeout,
            temperature=temperature, seed=seed, num_predict=num_predict, num_ctx=num_ctx,
        )

    return ProcessDocumentResult(
        document_type=document_type,
        atoms=atoms,
        rejected=rel_rejected,
        entity_type_proposals_needing_verification=proposals_needing_verification,
        extraction_rejected=extraction_rejected,
        all_entities=entities,
        contract_summary=contract_summary,
    )
