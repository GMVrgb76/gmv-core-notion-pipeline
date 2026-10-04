# OpenCode Task 17 — rescue clean "medium, dimensions" caption facts, and propose identity for WORK subjects

**Status: DRAFT TASK — not yet executed. Direct follow-up to Task 16 (commit `6d1a2a06`), which
registered `dimensions`/`medium`/`creation_year` and generalized `gmv_crawler_atom_builder.py` to
build them -- but nothing in the real pipeline produces a clean `dimensions`/`medium` proposition
from real text yet. This task closes that gap for the one shape real data actually supports, and
gives a WORK its own identity-proposal path, parallel to the one Task 15 built for PERSON/
INSTITUTION-shaped `CandidateEntity` mentions.**

## Why this task exists, and what real data actually shows (read before writing anything)

The real, live `01_RUNTIME/gmv_crawler/rejection_queue.jsonl` (11700+ real rejected claims) was
queried directly this session, not assumed. Two real findings:

1. **A small, clean, safe rescue exists.** Filtering `reason_code == "PREDICATE_TEXT_NOT_MAPPED"`
   entries (the ones `gmv_crawler_relation_atom_builder.py` logs when a raw predicate text has no
   entry in `00_CONFIG/crawler_predicate_text_mapping.json`) to those whose `object_raw`, once
   `.strip()`-ped and split on `,`, has EVERY resulting part fully matching the regex
   `^\d+[.,]?\d*\s*[xX×]\s*\d+[.,]?\d*(\s*[xX×]\s*\d+[.,]?\d*)?\s*cm\.?$` (case-insensitive)
   yields **exactly 5 real cases in the whole queue, zero false positives**, all the same shape --
   `subject_raw` is a work title, `raw_predicate` is a medium/technique description, `object_raw`
   is a pure dimension expression:
   ```
   subject_raw='Il bacio'                 predicate='smalto, unghie, alluminio e carta su tavola'  object_raw='90 x 60 x 5 cm'
   subject_raw='Voodoo children'          predicate='crossage su tavola'                            object_raw='150 x 150 x 5 cm'
   subject_raw='Voodoo children'          predicate='arazzo e collage di tessuti su cartoncino'      object_raw='215 x 210 cm'
   subject_raw='Nuvole'                   predicate='metallo, legno e acrilico'                      object_raw='175 x 58 cm'
   subject_raw='Chi è la mamma del sole'  predicate='smalto e acrilico su tavola'                    object_raw='160 x 110 cm'
   ```
   This is a real, recurring art-catalogue caption convention ("technique, WxH cm"), and the LLM
   extractor happens to already put the technique text in `predicate` and the dimension text in
   `object_raw` -- it just never resolves through the RELATION path because it isn't a relation.
   **This is an ATTRIBUTE-domain fact pair, not one relation.** The fix is not a text->predicate
   mapping entry (the technique text is different every time, never a repeated exact string like
   "a cura di") -- it is a structural recognition rule: whenever `object_raw` is unambiguously a
   dimension expression, treat the pairing as two ATTRIBUTE facts about the same subject:
   `dimensions = object_raw` (verbatim) and `medium = the original raw predicate text` (verbatim).

2. **What is deliberately NOT rescued, and why (EIC-12, less-assertive interpretation over
   guessing):**
   - Multi-panel dimension strings where only the LAST comma-separated part carries "cm"
     (e.g. `'45 x 55, 45 x 60 cm'`, `'150 x 100, 166 x 112 cm'`) -- the strict per-part regex above
     deliberately excludes these; forcing them would require guessing whether "cm" applies to every
     part or just the last, which is not this task's call to make.
   - The idiom `"dimensioni ambientali"`/`"dimensione ambientale"` ("environmental/variable
     dimensions", a real real-corpus phrase for site-specific/installation work with no fixed
     measurement) -- arguably a valid free-text `dimensions` value, but that is a content/governance
     judgment about what counts as a valid value for a CANDIDATE predicate, not a mechanical
     pattern match, and is left for a future explicit decision, not decided silently here.
   - `'2014 enamel on paper 150x100 cm'` (subject `'ASSOLO 002'`, predicate `'present'`) -- a
     genuine 3-way compound (year + medium + dimensions all in one `object_raw`), excluded by the
     strict per-part regex (the full string does not fully match after splitting on `,`, since
     there is no comma at all and the leading "2014 enamel on paper" prefix fails the regex).
     Correctly excluded, not a bug in the regex.
   - **`creation_year` population from this rejection-queue backlog is NOT attempted.** No clean,
     isolated "work created in `<year>`" case was found anywhere in the real queue (verified by
     grep across raw_predicate/object_raw for date-like patterns) -- the closest real cases are a
     year embedded inside `evidence_excerpt` text near a title but never isolated into
     `subject`/`predicate`/`object` by the extractor (e.g. `evidence_excerpt`:
     `"*Fulmine a ciel notturno -2014 carta, dimensioni ambientali"`, but `creation_year` never
     appears as a clean fact anywhere in `subject_raw`/`predicate`/`object_raw`). Fixing that is an
     extraction-quality problem (parsing `evidence_excerpt`'s leading "Title - YYYY" caption
     convention), a materially different and larger task, explicitly out of scope here.

## What this task is

**Two real, additive changes to the already-running pipeline, both read-mostly/rescue-only, never
guessing:**

### Part A — rescue the 5-case "medium, dimensions" caption pattern into real atoms

A new pure function, `10_API/gmv_crawler_caption_predicate_splitter.py` (new file, mirror the
style/docstring rigor of `gmv_crawler_atom_builder.py` and `gmv_crawler_relation_atom_builder.py`):

```python
def split_medium_dimensions_captions(
    rejected: Sequence[RejectedCandidate],
) -> tuple[CandidateProposition, ...]:
```

- Input: the `RejectedCandidate` tuple `build_atoms()` already produces (imported, not
  reimplemented) -- specifically only entries with `reason_code == "UNKNOWN_PREDICATE"` (the code
  `build_atom()` returns when `proposition.predicate` resolves to nothing in
  `_known_predicates(registry)` -- exactly the case for a raw technique description like `'smalto,
  unghie, alluminio e carta su tavola'`, which is not a registered predicate id or alias).
- For each: if `object_raw.strip()`, split on `,`, has every resulting part (each also `.strip()`,
  trailing `.` allowed) fully matching the dimension-unit regex above, emit exactly TWO new
  `CandidateProposition` objects, both copying `subject_raw`/`source_id`/`evidence_excerpt`
  verbatim from the rejected candidate's own fields (already on `RejectedCandidate` since
  2026-09-21 -- read `RejectedCandidate`'s real fields before writing this, they are exactly
  `source_id`/`extraction_claim_ref`/`raw_predicate`/`reason_code`/`detail`/`subject_raw`/
  `object_raw`/`evidence_excerpt`):
  - One with `predicate="medium"`, `object_raw=<the original raw_predicate text, verbatim>`,
    `extraction_claim_ref=f"{original}#medium"`.
  - One with `predicate="dimensions"`, `object_raw=<the original object_raw, verbatim>`,
    `extraction_claim_ref=f"{original}#dimensions"`.
  - `status`/`evidence_id`/`truncated_source` fields `CandidateProposition` requires but
    `RejectedCandidate` does not carry: read `CandidateProposition`'s real constructor
    (`gmv_crawler_candidate_extractor.py`) for what is required and pick the least-assertive
    real default that satisfies its own `__post_init__` (e.g. `evidence_id=()` is likely NOT
    legal if `_validate_evidence_id` requires at least one -- check the real validator and use
    whatever is both truthful and constructible; if nothing truthful satisfies it, stop and
    disclose rather than inventing a fake evidence id).
  - A non-matching rejected candidate produces nothing (not re-emitted, not modified) -- this
    function only adds propositions, it never touches or drops the original rejection accounting.
- Pure, no I/O, no registry access, no entity resolution -- exactly the same "no side effects,
  structural pattern recognition only" scope `gmv_crawler_relation_atom_builder.py`'s own
  `_link_object_to_entity()` has for its narrower job.

### Part B — wire it into `10_API/gmv_crawler_orchestrator.py`, preserving every existing invariant

Read the real, current `process_document()` body fully before touching it -- in particular the
comment block (around the existing `attr_atoms, attr_rejected = build_atoms(...)` call) that
documents `rejected` in `ProcessDocumentResult` as **"ONLY `build_relation_atoms()`'s final
rejections"** and the `leftover_propositions` computation that follows it. This task must not
break that documented contract for any proposition NOT rescued by Part A.

Exact insertion point: immediately after `attr_atoms, attr_rejected = build_atoms(propositions,
now=now)` and before `rejected_refs = {...}` is computed:

1. `caption_synthetic = split_medium_dimensions_captions(tuple(r for r in attr_rejected if r.reason_code == "UNKNOWN_PREDICATE"))`
2. If `caption_synthetic` is non-empty: `caption_atoms, caption_rejected = build_atoms(caption_synthetic, now=now)` (reuses `build_atoms()`, no new atom-construction logic duplicated). Expect `caption_rejected == ()` in the intended case (the synthesized propositions use governed canonical predicate ids and already-validated real text) -- if it is ever non-empty in a real run, that is a signal to investigate, not to swallow; decide (and disclose) whether to fold `caption_rejected` into the function's final `rejected` accounting or surface it another way, matching the spirit of `build_atom()`'s own "never silently ignored" rule. If empty, skip the second `build_atoms()` call entirely (mirror the existing empty-batch-skip style already used for `build_relation_atoms()` a few lines below).
3. `attr_atoms = attr_atoms + caption_atoms`.
4. The ORIGINAL `extraction_claim_ref`s that were successfully split (i.e. produced by
   `split_medium_dimensions_captions()`, derivable from the synthetic propositions' own
   `extraction_claim_ref` before the `#medium`/`#dimensions` suffix, or by tracking which
   `RejectedCandidate`s were fed in and matched) must be EXCLUDED from `leftover_propositions`
   (the ones that continue on to `build_relation_atoms()`) -- otherwise a now-resolved caption
   would still be logged a second time as `PREDICATE_TEXT_NOT_MAPPED` by the relation builder,
   which would be actively misleading (the real gap it once represented no longer exists). Read
   the real `rejected_refs`/`leftover_propositions` computation and adjust it so a proposition
   whose `extraction_claim_ref` was successfully rescued is removed from that set, not just left
   alongside a stale duplicate rejection.
5. Do not otherwise touch `rel_built`/`rel_rejected`/the final `rejected=rel_rejected` assignment,
   `proposals_needing_verification`, or any other existing field.

### Part C — propose a WORK identity for the subject of any WORK-domain ATTRIBUTE proposition

Task 15 (commit `f89e0a35`) already generates `EntityIdentityProposal`s for every `CandidateEntity`
in `entities`, via `propose_entity_identity(entity.name, registry, source_id=..., evidence_excerpt=...)`.
This part adds a SECOND, independent source feeding the SAME `identity_proposals` tuple: the
subject of every proposition (original real ones AND Part A's synthetic ones) whose predicate
resolves, via the real registry, to a predicate whose `domain == ["WORK"]` -- today that is
`edition_size`, `dimensions`, `medium`, `creation_year` (verify this by reading the real registry,
do not hardcode the id list; `edition_number`'s domain is `ARTWORK_INSTANCE`, not `WORK`, and must
NOT be included).

- Reuse `_known_predicates(registry)` (`gmv_atom_validator.py`, already used by
  `gmv_crawler_atom_builder.py` for the exact same "resolve raw predicate text to its registry
  entry" job) to resolve `proposition.predicate` and read its `domain`.
- For each proposition whose resolved entry has `domain == ["WORK"]`:
  `propose_entity_identity(proposition.subject_raw, registry, source_id=proposition.source_id, evidence_excerpt=proposition.evidence_excerpt, suggested_entity_type="WORK")`.
  `None` results (already resolves to a known WORK `gmv_id`) are filtered out exactly like the
  existing `CandidateEntity` loop already does.
- **No deduplication** -- the same subject appearing in two WORK-domain propositions (e.g. a
  `dimensions` and a `medium` fact about the same work) produces two proposals, not one, exactly
  like Task 15's own documented non-goal for `CandidateEntity` names. This is disclosed here
  explicitly so it is not mistaken for a bug: querying the identity proposal queue by `raw_name`
  is how a human would see "this name appeared N times."
- **Disclosed limitation, do not try to fix it in this task:** this only catches a WORK subject
  when its predicate ALREADY resolves to a canonical WORK-domain predicate id -- which today means
  real naturally-clean LLM output (rare) plus whatever Part A's splitter rescues. It is not a
  general "recognize any work title in the text" mechanism. State this plainly in the module
  docstring, the same way Task 16 disclosed `creation_year`'s weak evidence rather than overstating
  it.
- Merge these into the SAME `identity_proposals` tuple `process_document()` already builds and
  returns as `entity_identity_proposals` -- do not add a second field, a second dataclass, or a
  second queue. `EntityIdentityProposal.suggested_entity_type` already exists precisely to carry
  this ("WORK" instead of `""`).

## Hard constraints

1. **Never call `confirm_new_entity()`/`confirm_entity_alias()`.** Same boundary every task in this
   series has protected. This task only proposes, exactly like Task 15.
2. **`00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json` and `00_CONFIG/crawler_predicate_text_mapping.json`
   are not touched.** Nothing here is a governance edit -- Part A is structural pattern recognition
   over already-governed predicate ids (`medium`/`dimensions`, registered in Task 16), Part C only
   reads the registry.
3. **Part A's regex must stay exactly as strict as specified above.** Do not loosen it to also
   catch the multi-panel or "dimensioni ambientali" cases -- those are named above as deliberately
   excluded, not missed.
4. **The documented contract "`ProcessDocumentResult.rejected` is ONLY
   `build_relation_atoms()`'s final rejections" must still hold** for every proposition Part A did
   NOT rescue. Verify this with a real test (Step 4 below), not by inspection alone.
5. **No new proposal dataclass, no new queue file, no new path constant** for Part C -- reuse
   `EntityIdentityProposal`/`entity_identity_proposal_queue.jsonl` exactly as Task 15 wired them.

## Real code to read before writing anything

- `10_API/gmv_crawler_atom_builder.py` -- `RejectedCandidate`'s real fields, `build_atom()`'s
  `UNKNOWN_PREDICATE` branch (post-Task-16 shape).
- `10_API/gmv_crawler_candidate_extractor.py` -- `CandidateProposition`'s real constructor and
  `__post_init__`/`_validate_evidence_id`, for Part A's synthetic-proposition field values.
- `10_API/gmv_crawler_orchestrator.py` -- the full real `process_document()` body, especially the
  `attr_atoms`/`attr_rejected`/`rejected_refs`/`leftover_propositions`/`rel_built`/`rel_rejected`
  chain and the final `ProcessDocumentResult(...)` construction (Task 15's `identity_proposals`
  block is right above it).
- `10_API/gmv_atom_validator.py::_known_predicates()` -- reuse directly, do not reimplement.
- `10_API/gmv_crawler_entity_resolver.py::propose_entity_identity()`,
  `EntityIdentityProposal` -- reuse directly, unmodified.
- `00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json` -- confirm the real WORK-domain predicate id set
  before hardcoding anything that depends on it.

## Steps

1. Write `10_API/gmv_crawler_caption_predicate_splitter.py` (Part A).
2. Wire Part A + Part C into `10_API/gmv_crawler_orchestrator.py` (Parts B and C).
3. Tests:
   - New test file for the splitter: exercise all 5 real cases above verbatim (as literal
     `RejectedCandidate` fixtures, not re-derived from the live runtime file), the two deliberately
     excluded shapes (multi-panel, `"dimensioni ambientali"`, the `'ASSOLO 002'` 3-way compound) to
     confirm they produce nothing, and a non-`UNKNOWN_PREDICATE` rejection (any other reason_code)
     to confirm it is not considered at all by the function (the caller filters by reason_code, but
     the function's own contract should be checked too if it does its own filtering).
   - `tests/test_gmv_crawler_orchestrator.py`: a real end-to-end case (stub `extract_candidates` to
     return one caption-shaped proposition, matching one of the 5 real cases above) asserting: two
     new atoms appear in `result.atoms` (`medium` and `dimensions`, correct `subject`/`object`/
     `object_type`), the original claim is NOT duplicated into `result.rejected`, and a WORK
     identity proposal appears in `result.entity_identity_proposals` for the work's title with
     `suggested_entity_type == "WORK"`. Also a case proving the documented "`rejected` is ONLY
     `build_relation_atoms()`'s final rejections" contract still holds for a genuinely unmapped,
     non-caption-shaped proposition (constraint 4).
   - A case with TWO WORK-domain propositions sharing one subject producing TWO identity proposals,
     not one (constraint on no dedup, mirroring Task 15's own equivalent test).
4. `.venv/bin/python -m pytest tests/ -q` and `.venv/bin/python -m ruff check .` -- same bar as
   every prior task: only the pre-existing `test_current_tracked_tree_passes_policy` failure
   allowed.
5. Live proof (not committed): re-run the 5 real cases (either by re-deriving them from the real
   `01_RUNTIME/gmv_crawler/rejection_queue.jsonl` read-only, or by hand-copying the verbatim values
   listed above) through `split_medium_dimensions_captions()` directly, print the resulting
   propositions, then through `build_atoms()`, print the resulting atoms (`subject`/`predicate`/
   `object`/`object_type` for each) -- confirm all 5 cases produce exactly 2 atoms each sharing the
   real work's title as `subject`. Never write to the real runtime queue or registry files.

## What to report back

1. The Step 5 live-proof output verbatim for all 5 real cases (10 atoms total).
2. Full `pytest`/`ruff` results, and explicit confirmation the "`rejected` is ONLY
   `build_relation_atoms()`'s final rejections" contract still holds (cite the specific test).
3. Complete `git diff`/`git status --short`. Do not commit anything yourself.
4. Any place where the real code contradicted this brief (the `evidence_id`/`status` field-value
   question in Part A is flagged above as one likely candidate) -- disclose and explain the
   resolution actually chosen, per this project's established norm.
