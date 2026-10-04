# OpenCode Task 33 — Phase 4 part B: materialize the 5 confirmed artists, close the plan's exit criterion

**Status: DRAFT TASK — approved plan, not yet executed.**

## Context — what changed since Task 32

The directing Claude session reviewed Task 32's report and confirmed all 5 artists as real
entities (commit `c5efcf42`): `GMV-000003` Manuel Bonfanti, `GMV-000004` Florencia Bruck (alias
`Florencia S.M. Brück` — her own document's spelling; `Florencia Bruck` is the real roster's
canonical form, verified before choosing), `GMV-000005` Davide Genna, `GMV-000006` Nicola
Evangelisti, `GMV-000007` Katia Dilella. `00_CONFIG/gmv_entity_registry.json` now has 7 entities
total. This task finishes Phase 4: materialize a real Monad for each, back them up, and report
the real pass/fail count against the plan's own exit criterion (≥3 of 5 genuinely non-empty).

## Hard constraints

1. **Re-derive everything live — do not reuse any cached/remembered numbers from Task 32's
   report.** Re-download each document, re-run extraction/atom-building/narrative composition
   fresh. Task 32's own PUBLIC text/atom counts are a prior reading, not a guarantee this run
   reproduces identically (same non-determinism caveat as every prior task this session).
2. **No further registry writes.** All 5 identities are already confirmed — do not call
   `confirm_new_entity()`/`confirm_entity_alias()` again this task.
3. **Do not overwrite `GMV-000001.md` or `GMV-000002.md`** (Garibaldi/Bucchi, from Tasks 31/20) —
   different files, different artists.
4. Same credentials/determinism/timeout conventions as Task 32 (`~/.gmv_dropbox_oauth.json`,
   `temperature=0, seed=42`, raise `timeout` per-call if a real `TIMEOUT` occurs — do not change
   any production default to do this).
5. **If `materialize_monad()` raises `MonadMaterializationError` for any artist, report the full
   blocker list verbatim and move to the next artist — do not skip silently, do not work around
   the validation.**

## Steps

For each of the 5 confirmed artists (same 5 locators as Task 32 — reuse them, they are already
real and verified):

1. Download, extract, `extract_candidates()`, `build_atoms()` + `build_relation_atoms()` — same
   real pipeline.
2. `compose_unmapped_narrative()` (`10_API/gmv_crawler_unmapped_narrative.py`, Task 31) on the
   `PREDICATE_TEXT_NOT_MAPPED` rejections whose `subject_raw` resolves to this artist's own
   `gmv_id` via `resolve_entity_gmv_id()` against the CURRENT real registry (it now has 7 entities
   — confirm each artist actually resolves this time, unlike Task 32 where all 5 correctly
   returned `None`).
3. Assemble a `MonadDocument`: real `gmv_id`/`entity_type`/`canonical_name` from the registry entry
   (not from this brief — read the real file), `status="active"`, real atoms, real `public_text`,
   one real `SourceManifestEntry` (same shape as Tasks 18/20/31: real size/modified/hash via
   `DropboxConnector.metadata()`, `epistemic_level="UNVERIFIED_PLACEHOLDER"`,
   `extraction_status="SUCCESS"`).
4. `materialize_monad(document, target_path=Path("03_STATE/ombra/<real-gmv-id>.md"))`.
5. After all 5: run the real backup script from Task 30 (`10_API/gmv_monad_backup.py`) for real,
   confirm all 7 Monads (2 pre-existing + 5 new) are now mirrored in `~/.gmv_backups/ombra/` with
   matching hashes.
6. Run `.venv/bin/python -m pytest tests/ -q` / `ruff check .` — confirm only the one pre-existing
   failure.

## Report back

1. Per artist: materialized successfully (y/n), real atom count + list, real PUBLIC character
   count, and if it failed, the exact `MonadMaterializationError` blocker list.
2. **The plan's exit criterion, answered explicitly**: how many of the 5 produced a genuinely
   non-empty Monad (atoms > 0 OR real non-trivial PUBLIC text)? Is it ≥ 3?
3. Confirmation all 7 Monads are now backed up (step 5), with hash comparison.
4. Any discrepancy between this run's real numbers and Task 32's report (expected, given model
   non-determinism — report it plainly, do not paper over a difference).
5. Test/ruff results, `git status --short` (expected: no tracked files changed — only the 5 new
   gitignored `03_STATE/ombra/*.md` files and their backups).
