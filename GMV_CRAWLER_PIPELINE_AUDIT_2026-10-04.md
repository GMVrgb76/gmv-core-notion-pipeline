# GMV Crawler — full pipeline audit, 2026-10-04

**Scope**: read-only audit of who calls whom in the GMV Crawler subsystem, to
establish where a future "push materialized Monads into GBrain" step could
attach. **No production file was modified.** This document is the only file
created by this task. Every "X calls Y" claim below was grounded in a real
grep/import/file-read performed during this session; where a docstring
disagrees with the code, that disagreement is reported explicitly in §7
rather than silently resolved.

**Method note / limitation, stated up front**: this audit establishes call
graph and trigger reality from the repository and from the operator's own
runtime artifacts. It cannot see inside the external GBrain MCP service. The
brief's premise that GBrain "has been pointed at `03_STATE/ombra/*.md`" is
**not verifiable from inside this worktree** — see §6, which reports what
was actually found instead.

---

## 1. Repo state at the time of this audit

`git log --oneline -20` (verbatim, most recent first, at session start):

```
c5efcf42 feat: confirm 5 real artists from Task 32's identity proposals (GMV-000003..007)
20d891e3 Task 30: standalone backup for materialized Monads
72dd637a Task 31: route PREDICATE_TEXT_NOT_MAPPED rejections into Monad # PUBLIC
9616c3b1 feat: filter ISO 3166-1 countries out of the identity-proposal queue
7ed59289 test: add the two orchestrator tests Task 27 left uncommitted
99fd6799 feat: filter known generic places out of the identity-proposal queue
57287cc0 fix: repair entity-resolver test broken by the real Bucchi registry confirmation
e26cbf10 feat: confirm Danilo Bucchi as GMV-000002 (ARTIST)
3f4cf00a feat: rescue "medium, dimensions" captions into atoms, propose WORK-subject identity
6d1a2a06 feat: register dimensions/medium/creation_year ATTRIBUTE predicates, widen BUILD ATOMS to string-range literals
f89e0a35 feat: wire real identity-proposal generation into the crawler pipeline
1b2ba0a1 feat: expose the identity propose/confirm loop in the Open WebUI review tool
d662bf37 feat: build the propose/confirm identity-resolution loop, human-gated
2d8e6e97 docs: record design decisions 7-8 -- registry columns, reconcile() ordering
9d1b435d docs: record design decision -- sensitivity classification lives on SOURCES
d4af1cb5 docs: record design decision -- VISIBILITY is a closed PUBLIC/INTERNAL vocabulary
19896528 docs: record design decision -- epistemic_level reuses ARCHIVE/WEB
e2d17d54 docs: record design decision -- registry writes stay human-confirmed
ef2a82c9 docs: record design decision -- entity matching is two deferred layers
a3090bbd docs: record design decision -- gmv_id assigned at first sighting
f6c295f4 docs: record design decision -- gmv_id sequence has no separate counter state
023b7f2d docs: record design decision -- gmv_id generation is sequential
```

Branch: `worktree-bridge-cse_01EFSz2nNresRvPh9GbfwwzK`.

**Today's concurrent session (Fase 0-4) is fully COMMITTED, not
working-tree.** All of it is in the history above: `9616c3b1` (Fase: ISO
3166-1 country filter), `20d891e3` (Task 30 backup), `72dd637a` (Task 31
unmapped narrative), `c5efcf42` (Fase 4: five confirmed artists). Real file
mtimes agree with the commit times (`10_API/gmv_crawler_unmapped_narrative.py`
18:34 vs commit 18:39; `10_API/gmv_monad_backup.py` 18:58 vs commit 19:15;
`10_API/gmv_crawler_entity_resolver.py` 15:26 vs commit 15:59).

**The working tree moved under this audit, and the reader must know it.**
`git status --short` at session start showed `M AGENTS.md`, `M opencode.json`
and 24 untracked `opencode_task_*.md`. Partway through this session a
concurrent session committed both:

```
5064d510 2026-10-04 22:47:52 +0200 docs: add narration-must-be-real-tool-calls rule; allow external_directory reads
4af8d807 2026-10-04 22:48:10 +0200 docs: add opencode task briefs 12-35 (never previously committed)
```

At the moment this report was written, `git rev-parse HEAD` =
`4af8d8073711d410b012f153de1869a6a0dc46cf` and `git status --short` shows
only `?? opencode_task_14_verify.py`, `?? opencode_task_15_verify.py`,
`?? opencode_task_16_verify.py`. This has one concrete, checkable
consequence, reported in §8.

---

## 2. Component table

Every "real callers" cell is from a `grep -rn` over the whole repository
(excluding `__pycache__`), cross-checked against the real import statements.
"Real trigger" is from launchd plists, `crontab -l`, the Open WebUI tool DB,
or from filesystem evidence of an ad-hoc run.

| File | Key function(s) | Real callers (grep-confirmed) | Real trigger | Writes to |
|---|---|---|---|---|
| `automation/com.gmv.crawler.nightly.plist` + `~/Library/LaunchAgents/com.gmv.crawler.nightly.plist` | launchd `StartCalendarInterval` 03:00 | `launchctl list` shows `com.gmv.crawler.nightly` loaded (exit 0) | 03:00 local, daily. **Verified firing**: `run_log.jsonl` has `run_complete` at `2026-10-02T01:00:03Z`, `2026-10-03T01:00:05Z`, `2026-10-04T01:00:01Z` (01:00Z = 03:00 CEST) | nothing directly; execs `run_nightly.sh` |
| `automation/run_nightly.sh` | bash wrapper: reads `~/.gmv_dropbox_oauth.json`, `exec python3 automation/gmv_crawler_nightly_run.py` | only the plist (`ProgramArguments`) | launchd 03:00 | nothing |
| `automation/gmv_crawler_nightly_run.py` | `main()`:385, `process_one_folder()`:209 | the plist→`run_nightly.sh`; and `automation/gmv_crawler_review_tool.py::run_crawler_now()`:83 which `subprocess.Popen`s `run_nightly.sh` | launchd 03:00 **or** Open WebUI tool call | `01_RUNTIME/gmv_crawler/`: `registry.db`, `rejection_queue.jsonl`, `entity_proposal_queue.jsonl`, `entity_identity_proposal_queue.jsonl`, `atoms_built.jsonl`, `price_log.jsonl`, `contract_log.jsonl`, `run_log.jsonl`, `processed_content_hashes.json`, `current_run.pid` |
| `automation/gmv_crawler_review_tool.py` (committed copy) | 19 methods incl. `run_crawler_now`:83, `run_crawler_on_files`:114, `check_last_run_status`:226, `list_pending_entity_identities`:300, `confirm_new_entity`:394, `confirm_entity_alias`:415 | **executed from the Open WebUI DB copy, not this file** — see §3 | Open WebUI chat tool invocation | same runtime dir as above (minus `registry.db`, `run_log.jsonl` writes) |
| `10_API/gmv_crawler_extractor.py` | `extract_document()`, `ExtractionDocument` | `gmv_crawler_nightly_run.py`:52, `gmv_crawler_review_tool.py`:146 | nightly + tool | nothing |
| `10_API/gmv_crawler_orchestrator.py` | `process_document()`:196 | `gmv_crawler_nightly_run.py`:53/288, `gmv_crawler_review_tool.py`:147/190 | nightly + tool | **nothing** — pure function, returns tuples |
| `10_API/gmv_crawler_document_classifier.py` | `classify_document()`:74 | `gmv_crawler_orchestrator.py`:112/384 | inside `process_document` | nothing |
| `10_API/gmv_crawler_candidate_extractor.py` | `extract_candidates()`:243 | `gmv_crawler_orchestrator.py`:101/401 | inside `process_document` | nothing |
| `10_API/gmv_crawler_atom_builder.py` | `build_atoms()`:336 | `gmv_crawler_orchestrator.py`:93/451 and again :474 (caption rescue) | inside `process_document` | nothing |
| `10_API/gmv_crawler_caption_predicate_splitter.py` | `split_medium_dimensions_captions()` | `gmv_crawler_orchestrator.py`:97/464 | inside `process_document` | nothing |
| `10_API/gmv_crawler_relation_atom_builder.py` | `build_relation_atoms()`:205 | `gmv_crawler_orchestrator.py`:128/554 | inside `process_document` | nothing |
| `10_API/gmv_crawler_entity_resolver.py` | `resolve_entity_gmv_id()`:474, `propose_entity_identity()`:670, `next_sequential_gmv_id()`:757, `confirm_new_entity()`:857, `confirm_entity_alias()`:980, `_load_known_artists()`:247, `_load_known_institutions()`:260, `_load_known_places()`:1068, `_is_known_country()`:1163 | reads: `gmv_crawler_orchestrator.py`:113/416-419; writes: **only** `automation/gmv_crawler_review_tool.py`:407/425 (via the Open WebUI tool) | reads: nightly + tool, per document; **writes: Open WebUI tool only, human-gated** | reads `00_CONFIG/{area35_known_artists,area35_known_institutions,area35_known_places,gmv_entity_registry}.json`; writes only `gmv_entity_registry.json` |
| `10_API/gmv_crawler_rejection_queue.py` | `append_rejected()`:55, `summarize_rejection_queue()`:86 | `gmv_crawler_nightly_run.py`:55/320, `gmv_crawler_review_tool.py`:148/210 | nightly + tool | `rejection_queue.jsonl` (append) |
| `10_API/gmv_crawler_entity_proposal_queue.py` | `append_entity_proposals()`:84 | `gmv_crawler_nightly_run.py`:56/322, `gmv_crawler_review_tool.py`:149/211 | nightly + tool | `entity_proposal_queue.jsonl` (append) |
| `10_API/gmv_crawler_entity_identity_proposal_queue.py` | `append_entity_identity_proposals()`:102 | `gmv_crawler_nightly_run.py`:57/333 | nightly **only** — `gmv_crawler_review_tool.py::run_crawler_on_files()` does **not** import it (see §8) | `entity_identity_proposal_queue.jsonl` (append) |
| `10_API/gmv_crawler_registry.py` | `register_scan()`:190 | `gmv_crawler_nightly_run.py`:54/224 | nightly only | `registry.db` (`crawler_source_registry`) |
| `10_API/gmv_crawler_unmapped_narrative.py` | `compose_unmapped_narrative()`:218 | **ZERO production callers.** Only `tests/test_gmv_crawler_unmapped_narrative.py` and two ad-hoc scripts (§4) | none wired | nothing (pure function) |
| `10_API/gmv_crawler_public_projector.py` | `project_public()`:281 | **ZERO production callers** outside its own module | none wired | nothing |
| `10_API/gmv_monad_materializer.py` | `materialize_monad()`:427, `render_monad_markdown()` | **ZERO production callers.** Only `tests/test_gmv_monad_materializer.py`, `tests/test_gmv_monad_backup.py`, and ad-hoc scripts (§4) | none wired | `target_path` supplied by caller → in practice `03_STATE/ombra/GMV-<id>.md` |
| `10_API/gmv_monad_backup.py` | `backup_materialized_monads()`:164, `default_backup_dir()`:156, `main()`:204 | **ZERO production callers.** Only `tests/test_gmv_monad_backup.py` + manual CLI invocation | **manual only** (`python3 10_API/gmv_monad_backup.py`) | `~/.gmv_backups/ombra/*.md` |
| `10_API/secure_storage.py` | `atomic_write_text()`:55 | `gmv_monad_materializer.py`:116/442, `gmv_monad_backup.py`:134/199, `backup_service.py` | via its callers | 0700 dir / 0600 file, tempfile+`os.replace` |

### 2.1 `process_document()` — verified composition order

Read in full at `10_API/gmv_crawler_orchestrator.py:196-611`. Actual order:

1. `:384` `classify_document(...)`
2. `:386-397` if `document_type == "price_list"`: `extract_price_entries(...)` and **return early** — nothing below runs for a price list.
3. `:401` `extract_candidates(...)` → `(entities, propositions, extraction_rejected)`
4. `:416-419` `_load_entity_registry()`, `_load_known_places()`; `:436` filter `entities` by known-places + ISO 3166-1 country; `:442` `propose_entity_identity(...)` per surviving entity → identity proposals source (a)
5. `:451` `build_atoms(propositions, now=now)` → ATTRIBUTE atoms
6. `:464` `split_medium_dimensions_captions(...)`; `:474` second `build_atoms()` on the synthetic propositions only if non-empty
7. `:519` WORK-domain subject proposals via the ontology registry's declared `domain == ["WORK"]` → identity proposals source (b); `:535` `propose_entity_identity(..., suggested_entity_type="WORK")`
8. `:552-563` `build_relation_atoms(...)` **only on propositions whose `extraction_claim_ref` is in `rejected_refs` and not rescued**; skipped entirely when that set is empty
9. `:571-590` `extract_contract_summary(...)` only when `document_type == "contract"`, wrapped in `try/except (OllamaResponseError, EvidenceError)`
10. `:592-601` return `ProcessDocumentResult`

**What `process_document()` does NOT call** (each verified by grep over the
whole repo, not by reading the docstring): it does not call
`compose_unmapped_narrative()`, `project_public()`, `materialize_monad()`,
`backup_materialized_monads()`, any `append_*` queue writer,
`register_scan()`, `confirm_new_entity()` or `confirm_entity_alias()`. It is
a pure function from one `ExtractionDocument` to one result dataclass. The
orchestrator's own module docstring at `:48` says "nothing here ever calls
`confirm_new_entity()`/`confirm_entity_alias()`" — **that claim is confirmed
by grep.**

### 2.2 The ungoverned-text path (`gmv_crawler_unmapped_narrative.py`)

`compose_unmapped_narrative()` (`:218`) is **not** invoked inside
`process_document()`. Confirmed three ways: (a) `process_document()` has no
import of the module (imports listed at `gmv_crawler_orchestrator.py:88-132`,
checked individually); (b) repo-wide grep for `gmv_crawler_unmapped_narrative`
returns only the module itself and `tests/test_gmv_crawler_unmapped_narrative.py:32`; (c) the only non-test callers are the two ad-hoc scripts in §4.

Relationship to `gmv_monad_materializer.py`'s `# PUBLIC` section, as the
module's own docstring states and as the code confirms: `public_text` is a
plain caller-supplied string on `MonadDocument`, written verbatim by
`atomic_write_text(target_path, render_monad_markdown(document))`
(`gmv_monad_materializer.py:442`). `compose_unmapped_narrative()` is one
*possible* producer of that string — an alternative input class to
`project_public()` — but the two have never been composed by any committed
code. `project_public()` likewise has zero production callers.

---

## 3. Trigger paths, all of them

### (a) 3am launchd cron — live, firing, and producing nothing new

`~/Library/LaunchAgents/com.gmv.crawler.nightly.plist` points at this
worktree's `automation/run_nightly.sh` (absolute worktree path, confirmed by
reading the plist). `launchctl list | grep gmv` shows
`com.gmv.crawler.nightly` loaded. `crontab -l` → "no crontab".

`run_log.jsonl` has 22 `run_complete` events. The last three:

```
{'event': 'run_complete', 'at': '2026-10-02T01:00:03Z', 'files_processed': 0, 'atoms_built': 0, 'needing_review': 0, 'scan_failed': False}
{'event': 'run_complete', 'at': '2026-10-03T01:00:05Z', 'files_processed': 0, 'atoms_built': 0, 'needing_review': 0, 'scan_failed': False}
{'event': 'run_complete', 'at': '2026-10-04T01:00:01Z', 'files_processed': 0, 'atoms_built': 0, 'needing_review': 0, 'scan_failed': False}
```

**The nightly path runs successfully and has built zero atoms every night
since at least 2026-09-26.** `01_RUNTIME/gmv_crawler/atoms_built.jsonl` is
**0 bytes** and `entity_proposal_queue.jsonl` is **0 bytes**. Reason, from
the code at `gmv_crawler_nightly_run.py:235-238`: every registry row whose
`content_hash` is already in `processed_content_hashes.json` (555 entries) is
skipped. `registry.db` shows 3513 rows, all `UNCHANGED` (3194) or `MOVED`
(319), across 50 connectors (= `ARTIST_FOLDERS`: 4 `MUTUALART_2026` exports +
46 roster names). So the nightly is a *change detector that currently detects
no change* — it cannot produce a Monad today even in principle, because it
never reaches `materialize_monad()` (§2).

Note on `run_complete`'s `at` field: `main()` captures `now = now_iso()` once
at `:400` and reuses it at `:416`, so the logged timestamp is the run's
**start**, not its end. `registry.db` and `run_log.jsonl` both have mtime
`2026-10-04 04:15:52 +0200` while the logged start is `01:00:01Z` (= 03:00
local), i.e. that run took ~1h15m. Inferred from mtimes, not measured.

### (b) Open WebUI "GMV Crawler Review" tool

Read directly from `~/gmv_openwebui/data/webui.db`, table `tool`, row id
`gmv_crawler_review` / name `GMV Crawler Review` (user
`bfaea9fb-…`, `created_at` 2026-09-18T11:30:30, `updated_at`
2026-09-26T15:31:04). The stored `content` column is 38593 bytes of Python;
the committed `automation/gmv_crawler_review_tool.py` is 37321 bytes.

**They are functionally identical.** Both define the same 19 functions; the
DB `specs` array lists 18 of them and every one exists in the committed file
(`_running_pid` is the only extra, and it is intentionally not exposed as a
tool). A whitespace-stripped, character-level `difflib` comparison of the two
sources yields **only** 14 insertions, every one of them a `(`/`)`, `,` or
space added by a formatter — zero semantic differences. So the DB copy is a
black-reformatted snapshot of the committed file, taken ~30 minutes after
commit `1b2ba0a1` (2026-09-26 15:01:35) added the identity propose/confirm
loop. **Anyone editing `automation/gmv_crawler_review_tool.py` today must
re-upload it into `webui.db`; the running tool is the DB copy, and editing
the repo file alone changes nothing until the DB row is updated.** I did not
touch the DB.

Two distinct entry points in that tool, and they are **not** equivalent:

- `run_crawler_now()`:83 — `subprocess.Popen`s `run_nightly.sh` exactly like
  launchd does, so it inherits path (a) in full, including the
  `atoms_built`/`registry.db` behaviour.
- `run_crawler_on_files()`:114 — re-processes specific Dropbox locators
  in-process. It calls `extract_document` → `process_document` and appends to
  `rejection_queue.jsonl` and `entity_proposal_queue.jsonl`
  (`:210-212`) but **does not** call `append_entity_identity_proposals()`,
  and **does not** touch `registry.db`. So a per-file rerun from chat
  silently loses identity proposals that the nightly run would have queued.

### (c) Ad-hoc / manual / delegated-task paths — the only real Monad producers

All seven files in `03_STATE/ombra/` were produced this way. Evidence is a
combination of real file mtimes, real scripts on disk, and a read-only query
of `~/.local/share/opencode/opencode.db` (table `part`) for the tool calls
that wrote them:

| Monad file | mtime | Real producer |
|---|---|---|
| `GMV-000001.md` | 2026-10-04 18:36 | `$TMPDIR/opencode/task31/live_proof.py` — `TARGET = REPO/"03_STATE"/"ombra"/"GMV-000001.md"` (line 34), `materialize_monad(document_md, target_path=TARGET)` (line 164). Session DB confirms the script was written 18:31 and run 18:35-18:36. |
| `GMV-000002.md` | 2026-10-04 16:09 | **Origin of the current mtime not established.** The file's content originates from Task 20's `/tmp/task20_*.py` heredoc scripts on 2026-10-02 (16 of them reference `GMV-000002`; `/tmp/task20_monad_final.py:97-99` has `out = REPO_ROOT/"03_STATE"/"ombra"/"GMV-000002.md"` + `materialize_monad(doc_monad, target_path=out)`). A targeted query of the session DB for any tool call mentioning `ombra` between 15:30 and 17:10 on 2026-10-04 found **reads only** (three `read` calls on the file/dir, plus unrelated files) and **no write**. So either it was rewritten by something outside the opencode session record (a Claude Code session is possible — `~/.claude/projects/` has worktree logs), or the mtime reflects an unexplained touch. **Flagged as unresolved rather than guessed.** |
| `GMV-000003.md` … `GMV-000007.md` | 2026-10-04 20:37-20:51 | `$TMPDIR/opencode/task33/run.py` — imports `materialize_monad` (line 40), `OMBRA = REPO/"03_STATE"/"ombra"` (line 43), `materialize_monad(doc_md, target_path=target)` (line 242). |

All three scripts are **outside the repository**, unversioned, and were run
by hand. Task 32's `pass1.py`/`pass2.py` explicitly document in their own
docstrings that they do *not* call `materialize_monad()`.

---

## 4. Every path that can create or modify a file under `03_STATE/ombra/`

Per the brief's constraint 8. Repo-wide grep for `materialize_monad` (all
`*.py`) returns, outside the module's own docstrings: the module itself, two
docstring mentions in `gmv_crawler_public_projector.py`, two in
`gmv_crawler_unmapped_narrative.py`, two in `gmv_monad_backup.py`, and the
test files. There is **no** committed non-test caller anywhere.

The complete list of real producers today:

1. **`$TMPDIR/opencode/task31/live_proof.py`** — creates/overwrites `GMV-000001.md`. Manual, one-shot, already run.
2. **`$TMPDIR/opencode/task33/run.py`** — creates/overwrites `GMV-000003..007.md`. Manual, one-shot, already run.
3. **`/tmp/task20_*.py`** (16 variants, 2026-10-02) — creates/overwrites `GMV-000002.md`. Manual, one-shot, already run; current mtime origin unresolved (§3c).
4. **A human (or any future script) calling `materialize_monad(doc, target_path=…)` directly** — the primitive itself. Reusable, tested, idempotent (`tests/test_gmv_monad_materializer.py:344`), and deliberately takes `target_path` from the caller rather than hardcoding `03_STATE/ombra/` (`gmv_monad_materializer.py:53-60`).
5. **`tests/test_gmv_monad_backup.py`** and **`tests/test_gmv_monad_materializer.py`** — write only under pytest `tmp_path`, never the real directory (the `tests/conftest.py` autouse `isolated_gmv` fixture also redirects `HOME`).

Paths that **cannot** touch the Ombra, verified:

- The 3am nightly job, end to end. `materialize_monad` never appears in `gmv_crawler_nightly_run.py`, and the script's only file writes are the `01_RUNTIME/gmv_crawler/*` artifacts listed in §2. **The directing session's belief is CONFIRMED: `automation/gmv_crawler_nightly_run.py` does not call it.**
- `automation/gmv_crawler_review_tool.py`, in either entry point (same grep).
- `10_API/gmv_monad_backup.py` — reads the Ombra, writes only `~/.gmv_backups/ombra/`. It never writes back.
- The `com.gmv.backup` launchd job at 03:00. `~/Library/LaunchAgents/com.gmv.backup.plist` execs `~/.gmv_core/12_SCHEDULER/run_backup.sh`, whose entire body is `backup_service.py create --core ~/.gmv_core --root ~/.gmv_backups`. `grep -rn "ombra"` over `12_SCHEDULER/` and `scripts/` returns nothing, and `backup_service.py` backs up `09_DATABASE/GMV.db` plus a `git archive HEAD` tarball — `03_STATE/` is "never Git", so it is structurally outside that tarball. **The Ombra has no scheduled backup.**
- `11_CLI/gmv` — grep for `crawler|monad|ombra` across `11_CLI/` returns nothing.

`03_STATE/ombra/` is governed: `00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md:51-52`
classifies `03_STATE/` and `03_STATE/ombra/` as "Live state / Runtime state
owner / Full-system backup after S002-20; never Git".

---

## 5. Registry DB, queues, backup destination — current real state

**`01_RUNTIME/gmv_crawler/registry.db`** (2154496 bytes, mtime 2026-10-04
04:15:52). The brief's "0 rows everywhere" (2026-10-02) is **no longer
true**:

| table | rows |
|---|---|
| `crawler_source_registry` | **3513** |
| `oid_sequences` | 6 |
| `sqlite_sequence`, `architecture_decisions`, `events`, `plugin_metadata`, `plugin_services`, `resources`, `import_queue`, `service_runs`, `engines`, `relations`, `objects` | 0 each |

`crawler_source_registry` by state: `UNCHANGED` 3194, `MOVED` 319,
`NEW`/`MODIFIED`/`DELETED`/`FAILED` 0. Distinct `connector` values: 50,
matching `ARTIST_FOLDERS`. Written only by `register_scan()` from the nightly
script.

**Queues** (all three under `01_RUNTIME/gmv_crawler/`, names confirmed in
both `gmv_crawler_nightly_run.py:128-139` and `gmv_crawler_review_tool.py:22-29`):

| file | lines | mtime | writer | reader |
|---|---|---|---|---|
| `rejection_queue.jsonl` | 11743 | 2026-09-25 10:50 | `append_rejected()` — nightly + tool | `list_unrecognized_predicates()`:263, `show_artist_data()`:432, `show_predicate_examples()`:586; plus
`summarize_rejection_queue()` standalone CLI |
| `entity_proposal_queue.jsonl` | **0** | 2026-09-20 11:14 | `append_entity_proposals()` — nightly + tool | `list_entities_needing_verification()`:281 |
| `entity_identity_proposal_queue.jsonl` | 262 | 2026-10-04 19:52 | `append_entity_identity_proposals()` — **nightly only**; last row `queued_at 2026-10-04T17:52:26Z, raw_name "Katia Dilella"` (written by Task 32's `pass2.py`, not by the nightly) | `list_pending_entity_identities()`:300 only |

**Nothing consumes any of the three queues automatically.** Every reader is
a human-invoked Open WebUI tool method that formats text for a chat reply.
There is no auto-apply, no retry, no cron reader.

**Entity registry** `00_CONFIG/gmv_entity_registry.json` — 7 entities, all
`ARTIST`/`ACTIVE`: GMV-000001 Federico Garibaldi (alias Garibaldi),
GMV-000002 Danilo Bucchi, GMV-000003 Manuel Bonfanti, GMV-000004 Florencia
Bruck (alias "Florencia S.M. Brück"), GMV-000005 Davide Genna, GMV-000006
Nicola Evangelisti, GMV-000007 Katia Dilella. A new `GMV-00000N` id is
minted **only** inside `confirm_new_entity()` (`:964` calls
`next_sequential_gmv_id()` at `:757`, then writes at `:974`); the two other
registry writes are `confirm_entity_alias()` (`:1052`). All three are
reachable in production **only** through the Open WebUI tool
(`gmv_crawler_review_tool.py:394`/`:415`), i.e. only when a human invokes
them. `confirm_predicate_mapping()` writes `crawler_predicate_text_mapping.json`
(`gmv_crawler_review_tool.py:695`) and `confirm_institution()` writes
`area35_known_institutions.json` (`:374`), same story. `area35_known_places.json`
(12 places), `area35_known_artists.json` (46 artists) and
`area35_known_institutions.json` (2) are read-only to the pipeline;
`area35_known_places.json` has **no writer at all** in any `.py` file.

**Backup** `10_API/gmv_monad_backup.py` — manual CLI only. Destination
`default_backup_dir()`:156 = `Path.home()/".gmv_backups"/"ombra"`, confirmed
live: `~/.gmv_backups/ombra/` holds 7 files, all `0600`, all mtime
2026-10-04 20:52 (Task 33's manual run; Task 30's own manual run at 19:13).
The brief's "`~/.gmv_backups/ombra/` per its own docstring" is **confirmed
in code**, not just in the docstring. Real, disclosed limitation: it is a
current-state mirror, not an archive — two runs on different days leave one
copy.

---

## 6. GBrain's current ingestion point — what is actually verifiable

**The brief's premise could not be confirmed, and I am not going to paper
over it.** Findings:

1. `GBRAIN_CRAWLER_HANDOFF.md` **does not exist** in this worktree (`ls
   GBRAIN*` → "no matches found"). `GBrain` appears in exactly four places
   in the whole repository, none of them code:
   - `.claude/agents/gmv-code-architect.md:3` and
     `.claude/agents/gmv-code-reviewer.md:37` — prose mentioning GBrain as a
     possible future component;
   - `.claude/agent-memory/gmv-code-architect/MEMORY.md:15` and
     `gmv-code-reviewer/MEMORY.md:18`, verbatim: *"GBrain" e "Shadow":
     nessun riscontro nel codice o nella storia Git di nessun branch alla
     data della verifica. Se citati come componenti esistenti,
     riverificare prima di assumerli.*
   - `opencode_task_35.md` (this task's own brief).
   A repo-wide `grep -rin "gbrain"` over `*.py *.md *.json *.sh *.toml`
   returns **no code reference whatsoever**.
2. GBrain is reachable as an **HTTP MCP server**, not as a filesystem
   watcher: `~/.claude.json` → `mcpServers.gbrain` = `{type: "http", url:
   "http://localhost:3131/mcp"}` plus a bearer header (redacted here; I read
   only the key names and the URL). `lsof -nP -iTCP:3131 -sTCP:LISTEN` shows
   a `bun` process (PID 13802) listening on `127.0.0.1:3131`, so the service
   is up right now. It is configured for **Claude Code**, not for opencode —
   this session has no `gbrain` tool available, and I did not attempt to call
   the MCP endpoint.
3. The one GBrain-related instruction I could read is
   `~/.claude/skills/gbrain-shared-a7f2974d6fe62a33b04088cd/SKILL.md`, which
   says verbatim: *"Use only the configured MCP connection 'gbrain'; never
   use an ambient CLI or another brain."* It exposes skill-discovery tools
   (`sync_brain_skills`, `list_skills`, `get_skill`, `get_skill_asset`) — no
   filesystem-import tool is described in it.

**Conclusion, stated at the limit of what I checked**: nothing in this
worktree, and nothing in any file I can read, points GBrain at
`03_STATE/ombra/` — or at any directory. The connection mechanism that *is*
configured is tool-call based, so "which directory is the brain pointed at" is
not a property of this repository at all; it is a property of the remote
service's own configuration, which I cannot see and was told not to touch.
If the human believes an import has been configured, that belief needs
confirming on the GBrain side before any insertion point below is chosen.

**What is verifiable, and is what actually matters for this task**: the set
of things that can create or modify a file in `03_STATE/ombra/` is §4 —
three already-run ad-hoc scripts plus `materialize_monad()` itself. Whatever
GBrain's configuration is, a future import step must run after one of those.

---

## 7. Discrepancies between existing docs and verified reality

**7.1 — `GMV_CRAWLER_HANDOFF.md:276` contradicts its own line 675.**
Line 276, in the structural "what exists now" table, row 8, says:
*"No canonical Monad directory decided; caller supplies `target_path`."*
Line 674-681 of the same file says: *"**RESOLVED this session.** The
canonical on-disk directory for materialized Monad `.md` files (the "Ombra")
is `03_STATE/ombra/` — a user decision, applied and documented in
`00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md` … and in
`10_API/gmv_monad_materializer.py`'s own module docstring."*
Verified reality: the decision **was** made and **is** in force —
`SOURCE_RUNTIME_BOUNDARIES.md:52` carries the `03_STATE/ombra/` row, and
`gmv_monad_materializer.py:47-60` documents it. The structural table row is
stale. Per the brief I did not edit the original.

**7.2 — the brief's "registry.db: 0 rows everywhere" is stale.** See §5:
3513 rows in `crawler_source_registry`, 6 in `oid_sequences`. The
2026-10-02 information is two days and ~15 nightly runs out of date.

**7.3 — the brief's belief about the nightly script is CONFIRMED, not
contradicted.** `automation/gmv_crawler_nightly_run.py` does not call
`materialize_monad()`. Nothing in the repo does.

**7.4 — `GMV_CRAWLER_HANDOFF.md:1835` ("Nothing in production backs up
`03_STATE/ombra/`") is still true**, verified: `com.gmv.backup` →
`run_backup.sh` → `backup_service.py create`, which touches only
`09_DATABASE/GMV.db` and a `git archive HEAD` tarball; `grep -rn ombra` over
`12_SCHEDULER/` and `scripts/` returns nothing. The Ombra is still backed up
only by hand.

**7.5 — `GMV_CRAWLER_HANDOFF.md:1813` ("nothing calls
`compose_unmapped_narrative()` in production yet") is still true**,
verified by grep: the only callers are the test module and the two ad-hoc
scripts.

**7.6 — docstring claims I checked and found accurate** (recorded because
this project's own history is one of false docstring claims, per
`AGENTS.md`): `gmv_crawler_orchestrator.py:48`'s "nothing here ever calls
`confirm_new_entity()`/`confirm_entity_alias()`" — confirmed;
`gmv_monad_materializer.py:42`'s "`materialize_monad()` … does not compute or
validate PUBLIC content" — confirmed, `public_text` is written verbatim at
`:442`; `gmv_monad_backup.py:30`'s "nothing in production code backs up
`03_STATE/ombra/` today" — confirmed.

**7.7 — one docstring-adjacent claim I could NOT verify.**
`gmv_crawler_entity_identity_proposal_queue.py:34-35` refers to
`crawler_predicate_text_mapping.json` and `area35_known_institutions.json`.
Both greps confirm those strings appear **only inside that docstring** — the
module's real imports are its own dataclasses plus `secure_storage`. So the
module does not read either file; the reference is explanatory prose. Harmless,
but it is exactly the kind of claim that reads as a dependency edge, so it is
flagged rather than passed over.

---

## 8. Side finding: the git-policy security test currently fails, and
commit `4af8d807` widened it

`pytest tests/ -q` → **1 failed, 1326 passed in 35.15s**.
`ruff check .` → **All checks passed!**

The failure is
`tests/security/test_runtime_git_policy.py::test_current_tracked_tree_passes_policy`
(`assert findings == []`). Enumerating the findings with the real scanner
(`scripts/check_runtime_git_policy.py::audit_tracked_files`) gives **8**
`personal_absolute_path` findings:

```
automation/gmv_crawler_review_tool.py:16
automation/gmv_crawler_review_tool.py:49
automation/run_nightly.sh:16
automation/run_nightly.sh:17
opencode_task_21.md:17
opencode_task_21.md:20
opencode_task_21.md:88
opencode_task_32.md:12
```

The four in `automation/` are pre-existing and were already documented as
such by the Task 30 session on 2026-10-04 19:13 (it recorded "still exactly
4 findings, all in `automation/`"). The other four are new **only because
commit `4af8d807` (22:48 today) tracked `opencode_task_21.md` and
`opencode_task_32.md` for the first time** — `tracked_files()` is
`git ls-files -z` (`scripts/check_runtime_git_policy.py:121-131`), so an
untracked brief was invisible to the scan and a tracked one is not. The test
was already red before that commit (4 findings ≠ 0); it is now red with a
larger set, and the extra entries are in task briefs, not in pipeline code.
**I have not fixed this and it is out of scope for this audit** — it is
reported because the reader should not be surprised by a red suite, and
because a future session will otherwise rediscover it from scratch.

---

## 9. Candidate insertion points for a future gbrain-import step

Listed neutrally. **No recommendation is made — that decision belongs to the
human and the directing session.** Each entry states what is actually
guaranteed to have run before it, and what would and would not trigger it.

**Option A — end of `automation/run_nightly.sh`, after the `exec` returns.**
The script's last line is `exec python3 automation/gmv_crawler_nightly_run.py`
(`run_nightly.sh`, final line); an `exec` cannot be followed, so this
requires converting it to a plain call plus an explicit `exit $?`. Timing:
runs once per nightly cycle, at 03:00 local, ~1h15m after start in the most
recent observed run. Guaranteed before it: every Dropbox scan
(`crawler_source_registry` updated to 3513 rows), every queue append, the
`run_complete` log line. Guaranteed *not* to have happened: **no Monad can
exist from this path**, because `materialize_monad()` is not called anywhere
in it (§4). Triggered by launchd and by the Open WebUI `run_crawler_now()`
tool, since both go through this same script. Consequence to weigh: a
gbrain step here would run nightly and, on current reality, import nothing,
ever — unless materialization is first wired into the nightly path.

**Option B — end of `automation/gmv_crawler_nightly_run.py::main()`, after
`run_complete`.** Same trigger coverage as A, without touching the shell
wrapper, and it can read the run's own counters (`total_atoms`,
`total_review`, `any_scan_failed`) directly instead of re-parsing
`run_log.jsonl`. Same blocker: it sits upstream of any Monad creation. Also
note `run_complete` is logged with the run's *start* timestamp (`:400` +
`:416`), so a gbrain step keyed off that field would be stamped an hour
early.

**Option C — inside `materialize_monad()` itself, after
`atomic_write_text()` at `gmv_monad_materializer.py:442`.** This is the only
option that is *guaranteed* to run immediately after any successful write,
wherever the write came from — including the ad-hoc scripts of §4 that
produced all seven existing Monads. Trigger coverage: exactly the set of
producers in §4, which today is 100% manual. Tradeoff to weigh: it puts a
network/external side effect inside a function whose module docstring
currently promises a pure render + atomic write, and it would fire on the
test suite's `tmp_path` writes too unless explicitly gated.

**Option D — a new standalone import wrapper script, run manually after a
batch.** The pattern that has actually produced every artifact in this
subsystem: three separate unversioned scripts under `$TMPDIR/opencode/`,
each re-deriving extraction from scratch and calling `materialize_monad()`
itself. A wrapper would be the first *committed*, reviewable version of that
pattern. Timing: entirely operator-initiated. Guaranteed before it: whatever
the operator ran. Not guaranteed: anything. This is the lowest-risk option
and the one that matches today's real behaviour rather than an aspiration.

**Option E — a new Open WebUI tool method, beside
`list_pending_entity_identities()` in `automation/gmv_crawler_review_tool.py`.**
Triggered by a human in chat, alongside the other review surfaces (§5).
Requires **two** edits, not one: the committed file *and* the
`webui.db` `tool` row `gmv_crawler_review` (§3b) — the DB copy is what
actually executes, and today they are byte-divergent by formatting only.
Guarantees: none; it runs when asked.

**Cross-cutting fact that applies to every option above**: `03_STATE/ombra/`
has **no scheduled backup** (§5, §7.4) and `~/.gmv_backups/ombra/` is a
mirror, not an archive (§5). Any option that pushes Ombra content to an
external system inherits that: the external copy would be the *only*
durable copy of some of this content, since `03_STATE/` is "never Git" by
governance (`SOURCE_RUNTIME_BOUNDARIES.md:51-52`).

---

## 10. What this audit could not determine

- **Whether GBrain is actually pointed at `03_STATE/ombra/`.** §6. Requires
  checking the GBrain service's own configuration; out of scope here by
  instruction.
- **Why `GMV-000002.md`'s mtime is 2026-10-04 16:09.** §3c. A targeted
  query of the opencode session DB for that window found reads only. Either
  a non-opencode session rewrote it, or the timestamp has another cause I
  did not find.
- **Whether the 3am launchd job has *ever* built an atom.** `atoms_built.jsonl`
  is 0 bytes now and the retained `run_log.jsonl` covers 22 runs, all zero;
  earlier history is not in the log.
- **The exact wall-clock duration of the nightly run.** Inferred (~1h15m)
  from the gap between the logged start timestamp and the two files' shared
  mtime; not measured.
- **Whether `run_nightly.sh`'s `exec` line was ever intended to be
  non-terminal.** I report what it is, not what it should be.
