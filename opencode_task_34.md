# OpenCode Task 34 — complete the medium/dimensions predicate-text curation (already-approved, never finished)

**Status: DRAFT TASK — approved plan, not yet executed.**

## Why

`medium`/`dimensions` are real, already-registered ATTRIBUTE predicates in
`00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json` (`domain=["WORK"]`, `range=["string"]`), registered on
real cited evidence ("olio su tela", "90 x 60 cm", etc.). But `00_CONFIG/crawler_predicate_text_mapping.json`
has **zero entries for either** — the curation step was approved in principle and never completed.
This session's own fresh frequency analysis of `01_RUNTIME/gmv_crawler/rejection_queue.jsonl`
(11,743 lines, cross-referenced against the CURRENT mapping file, not the original 09-21 snapshot)
found real, repeated, material/dimension-shaped raw predicates still unmapped: 48 distinct
medium-like texts (141 lines, top: `"olio su tela"` x39, `"mix media on canvas"` x28) and 57
distinct dimension-like texts (90 lines, top: `"cm 30 x 40 - pastello a cera su carta"` x6, `"30 ×
24 cm"` x5). This task finishes that curation — no new ontology predicate, no new design decision,
just completing an already-approved mapping.

## Hard constraints

1. **No new predicate_id, no ontology registry edit.** `medium`/`dimensions` already exist with
   the domain/range above — this task only adds entries to `crawler_predicate_text_mapping.json`.
2. **Every mapping entry needs a real domain/range check against a real example** — same
   discipline as every other entry in that file (`verified_against` field citing real cases), and
   the same discipline this session already caught a real error with (Garibaldi/`located_at`,
   subject was the artist not an exhibition — do not repeat that class of mistake here in
   reverse: confirm the SUBJECT of each candidate raw predicate is WORK-shaped — an artwork title
   — not a PERSON/ARTIST before mapping it to `medium`/`dimensions`).
3. **Not every "medium-like" string found by this brief's own keyword search is real.** The
   session's own quick pass already caught two likely false positives worth re-checking yourself,
   not trusting: `"dipendenza tecnica o metadato di un pacchetto editoriale; conservato per
   revisione."` and `"catalogo, monografia, portfolio o dépliant identificato."` — read their real
   source context before deciding whether they are genuine medium-type values or something else
   entirely (they read like system/pipeline notes, not artwork descriptions — verify, don't guess
   either way).
4. **The rejection queue you're reading from is STALE (dated 2026-09-25)** — real `source_id`/
   `extraction_claim_ref` values in it point at real documents, so re-derive the real subject for
   each candidate by reading the real document (via `DropboxConnector`, same credentials pattern
   as every prior task), not by trusting the queue line's context alone — the queue line only
   carries the raw predicate text and a reference, not the real subject/object pair reliably
   verified for every entry.
5. **Do not touch `rejection_queue.jsonl` itself.** It is stale, real runtime state, out of scope.

## Steps

1. Load the real current `rejection_queue.jsonl`, cross-reference raw predicates against the
   CURRENT `crawler_predicate_text_mapping.json` (not assumed empty — read it fresh), and collect
   every distinct raw predicate text matching material/technique or dimension shape not already
   mapped. Use the real counts above as a starting point, but re-derive them yourself — don't just
   copy the numbers from this brief.
2. For the top ~15-20 by frequency (your judgment on where real signal thins out — the long tail
   of 1-2 occurrence texts is likely not worth curating one at a time), trace each back to its real
   source document via `source_id`/`extraction_claim_ref`, confirm the real subject is WORK-shaped
   (an artwork title, not a person), and add a real mapping entry with a real `verified_against`
   citation, following this file's own existing entries' exact format.
3. Tests: at minimum, a test proving `build_atoms()` or `build_relation_atoms()` (whichever path
   ATTRIBUTE predicates actually go through — confirm which, don't assume) now successfully builds
   a real `medium`/`dimensions` atom from one of the newly-mapped real raw texts, using a realistic
   fixture (mirror this session's own established fixture style).
4. Live proof: pick ONE real document from this session's own already-confirmed-real artist list
   (Task 28/32/33's 7 artists, or Garibaldi/Bucchi) whose real extraction is likely to contain a
   medium/dimension mention — check Task 28's own survey output first
   (`/tmp/opencode/task28/work/*_result.json`, if still present) for a real candidate before
   downloading anything fresh. Re-run `build_atoms()`/`build_relation_atoms()` on that real
   document with the new mappings in place, and report whether a real ATTRIBUTE atom now builds
   that did not before.
5. Run `.venv/bin/python -m pytest tests/ -q` / `ruff check .` — confirm only the one pre-existing
   failure.

## Report back

1. The real, re-derived count of distinct medium/dimension-shaped unmapped texts (don't just repeat
   this brief's numbers).
2. Every mapping entry you added, with its real `verified_against` citation.
3. Your disposition on the two flagged possible-false-positives (step 3 above) — mapped, or
   excluded, and why.
4. The live proof result (step 4): did a real ATTRIBUTE atom actually build this time?
5. Test/ruff results, exact diff, `git status --short`.
