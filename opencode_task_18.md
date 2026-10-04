# OpenCode Task 18 — Minimal end-to-end Monad materialization proof (Federico Garibaldi)

**Status: DRAFT TASK — approved plan, not yet executed. Delegated for implementation.**
**Do not treat anything in this file as already true of the codebase except where it says "verified".**

## Why this task exists, and why it supersedes `opencode_task_12.md`

`opencode_task_12.md` (same goal) was drafted against an earlier snapshot of this repo and is now
**stale on its own Steps 1-2** — do not execute that file, use this one. Verified by directly
reading `10_API/gmv_crawler_entity_resolver.py`'s own module docstring and code, this session:

- `00_CONFIG/gmv_entity_registry.json` **already exists and is already committed** (constant
  `ENTITY_REGISTRY_PATH` in that module; the module's "third piece" docstring section states the
  registry was seeded, then the Garibaldi entry was "retrofitted from the rejected content-derived
  format [`GMV-ARTIST-FEDERICO-GARIBALDI`] to `GMV-000001`" because a content-derived id is not
  "stabile e indipendente dal nome corrente"). **Task 12's own Step 1 JSON snippet, which still
  uses `"gmv_id": "GMV-ARTIST-FEDERICO-GARIBALDI"`, is therefore wrong — do not write that file,
  and do not use that id string anywhere in this task.** Confirm the real current id by reading the
  file at the start of Step 1 below; do not assume `GMV-000001` either without checking, since the
  registry may have grown since this docstring was last edited.
- `resolve_entity_gmv_id()`, `propose_entity_identity()`, `next_sequential_gmv_id()`,
  `confirm_new_entity()`, `confirm_entity_alias()` **already exist** in
  `10_API/gmv_crawler_entity_resolver.py`, committed (`git log` shows `d2644137 feat: add
  resolve_entity_gmv_id()...` and `d662bf37 feat: build the propose/confirm identity-resolution
  loop, human-gated`). **Task 12's own Step 2 (write `resolve_entity_gmv_id()`) is therefore
  already done — do not write it again, just import and use it.**

What is genuinely still unverified, and is this task's real job: whether `materialize_monad()`
(`10_API/gmv_monad_materializer.py`) and `project_public()`
(`10_API/gmv_crawler_public_projector.py`) have ever actually been called outside `tests/` with
this real registry entry, and whether a real `03_STATE/ombra/*.md` file exists on disk yet. The
directing Claude session could not finish checking this live before handing off this task — **your
Step 0 below must check it first**, and if you find a Monad file already materialized for this
entity, STOP after Step 0 and report that instead of re-running the proof — do not overwrite an
existing real result without being told to.

## Step 0 — verify current reality before doing anything else (report findings even if this task then stops here)

Run and report the raw output of all of these, from the repo root:

1. `cat 00_CONFIG/gmv_entity_registry.json` — the real current entity list and the real current
   `gmv_id` for Federico Garibaldi (canonical_name match, case/whitespace-insensitive per
   `resolve_entity_gmv_id()`'s own rules — do not assume the literal string "Federico Garibaldi").
2. `ls -la 03_STATE/ombra/ 2>&1` — does this directory exist, and does it already contain a Monad
   file for this entity's `gmv_id`?
3. `grep -rn "materialize_monad(\|project_public(" --include="*.py" . | grep -v "/tests/\|__pycache__"`
   — confirm (or correct) the directing session's belief that neither function is called in
   production code today.
4. `git log --oneline -5 -- 03_STATE/` and `git status --short -- 03_STATE/` (expect nothing
   tracked — `03_STATE/` is classified "never Git" in
   `00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md:52` — if `git status` shows it as tracked or staged,
   stop and report that discrepancy rather than proceeding).

If Step 0 shows a real, already-materialized Monad file for this entity: stop, report its content
and the findings above, and do not run Steps 1-4. Otherwise continue.

## Hard constraints — do not exceed this scope

1. **No SQL migration.** Do not touch `gmv_core/migration_sql/`, do not raise
   `ENTITY_REGISTRY_VERSION` in `automation/gmv_crawler_nightly_run.py`.
2. **No LLM call for entity matching.** `resolve_entity_gmv_id()` already does exact,
   case-insensitive, whitespace-normalized matching — reuse it as-is, do not add fuzzy matching or
   a model call on top of it.
3. **No `reconcile()` wiring.** `10_API/gmv_crawler_reconciliation.py` is not touched or called.
4. **No change to any production pipeline file.** Do not edit
   `automation/gmv_crawler_nightly_run.py`, `10_API/gmv_crawler_orchestrator.py`, or
   `10_API/gmv_crawler_relation_atom_builder.py`. This is a standalone proof script, run once, not
   a new pipeline stage.
5. **Do not write to `00_CONFIG/gmv_entity_registry.json`.** `confirm_new_entity()` /
   `confirm_entity_alias()` exist but are human-confirmed write paths — do not call them from this
   task. If Step 3.4 below finds a name that fails to resolve, report it; do not "fix" it yourself
   by calling `confirm_entity_alias()`.
6. **The proof script itself is not committed.** Run it from anywhere outside `automation/`,
   `10_API/`, or any other tracked directory (e.g. `/tmp/`) — discard it or leave it uncommitted
   when done.
7. **The output `.md` file is not committed.** `03_STATE/ombra/` is "never Git" — leave it there,
   do not `git add` it.

## Real, already-built pieces to reuse (do not reimplement any of these)

- `10_API/gmv_monad_materializer.py`: `materialize_monad()`, `MonadDocument`,
  `SourceManifestEntry`. Read this file's own module docstring before using it — it explains the
  exact frozen schema and the canonical `03_STATE/ombra/` target directory convention.
- `10_API/gmv_crawler_entity_resolver.py`: `resolve_entity_gmv_id(name, registry)` — pass it the
  parsed `00_CONFIG/gmv_entity_registry.json` dict directly, per its own docstring.
- `10_API/gmv_crawler_public_projector.py::project_public()` — turns a list of `AtomCandidate` into
  `public_text`. This task is its first real (non-test) caller.
- `10_API/gmv_crawler_candidate_extractor.py::extract_candidates()` — real LLM extraction, already
  used throughout this project's history on real Garibaldi documents.
- `10_API/gmv_crawler_extractor.py::extract_document()`, `10_API/gmv_evidence_pipeline.py::sha256_file()`
  — real document extraction + hashing.
- `10_API/gmv_dropbox_connector.py::DropboxConnector` — `.metadata(locator)` returns real
  `size`/`modified` for a Dropbox path. Dropbox credentials: read `~/.gmv_dropbox_oauth.json`
  (`refresh_token`, `app_key`, `app_secret`) and pass them directly to `DropboxConnector(...)` — do
  not set environment variables globally, same pattern already used in
  `automation/gmv_crawler_review_tool.py::run_crawler_on_files`.
- `10_API/gmv_crawler_extractor.py::STATUS_VALUES` — the closed vocabulary for
  `SourceManifestEntry.extraction_status`.
- `10_API/gmv_crawler_atom_builder.py::build_atoms()` (ATTRIBUTE-class predicates) and
  `10_API/gmv_crawler_relation_atom_builder.py::build_relation_atoms()` (RELATION-class predicates)
  — use whichever matches each resolved proposition's predicate class; do not reimplement atom
  construction.

## Steps

### Step 1 — confirm the real `gmv_id`

From Step 0.1's real file content, note the exact `gmv_id` currently registered for Federico
Garibaldi (expected to be `GMV-000001` per the docstring evidence above, but confirm against the
live file, not this assumption). Use this real value everywhere below — do not hardcode
`GMV-ARTIST-FEDERICO-GARIBALDI`.

### Step 2 — one-off proof script (not committed)

Write and run a script (e.g. under `/tmp/`) that does, in order:

1. Pick a real Garibaldi document already used in prior sessions — the MutualArt biography at
   `/GMV_MASTER_SYSTEM/01_AREA35_MASTER/01_ARTISTS/GARIBALDI_Federico/00_MASTER/2026_06_17_MUTUALART_BIOGRAPHY.md`
   (Dropbox path). It is known (verified live in a prior session) to contain real "presente
   in"/"ha esposto"-shaped claims about real exhibitions/venues.
2. Download it via `DropboxConnector` (credentials as described above), extract it via
   `extract_document()`, compute its real hash via `sha256_file()`.
3. Run `extract_candidates()` on the extracted document (reuse `DEFAULT_MODEL`/`DEFAULT_API_STYLE`
   from `10_API/gmv_crawler_candidate_extractor.py`, `temperature=0, seed=42` — same defaults
   `process_document()` already uses, for the same determinism reason documented there).
4. For every resulting `CandidateProposition`, call `resolve_entity_gmv_id(proposition.subject_raw,
   registry)` (registry = Step 0.1's parsed dict). Keep only the ones that resolve to the real
   `gmv_id` confirmed in Step 1. **If NONE resolve** (e.g. the model paraphrases the name in a way
   neither the canonical name nor any registered alias covers), that is a real, reportable finding
   — report it and stop for a decision instead of improvising a fix or adding an alias yourself
   (constraint 5 above).
5. Build the `AtomCandidate` tuple from the resolved propositions: ATTRIBUTE-class predicates via
   `build_atoms()`, RELATION-class predicates via `build_relation_atoms()` — check each resolved
   proposition's predicate class against `GMV_ONTOLOGY_REGISTRY_v0.1.json` to route it correctly.
6. Build one real `SourceManifestEntry`:
   - `source_id` / `path`: the same Dropbox locator string, used consistently as both.
   - `source_type`: file extension or a reasonable literal (check what similar code elsewhere uses,
     e.g. `gmv_crawler_extractor.py`'s handling of `.md`).
   - `size` / `modified`: from `DropboxConnector.metadata(locator)` — real values, not placeholders.
   - `hash_value`: the real `sha256_file()` result from Step 2.2.
   - `epistemic_level`: no governed vocabulary exists for this field yet (confirmed in
     `GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md` §1.3) — use a clearly-labeled placeholder (e.g.
     `"UNVERIFIED_PLACEHOLDER"`) and say so plainly in your final report; do not invent a governed
     vocabulary term here.
   - `extraction_status`: `"SUCCESS"` (from `gmv_crawler_extractor.STATUS_VALUES`).
   - `notes`: state plainly this is a proof-of-concept manifest entry, not a production one.
7. Call `project_public()` on the resolved atoms to get real `public_text`.
8. Assemble a `MonadDocument` using the real `gmv_id`/`entity_type`/`canonical_name` from the
   registry entry confirmed in Step 1, `status="active"`, and the `public_text`/`atoms`/`sources`
   from steps 7/5/6.
9. Call `materialize_monad(document, target_path=Path("03_STATE/ombra/<real-gmv-id>.md"))` relative
   to the repo root (create `03_STATE/ombra/` if it doesn't exist — fine to create the directory,
   not fine to commit anything inside it). If `materialize_monad()` raises
   `MonadMaterializationError`, print the full list of blocking issues it carries and stop — do not
   work around a validation failure by changing the input data to make it pass; report the real
   failure instead.

### Step 3 — verify by inspection

Read the resulting `03_STATE/ombra/<real-gmv-id>.md` file in full. Confirm:
- It matches the frozen `GMV_KNOWLEDGE_MONAD_SPEC_v1.0` §19 skeleton (YAML/IDENTITY block, then
  `# PUBLIC`, `# ATOMS` table, `# SOURCES` table, in that order).
- Every atom's `PREDICATE_CLASS` column matches what `GMV_ONTOLOGY_REGISTRY_v0.1.json` says for
  that `predicate_id`.
- The `SOURCES` row has real, non-placeholder `SIZE`/`MODIFIED`/`HASH` values (except
  `EPISTEMIC_LEVEL`, explicitly placeholder per Step 2.6).
- No blocker was raised (a clean file was written, not an exception).

### Step 4 — regression check

Run `.venv/bin/python -m pytest tests/ -q` from the repo root and confirm no NEW failure was
introduced (nothing in this task touches tracked code, so none is expected — confirm rather than
assume). One pre-existing failure is expected and unrelated to this task:
`tests/security/test_runtime_git_policy.py::test_current_tracked_tree_passes_policy`.

## What to report back when done

A short, factual report (not a new markdown file in the repo unless asked) covering:
1. Step 0's raw findings, verbatim — especially whether a Monad already existed (in which case
   report that and stop, per Step 0's own instruction).
2. Whether the proof succeeded (a real `.md` file was written and passed Step 3's checks), and if
   not, the exact blocking issue(s) `materialize_monad()` raised, verbatim.
3. How many real atoms ended up in the final Monad, and their real subject/predicate/object values
   (so this can be sanity-checked against the source document).
4. Whether any candidate name variant of Federico Garibaldi failed to resolve in Step 2.4, and what
   the raw text was — this is exactly the kind of real evidence the open entity-resolution design
   questions (`GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md` §2) need.
5. Confirmation of Step 4's pytest result.
6. The exact diff of every tracked file you changed, if any (`git diff` / `git status --short`), so
   it can be reviewed before any commit decision — do not commit anything yourself; that is a
   separate, explicit step for a human.
