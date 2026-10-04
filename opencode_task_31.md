# OpenCode Task 31 — route unmapped descriptive text into the Monad's PUBLIC section (not a new predicate)

**Status: DRAFT TASK — approved plan, not yet executed.**
**Supersedes the earlier plan to register a new ATTRIBUTE predicate. That path was investigated
(Task 28) and rejected by real data: 9 of 129 real propositions were practice-description-shaped,
and all 9 were DISTINCT raw texts with zero repetition — no stable lexical pattern exists to
govern with one predicate. This task takes the alternative, already-designed-for path instead.**

## Why PUBLIC, not a new predicate

`10_API/gmv_monad_materializer.py`'s own docstring: `materialize_monad()` takes `public_text` as a
caller-supplied string and writes it verbatim — "it does not compute or validate PUBLIC content."
This is already the schema's designated home for non-governed free text, separate from the
governed ATOMS table. Federico Garibaldi's Monad proof (Task 18, this session) produced an empty
Monad (0 atoms, empty PUBLIC) because none of his document's RELATION-shaped propositions mapped —
but his document's real, unmapped sentences (practice description, descriptive prose) still exist
as real text, just never routed anywhere. This task routes them into PUBLIC, verbatim, deduplicated
— no synthesis, no LLM call, no governance claim over this text.

## Hard constraints

1. **No new ontology predicate, no edits to `GMV_ONTOLOGY_REGISTRY_v0.1.json` or
   `crawler_predicate_text_mapping.json`.** That path is explicitly closed per the evidence above.
2. **Do not modify `10_API/gmv_crawler_public_projector.py::project_public()`.** Its contract is
   "generate PUBLIC text FROM already-validated ATOMS" — reused unchanged. This task's text comes
   from a different source (rejected/unmapped propositions) and must be a separate function.
3. **Do not modify `gmv_monad_materializer.py`.** It already accepts `public_text` as a plain
   string with no validation — nothing there needs to change.
4. **Verbatim only — no LLM call, no paraphrasing, no synthesis.** The new function reads real
   `evidence_excerpt` values already present on `RejectedCandidate` (`10_API/gmv_crawler_atom_builder.py:160`,
   added 2026-09-21 specifically so a human/consumer can recover "the real sentence it came from")
   and assembles them into readable text by concatenation/deduplication only.
5. **Only `reason_code == "PREDICATE_TEXT_NOT_MAPPED"` rejections are eligible.** Other rejection
   reasons (e.g. `OBJECT_NOT_LINKED_TO_KNOWN_ENTITY`, `VALIDATION_FAILED`) are a different kind of
   problem (a real governed predicate that failed to build, not "no predicate fits") — do not route
   those into PUBLIC, they would misrepresent a validation failure as unvalidated-but-fine prose.

## Steps

1. Decide file placement by reading real precedent first: does a new function belong alongside
   `project_public()` in `gmv_crawler_public_projector.py` (as a clearly-separate, clearly-labeled
   sibling — read that module's own docstring in full first to confirm this doesn't contradict its
   stated scope), or in a new small file? Your call, but justify it against what you actually read,
   not a guess.
2. Write `compose_unmapped_narrative(rejected: Sequence[RejectedCandidate]) -> str` (or your own
   better name, but keep the "narrative"/"PUBLIC" intent clear in the name): filters to
   `reason_code == "PREDICATE_TEXT_NOT_MAPPED"`, collects `evidence_excerpt` values, deduplicates by
   exact string equality (not fuzzy — same discipline as every exact-match function in this
   subsystem), joins into one string (your call on separator — a blank line between excerpts is
   reasonable, justify your choice). Empty input -> empty string, not an error.
3. Tests: real `RejectedCandidate` fixtures (mirror this file's own dataclass fields exactly — read
   them, don't guess), covering: multiple real excerpts joined correctly; exact-duplicate excerpts
   collapsed to one; a `VALIDATION_FAILED`-reason rejection NEVER appears in the output even if its
   excerpt text would otherwise match; empty input returns empty string.
4. Live proof — the real Garibaldi case this was built for:
   - Reuse the real Task 18 pipeline (download the same Garibaldi document via `DropboxConnector`,
     same credentials pattern as every prior task, `extract_candidates()` → `build_relation_atoms()`
     → the real `rejected` tuple).
   - Call your new function on that real `rejected` tuple.
   - Assemble a `MonadDocument` exactly as Task 18 did (same `gmv_id`/`entity_type`/`canonical_name`
     for `GMV-000001` Federico Garibaldi — confirm this is still the real registered id before
     using it), but with `public_text` now set to your function's real output instead of `""`.
   - Call `materialize_monad()`, target `03_STATE/ombra/GMV-000001.md` (do not overwrite
     `GMV-000002.md`, the real Bucchi Monad — different file).
   - Read the resulting file in full. Confirm `# PUBLIC` now contains real, readable text (not
     empty), and that the `# ATOMS` table is still correctly empty (this document still has zero
     governed RELATION atoms — that has not changed, and should not be papered over).
5. Run `.venv/bin/python -m pytest tests/ -q` / `ruff check .` — confirm only the one pre-existing
   failure.

## Report back

1. Where you placed the function and why.
2. The real Garibaldi `# PUBLIC` content produced (verbatim, so it can be judged for actual
   readability — this is the whole point of the task).
3. Confirmation `# ATOMS` is still empty for this document (unchanged, not quietly fixed).
4. Test/ruff results, exact diff, `git status --short`.
5. Your own honest read: is the resulting PUBLIC text actually readable/useful prose, or just a
   disjointed pile of sentence fragments? This determines whether this approach is actually good
   enough to extend to other zero-atom documents, or needs more thought before that.
