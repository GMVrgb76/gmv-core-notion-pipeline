# OpenCode Task 35 — full pipeline audit: who calls whom, end to end, to find where a gbrain-import step fits

**Status: DRAFT TASK — read-only audit, no code changes, Group A (documentation).**

## Why

The directing Claude session and the human want to add a step that pushes freshly materialized
Monad files (`03_STATE/ombra/*.md`) into GBrain (a separate, already-connected MCP knowledge
brain — see `GBRAIN_CRAWLER_HANDOFF.md`/`GMV_CRAWLER_HANDOFF.md` if either mentions it, otherwise
treat GBrain as external and out of scope for anything except "where would a call to its CLI go").
Before deciding *where* that step belongs, we need a real, current, verified map of this pipeline's
components — not a re-read of `GMV_CRAWLER_HANDOFF.md` alone, because the repo has moved since it
was last written: at minimum `10_API/gmv_crawler_unmapped_narrative.py`, `10_API/gmv_monad_backup.py`,
and changes to `10_API/gmv_crawler_entity_resolver.py` / `00_CONFIG/area35_known_places.json` landed
TODAY (2026-10-04, evening) from a concurrent session's own work (Fase 0-4, see its own commits/diffs
if committed, or working-tree state if not). Confirm current reality with `git log --oneline -20`,
`git status`, and real file mtimes (`ls -la`) before trusting any existing doc's claims, including
this brief's.

This is explicitly an **audit, not a design or implementation task**. Deliverable is one new
markdown report. Do not modify any existing pipeline file. Do not propose or make a design decision
about where to actually insert the gbrain step — that decision is for the human and the directing
Claude session after reading your report.

## Hard constraints

1. **No code changes anywhere.** Create exactly one new file:
   `GMV_CRAWLER_PIPELINE_AUDIT_2026-10-04.md` at the repo root. Everything else is read-only
   investigation (`git log`, `git diff`, `grep`, reading files, optionally running existing tests —
   never editing them).
2. **Verify, don't transcribe docstrings.** Every "X calls Y" or "Y is triggered by Z" claim in
   your report must be grounded in something you actually checked this session — a real `grep -rn`
   for the call site, a real import statement, a real launchd/cron file, a real test that exercises
   the path. If a docstring claims something a grep doesn't confirm, report the discrepancy
   explicitly rather than picking one side silently.
3. **Cover every real trigger path, not just the nightly one.** At minimum: (a) the 3am launchd cron
   (`~/Library/LaunchAgents/com.gmv.crawler.nightly.plist` → `automation/run_nightly.sh` →
   `automation/gmv_crawler_nightly_run.py`), (b) the Open WebUI "GMV Crawler Review" tool's
   `run_crawler_now()` path (DB-stored Python in `~/gmv_openwebui/data/webui.db`, table `tool`, id
   `gmv_crawler_review` — read it directly, don't assume it matches any committed copy), (c) any
   ad-hoc/manual/opencode-task invocation path you find evidence of (e.g. today's Fase 4 5-artist
   batch, or Task 18/20's Bucchi run) — these may call individual functions directly rather than
   going through either of the above, which matters for finding every place a Monad can be created
   or modified.
4. **Real tool calls only, no narrated-but-not-executed steps.** Every command you report running
   must actually have been run via a real tool call this session — the directing Claude session
   will cross-check your actual tool-call history against this report's claims afterward (via your
   own session database) and treat any mismatch as a serious finding, not a style issue.
5. **Do not touch `GMV_CRAWLER_HANDOFF.md` or any other existing doc.** If you find it's stale or
   wrong, say so in your new report's own section for that — do not edit the original.

## What to map (be concrete: file path, function name, real callers found by grep, real triggers)

1. **Extraction → atoms, the per-document chain**: `gmv_crawler_candidate_extractor.py`
   (`extract_candidates`) → `gmv_crawler_document_classifier.py` (`classify_document`) →
   `gmv_crawler_atom_builder.py` (`build_atoms`, ATTRIBUTE) + `gmv_crawler_relation_atom_builder.py`
   (`build_relation_atoms`, RELATION) → `gmv_crawler_orchestrator.py` (`process_document`, the
   function that composes all of the above — confirm the exact composition order and what it does
   NOT call).
2. **The ungoverned-text path added 2026-10-04**: `gmv_crawler_unmapped_narrative.py`
   (`compose_unmapped_narrative`) — confirm exactly where in the chain this is invoked (is it
   inside `process_document()`, or called separately by whatever ran Fase 1-4 today?), and confirm
   its real relationship to `gmv_monad_materializer.py`'s `# PUBLIC` section.
3. **Entity/identity side-channel**: `gmv_crawler_entity_resolver.py`, `00_CONFIG/area35_known_places.json`,
   `00_CONFIG/area35_known_artists.json`, `00_CONFIG/gmv_entity_registry.json` — who reads/writes
   each, when, and what triggers a new `GMV-00000N` id to be minted.
4. **Monad materialization**: `gmv_monad_materializer.py` (`materialize_monad`) — confirm, by
   grepping the WHOLE repo (not just `automation/` and `10_API/`), every real call site. State
   explicitly whether `automation/gmv_crawler_nightly_run.py` calls it (directing session's current
   belief: NO, confirm or refute this with a real grep) and what DOES call it today (manual script?
   opencode task runner? something under `/tmp/opencode/`?).
5. **Backup**: `gmv_monad_backup.py` — confirm its trigger (manual? wired into anything?) and real
   target path (`~/.gmv_backups/ombra/` per its own docstring — confirm).
6. **Queues and human-review surfaces**: `rejection_queue.jsonl`, `entity_proposal_queue.jsonl`,
   `entity_identity_proposal_queue.jsonl` (confirm real filenames/paths) — who writes, who reads,
   is anything currently consuming them automatically or are they 100% manual today.
7. **Registry DB**: `10_API/gmv_crawler_registry.py` / `registry.db` — confirm current real row
   counts per table (the directing session's last information, 2026-10-02, was "0 rows everywhere"
   — re-check, it may have changed).
8. **GBrain's current ingestion point** (informational only, do not touch GBrain or its CLI):
   confirm that `03_STATE/ombra/*.md` is the only directory GBrain has been pointed at from this
   worktree, and list every distinct code path (steps 1-5 above) capable of creating or modifying a
   file in that directory — this list IS the actual set of things a gbrain-import step would need
   to run after, whichever single or multiple insertion points get chosen later.

## Report back (inside `GMV_CRAWLER_PIPELINE_AUDIT_2026-10-04.md`)

1. A component table: file | key function(s) | real callers (grep-confirmed) | real trigger
   (cron/manual/tool/other) | writes to (which files/dirs).
2. An explicit list of every distinct path that can create/modify a file under `03_STATE/ombra/`
   today, per constraint 8.
3. A dedicated final section, **"Candidate insertion points for a future gbrain-import step"** —
   list the real options this audit surfaced (e.g. end of `run_nightly.sh`, end of
   `materialize_monad()` itself, a new explicit wrapper script run manually after a batch, etc.)
   with the real tradeoff each implies given what you found (timing, what's guaranteed to have run
   before it, what triggers it). **Do not recommend one** — list them neutrally, the decision is
   not yours to make.
4. Any discrepancy found between `GMV_CRAWLER_HANDOFF.md` (or any other existing doc) and what you
   actually verified — cite the doc's claim and your contradicting evidence.
5. `git log --oneline -20`, `git status --short`, and a one-line note on whether today's concurrent
   session's work (Fase 0-4) is committed or still working-tree.
