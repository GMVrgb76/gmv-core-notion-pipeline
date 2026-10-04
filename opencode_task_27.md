# OpenCode Task 27 — finish Task 26: missing tests + the real re-run that was substituted with an estimate

**Status: DRAFT TASK — approved plan, not yet executed.**
**Builds on Task 26's work (already committed: `_load_known_places()`, orchestrator filtering,
`00_CONFIG/area35_known_places.json`). The directing Claude session already fixed one issue itself
(`@lru_cache` removed from `_load_known_places()` to match the no-caching convention every other
loader in that file follows) — don't re-add it.**

## Why this task exists

Task 26's own report flagged two of its requirements as unmet, honestly, but didn't complete
them:
1. **No tests exist for the new filtering behavior.** The report: "Added and then removed two
   temporary tests... because they were exploratory." Task 26 Step 5 explicitly asked for two real
   committed tests. Neither exists (`git diff` on the test files shows nothing).
2. **The "44 of 257" impact number is a static match against the ALREADY-EXISTING queue file**,
   not the live re-run Task 26 Step 2 asked for ("re-run (don't just estimate)"). Verified by the
   directing session: recomputing it directly gives the same 44/257 total-line figure, but the
   more informative number — **distinct names drop from 207 to only 195 (12 removed, ~6%)** — was
   not surfaced. Most of the queue's distinct-name clutter is NOT bare known places already in the
   new list; it's other noise the current 12-entry list doesn't cover yet.

## Steps

### Part A — the two missing tests (Task 26 Step 5, do not skip this time)

In `tests/test_gmv_crawler_orchestrator.py`:
1. A test proving a known place name (pick one from `00_CONFIG/area35_known_places.json`, e.g.
   `"Roma"`) never produces an entry in `process_document()`'s `entity_identity_proposals` output,
   even when the document's extracted entities include it unresolved.
2. A test proving a real institution name already in `00_CONFIG/area35_known_institutions.json`
   (or any name NOT in the new places list) is UNAFFECTED — still produces a proposal when
   unresolved, exactly as before Task 26.

Both committed for real this time, not added-then-removed. Run `.venv/bin/python -m pytest tests/ -q`
afterward — confirm only the one pre-existing, unrelated failure.

### Part B — the real re-run Task 26 asked for

1. Using the real document(s) that originally produced
   `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl`'s 257 lines (Danilo Bucchi's real
   document, per this session's established work — confirm this is still the right source document
   before assuming it), actually call `process_document()` (or whatever real entry point produces
   identity proposals) end-to-end with the Task 26 filter in place, on a FRESH copy — do not
   mutate the real queue file.
2. Report the real, live count of identity proposals produced now vs. what the original 257-line
   run produced for the same document — not a static match against the old file, an actual new
   execution.
3. **Separately**, go back to `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl` and
   list every one of the 195 distinct names that are NOT in the new known-places list but that YOU
   judge are still bare geographic references the current list missed (the directing session's own
   quick read already spotted this gap — there are likely more). Do not add them to
   `area35_known_places.json` yourself (same human-curation discipline as Task 26) — just report
   the candidates, flagged clearly as "found, not yet added, needs human review."

## Report back

1. The two new tests, passing, plus full pytest/ruff results.
2. Part B's real before/after proposal count for the live re-run (not an estimate).
3. The list of additional candidate bare-place names found in step B.3, explicitly not yet added
   to the curated file.
4. `git diff`/`git status --short` for everything you changed.
