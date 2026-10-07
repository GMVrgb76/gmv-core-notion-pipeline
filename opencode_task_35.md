# OpenCode Task 35 — gate non-prose files (CSV manifests) out of extraction entirely

**Status: DRAFT TASK — approved plan, not yet executed.**

## Why

Fresh frequency analysis of `01_RUNTIME/gmv_crawler/rejection_queue.jsonl` (this session, cross-
referenced against the CURRENT `crawler_predicate_text_mapping.json`, not the stale 09-21 snapshot)
found `MOVE_CANONICAL`/`MOVE_TEMP_IMPORT`/`MOVE_DUPLICATE` as the single largest unmapped-predicate
cluster (400+225+47 = 672 lines). Verified real root cause: these are file-management/dedup status
values from `source_manifest.csv`-type files (confirmed real `source_id`s:
`/gmv_master_system/01_area35_master/01_artists/geranzani_pietro/00_master/source_manifest.csv`,
`.../nazeraj_erjon/00_master/source_manifest.csv` — at least 2 artists, check for more before
concluding it's only these 2), run through the SAME prose-extraction pipeline as a real biography.
A `.csv` manifest is not prose by construction — no amount of predicate-mapping curation fixes
this, the document itself should never have reached `extract_candidates()`.

This is the same CLASS of bug already fixed once this session for price_list/contract
misclassification, but **does not need `classify_document()`'s LLM call** — unlike
biography-vs-contract-vs-price_list (which all can be prose in any file format and genuinely need
content classification), a bare `.csv` file extension is already unambiguous, deterministic signal.
Same "deterministic-first" principle already used in the real-estate pipeline's
`is_generic_regulatory_reference()`/`is_construction_safety_document()` — check that module
(`10_API/gmv_property_extract_templates.py`) for the exact precedent shape before designing this.

## Hard constraints

1. **Deterministic only — no LLM call for this specific check.** A file extension/structural check,
   not a `classify_document()` call.
2. **Do not modify `classify_document()`'s own `DOCUMENT_TYPES` enum or its classification logic.**
   This gate runs BEFORE classification, not as a new type inside it — a `.csv` manifest was never
   a document TYPE question (biography vs contract vs price_list all legitimately need content
   classification; "is this even prose" does not).
3. **Investigate first whether this is CSV-specific or a broader "non-prose file" problem** — check
   the real archive for other obviously-non-prose extensions (`.json`, `.yaml`, `.xml` outside
   `00_CONFIG`) feeding into this same pipeline before deciding the gate's exact scope. Do not
   invent a broad "skip anything weird" rule — ground it in what you actually find.
4. Same live-verification discipline as every prior task: re-derive real counts, don't just trust
   this brief's numbers.

## Steps

1. Read `10_API/gmv_property_extract_templates.py`'s `is_generic_regulatory_reference()` /
   `is_construction_safety_document()` / `_skip_reason()` in full — this is the real, precedent
   "pre-extraction deterministic gate" pattern already shipped and tested in this repo. Follow its
   shape (a detector function + an ordered list of detectors + a single stable skip-status, not one
   new status per detector).
2. Grep the real archive (or the real `01_RUNTIME/gmv_crawler/` scan state, whichever is the real
   source of truth for what files this pipeline has touched) for how many real `source_manifest.csv`
   (or other non-prose) files exist and have been run through extraction. Confirm the real scope
   before building anything.
3. Add a deterministic `is_non_prose_file(record, paths) -> bool` (or similarly-named) check in
   `10_API/gmv_crawler_orchestrator.py` (or wherever `process_document()`'s own real precedent for
   this kind of gate lives — check if one already exists there, don't assume it doesn't), wired to
   run BEFORE `classify_document()`/`extract_candidates()` are ever called, with its own stable skip
   status (not reusing one of `DOCUMENT_TYPES`).
4. Tests: a real fixture proving a `.csv`-sourced record never reaches `extract_candidates()`
   (same mocking convention already established in `tests/test_gmv_crawler_orchestrator.py` —
   `monkeypatch.setattr(orchestrator, "extract_candidates", ...)` that raises if called), and a
   test proving a normal prose document is completely unaffected.
5. Live proof: re-run `process_document()` (or the real scan/extract step, whichever is appropriate)
   on one of the real `.csv` manifest files found in step 2, confirm zero propositions/rejections
   are produced for it now, where before it produced the `MOVE_CANONICAL`-type noise.
6. Run `.venv/bin/python -m pytest tests/ -q` / `ruff check .` — confirm only the one pre-existing
   failure.

## Report back

1. The real scope found in step 2 (how many files, which extensions, confirmed non-prose).
2. Exact diff, the real skip status name chosen and why.
3. Live proof result (step 5), real before/after.
4. Test/ruff results, `git status --short`.
