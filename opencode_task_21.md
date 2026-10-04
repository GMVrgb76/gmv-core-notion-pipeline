# OpenCode Task 21 — verify the real Bucchi source document (local vs. Dropbox cloud), and fix a test broken by the real Bucchi registry confirmation

**Status: DRAFT TASK — approved plan, not yet executed. Delegated for implementation.**
**Do not treat anything in this file as already true of the codebase except where it says "verified".**
**This task does NOT redo Task 20's extraction/materialization. It resolves two open questions
first. A follow-up task will redo the Bucchi proof once Part A's finding is known.**

## Why this task exists

### Part A — a real, unresolved size discrepancy on the Bucchi source document

Task 20's materialized Monad (`03_STATE/ombra/GMV-000002.md`) has a SOURCES row with
`SIZE=11339`, `MODIFIED=2026-08-31T12:38:53Z`,
`HASH=b2c9df372366c708e7b736723dfd7df6b6f94b46a61270e480aa568e5f7a8fc9`. The directing Claude
session verified this independently and it matches **exactly** the file currently on the local
macOS filesystem at
`/Users/giacomomarcovalerio/Library/CloudStorage/Dropbox/GMV_MASTER_SYSTEM/01_AREA35_MASTER/01_ARTISTS/BUCCHI_Danilo/10_MD_PROCESSED_FILES/09_TEMP_IMPORT__Danilo Bucchi cat.pdf.md`
(verified via `shasum -a 256` and `ls -la` this session, same session, same machine).

But also this session, a few turns earlier, a listing of the SAME nominal path (no `/Users/.../Dropbox/`
prefix — `/GMV_MASTER_SYSTEM/01_AREA35_MASTER/01_ARTISTS/BUCCHI_Danilo/10_MD_PROCESSED_FILES/`,
run from inside your own environment) showed:
```
-rw-r--r--  1 gmv  staff  3740595 Sep 26  2026 09_TEMP_IMPORT__Danilo Bucchi cat.pdf.md
```
**3,740,595 bytes, modified Sep 26 — not 11,339 bytes, modified Aug 31.** Same filename, wildly
different size (~330x) and a different modification date, owner shown as `gmv` rather than the
real local macOS user. This is either (a) two genuinely different files/versions that happen to
share a name, (b) a stale local Dropbox sync that has not picked up a real, larger, newer cloud
version, or (c) an artifact of how paths resolve inside your own sandboxed environment vs. the
real local filesystem — the directing session does not know which, and is not guessing.

**This matters concretely**: Task 20 used a plain local filesystem read instead of
`DropboxConnector` (confirmed by the directing session: the rendered SOURCES `PATH` is a raw local
absolute path, not the lowercase Dropbox-locator style Task 18's Garibaldi proof used). If the real,
current, authoritative version of this document is the 3.7MB one, Task 20 extracted propositions
from roughly 1/330th of the real content — which would also explain why only 3 `"partecipa"`-ish
propositions surfaced this run, versus the 2026-09-26 run's 207 distinct queued names from
(presumably) the same document.

### Part B — a test broken by a real, deliberate, already-explained registry write

`tests/test_gmv_crawler_entity_resolver.py::test_no_new_function_ever_writes_the_committed_registry_file`
now fails. Root cause, already diagnosed by the directing session (verified by running this one
test in isolation and reading its source): the test's `BUCCHI` fixture constant is the literal
string `"Danilo Bucchi"`, and the test's whole premise is `propose_entity_identity(BUCCHI, ...)`
returning a real proposal (i.e., that this name is NOT YET in the registry) followed by
`confirm_new_entity(BUCCHI, "ARTIST", copy_path) == "GMV-000002"`. Since the directing session
confirmed the REAL "Danilo Bucchi" as the REAL `GMV-000002` in the committed registry (commit
`e26cbf10`, deliberate, human-confirmed, predating this task), the test's premise is now false:
`propose_entity_identity` correctly returns `None` for an already-resolved name, exactly as
documented. **This is not a pipeline defect and not something Task 20 caused** — it is a test
whose fixture silently assumed a registry state that a real, intentional commit has since changed.
Fix it, do not revert the registry.

## Hard constraints — do not exceed this scope

1. **No further writes to `00_CONFIG/gmv_entity_registry.json`.** Do not call `confirm_new_entity()`
   or `confirm_entity_alias()` against the real file in this task — Part B's fix operates on tests
   using tmp copies only, exactly as the existing test already does.
2. **Do not redo Task 20's materialization.** Do not re-run `extract_candidates()`,
   `classify_entity_types()`, `build_relation_atoms()`, or `materialize_monad()` for Bucchi in this
   task, even if Part A's finding makes it tempting — that is explicitly a follow-up task, after a
   human reviews Part A's finding.
3. **No SQL migration, no fuzzy matching, no production pipeline file changes** — same standing
   constraints as every prior task in this subsystem.
4. **Part A is read-only.** Do not modify, move, re-download-and-overwrite, or delete either the
   local file or anything on Dropbox. If a real download via `DropboxConnector` is needed to
   compare against the cloud version, write it to a `/tmp/` scratch path, never back over the real
   local file.
5. **Part B's fix must preserve the test's real intent** (prove the propose→confirm→alias cycle
   works end-to-end on a name NOT already in the registry) — do not just loosen the assertion to
   match whatever `propose_entity_identity` now returns for "Danilo Bucchi". Either (a) change the
   fixture to a different, genuinely unregistered placeholder name, updating every dependent
   assertion (e.g. the expected minted id, since the real registry now has 2 entities, not 1), or
   (b) another fix that preserves the same proof — your judgment, but state which you chose and
   why in your report.

## Steps

### Part A — resolve the real file size

1. Re-confirm the local file's real `size`/`mtime`/`sha256` right now (`ls -la` + `shasum -a 256`
   on the real path given above) — do not trust the number already cited in this brief, re-derive
   it live in case anything changed between sessions.
2. Call the REAL `DropboxConnector.metadata(locator)` (credentials from
   `~/.gmv_dropbox_oauth.json`, same convention as Task 18/20) on the Dropbox-locator form of this
   same path (strip the local `/Users/.../Dropbox/` prefix — the locator is
   `/GMV_MASTER_SYSTEM/01_AREA35_MASTER/01_ARTISTS/BUCCHI_Danilo/10_MD_PROCESSED_FILES/09_TEMP_IMPORT__Danilo Bucchi cat.pdf.md`).
   Print the real returned `size`/`modified`/whatever hash-like field it exposes, verbatim.
3. If the API's reported size differs from the local file's real size: download the real content
   via the Dropbox API (not the local filesystem) to a `/tmp/` scratch path, compute its real
   `sha256`, and report whether it matches the content you earlier saw cited as 3,740,595 bytes /
   Sep 26, or is something else again. Do not assume — derive.
4. If the API and local filesystem report the SAME size/content: say so plainly, and give your own
   best-effort account of where the earlier 3.7MB/Sep-26 listing could have come from (e.g. a
   different user/sandbox view, a different path that only looks identical) — but label this
   explicitly as your own inference if you cannot verify it directly, not as a verified fact.
5. State a clear conclusion: which version (if they differ) is the one any future real extraction
   of this document should use, and why.

### Part B — fix the broken test

1. `grep -n "BUCCHI\b" tests/test_gmv_crawler_entity_resolver.py` — find every line that
   references the constant, not just the one in the failing test, so a fix does not leave a second
   place silently inconsistent.
2. Apply your chosen fix (see constraint 5). If you rename the fixture, pick a name that is
   obviously synthetic/not a real person (so a future real confirmation of an actual artist by that
   name can never collide with this test again) and update every dependent assertion (expected
   minted `gmv_id` etc.) to match the CURRENT real registry state (2 real entities committed:
   `GMV-000001` Federico Garibaldi, `GMV-000002` Danilo Bucchi — so a fresh unregistered-name
   confirmation in a test copy should mint `GMV-000003`, not `GMV-000002`).
3. Run `.venv/bin/python -m pytest tests/ -q`. Confirm it returns to showing only the ONE
   pre-existing, unrelated failure (`tests/security/test_runtime_git_policy.py::test_current_tracked_tree_passes_policy`)
   — nothing else new or missing.
4. `ruff check .` — confirm clean.

## What to report back when done

1. Part A's real findings, verbatim: local file's live-re-derived size/mtime/hash, the real
   `DropboxConnector.metadata()` response, and (if a download was needed) the downloaded content's
   real hash and your conclusion about which version is authoritative.
2. Part B's exact diff (`git diff` for the test file only — nothing else should change), and
   confirmation of the full pytest result (back to exactly one known failure).
3. Your own honest read on whether Task 20's already-materialized `03_STATE/ombra/GMV-000002.md`
   should now be considered unreliable (built from a stale/truncated document) and worth redoing,
   or whether Part A's finding clears it — do not decide to redo it yourself either way; that is
   the next, separate, explicit task.
4. `git status --short` outside the test file — expected empty.
