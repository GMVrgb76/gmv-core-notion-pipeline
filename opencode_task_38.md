# OpenCode Task 38 — stop gating the Notion canon export on GMV registry resolution; export ALL real Area35 Notion pages

**Status: DRAFT TASK — deliberate redesign of Task 37's behavior, approved by the human.**

## Why

Task 37 (`10_API/gmv_notion_canon_export.py`, commit `d73b8a40`) deliberately wrote a canon file
ONLY when a Notion page's name resolved to an entity already confirmed in
`00_CONFIG/gmv_entity_registry.json` — correct for a "compare Notion vs Monad for the same entity"
use case, which is what that brief asked for. Real result: of 442 real pages across Area35's six
Notion data sources, only 6 resolved (the registry currently has exactly 7 entities, all type
ARTIST, and one of them — Bucchi — has no Notion page at all).

**The human has now explicitly said this is the wrong goal.** They want every real Area35 Notion
page archived into GBrain, full stop — the pages are the gallery's own research (built from the
Dropbox archive plus independent web cross-checking), considered valid on their own terms, and NOT
meant to be gated behind whether GMV Core's much-smaller, much-slower-growing entity registry has
caught up to them. Waiting for registry growth to unlock coverage is explicitly not acceptable to
them.

**This is a redesign, not a bug fix.** Update Task 37's docstring and tests to describe the new
intended behavior plainly — do not frame the old gate as a bug that was "fixed"; it was correct for
the question it was built to answer, which has now changed.

## What changes, concretely

1. **Every real Notion page gets a canon file written. No page is skipped for lack of a registry
   match.** Registry resolution becomes enrichment, never a gate.
2. **Filename changes from `<gmv_id>.md` to `<notion_page_id>.md`, for every page, uniformly** —
   `gmv_id` is not always available, `source_notion_page_id` always is. Re-run the full export so
   the existing 6 `GMV-00000N.md` files are replaced by their `<page_id>.md` equivalents (same
   content, new filename) — do not leave two files for the same page under two different names.
3. **Frontmatter**: keep `gmv_id` / `canonical_name` / `entity_type` as OPTIONAL fields, present only
   when `resolve_entity_gmv_id()` actually matched — omit them entirely otherwise (not `null`, not
   empty string: absent). Add `notion_kind` carrying the RAW Notion data-source label verbatim as
   it appears in `config.json`'s `entita` key (e.g. `artista`, `mostra`, `persona`, `istituzione`,
   `opera`, `sponsor`) for every page, resolved or not. **Do not invent a mapping from this raw label
   to the governed `entity_type` vocabulary (ARTIST/EXHIBITION/...)** — Task 37 already correctly
   flagged that mapping as a Group B decision not made; this task does not make it either. Required
   fields for every file: `schema: GMV_NOTION_CANON_SNAPSHOT_V1`, `status: canon_unaudited`,
   `source_notion_page_id`, `notion_kind`, `exported_at`. `notion_title` (the page's real title,
   never the "(senza titolo) <id>" placeholder — reuse Task 37's existing handling of that) is also
   required, since without a `gmv_id`/`canonical_name` it is the only human-readable identifier most
   files will have.
4. **Still propose unresolved names to the identity queue, but as a side effect, never a gate.**
   `append_entity_identity_proposals()` (the real shared queue path, not Task 37's proof-run temp
   queue) still gets called for names that don't resolve — this keeps the registry-growth path alive
   for later — but a proposal being queued must never prevent the canon file from being written.
5. **Run across ALL SIX real Notion data sources in one pass**, not just `artista` (Task 37's proof
   run scope) — confirm the real current page count across all six before writing anything (expect
   roughly 442 per Task 37's own count, but re-derive it, don't trust last week's number blindly).
6. **Destination stays `03_STATE/area35_canon/`** — same governance class already established
   (never-Git, inherited from `03_STATE/`), no change needed there.

## Hard constraints (unchanged from Task 37, still apply)

1. **The EIC-10 hard wall is unchanged**: no import of any Monad/atom/ledger module in this
   exporter, still pinned by the existing ast-scan test plus the atomic_write_text path-recording
   test. This redesign does not touch the Monad pipeline's relationship to this data at all — it
   only changes who the exporter is willing to write a file FOR.
2. **Do not touch GBrain or the morning-sync script.** Once this task lands and is reviewed, the
   directing Claude session will re-run the existing `~/.gmv_scripts/gbrain_morning_sync.sh`
   manually to pick up the full export — that is out of scope for you here.
3. **Credentials**: same real ones Task 37 already found and used
   (`~/.config/area35-qa/notion_token`, `~/.gmv_core/area35-qa/config.json`) — confirm they still
   work, do not re-derive from scratch.
4. **Keep the existing atomic-write / 0700-dir / 0600-file permission discipline** Task 37 already
   established — no regression there.

## Steps

1. Read the real current `10_API/gmv_notion_canon_export.py` and `tests/test_gmv_notion_canon_export.py`
   in full (not from memory of Task 37's commit message — read the actual current file, it is the
   only source of truth).
2. Change `export_notion_page_to_canon()` (or whatever the real current function boundary is) so
   resolution failure no longer returns a no-file result — it writes the file with the reduced
   frontmatter (constraint 3) and still returns/propagates the `EntityIdentityProposal` for the
   caller to queue. Change `main()` to call the REAL shared `append_entity_identity_proposals()`
   path by default (constraint 4), not a temp/test-only queue.
3. Add `notion_kind` extraction from the real `config.json` `entita` structure (confirm its real
   shape before coding — Task 37's own commit message describes `entita`, re-verify it directly).
4. Update/replace Task 37's tests to match the new contract: a resolved-entity page still gets
   `gmv_id`/`canonical_name`/`entity_type` in frontmatter; an unresolved one gets a file too, with
   those three fields absent and `notion_kind` present; a test proving a proposal is queued AND a
   file is written in the same run for the same unresolved page (not one-or-the-other); the existing
   EIC-10 non-interference test stays, unchanged in spirit.
5. Live proof: run the real exporter across all six real Notion data sources. Report the real total
   page count found, how many resolved to a `gmv_id` (expect ~6, confirm), how many did not, and
   confirm `03_STATE/area35_canon/` now contains one file per real page with no duplicates and no
   silently-skipped page. Explicitly check: are there any two distinct real Notion pages that would
   collide on the same `source_notion_page_id`-derived filename? (Should be impossible by
   construction, but confirm empirically on the real run rather than assuming.)
6. Clean up the old `GMV-00000N.md` files in `03_STATE/area35_canon/` left over from Task 37's run
   if the new run does not naturally replace them (confirm whether it does; if the 6 old files would
   otherwise linger alongside their `<page_id>.md` replacements as duplicates, remove the stale
   `GMV-00000N.md` ones explicitly and say so in your report).
7. Run `.venv/bin/python -m pytest tests/ -q` / `ruff check .` — report results and compare against
   the known baseline (1 pre-existing `test_runtime_git_policy.py` failure; confirm the count of
   `personal_absolute_path` findings is unchanged by this task, same discipline as Task 35/37).

## Report back

1. Real total page count across all six data sources, and the real resolved/unresolved split.
2. The exact new frontmatter shape produced for one resolved and one unresolved example (real
   content, not paraphrased).
3. Confirmation the old `GMV-00000N.md` files were handled (replaced or explicitly removed) with no
   duplicates left behind.
4. Confirmation proposals were queued to the real shared queue (count of new lines appended to
   `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl`, or wherever `append_entity_identity_proposals()`
   really writes — confirm the real path).
5. Test/ruff results, exact diff, `git status --short`.
