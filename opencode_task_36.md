# OpenCode Task 36 — curate real exhibition-participation verb forms into crawler_predicate_text_mapping.json

**Status: DRAFT TASK — approved plan, not yet executed.**

## Why

Fresh frequency analysis (this session) of `01_RUNTIME/gmv_crawler/rejection_queue.jsonl`, cross-
referenced against the CURRENT (not stale) `crawler_predicate_text_mapping.json`, found real,
repeated raw predicates closely related to already-mapped forms, still unmapped:
`"present"` (210), `"exhibited"` (197), `"held"` (141), `"mostra"` (85), `"held at"` (76),
`"presente"` (71), `"exhibited at"` (56). The file already maps `"was held at"`/`"was presented
at"`/`"presente in"` → `located_at` and `"ha esposto"`/`"partecipa"` → `participated_in` — these
look like near-miss surface variants (missing "was"/preposition, English vs the already-mapped
Italian forms, etc.) of the SAME real-world facts, not a new kind of predicate. This is the most
promising real lead this session found for getting actual governed RELATION atoms out of
biography-type documents (today: 7 real Monads, 0 atoms, 100% PUBLIC-text only).

## Hard constraints — the one this project has gotten wrong before, twice

1. **Every single mapping entry needs a real domain/range check against a REAL example from a
   REAL document — never map on name-similarity alone.** This exact project already shipped one
   real editorial error this way (`"ha esposto"` → `exhibited_at` without checking the subject was
   a PERSON not an ARTWORK_INSTANCE, caught and fixed 2026-09-21) and this session caught a second,
   different-shaped one (`located_at` misapplied to a Garibaldi sentence whose real subject was the
   artist, not an exhibition — found during Task 22). **A bare raw text like `"held"` or
   `"present"` is dangerously generic** — it may appear in completely unrelated real sentences with
   a different subject/object shape than the exhibition-participation sense this task is looking
   for (e.g. "present" as an adjective, "held" in "held the position of"). Do not map a raw text
   just because it name-matches; verify the REAL sentence it actually came from, every time.
2. **No new predicate_id, no ontology registry edit.** `located_at`/`participated_in` already
   exist with the domain/range below — read them fresh from
   `00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json` yourself, do not trust these as still-current:
   `located_at`: domain `[EXHIBITION,EVENT,ORGANIZATION]`, range `[PLACE,INSTITUTION]`.
   `participated_in`: domain `[PERSON,ARTIST]`, range `[EVENT,EXHIBITION,PROJECT]`.
3. **A single raw text may legitimately split into TWO different real cases with different real
   shapes** (e.g. `"present"` might be `located_at`-shaped in one real sentence and not a relation
   at all in another). If you find this, do not force one mapping to cover both — report the split
   and only map the shape that genuinely recurs with the same subject/object pattern.
4. **The rejection queue you're reading is STALE (dated 2026-09-25)** — re-derive the real subject/
   object for each candidate by reading the real source document (via `DropboxConnector`, same
   credentials pattern as every prior task), not by trusting the queue line's `raw_predicate`
   string alone.

## Steps

1. Re-derive the real current counts yourself (cross-reference against the CURRENT mapping file,
   not the numbers in this brief) — confirm these 7 raw texts are still genuinely unmapped today.
2. For each of the 7, trace back to several (not just one) real source documents via
   `source_id`/`extraction_claim_ref`, download via `DropboxConnector`, and read the real
   surrounding context — not just the single extracted triple — to confirm the real subject/object
   shape and that this is genuinely the exhibition-participation sense, not a homonym.
3. For each raw text that is genuinely exhibition-participation-shaped AND has a consistent
   subject/object pattern across multiple real examples, add a mapping entry to
   `00_CONFIG/crawler_predicate_text_mapping.json`, following that file's own existing entry format
   exactly (`raw_predicate_text`, `predicate_id`, `verified_against` citing the REAL cases you
   checked — plural, not one).
4. For any of the 7 that turns out NOT to be safely mappable (homonym risk, inconsistent shape,
   too generic), explicitly exclude it and say why — do not force a mapping to hit a target count.
5. Tests: for each new mapping added, a real fixture test proving `build_relation_atoms()` now
   builds a correctly-shaped atom from it (mirroring this session's own established fixture
   conventions in `tests/test_gmv_crawler_orchestrator.py`/the relation-atom-builder's own test
   file), AND a negative test proving a homonym/wrong-shape use of the same raw text is still
   correctly rejected (not silently atom-ified just because the text matches).
6. Live proof: pick at least 2 of this session's already-confirmed real entities/documents (the 7
   Monad-backed artists, or Garibaldi/Bucchi) whose real extraction is likely to contain one of
   the newly-mapped forms, re-run the real pipeline, and report whether a real new RELATION atom
   now builds that did not before.
7. Run `.venv/bin/python -m pytest tests/ -q` / `ruff check .` — confirm only the one pre-existing
   failure.

## Report back

1. Per raw text: mapped or excluded, with the real `verified_against` citation (or the real reason
   for exclusion).
2. Any case where one raw text split into two different real shapes (constraint 3).
3. Live proof result (step 6): real new atom(s) built, verbatim.
4. Test/ruff results, exact diff, `git status --short`.
