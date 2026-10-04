# OpenCode Task 32 — Phase 4 part A: real extraction + identity proposals for 5 real artists (no confirmations, no materialization yet)

**Status: DRAFT TASK — approved plan, not yet executed.**
**This task stops BEFORE minting any new entity identity. Confirming new entities
(`confirm_new_entity()`) is a human-gated action the directing Claude session performs itself,
one artist at a time, exactly as it already did for Danilo Bucchi (`GMV-000002`) this session —
never inside an opencode task. A follow-up task (33) does final materialization once the directing
session has confirmed whichever of these 5 artists it decides to.**

## Why / context

This is Phase 4 of the approved plan (`/Users/giacomomarcovalerio/.claude/plans/velvet-snacking-corbato.md`):
a real end-to-end run on a small, named sample — not the full 46-artist archive — to get real
throughput numbers before deciding whether to scale further. Phases 0-3 are done: operating
discipline noted in `AGENTS.md`, the Garibaldi PUBLIC-text proof (Task 31), the geography filters
(Tasks 26/27/29), and the Monad backup mechanism (Task 30, `~/.gmv_backups/ombra/`).

## The 5 named artists — do not substitute, do not ask which ones to use

Reuse exactly these 5, already confirmed real and accessible in Task 28 (their real Dropbox
locators are below — use them directly, do not re-derive or guess new ones):

1. **Manuel Bonfanti** — `/gmv_master_system/01_area35_master/99_exports/mutualart_2026/02_manuel_bonfanti/biography_manuel_bonfanti.docx`
2. **Florencia Bruck** — `/gmv_master_system/01_area35_master/99_exports/mutualart_2026/03_florencia_bruck/biography_florencia_bruck.docx`
3. **Davide Genna** — `/gmv_master_system/01_area35_master/99_exports/mutualart_2026/04_davide_genna/biography_davide_genna.docx`
4. **Nicola Evangelisti** — `/gmv_master_system/01_area35_master/01_artists/evangelisti_nicola/10_md_processed_files/09_temp_import__bio evangelisti en.pdf.md`
5. **Katia Dilella** — `/gmv_master_system/01_area35_master/01_artists/dilella_katia/10_md_processed_files/09_temp_import__bio katia dilella.docx.md`

If one of these 5 genuinely fails for a real technical reason (not a judgment call — a real
download/extraction error), use ONE of these two named fallbacks, in order, and say explicitly
which one and why: **Pietro Geranzani** (`/gmv_master_system/01_area35_master/01_artists/geranzani_pietro/10_md_processed_files/07_career__01_biography__pietro geranzani bio__pietro geranzani biografia.docx.md`),
then **Barbara Colombo** (ask Task 28's own survey output under `/tmp/opencode/task28/work/` for her
locator if it still exists; if not, report that you could not recover it rather than guessing one).

## Hard constraints

1. **No `confirm_new_entity()` or `confirm_entity_alias()` calls anywhere in this task.** None of
   these 5 names exist in `00_CONFIG/gmv_entity_registry.json` today (it has only `GMV-000001`
   Federico Garibaldi and `GMV-000002` Danilo Bucchi) — every one of them will fail to resolve, and
   that is the expected, correct outcome of this task, not a problem to fix.
2. **No `materialize_monad()` calls in this task.** Without a confirmed `gmv_id`, there is nothing
   valid to materialize under — building a `MonadDocument` with an invented or placeholder
   `gmv_id` would violate `gmv_id_is_well_formed()`'s real governance and is explicitly not this
   task's job.
3. **Real queuing IS allowed and expected**: `propose_entity_identity()` +
   `append_entity_identity_proposals()` against the REAL
   `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl` — this is the one real write this
   task performs, and it is the designed "propose" half of the human-gated loop, not a registry
   mutation. Before queuing any of the 5 artist names, check the queue for an existing entry first
   (same discipline as Task 19) — do not duplicate.
4. Credentials: `~/.gmv_dropbox_oauth.json` (`refresh_token`/`app_key`/`app_secret`), same pattern
   as every prior task. `external_directory` permission is now `allow` in `opencode.json` — reading
   that file should not prompt.
5. `temperature=0, seed=42` for every real model call, same as the whole session.

## Steps

For each of the 5 (or fallback) artists, in order:

1. Download the real document via `DropboxConnector`, extract via `extract_document()`
   (`sha256_file()` for the real hash).
2. Run `extract_candidates()` → real `entities`, `propositions`.
3. Run `build_atoms()` (ATTRIBUTE-class) and `build_relation_atoms()` (RELATION-class, real
   `00_CONFIG/crawler_predicate_text_mapping.json`) — same real pipeline every prior task used.
   Record how many atoms would build, and their real predicate/subject/object values.
4. Run Task 31's real `compose_unmapped_narrative()` (`10_API/gmv_crawler_unmapped_narrative.py`)
   on the `PREDICATE_TEXT_NOT_MAPPED` rejections whose `subject_raw` matches the artist's own name
   (same filtering discipline Task 31 itself used for Garibaldi — do not include excerpts about
   OTHER entities mentioned in the same document). Record the real resulting text.
5. Call `resolve_entity_gmv_id(artist_name, registry)` against the real, current
   `gmv_entity_registry.json` — confirm it returns `None` (expected). If it unexpectedly resolves
   to something, STOP for this artist and report that exactly — do not proceed as if nothing
   happened.
6. Check the real identity-proposal queue for an existing entry for this exact name; if absent,
   call `propose_entity_identity()` + `append_entity_identity_proposals()` for real, with a real
   `source_id`/`evidence_excerpt` from this document.

## Report back

A table, one row per artist (5 or 6 rows):

| artist | atoms that would build (count + real predicate list) | PUBLIC narrative length (chars) | already in identity queue? | newly queued this run? |

Plus, for each artist: the real PUBLIC narrative text in full (so the directing session can judge
readability before deciding whether to confirm that artist's identity), and the real RELATION atom
list if any built. State plainly, per artist, whether you'd expect a materialized Monad for them to
be genuinely non-empty (atoms > 0 OR real PUBLIC text non-trivial) once their identity is
confirmed — this is the signal the directing session needs to decide which artists to confirm
next, not a decision for you to make.

`git status --short` / `git diff` for anything touched in the repo (expected: none — this task's
only real write is to the gitignored runtime queue file, not to any tracked file).
