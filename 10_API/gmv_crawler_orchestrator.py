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
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    CandidateEntity,
    extract_candidates,
)
from gmv_crawler_entity_resolver import EntityTypeProposal  # noqa: E402 -- reused, not reimplemented
from gmv_crawler_extractor import ExtractionDocument  # noqa: E402 -- reused, not reimplemented
from gmv_crawler_relation_atom_builder import (  # noqa: E402 -- reused, not reimplemented
    build_relation_atoms,
)


@dataclass(frozen=True, slots=True)
class ProcessDocumentResult:
    """Everything one document produced, already routed -- no field here
    requires the caller to re-derive which builder produced what."""

    atoms: tuple[AtomCandidate, ...]
    rejected: tuple[RejectedCandidate, ...]
    entity_type_proposals_needing_verification: tuple[EntityTypeProposal, ...]
    extraction_rejected: tuple[str, ...]
    all_entities: tuple[CandidateEntity, ...]


def process_document(
    document: ExtractionDocument,
    *,
    evidence_ids: tuple[str, ...],
    now: str,
    endpoint: str = DEFAULT_ENDPOINT,
    model: str = DEFAULT_MODEL,
    max_prompt_chars: int = 24000,
    timeout: int = 60,
) -> ProcessDocumentResult:
    """EXTRACT CANDIDATES -> BUILD ATOMS (ATTRIBUTE then RELATION) for one
    document, in the one order that avoids double-processing.

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
    entities, propositions, extraction_rejected = extract_candidates(
        document,
        evidence_ids=evidence_ids,
        endpoint=endpoint,
        model=model,
        max_prompt_chars=max_prompt_chars,
        timeout=timeout,
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

    return ProcessDocumentResult(
        atoms=atoms,
        rejected=rel_rejected,
        entity_type_proposals_needing_verification=proposals_needing_verification,
        extraction_rejected=extraction_rejected,
        all_entities=entities,
    )
