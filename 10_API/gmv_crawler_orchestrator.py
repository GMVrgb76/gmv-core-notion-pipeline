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

The identity question joined the type question here on 2026-09-26, in
the same shape and under the same rules: `ProcessDocumentResult` gained
`entity_identity_proposals` (the IDENTITY counterpart of
`entity_type_proposals_needing_verification`, built by
`propose_entity_identity()` over a read-only load of the real
00_CONFIG/gmv_entity_registry.json) and this module still writes to no
queue and still touches no governance file. Two consequences of that
naming worth stating rather than leaving to be discovered:
`entity_identity_proposals` is NOT the type proposals' sibling in any
functional sense -- it is produced from `all_entities` plus the subjects
of WORK-domain propositions, and it decides nothing about any atom; and
nothing here ever calls `confirm_new_entity()`/`confirm_entity_alias()`,
the only two
functions in the repository that write the registry, because this module
runs unattended. The one thing this addition did change in practice: a
name a human confirms mid-run is visible to the NEXT document of the same
run, because the registry is re-read per document rather than cached
(`_load_entity_registry()`'s own docstring gives the reasoning).

Two later additions, both 2026-09-27 and both strictly additive to the
same result object -- never a second field, never a second queue, never a
new dataclass:

- **The "technique, WxH cm" caption rescue** (Parts A/B of the task brief
  `opencode_task_17.md`), via
  `gmv_crawler_caption_predicate_splitter.split_medium_dimensions_captions()`:
  the five real claims in the live rejection queue whose `object_raw` is
  a pure dimension expression become two governed ATTRIBUTE propositions
  each (`medium` = the raw predicate text verbatim, `dimensions` = the
  dimension text verbatim) and are built through the UNMODIFIED
  `build_atoms()`. A rescued claim is then withheld from
  `build_relation_atoms()` so it is not logged a second time as
  `PREDICATE_TEXT_NOT_MAPPED` -- a reason that no longer describes it.
- **WORK-subject identity proposals** (Part C of the same brief): the
  subject of every proposition whose predicate resolves, through the real
  ontology registry, to a `domain == ["WORK"]` predicate becomes an
  `EntityIdentityProposal` carrying `suggested_entity_type="WORK"`. That
  field existed precisely to carry a non-empty type and was dead until
  this: every proposal produced before it was `""`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_atom_validator import (  # noqa: E402 -- reused, not reimplemented
    AtomCandidate,
    _known_predicates,
    _load_ontology_registry,
)
from gmv_crawler_atom_builder import (  # noqa: E402 -- reused, not reimplemented
    RejectedCandidate,
    build_atoms,
)
from gmv_crawler_caption_predicate_splitter import (  # noqa: E402 -- reused, not reimplemented
    _base_claim_ref,
    split_medium_dimensions_captions,
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
from gmv_crawler_entity_resolver import (  # noqa: E402 -- reused, not reimplemented
    EntityIdentityProposal,
    EntityTypeProposal,
    _forma,
    _is_known_country,
    _load_entity_registry,
    _load_known_places,
    propose_entity_identity,
)
from gmv_crawler_extractor import ExtractionDocument  # noqa: E402 -- reused, not reimplemented
from gmv_evidence_pipeline import EvidenceError, OllamaResponseError  # noqa: E402 -- reused, not reimplemented
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
    own module docstring for the live-reproduced finding this is based on.

    `entity_identity_proposals` (added 2026-09-26) is the IDENTITY half of
    what `entity_type_proposals_needing_verification` is for the type
    question: one `EntityIdentityProposal` per extracted entity name that
    `resolve_entity_gmv_id()` could NOT map to exactly one `gmv_id` in the
    real 00_CONFIG/gmv_entity_registry.json -- the same
    "a human decides, never the pipeline" contract, over a different file
    and a different queue. It is `()` for `document_type == "price_list"`
    (that branch returns before `extract_candidates()` ever runs, so there
    is no entity to propose anything about), and it is orthogonal to
    everything else here: building it changes no atom, rejects no
    proposition and consumes no model call, and the registry is only ever
    READ. `suggested_entity_type` is `""` on a proposal produced from a
    `CandidateEntity` -- type classification stays `build_relation_atoms()`'s
    job, scoped to relation objects, and joining that classification in
    here stays a separate, deliberate decision (see
    `process_document()`'s own docstring) -- and `"WORK"` on one produced
    from a WORK-domain proposition's subject (2026-09-27, `opencode_task_17.md`
    Part C), which is a fact read from the ontology registry's declared
    `domain`, not a model inference. Two sources, one tuple, one queue, one
    human gate: `gmv_crawler_entity_identity_proposal_queue.py` never has to
    know which produced a given row."""

    document_type: str
    atoms: tuple[AtomCandidate, ...]
    rejected: tuple[RejectedCandidate, ...]
    entity_type_proposals_needing_verification: tuple[EntityTypeProposal, ...]
    extraction_rejected: tuple[str, ...]
    all_entities: tuple[CandidateEntity, ...]
    price_entries: tuple[CandidateArtworkPrice, ...] = ()
    price_rejected: tuple[str, ...] = ()
    contract_summary: CandidateContractSummary | None = None
    entity_identity_proposals: tuple[EntityIdentityProposal, ...] = ()


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
    2-bis. The "technique, WxH cm" caption rescue (2026-09-27,
       `opencode_task_17.md`): every `build_atoms()` rejection whose
       `reason_code` is `UNKNOWN_PREDICATE` and whose `object_raw` is a
       pure dimension expression is turned, by
       `split_medium_dimensions_captions()`, into two more
       `CandidateProposition`s that go through the UNMODIFIED
       `build_atoms()` again. A claim rescued this way is then EXCLUDED
       from step 3's input, so it is no longer re-reported as
       `PREDICATE_TEXT_NOT_MAPPED` by `build_relation_atoms()` -- a
       reason that no longer describes it. Every claim NOT rescued keeps
       step 3's path byte-for-byte, which is what keeps step 4's
       "`rejected` is ONLY `build_relation_atoms()`'s final rejections"
       contract true for all of them; verified by a real test, not by
       inspection.
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
       also rejects appears exactly once, not twice; one rescued by
       step 2-bis never reaches step 3 at all). The parenthetical
       "`object_type` is always the literal `"integer"`" above is
       PRE-2026-09-27 wording and is now narrower than the truth: since
       Task 6 was widened, an ATTRIBUTE atom's `object_type` is whatever
       the registry's declared `range` says for that predicate
       (`"integer"` or `"string"`), and it is still always a literal, so
       nothing to verify, so still no entity type proposal from it.
       `entity_type_proposals_needing_verification` = the
       `object_type_proposal` of every `BuiltRelationAtom` where
       `needs_verification` is True.
       `extraction_rejected` = `extract_candidates()`'s own third
       return value verbatim (malformed-candidate strings, a different
       shape than `RejectedCandidate` -- kept separate, never merged
       into `rejected`, since it describes a different stage's
       failures with a different contract).
    5. `entity_identity_proposals` has TWO sources, merged into the one
       tuple. (a) 2026-09-26, computed straight after step 1's
       `extract_candidates()` and BEFORE any atom builder, from
       `all_entities` alone: every name the real
       registry cannot resolve to exactly one `gmv_id` becomes one
       `EntityIdentityProposal` carrying the `CandidateEntity`'s own
       `name`/`source_id`/`evidence_excerpt` verbatim. It runs this
       early and unconditionally for a reason worth stating: a name
       that does not resolve is a fact about the DOCUMENT, not about
       the predicates the builders happen to consume, so scoping it to
       atoms would silently drop every entity no atom references --
       which is most of them, since `build_atoms()`'s ATTRIBUTE slice
       and `build_relation_atoms()`'s `located_at` mapping use a small
       fraction of what the extractor returns. (b) 2026-09-27, computed
       after step 2-bis because it needs the propositions that step
       produced: the subject of every proposition whose predicate
       resolves through the real ontology registry to a `domain ==
       ["WORK"]` predicate, with `suggested_entity_type="WORK"`.

       Three deliberate non-behaviours, each a decision rather than an
       omission:

       - **The registry is re-read for every document, never cached**
         and never written. It is a hand-curated file a human can
         legitimately edit between two documents of one run (that is
         its whole maintenance model), and a cached copy would keep
         proposing a name a human just confirmed for the rest of the
         process -- `resolve_entity_gmv_id()`'s own point 7 gives the
         same reasoning for the same file. Stated as a real consequence
         rather than left to be discovered: a MISSING or malformed
         `gmv_entity_registry.json` now raises out of this function for
         every document, exactly as `_load_known_artists()`'s missing
         file already does for `classify_entity_types()`. Swallowing it
         here was considered and rejected -- an unreadable governance
         file that silently yields "no name resolves" would queue a
         proposal for every entity in every document of a run, including
         names a human had already confirmed, which is a far worse
         failure than a loud one. In the real nightly script that
         failure surfaces per file as a logged `processing_failed` and
         the run continues with the next one.
       - **No deduplication, no grouping, no "did you mean".** The
         same raw name extracted twice in one document produces two
         proposals, exactly as the identity queue's own module
         docstring requires; whether those are one real entity is a
         human judgement, and that queue exists so the human is the one
         making it.
        - **No `classify_entity_types()` call, so a MODEL-INFERRED
          `suggested_entity_type` never appears here.** That costs no
          model call on an unattended path (the type question already has
          its own two-source principle, where a roster hit is a fact and a
          model inference is not), and it keeps the two questions from
          acquiring two independent, unreconcilable answers for one
          name. Typing the unresolved names stays
          `build_relation_atoms()`'s scoped job; joining the two is
          deliberately NOT done here. What a WORK-domain proposition's
          subject DOES carry is the literal `"WORK"`, which is a
          different kind of claim: the ontology registry declares that
          predicate's domain IS `["WORK"]`, and reading a declared domain
          is not a classification. It is still not a decision -- nothing
          here confirms anything, and the queue's human gate is
          unchanged.
        - **This only catches a WORK subject whose predicate already
          resolves to a canonical WORK-domain id.** That is, in practice,
          rare naturally-clean LLM output plus whatever the caption
          rescue above produces. It is NOT a "recognize any work title in
          the text" mechanism, and no such mechanism exists in this
          repository; proposing an identity for every unresolvable noun
          phrase would flood the queue with fragments. Stated plainly
          here so the feature is not read as broader than it is.
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
            entity_identity_proposals=(),
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

    registry = _load_entity_registry()
    known_places = _load_known_places()
    # The second, deterministic geography filter (task brief
    # opencode_task_29.md), alongside `known_places` rather than inside
    # it: `area35_known_places.json` is a human-curated FILE and this is
    # ISO 3166-1, so they have different failure modes to reason about and
    # different maintenance (one is edited by a human, the other ships
    # with a pinned dependency). Merging them would make "which roster
    # filtered this?" unanswerable from the file alone, and would force a
    # package upgrade to be diffed against a governance file.
    #
    # Both checks are exact normalized matches, so neither can swallow an
    # institution that merely CONTAINS a country name -- a real name from
    # the corpus, "Biennale di Venezia, Padiglione Italia", is still
    # proposed. See `_is_known_country()`'s own docstring.
    #
    # Deliberately NOT applied to `all_entities`/atom building: it is an
    # identity-queue filter, exactly like the `known_places` check it
    # sits beside, and a country-named proposition still belongs in the
    # atom/rejection paths on its own merits.
    filtered_entities = tuple(
        entity for entity in entities
        if _forma(entity.name) not in known_places
        and not _is_known_country(entity.name)
    )
    identity_proposals = tuple(
        proposal for proposal in (
            propose_entity_identity(
                entity.name, registry,
                source_id=entity.source_id, evidence_excerpt=entity.evidence_excerpt,
            )
            for entity in filtered_entities
        )
        if proposal is not None
    )

    attr_atoms, attr_rejected = build_atoms(propositions, now=now)

    # The "technique, WxH cm" caption rescue (2026-09-27, opencode task
    # brief opencode_task_17.md). Five real cases in the live
    # rejection_queue.jsonl, all the same shape, all described in
    # gmv_crawler_caption_predicate_splitter.py's own module docstring
    # with the real values. It is a rescue, never a rewrite: the
    # RejectedCandidate rows it consumes stay in `attr_rejected`
    # untouched, and a claim it does not rescue keeps the exact
    # `build_relation_atoms()` path below it already had.
    #
    # The caller filters by reason_code here AND the function re-checks
    # it, so the function's own contract does not depend on every caller
    # remembering (the real UNKNOWN_PREDICATE detail is in the splitter).
    caption_synthetic = split_medium_dimensions_captions(
        tuple(rejected for rejected in attr_rejected if rejected.reason_code == "UNKNOWN_PREDICATE"),
        propositions,
    )
    # Same empty-batch-skip style as build_relation_atoms() below: nothing
    # recognized means no second build_atoms() call at all.
    caption_atoms: tuple[AtomCandidate, ...] = ()
    caption_rejected: tuple[RejectedCandidate, ...] = ()
    if caption_synthetic:
        caption_atoms, caption_rejected = build_atoms(caption_synthetic, now=now)
        attr_atoms = attr_atoms + caption_atoms
    # A rescued claim is dropped from the RELATION builder's input ONLY
    # when every proposition split out of it actually built --
    # `caption_rejected` is expected to be `()` (the synthesized
    # propositions name governed canonical ids and carry real, already
    # validated text), and if it is ever not, the parent claim simply
    # keeps its original unchanged path and is still logged as
    # `PREDICATE_TEXT_NOT_MAPPED` by build_relation_atoms(), which is
    # where a human sees it. Nothing is swallowed and no new
    # ProcessDocumentResult field is invented to carry it. The disclosed
    # consequence of that choice: a claim whose pair split only
    # partially keeps its `medium` (or `dimensions`) atom AND still
    # appears once in `rejected` -- a state reachable only if the
    # registry and this module's own assumptions disagree, which is the
    # signal to investigate, not to paper over.
    rescued_claim_refs = (
        {_base_claim_ref(p.extraction_claim_ref) for p in caption_synthetic}
        - {_base_claim_ref(r.extraction_claim_ref) for r in caption_rejected}
    )

    # WORK-domain subjects, second independent source into the SAME
    # `entity_identity_proposals` tuple (2026-09-27). The predicate is
    # resolved through the real ontology registry's alias/canonical map
    # and its own declared `domain` is read there, never a hardcoded id
    # list: today `edition_size`, `dimensions`, `medium` and
    # `creation_year` declare `domain == ["WORK"]` exactly, while
    # `edition_number` declares `["ARTWORK_INSTANCE"]` and the two
    # RELATION predicates that also accept a WORK subject (`created_by`,
    # `critical_text_by`) declare a MULTI-element domain -- so exact list
    # equality is what keeps all three out, deliberately, with no
    # exclusion list to keep in sync.
    #
    # NOTE the two different registries in this function, easy to confuse:
    # `registry` is the ENTITY registry (gmv_entity_registry.json, what
    # propose_entity_identity() resolves names against), the local
    # `ontology_known` below is the ONTOLOGY registry
    # (GMV_ONTOLOGY_REGISTRY_v0.1.json, what decides a predicate's
    # domain). The first is re-read per document by design (a human
    # edits it mid-run); the second is a governance file this function
    # only ever reads.
    ontology_known = _known_predicates(_load_ontology_registry())
    work_subject_propositions = tuple(
        proposition for proposition in propositions + caption_synthetic
        if (entry := ontology_known.get(proposition.predicate)) is not None
        and entry["domain"] == ["WORK"]
    )
    # No deduplication, exactly like the CandidateEntity loop above: two
    # WORK-domain propositions about the same work (a `dimensions` and a
    # `medium`, which is what the caption rescue produces) yield TWO
    # proposals, and the human reading the identity queue sees "this name
    # appeared N times" by querying on raw_name. Collapsing them here
    # would be this function deciding they are one entity.
    known_places_w = _load_known_places()
    work_subject_propositions_filtered = tuple(
        proposition for proposition in work_subject_propositions
        if _forma(proposition.subject_raw) not in known_places_w
        and not _is_known_country(proposition.subject_raw)
    )
    work_identity_proposals = tuple(
        proposal for proposal in (
            propose_entity_identity(
                proposition.subject_raw, registry,
                source_id=proposition.source_id,
                evidence_excerpt=proposition.evidence_excerpt,
                suggested_entity_type="WORK",
            )
            for proposition in work_subject_propositions_filtered
        )
        if proposal is not None
    )
    identity_proposals = identity_proposals + work_identity_proposals

    rejected_refs = {rejected.extraction_claim_ref for rejected in attr_rejected} - rescued_claim_refs
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
        # Best-effort: extract_contract_summary() is deliberately NOT
        # chunked (see its own module docstring -- a contract's terms
        # don't merge sensibly across independent halves), so a long real
        # contract can overflow num_predict in one shot and raise
        # OLLAMA_OUTPUT_TRUNCATED. Live, reproduced 2026-09-23 (nightly
        # crawler run, real Garibaldi "accordo di rappresentanza"): that
        # exact failure was propagating straight out of process_document()
        # and discarding the atoms/entities extract_candidates() had ALREADY
        # extracted successfully just above -- the one enrichment this
        # function treats as optional (the docstring above already says
        # contract_summary complements, not replaces, extract_candidates()'s
        # own coverage of the same contract) was destroying the reliable
        # result. A genuine LLM/network failure here now just leaves
        # contract_summary=None instead of losing everything.
        try:
            contract_summary = extract_contract_summary(
                document.text, source_id=document.source_id, evidence_ids=evidence_ids,
                endpoint=endpoint, model=model, max_prompt_chars=max_prompt_chars, timeout=timeout,
                temperature=temperature, seed=seed, num_predict=num_predict, num_ctx=num_ctx,
            )
        except (OllamaResponseError, EvidenceError):
            contract_summary = None

    return ProcessDocumentResult(
        document_type=document_type,
        atoms=atoms,
        rejected=rel_rejected,
        entity_type_proposals_needing_verification=proposals_needing_verification,
        extraction_rejected=extraction_rejected,
        all_entities=entities,
        contract_summary=contract_summary,
        entity_identity_proposals=identity_proposals,
    )
