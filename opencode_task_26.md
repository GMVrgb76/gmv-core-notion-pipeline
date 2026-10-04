# OpenCode Task 26 — filter known generic places out of the identity-proposal queue

**Status: DRAFT TASK — approved plan, not yet executed.**

## Why

`gmv_crawler_orchestrator.py` (~line 410-420, `process_document()`) calls
`propose_entity_identity(entity.name, registry, ...)` for **every** `CandidateEntity` extracted by
`extract_candidates()`, with no type filtering. Real, measured consequence (verified this session
against `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl`): of 257 queued proposals /
207 distinct names, the most repeated are bare geographic references — `"Roma"` (19x), `"ITALIA"`
(7x) — plus several bare city names from one document's "mostre internazionali" list (Singapore,
New York, Pechino, Alessandria d'Egitto, Buenos Aires, Baku, Amsterdam). These aren't ambiguous
near-duplicates a fuzzy matcher would help with — they're generic place references that don't need
a human to confirm a stable identity for, and they crowd out the real decisions (actual new
people/institutions) in the same queue a human has to review.

`propose_entity_identity()` itself must stay network-free (its own docstring: "reads the registry,
writes nothing, and touches no network" — same contract `resolve_entity_gmv_id()` has). So this
cannot reuse `classify_entity_types()` (a model call) as the filter — it needs a deterministic,
hand-curated list, the exact same pattern this project already uses for
`00_CONFIG/area35_known_artists.json` / `00_CONFIG/area35_known_institutions.json`.

## Hard constraints

1. **No model call added anywhere in this path.** The filter must be a plain deterministic
   lookup, not a `classify_entity_types()` call.
2. **No invented vocabulary.** Do not try to build or embed a general-purpose gazetteer/country
   list from scratch. Seed the new file ONLY with names actually observed as real noise in
   `entity_identity_proposal_queue.jsonl` (investigate the full file yourself, don't just reuse the
   9 names already cited above — there may be more real geographic noise in there) — same
   "human-curated, grows from real observed cases" discipline as the artist/institution rosters.
3. **Do not retroactively edit the existing 257-line queue.** This task only prevents NEW noise
   from being queued going forward. Cleaning up what's already there is a separate, later curation
   decision for a human.
4. **Do not change `propose_entity_identity()`'s own signature or its no-network contract.** The
   filter is a check the ORCHESTRATOR applies before calling it, not something added inside it.
5. **No SQL migration, no commits.**

## Steps

1. Read `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl` in full. List every distinct
   `raw_name` that is a bare geographic reference (city/country/region name with nothing else to
   it — not "Museo di Roma" or similar, which IS a real institution worth tracking). Report the
   full list you find, not just the ones already cited in this brief.
2. Create `00_CONFIG/area35_known_places.json`, same file shape/governance-note style as
   `area35_known_institutions.json` (a `"note"`/`"note_on_maintenance"` pair + a `"places"` array),
   seeded with exactly the real names from step 1.
3. Add a small function to `10_API/gmv_crawler_entity_resolver.py`, same pattern as
   `_load_known_artists()`/`_load_known_institutions()` (`_load_known_places()`, `_forma()`-
   normalized frozenset).
4. In `gmv_crawler_orchestrator.py`'s `process_document()`, before the existing identity-proposal
   loop over `entities`, skip any entity whose `_forma(entity.name)` is in the known-places set —
   it should never reach `propose_entity_identity()` at all, same shape as the existing
   `identity_proposals` generator expression, just with an added filter clause. Do the same for the
   WORK-domain proposal loop further down if it could ever receive a bare place name as a subject
   (check whether that's actually reachable before adding a redundant filter there).
5. Tests: a test proving a known place name never produces an identity proposal through the real
   orchestrator path (not just a unit test of the loader), and a test proving a real institution
   name (e.g. one already in `area35_known_institutions.json`) is UNAFFECTED by this change (still
   produces a proposal if unresolved, since that list is separate from the new places list).
6. Run `.venv/bin/python -m pytest tests/ -q` — confirm only the one pre-existing, unrelated
   failure. `ruff check .` clean.

## Report back

1. The real full list of bare-geographic names found in step 1.
2. How much this actually reduces the queue: re-run (don't just estimate) the same document-level
   extraction that originally produced the 257-line queue, with the filter in place, and report
   the new count vs. 257/207.
3. Exact diff of every file changed, pytest/ruff results, `git status --short`.
4. Any bare place-like name you were UNSURE about (e.g. a name that could be either a place or an
   institution depending on context) — list it separately and do NOT add it to the seeded file
   yourself; flag it for a human decision instead.
