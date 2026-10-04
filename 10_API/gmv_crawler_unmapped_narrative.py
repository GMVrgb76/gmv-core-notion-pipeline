#!/usr/bin/env python3
"""GMV Crawler — PUBLIC narrative from propositions NO governed predicate fits.

`gmv_crawler_public_projector.py` (step 15) computes
`gmv_monad_materializer.MonadDocument.public_text` from ATOMS, and its
own module docstring fixes that contract in writing: "AtomCandidate
sequence (+ optional SOURCES manifest) -> the PUBLIC section text", with
every one of GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §14's exclusion rules mapped
onto an ATOM field (STATUS, VISIBILITY, SOURCE, PREDICATE_CLASS). This
module is a deliberate, separate input class: a sequence of
`RejectedCandidate` (`gmv_crawler_atom_builder.py`, BUILD ATOMS) ->
the PUBLIC section text. It exists because a real document's sentences
that no governed predicate fits are real, existing text that
`project_public()` structurally cannot reach: there is no ATOM behind
them, so there is nothing for that module's selection logic to select.

**Why a new module and not a sibling function inside
`gmv_crawler_public_projector.py`** (a real decision, taken after reading
that file in full, not a stylistic preference):

1. That module's stated scope is atoms -> PUBLIC. Its entire gate chain
   (`select_public_atoms()`) is a function of `AtomCandidate` fields.
   A `RejectedCandidate` has no STATUS, no VISIBILITY, no PREDICATE_CLASS
   and no OBJECT_TYPE, so NONE of that module's gates has anything to
   read here. Placing this beside it would imply a shared contract that
   does not exist.
2. `project_public()`'s own docstring promises "the exact string a caller
   should pass as `MonadDocument.public_text`". Two functions in one
   module producing two different kinds of `public_text`, one of them
   carrying no epistemic gate at all, would make that promise ambiguous
   for every future reader -- and the whole reason this is a separate
   module is so nobody has to guess which guarantee covers which input.
3. That module's "Reuse, verified by import line in this file" section is
   an explicit claim-by-claim inventory of its dependencies. Importing
   `RejectedCandidate` (which lives in the BUILD ATOMS module) into it
   would add a real dependency edge from step 15 to the atom builder for
   no functional reason, and would falsify that inventory.

`project_public()` itself is NOT modified, and neither is
`gmv_monad_materializer.py` -- `materialize_monad()` already takes
`public_text` as a plain caller-supplied string and writes it verbatim
("it does not compute or validate PUBLIC content", its own docstring),
which is exactly the property this module needs and the reason no change
there was required.

## What this module does NOT do, stated before anything else

- **No LLM call, no paraphrase, no synthesis, no summarization.** The
  text is assembled by concatenation and exact-string deduplication
  only. `compose_unmapped_narrative()` is a pure function: no I/O, no
  registry read, no network, no clock.
- **No new ontology predicate.** The governed vocabularies
  (`00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json`,
  `00_CONFIG/crawler_predicate_text_mapping.json`) are NOT touched, and
  this module reads neither. Registering a predicate to cover
  practice-description-shaped text was investigated on real data (task
  brief `opencode_task_28.md`) and rejected there: 9 of 129 real
  propositions were practice-description-shaped and all 9 were DISTINCT
  raw texts with zero repetition, so no single governed predicate could
  be grounded in them. This module routes that text instead of claiming
  governance over it.
- **No eligibility widening.** Only `PREDICATE_TEXT_NOT_MAPPED`
  rejections are eligible. The other real reason codes are a different
  kind of problem and are excluded on purpose: `UNKNOWN_PREDICATE` and
  `PREDICATE_NOT_YET_SUPPORTED` (BUILD ATOMS' first stage -- and, per
  `gmv_crawler_orchestrator.py`'s documented contract, NOT present in
  the `rejected` tuple a caller normally has) and
  `OBJECT_NOT_LINKED_TO_KNOWN_ENTITY` / `VALIDATION_FAILED` (a real
  governed predicate whose atom failed to build or whose object could
  not be linked to an entity). Publishing the last two as if they were
  fine prose would misrepresent a validation failure as
  unvalidated-but-unobjectionable text, which is the opposite of what
  §14 is for.

## THE HONEST LIMITATION, stated rather than buried

§14 requires every PUBLIC sentence to be "traceable to atom(s)/source(s)
compatible with publication" (quoted from
`gmv_crawler_public_projector.py`'s own docstring, which read that rule
off the frozen spec). This module satisfies the provenance half and NOT
the compatibility half, and the difference is not cosmetic:

- **Provenance: real.** Every emitted sentence is the verbatim
  `evidence_excerpt` of a real `RejectedCandidate`, which carries the
  real `source_id` of the document it came from. The text is traceable to
  a real source.
- **Compatibility: absent, by construction.** No atom was built for
  these propositions -- that is *why* they are rejected -- so there is no
  STATUS (never VALID), no VISIBILITY (never PUBLIC), no
  ASSERTED_BY/CONFIDENCE, and no `validate_atom()` ever ran on them.
  None of step 15's four mechanical gates can be evaluated, because
  every one of them reads an ATOM field that does not exist here. §14's
  remaining exclusions ("fatti INTERNAL", "claim UNVERIFIED non
  attribuite", "scheduled events presented as occurred", "bozze
  contrattuali e dati economici privati") are equally unevaluable: this
  module cannot tell whether a given practice-description sentence
  mentions an internal figure, an unverified attribution, a future
  event, or a private contract term. A caller wiring this text into a
  `# PUBLIC` section of a materialized Monad is making an editorial
  decision that no code in this repository checks, and the reviewing
  human should know that when they read it.
- **"Verbatim" here means "we do not transform it", NOT "it is
  byte-identical to the source document".** The excerpt is the
  extractor's own rendering of a passage. `gmv_crawler_candidate_
  extractor.py`'s `DEFAULT_MODEL` comment records a MEASURED rate of
  `evidence_excerpt` values that are not a verbatim substring of the
  source text: ~4.5% for `numind/nuextract3:q4_k_m` and ~15.7% for
  `gemma4:12b`, across 4 real Area35 documents. This module does not
  increase that rate and does not hide it; a caller who needs a
  guaranteed-verbatim sentence must re-derive it from the source
  document, which this module has no access to by design.

## Determinism and order

Output order is FIRST-APPEARANCE order of the input sequence, not a
sort. This is a deliberate divergence from `render_public_text()`,
which sorts by `atom_id` for determinism, and the reason is that the two
inputs are different in kind: an `atom_id` is a stable identifier whose
sort order carries no meaning, whereas the input sequence here is
already the document/extraction order -- `extract_candidates()` emits
propositions in chunk-then-model-output order and
`build_relation_atoms()` appends rejections while iterating that same
sequence in order, so "the order the caller passed" IS a real,
reproducible document order, not an arbitrary collection order. Sorting
by `extraction_claim_ref` (the only other unique key available) would
order paragraphs by a sha-derived suffix, which is exactly the
unreadable output this module exists to avoid.

## Deduplication, and why it happens AFTER the eligibility filter

Deduplication is by EXACT string equality on the `evidence_excerpt` value
as stored, and never case-folding: two sentences differing only in
capitalization are two distinct sentences, and collapsing them would be
fuzzy matching, which every exact-match function in this subsystem
refuses to do (`resolve_entity_gmv_id()` and `_link_object_to_entity()`
are the in-repo precedents for exact-only comparison).

The stored value is compared AND emitted unmodified. `.strip()` is used
for exactly one thing -- deciding whether a row carries any text at all
-- and never to build the paragraph. This is deliberate, and it is a
narrowing of an earlier draft of this file that did strip before both
steps. The reasoning, since "strip-then-compare" has real precedent here
and was not chosen by accident:

- The task brief this module was written against asks for "verbatim only"
  and for dedup "by exact string equality". Both point the same way, and
  the difference between the two readings is whether this module is
  allowed to rewrite the string it publishes.
- The in-repo precedent for `.strip()`-then-compare is
  `resolve_entity_gmv_id()`, whose own docstring gives the reason it
  normalizes: a registry name must match despite a model spelling it
  `Garibaldi, Federico`. That reason does not transfer to a quoted
  passage. Here the input is the extractor's own rendering of a
  sentence, and normalizing it would mean publishing a string that is not
  the one on the record.
- **Measured on the real document this was built for**, stripping changed
  nothing: all 9 real `evidence_excerpt` values from the live Garibaldi
  run are already free of leading/trailing whitespace, so the rendered
  `# PUBLIC` is byte-identical under either reading. The stricter reading
  therefore costs nothing that is actually demonstrated, and it leaves
  this function with zero interpretation of its input.

The consequence, stated rather than discovered later: two rows quoting
the same sentence with different incidental whitespace are NOT collapsed,
because they are not the same string. They would render as two
paragraphs differing only in invisible characters. No real Garibaldi row
does this. If it ever happens at scale, the fix belongs in the producer
that emits `evidence_excerpt`, not in a publisher-side normalization
that would make the published text differ from the recorded one.

The order of operations is load-bearing and is pinned by a test: filter
by `reason_code` FIRST, then deduplicate. Dedup-first would let an
ineligible row's excerpt claim the slot and its eligible twin be
dropped, i.e. a `VALIDATION_FAILED` row could suppress the text of the
`PREDICATE_TEXT_NOT_MAPPED` row that shares it. Filter-first makes the
output a function of the eligible rows only.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_crawler_atom_builder import RejectedCandidate  # noqa: E402 -- reused, not reimplemented

#: The one `RejectedCandidate.reason_code` this module will read, taken
#: verbatim from what `gmv_crawler_relation_atom_builder.build_relation_
#: atoms()` actually WRITES on that field (its pass-1 `predicate_id is
#: None` branch). It is spelled out as a named constant rather than
#: inlined because every other occurrence of this string in the
#: repository is a bare literal with no shared home; the accompanying
#: test executes the real producer with a real unmapped predicate and
#: asserts the value it really returns equals this one, which is the
#: grounding discipline GMV_CRAWLER_HANDOFF.md's process-improvement
#: item 7 asks for (name the exact field, then verify the cited
#: precedent populates THAT field -- not merely that the string appears
#: somewhere in the right file). That producer call needs no network:
#: an unmapped predicate is rejected in pass 1, before
#: `classify_entity_types()` is ever reached.
UNMAPPED_PREDICATE_REASON_CODE = "PREDICATE_TEXT_NOT_MAPPED"

#: Paragraph separator. A blank line, not a newline and not a bullet:
#: `render_monad_markdown()` writes `public_text` verbatim between
#: `# PUBLIC` and `# ATOMS`, so the separator is the only structure the
#: reader gets. A blank line keeps each excerpt visually its own
#: paragraph; a single newline would run them together into one
#: unreadable block, and a bullet marker would add a claim this module
#: cannot make (that these are a list of items, i.e. governed facts
#: rather than prose).
PARAGRAPH_SEPARATOR = "\n\n"


def compose_unmapped_narrative(rejected: Sequence[RejectedCandidate]) -> str:
    """`PREDICATE_TEXT_NOT_MAPPED` rejections -> one PUBLIC-ready string.

    Filters `rejected` to rows whose `reason_code` is exactly
    `UNMAPPED_PREDICATE_REASON_CODE`, takes each one's
    `evidence_excerpt` exactly as stored, drops the rows that carry no
    characters at all, collapses exact duplicates to their first
    occurrence, and joins what is left with `PARAGRAPH_SEPARATOR`.

    Empty input, or input with no eligible row, returns `""` -- never
    an error and never an invented placeholder sentence. That matches
    `render_public_text()`'s own stated behavior for the no-eligible-
    atom case, so a caller can pass either module's output to
    `MonadDocument.public_text` without special-casing "nothing found".

    A row whose `evidence_excerpt` has no non-whitespace character is
    dropped rather than emitted as an empty paragraph. That case is
    genuinely constructible: `CandidateProposition.__post_init__` rejects
    only a FALSY excerpt, so a whitespace-only one builds fine, and
    `RejectedCandidate` has no `__post_init__` at all, so an empty-string
    one is constructible too. Such a row carries no sentence to route,
    and keeping it would put a blank line where content was expected --
    a reader could not tell it from a rendering bug. The emptiness test
    is the ONLY place `.strip()` appears; the emitted paragraph is the
    stored value itself. See the module docstring's deduplication section
    for why that distinction is deliberate.
    """
    paragraphs: list[str] = []
    seen: set[str] = set()
    for candidate in rejected:
        if candidate.reason_code != UNMAPPED_PREDICATE_REASON_CODE:
            continue
        excerpt = candidate.evidence_excerpt
        if not excerpt.strip() or excerpt in seen:
            continue
        seen.add(excerpt)
        paragraphs.append(excerpt)
    return PARAGRAPH_SEPARATOR.join(paragraphs)