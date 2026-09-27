#!/usr/bin/env python3
"""GMV Crawler — structural rescue of the "technique, WxH cm" art-catalogue caption.

Pure structural pattern recognition over claims `build_atoms()` already
refused, and nothing else: no I/O, no registry load, no entity resolution,
no queue, no governance read or write, no network. Scope is the same
narrow one `gmv_crawler_relation_atom_builder._link_object_to_entity()` has
for its own purely structural job.

**Why this exists, in real data, not hypothetically.** The live
`01_RUNTIME/gmv_crawler/rejection_queue.jsonl` (11700+ real rejected claims
accumulated by real nightly runs) was filtered directly, not assumed:
restricting to `reason_code == "PREDICATE_TEXT_NOT_MAPPED"` (the code
`build_relation_atoms()` logs when a raw predicate text has no entry in
`00_CONFIG/crawler_predicate_text_mapping.json`) and keeping only entries
whose `object_raw`, stripped and split on `,`, has EVERY part fully
matching `_DIMENSION_WITH_UNIT` yields **exactly 5 hits in the whole queue,
zero false positives**, all the same shape -- `subject_raw` is a work
title, `raw_predicate` is a technique/medium description, `object_raw` is a
pure dimension expression:

```
subject_raw='Il bacio'                predicate='smalto, unghie, alluminio e carta su tavola'  object_raw='90 x 60 x 5 cm'
subject_raw='Voodoo children'         predicate='crossage su tavola'                            object_raw='150 x 150 x 5 cm'
subject_raw='Voodoo children'         predicate='arazzo e collage di tessuti su cartoncino'      object_raw='215 x 210 cm'
subject_raw='Nuvole'                  predicate='metallo, legno e acrilico'                      object_raw='175 x 58 cm'
subject_raw='Chi è la mamma del sole' predicate='smalto e acrilico su tavola'                    object_raw='160 x 110 cm'
```

That is a real, recurring art-catalogue caption convention ("technique,
WxH cm"), and the LLM extractor already puts the technique text in
`predicate` and the dimension text in `object_raw` -- it just never
resolves, because the pair is **not a relation**. A `crawler_predicate_
text_mapping.json` entry cannot fix it: the technique text is different
every single time, so there is no repeated exact string to key a mapping
on (contrast "a cura di", which is what that curated file is for). What
the shape actually is, is TWO ATTRIBUTE facts about one subject:
`dimensions = object_raw` and `medium = raw_predicate`, both verbatim.

**The two predicate ids used here are already governed**, registered in
`00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json` by task brief
`opencode_task_16.md` (`medium`/`dimensions`, `predicate_class` ATTRIBUTE,
`domain` `["WORK"]`, `range` `["string"]`). This module therefore invents
no vocabulary and edits no governance file: it recognises a structure and
emits two propositions naming predicates that already exist, which the
unmodified `build_atoms()` then builds through its own unchanged path.

What is deliberately NOT rescued, and why (EIC-12 read as "the less
assertive interpretation", never "guess"):

- **Multi-panel dimension strings** where only the LAST comma-separated
  part carries "cm" (real examples: `'45 x 55, 45 x 60 cm'`,
  `'150 x 100, 166 x 112 cm'`). The strict per-part rule excludes them on
  purpose: accepting them requires deciding whether "cm" governs every
  part or only the last, which is a corpus-reading decision, not a
  mechanical one. Excluded, not missed.
- **`"dimensioni ambientali"` / `"dimensione ambientale"`** (real corpus
  phrase for site-specific work with no fixed measurement). Arguably a
  valid free-text `dimensions` value, but whether it counts as a valid
  value for a CANDIDATE predicate is a content/governance judgement about
  what a governed `dimensions` may contain -- not a pattern match. Left
  for an explicit human decision, not silently decided here.
- **The 3-way compound** `'2014 enamel on paper 150x100 cm'` (real,
  subject `'ASSOLO 002'`, predicate `'present'`): year + medium +
  dimensions in one `object_raw`. Excluded by the same rule (the whole
  string fails to match, and splitting on `,` yields no rescue), which is
  the correct outcome, not a gap in the pattern.
- **`creation_year` from this backlog**: not attempted, and not because of
  this module. No clean isolated "work created in <year>" claim exists in
  the real queue; the closest real cases leave a year inside
  `evidence_excerpt` only ("*Fulmine a ciel notturno -2014 carta,
  dimensioni ambientali"), never isolated into
  `subject_raw`/`predicate`/`object_raw` by the extractor. Extracting it
  would mean parsing the caption's leading "Title - YYYY" convention out
  of `evidence_excerpt` -- an extraction-quality problem of a materially
  different size, out of scope here.

Non-negotiable boundaries, mirrored in the code:

- **Never touches the original rejection accounting.** This function only
  ADDS propositions. It does not re-emit, mutate, drop, or "upgrade" any
  `RejectedCandidate`; the caller decides what to do with the ones this
  function did not consume, and the pre-existing
  `build_relation_atoms()` -> `rejected` path stays exactly as it was for
  every claim not rescued here.
- **Never emits a fact it did not read.** Both objects are copied
  verbatim from the rejected candidate's own fields. Nothing is
  normalized, lower-cased, re-ordered, unit-converted, or expanded --
  "90 x 60 x 5 cm" stays exactly that string, and an unrecognised
  technique description stays exactly the text the LLM produced.
- **Never calls `confirm_new_entity()`/`confirm_entity_alias()`**, and
  never writes anywhere at all.
- **No `creation_year`, no `edition_*`**: the shape rescued is a
  `(medium, dimensions)` caption pair and nothing else. Widening it to
  other predicates is a different recognition rule, to be added on
  purpose.

**One documented deviation from the task brief, on
`CandidateProposition.evidence_id`/`status`/`truncated_source`.** The brief
specified `split_medium_dimensions_captions(rejected)` taking only
`RejectedCandidate`s, and flagged that `RejectedCandidate` carries no
`evidence_id`/`status`/`truncated_source`. Verified against the real code
before deciding anything: `_validate_evidence_id()`
(`gmv_crawler_candidate_extractor.py:168`) raises `ValueError` on an
empty tuple -- spec v0.2 §10, "Ogni candidato richiede evidence_id[]
obbligatorio" -- so `evidence_id=()` is **not** constructible, exactly as
the brief suspected. The real `evidence_id` is not missing, though: it is
lost only because `RejectedCandidate` is a deliberately narrow record, and
the caller still holds the `CandidateProposition` it came from. So the
function takes that second sequence and looks each rejected candidate up by
`extraction_claim_ref` -- the same key the orchestrator's own
`rejected_refs`/`leftover_propositions` computation already uses three
lines below this call site -- and copies all three fields verbatim.

The alternative was a placeholder/sentinel `evidence_id` plus an invented
`status` string. That was rejected: it fabricates an
`EvidenceUnit`-shaped reference that does not exist and an epistemic status
the pipeline never produced, for a value that is one function argument
away. A rejected candidate whose ref is NOT in the supplied propositions
is simply not rescued (no exception, no substitution) -- it keeps its
original, unchanged, already-accounted-for path through
`build_relation_atoms()`.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_crawler_atom_builder import RejectedCandidate  # noqa: E402 -- reused, not reimplemented
from gmv_crawler_candidate_extractor import CandidateProposition  # noqa: E402 -- reused, not reimplemented

#: A pure "<number> [x <number>[ x <number>]] cm" measurement, optionally
#: with a trailing full stop. Applied with `.fullmatch()`, not `.match()`:
#: fullmatch additionally rejects a trailing newline that `$` alone would
#: let through, which is the stricter of the two and the one this module
#: means. Character classes are copied verbatim from the task brief's
#: regex and are deliberately NOT tightened -- `\d+[.,]?\d*` accepts
#: "90", "90.5" and "90,5" (both real decimal conventions), which is the
#: brief's stated tolerance, not an oversight here.
_DIMENSION_WITH_UNIT = re.compile(
    r"^\d+[.,]?\d*\s*[xX×]\s*\d+[.,]?\d*(\s*[xX×]\s*\d+[.,]?\d*)?\s*cm\.?$",
    re.IGNORECASE,
)

#: The suffix appended to the ORIGINAL `extraction_claim_ref` for each of
#: the two emitted propositions. Two distinct suffixes, never one shared
#: one, so the two atoms' `atom_id`s (which Task 6 derives from
#: `source_id|extraction_claim_ref`) cannot collide with each other.
MEDIUM_CLAIM_SUFFIX = "#medium"
DIMENSIONS_CLAIM_SUFFIX = "#dimensions"

#: The only `reason_code` this function considers. `build_atom()` returns
#: it when `proposition.predicate` resolves to neither a registered
#: canonical id nor a registered alias -- which is what a free-text
#: technique description like `'smalto, unghie, alluminio e carta su
#: tavola'` always is. The other three reason codes
#: (PREDICATE_NOT_YET_SUPPORTED / OBJECT_NOT_INTEGER / VALIDATION_FAILED)
#: describe a claim that DID resolve to a governed predicate, so the
#: "unmapped raw text" premise this module is built on does not hold for
#: them, and a dimension-shaped object on such a claim means something
#: else entirely (e.g. an `OBJECT_NOT_INTEGER` failure on a `medium`
#: string). Re-checked here even though the caller also filters, so the
#: function's own contract does not depend on every caller remembering.
_CONSIDERED_REASON_CODE = "UNKNOWN_PREDICATE"


def _is_pure_dimension_expression(object_raw: str) -> bool:
    """True only when EVERY comma-separated part of `object_raw` is a
    whole `<number>[ x <number>[ x <number>]] cm` measurement.

    Split on `,` and require all parts, never any part: a real multi-panel
    caption like `'45 x 55, 45 x 60 cm'` carries "cm" on the last part
    only, and reading it as "45 x 55 [cm], 45 x 60 cm" is a decision this
    module refuses to make on the corpus's behalf. A blank or
    whitespace-only `object_raw` strips to `""`, splits to `[""]`, and
    fails to match -- so no empty-part crash is reachable, and
    `CandidateProposition.__post_init__`'s non-empty guarantee is not
    relied upon here.
    """
    parts = [part.strip() for part in object_raw.strip().split(",")]
    return bool(parts) and all(_DIMENSION_WITH_UNIT.fullmatch(part) for part in parts)


def _base_claim_ref(extraction_claim_ref: str) -> str:
    """The original ref a synthetic ref was derived from: the synthetic
    suffix is always the LAST `#`-delimited segment, so `rsplit` on the
    final one is exact even for the real ref shape
    `"{source_id}#{chunk_id}:{index}"` (`extract_candidates()`'s own
    format, which itself contains a `#`).
    """
    return extraction_claim_ref.rsplit("#", 1)[0]


def split_medium_dimensions_captions(
    rejected: Sequence[RejectedCandidate],
    propositions: Sequence[CandidateProposition],
) -> tuple[CandidateProposition, ...]:
    """`RejectedCandidate`s whose shape is a "(medium, dimensions)"
    caption -> two `CandidateProposition`s each, `()` for everything else.

    For each entry of `rejected` (in the given order), and only when ALL
    of the following hold, two propositions are emitted, in this order:

    1. `reason_code == "UNKNOWN_PREDICATE"` (the claim's raw predicate is
       unmapped -- see `_CONSIDERED_REASON_CODE`).
    2. `object_raw` is a pure dimension expression (see
       `_is_pure_dimension_expression`).
    3. `raw_predicate.strip()` and `subject_raw.strip()` are non-empty.
       Not a content judgement: an empty one makes the corresponding
       `CandidateProposition` unconstructible
       (`__post_init__` raises), and a "caption" with no technique text or
       no subject is not the shape this function is for. Such an entry is
       skipped, not rescued into a placeholder.
    4. `extraction_claim_ref` is found in `propositions`, so the three
       fields `RejectedCandidate` does not carry can be copied verbatim
       rather than invented (see the module docstring's deviation note).

    The two emitted propositions, both copying `subject_raw`,
    `source_id` and `evidence_excerpt` VERBATIM from the rejected
    candidate (not from the looked-up proposition -- they are the same
    value, and the rejected candidate is the record of what was actually
    refused):

    - `predicate="medium"`, `object_raw=<raw_predicate verbatim>`,
      `extraction_claim_ref=f"{original}{MEDIUM_CLAIM_SUFFIX}"`
    - `predicate="dimensions"`, `object_raw=<object_raw verbatim>`,
      `extraction_claim_ref=f"{original}{DIMENSIONS_CLAIM_SUFFIX}"`

    `status`/`evidence_id`/`truncated_source` come from the matched
    original proposition, verbatim. Both `predicate` values are governed
    canonical ids, so feeding the result to the unmodified `build_atoms()`
    is the only further step needed -- this function builds no atom and
    validates nothing.

    Nothing here is deduplicated or ordered beyond the input order: two
    rejected candidates describing two real works produce four
    propositions, and two describing the same work produce four too. A
    "these are the same work" judgement belongs to a human reading the
    queues, and collapsing them here would be this module making the call
    (the same non-goal `process_document()`'s identity proposals already
    declare for entity names).

    Pure: no I/O, no registry access, no entity resolution, no mutation
    of the input, no exception on any input. An unmatched ref, a
    non-`UNKNOWN_PREDICATE` code, or a non-dimension object all yield
    "nothing emitted for this entry" -- and the entry's own rejection
    accounting is untouched either way, which is the caller's to read.
    """
    originals_by_ref = {
        proposition.extraction_claim_ref: proposition for proposition in propositions
    }
    emitted: list[CandidateProposition] = []
    for candidate in rejected:
        if candidate.reason_code != _CONSIDERED_REASON_CODE:
            continue
        if not _is_pure_dimension_expression(candidate.object_raw):
            continue
        if not candidate.raw_predicate.strip() or not candidate.subject_raw.strip():
            continue
        original = originals_by_ref.get(candidate.extraction_claim_ref)
        if original is None:
            continue
        common = {
            "subject_raw": candidate.subject_raw,
            "evidence_excerpt": candidate.evidence_excerpt,
            "status": original.status,
            "source_id": candidate.source_id,
            "evidence_id": original.evidence_id,
            "truncated_source": original.truncated_source,
        }
        emitted.append(CandidateProposition(
            predicate="medium",
            object_raw=candidate.raw_predicate,
            extraction_claim_ref=f"{candidate.extraction_claim_ref}{MEDIUM_CLAIM_SUFFIX}",
            **common,
        ))
        emitted.append(CandidateProposition(
            predicate="dimensions",
            object_raw=candidate.object_raw,
            extraction_claim_ref=f"{candidate.extraction_claim_ref}{DIMENSIONS_CLAIM_SUFFIX}",
            **common,
        ))
    return tuple(emitted)
