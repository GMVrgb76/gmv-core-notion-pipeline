# OpenCode Task 12 — Minimal end-to-end Monad materialization proof (Federico Garibaldi)

**Status: DRAFT TASK — approved plan, not yet executed. Delegated for implementation.**
**Do not treat anything in this file as already true of the codebase except where it says "verified".**

## Why this task exists (context, verified this session)

`10_API/gmv_monad_materializer.py::materialize_monad()` is complete and tested, but nothing in
the real GMV Crawler pipeline ever calls it (verified: `grep -rn "materialize_monad(" --include=*.py .`
outside `tests/` returns nothing). Same for `10_API/gmv_crawler_public_projector.py::project_public()`.
The one real reason nothing is wired: there is no entity resolution anywhere in this repo — no
code assigns a stable `gmv_id` to a name string, and `10_API/gmv_crawler_atom_builder.py:174`
says so explicitly in its own comment ("only ATTRIBUTE predicates are supported in this v0 slice
(the rest need entity resolution, which does not exist yet)"). This is documented at length in
`GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md` (repo root, committed `9393efb6`) — read that file
first if anything below is unclear; it is the authority this task was derived from.

The goal of THIS task is not to solve entity resolution in general. It is to prove the rest of
the chain (atoms → resolved identity → PUBLIC projection → materialized Monad file) actually
works end-to-end, on ONE real entity this project has used as its reference case since its
earliest research protocol: **Federico Garibaldi**. A working reference file turns the remaining
open design questions (registry schema, matching algorithm, confidence thresholds — all listed
in the audit doc, §2) into informed decisions instead of speculation.

## Hard constraints — do not exceed this scope

These are deliberate exclusions, not omissions. Do not "improve" on them without asking first:

1. **No SQL migration.** Do not touch `gmv_core/migration_sql/`, do not raise
   `ENTITY_REGISTRY_VERSION` in `automation/gmv_crawler_nightly_run.py`. The registry for this
   task is a plain JSON file (see Step 1).
2. **No LLM call for entity matching.** Exact, case-insensitive, whitespace-normalized string
   matching only. No fuzzy matching, no embedding similarity, no Jev/Laya/Ollama call for this
   step. (Reason, verified in the audit's §6/§7 and in the real Epistemic Ingestion Constitution
   v0.1 rule 12: "when two interpretations are possible, choose the less assertive one" — prove
   the simplest match works before adding a model dependency.)
3. **No `reconcile()` wiring.** `10_API/gmv_crawler_reconciliation.py` is not touched or called.
4. **No change to any production pipeline file.** Do not edit `automation/gmv_crawler_nightly_run.py`,
   `10_API/gmv_crawler_orchestrator.py`, or `10_API/gmv_crawler_relation_atom_builder.py`. This
   is a standalone proof script, run once, not a new pipeline stage.
5. **The proof script itself is not committed.** Run it, inspect its output, then discard it (or
   leave it uncommitted) — do not add it to `automation/` or any tracked location. If it proves
   useful enough to keep, that is a separate decision for a human, not this task.
6. **The output `.md` file is not committed.** `03_STATE/ombra/` is classified "never Git" in
   `00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md:52` — leave it there, do not `git add` it.

## Real, already-built pieces to reuse (do not reimplement any of these)

- `10_API/gmv_monad_materializer.py`: `materialize_monad()`, `MonadDocument`, `SourceManifestEntry`.
  Read this file's own module docstring before using it — it explains the exact frozen schema and
  the canonical `03_STATE/ombra/` target directory convention.
- `10_API/gmv_crawler_public_projector.py::project_public()` — turns a list of `AtomCandidate`
  into `public_text`. This task is its first real (non-test) caller.
- `10_API/gmv_crawler_candidate_extractor.py::extract_candidates()` — real LLM extraction,
  already used throughout this project's history on real Garibaldi documents.
- `10_API/gmv_crawler_extractor.py::extract_document()`, `10_API/gmv_evidence_pipeline.py::sha256_file()`
  — real document extraction + hashing.
- `10_API/gmv_dropbox_connector.py::DropboxConnector` — `.metadata(locator)` returns real
  `size`/`modified` for a Dropbox path (verified this session, `gmv_dropbox_connector.py:227-244`).
  Dropbox credentials: read `~/.gmv_dropbox_oauth.json` (`refresh_token`, `app_key`, `app_secret`)
  and pass them directly to `DropboxConnector(...)` — do not set environment variables globally,
  same pattern already used in `automation/gmv_crawler_review_tool.py::run_crawler_on_files`.
- `10_API/gmv_crawler_extractor.py::STATUS_VALUES` — the closed vocabulary for
  `SourceManifestEntry.extraction_status`.
- Convention for a human-curated JSON roster to copy exactly: `00_CONFIG/area35_known_artists.json`
  and `00_CONFIG/area35_known_institutions.json` — read both before writing Step 1's file. Same
  `note`/`note_on_maintenance` field style, same "populated only by explicit human confirmation,
  never auto-populated" principle.

## Steps

### Step 1 — `00_CONFIG/gmv_entity_registry.json`

New file. Match the exact style (fields, tone, governance notes) of
`00_CONFIG/area35_known_institutions.json`. Content:

```json
{
  "note": "Human-curated, verified registry mapping a canonical name to a stable gmv_id, for the crawler's entity resolution (10_API/gmv_crawler_entity_resolver.py). Deliberately minimal and hand-seeded for a single-entity proof of concept (see GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md) -- NOT a production entity registry, NOT auto-populated. A real production registry (schema, matching algorithm, gmv_id generation scheme) remains an open design decision, not something this file decides.",
  "note_on_maintenance": "Created 2026-09-26 for one proof-of-concept entity. Do not add entries here without the same human-verification discipline already applied to area35_known_artists.json/area35_known_institutions.json.",
  "entities": [
    {
      "gmv_id": "GMV-ARTIST-FEDERICO-GARIBALDI",
      "entity_type": "ARTIST",
      "canonical_name": "Federico Garibaldi",
      "aliases": ["Garibaldi"],
      "status": "active"
    }
  ]
}
```

(Use today's real date in `note_on_maintenance` if you run this later than 2026-09-26 — check
with `date` rather than assuming.)

### Step 2 — `resolve_entity_gmv_id()` in `10_API/gmv_crawler_entity_resolver.py`

Add one new function to this existing module (do not create a new file — this module is already
the home for entity-identity logic; `classify_entity_types()` assigns TYPE, this new function
assigns IDENTITY, they do not overlap and should sit side by side). Read the existing file first
to match its docstring style and conventions (see `classify_entity_types()` for the expected
level of detail in comments — this project's own convention is to cite the live/reproduced
finding behind every non-obvious design choice, not just describe what the code does).

Signature and behavior:

```python
def resolve_entity_gmv_id(name: str, registry: dict) -> str | None:
    """Exact, case-insensitive, whitespace-normalized match of `name` against
    `registry`'s canonical_name or any alias. No fuzzy matching, no LLM call --
    see [this task's handoff / the audit doc] for why. Returns the matching
    entity's gmv_id, or None if no entry matches (the caller must treat None
    as "stays unresolved / type-neutral", never as an error and never as a
    reason to invent a new gmv_id automatically -- assigning new gmv_ids is
    an open design decision, not this function's job)."""
```

`registry` is the parsed JSON from Step 1 (`{"entities": [...]}`). Normalize by
`.strip().lower()` on both sides before comparing. Write a couple of direct unit-style checks
(not necessarily a full pytest file for this proof — your judgment, but if you do add tests,
they must go through the same `.venv/bin/python -m pytest` this repo already uses, and must not
break `tests/characterization/test_ontology_registry.py` or anything else already passing).

Before finishing this step, run the full test suite once (`.venv/bin/python -m pytest tests/ -q`
from the repo root) and confirm you have not introduced any NEW failure. One pre-existing failure
is expected and unrelated to this task: `tests/security/test_runtime_git_policy.py::test_current_tracked_tree_passes_policy`
(a personal-absolute-path finding in `automation/gmv_crawler_review_tool.py`, present before this
task and not something to fix here).

### Step 3 — one-off proof script (not committed)

Write and run a script (anywhere convenient, e.g. `/tmp/` or a scratch path — not under
`automation/`, `10_API/`, or any tracked directory) that does, in order:

1. Pick a real Garibaldi document already used this session — the MutualArt biography at
   `/GMV_MASTER_SYSTEM/01_AREA35_MASTER/01_ARTISTS/GARIBALDI_Federico/00_MASTER/2026_06_17_MUTUALART_BIOGRAPHY.md`
   (Dropbox path). It's known (this session, live) to contain real "presente in"/"ha esposto"-shaped
   claims about real exhibitions/venues.
2. Download it via `DropboxConnector` (credentials as described above), extract it via
   `extract_document()`, compute its real hash via `sha256_file()`.
3. Run `extract_candidates()` on the extracted document (reuse `DEFAULT_MODEL`/`DEFAULT_API_STYLE`
   from `10_API/gmv_crawler_candidate_extractor.py`, `temperature=0, seed=42` — same defaults
   `process_document()` already uses, for the same determinism reason documented there).
4. For every resulting `CandidateProposition`, call `resolve_entity_gmv_id()` (Step 2) on
   `subject_raw`. Keep only the ones that resolve to `GMV-ARTIST-FEDERICO-GARIBALDI`. If NONE
   resolve (e.g. the model paraphrases the name in some way `Garibaldi`/`Federico Garibaldi`
   doesn't cover), that's a real, reportable finding for this task, not a reason to loosen Step 2's
   matching or add a name variant you're guessing at — report it and stop for a decision instead
   of improvising a fix.
5. Build the `AtomCandidate` tuple from the resolved propositions the same way
   `10_API/gmv_crawler_atom_builder.py::build_atoms()` already does for ATTRIBUTE-class
   predicates (reuse that function directly rather than reimplementing atom construction) —
   check whether any of the resolved predicates are RELATION-class (needing
   `10_API/gmv_crawler_relation_atom_builder.py::build_relation_atoms()` instead); if so, use
   that path, since it's the one that already knows how to set `object_type` from a real entity
   classification.
6. Build one real `SourceManifestEntry`:
   - `source_id`: the same `locator` string used as `source_id` throughout (the Dropbox path).
   - `path`: same locator.
   - `source_type`: file extension or a reasonable literal (check what similar code elsewhere
     uses, e.g. `gmv_crawler_extractor.py`'s handling of `.md`).
   - `size`/`modified`: from `DropboxConnector.metadata(locator)` — real values, not placeholders.
   - `hash_value`: the real `sha256_file()` result from step 2.
   - `epistemic_level`: no existing vocabulary for this field (confirmed in the audit, §1.3) —
     use a clearly-labeled placeholder value (e.g. `"UNVERIFIED_PLACEHOLDER"`) and say so plainly
     in your final report; do not invent a governed vocabulary term here.
   - `extraction_status`: `"SUCCESS"` (from `gmv_crawler_extractor.STATUS_VALUES`).
   - `notes`: mention this is a proof-of-concept manifest entry, not a production one.
7. Call `project_public()` on the resolved atoms to get real `public_text`.
8. Assemble a `MonadDocument`:
   - `gmv_id`: `"GMV-ARTIST-FEDERICO-GARIBALDI"`.
   - `entity_type`: `"ARTIST"`.
   - `canonical_name`: `"Federico Garibaldi"`.
   - `status`: `"active"`.
   - `public_text`, `atoms`, `sources`: from steps 7, 5, 6.
9. Call `materialize_monad(document, target_path=Path("03_STATE/ombra/GMV-ARTIST-FEDERICO-GARIBALDI.md"))`
   relative to the repo root (create `03_STATE/ombra/` if it doesn't exist — it's gitignored/
   untracked runtime state, creating the directory is fine, committing anything inside it is not).
   If `materialize_monad()` raises `MonadMaterializationError`, print the full list of blocking
   issues it carries and stop — do not work around a validation failure by changing the input
   data to make it pass; report the real failure instead.

### Step 4 — verify by inspection

Read the resulting `03_STATE/ombra/GMV-ARTIST-FEDERICO-GARIBALDI.md` file in full. Confirm:
- It matches the frozen `GMV_KNOWLEDGE_MONAD_SPEC_v1.0` §19 skeleton (YAML/IDENTITY block, then
  `# PUBLIC`, `# ATOMS` table, `# SOURCES` table, in that order).
- Every atom's `PREDICATE_CLASS` column matches what `GMV_ONTOLOGY_REGISTRY_v0.1.json` says for
  that `predicate_id`.
- The `SOURCES` row has real, non-placeholder `SIZE`/`MODIFIED`/`HASH` values (except
  `EPISTEMIC_LEVEL`, explicitly placeholder per Step 3.6).
- No blocker was raised (a clean file was written, not an exception).

## What to report back when done

A short, factual report (not a new markdown file in the repo unless asked) covering:
1. Whether the proof succeeded (a real `.md` file was written and passed the Step 4 checks), and
   if not, the exact blocking issue(s) `materialize_monad()` raised, verbatim.
2. How many real atoms ended up in the final Monad, and their real subject/predicate/object
   values (so this can be sanity-checked against the source document).
3. Whether any candidate name variant of "Federico Garibaldi" failed to resolve in Step 3.4, and
   what the raw text was — this is exactly the kind of real evidence the open entity-resolution
   design questions (in `GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md`, §2) need.
4. Confirmation that `.venv/bin/python -m pytest tests/ -q` still shows only the one pre-existing,
   unrelated failure named in Step 2, nothing new.
5. The exact diff of every file you changed (`git diff`), so it can be reviewed before any commit
   decision — do not commit anything yourself; that is a separate, explicit step for a human.
