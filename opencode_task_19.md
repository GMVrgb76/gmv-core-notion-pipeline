# OpenCode Task 19 — clean up the stale proof artifact; queue the first real identity proposal (Danilo Bucchi)

**Status: DRAFT TASK — approved plan, not yet executed. Delegated for implementation.**
**Do not treat anything in this file as already true of the codebase except where it says "verified".**

## Context (verified this session, by the directing Claude session, independently of your own Task-18 report)

Your Task 18 report is confirmed accurate by direct inspection:
`03_STATE/ombra/GMV-ARTIST-FEDERICO-GARIBALDI.md` is real `materialize_monad()` output (mtime
2026-09-26 12:45:33, mode 0600/dir 0700), with an empty ATOMS table and empty PUBLIC section, under
the since-rejected content-derived id. `00_CONFIG/gmv_entity_registry.json` has exactly one entity,
`GMV-000001` / "Federico Garibaldi". `03_STATE/ombra/` contains exactly that one file — **no Monad
with real, non-empty atoms has ever been materialized by this subsystem**, confirmed by listing the
directory. The registry's own `registry.db` (`01_RUNTIME/gmv_crawler/registry.db`) also shows 0
rows in every table (`objects`, `relations`, `import_queue`, `events`, `resources`) as of today —
consistent, not contradictory.

Decision made by the human (not yours to re-open): the stale empty file should be deleted, not
renamed or left in place — it carries no information (zero atoms) and sits under an id that
resolves to nothing in the current registry. See Step 1.

The more valuable next step, already planned but never executed: `opencode_task_13.md`'s own Step
5 (never run) proposed a second proof on a real **Danilo Bucchi** document, chosen specifically
because its real predicate `"partecipa"` is already mapped and verified in
`00_CONFIG/crawler_predicate_text_mapping.json` (verified again this session —
`raw_predicate_text: "partecipa"` maps to `participated_in`, `verified_against` cites two real
Bucchi cases: EMERGENZE FESTIVAL and the XVI Biennale di Venezia di Architettura). Unlike the
Garibaldi document, this one has a real chance of producing the first genuinely non-empty Monad
this subsystem has ever built — but that full materialization is Task 20's job, not this one's.
**This task stops one step earlier, at the proposal queue** — see "Hard constraints" point 5.

## Hard constraints — do not exceed this scope

1. **No SQL migration.** Do not touch `gmv_core/migration_sql/` or `ENTITY_REGISTRY_VERSION`.
2. **No LLM call for entity matching, no fuzzy matching.** `resolve_entity_gmv_id()` already does
   exact, case-insensitive, whitespace-normalized matching — reuse as-is.
3. **No `reconcile()` wiring, no change to any production pipeline file**
   (`automation/gmv_crawler_nightly_run.py`, `10_API/gmv_crawler_orchestrator.py`,
   `10_API/gmv_crawler_relation_atom_builder.py`).
4. **No SQL/registry schema changes.** `00_CONFIG/gmv_entity_registry.json` itself is not touched
   by this task — Danilo Bucchi is NOT yet a known entity and this task must not change that.
5. **Do not call `confirm_new_entity()` or `confirm_entity_alias()` in this task, under any
   circumstances, even if Step 3 makes it tempting.** Minting a new `gmv_id` for a real person is a
   deliberate human editorial act (see `gmv_crawler_entity_resolver.py`'s own docstring, "the WRITE
   half... exist to be CALLED BY A HUMAN"), and the human directing this work has not made that
   call yet — only approved queuing the proposal, not confirming it. This task's job ends at a
   real, on-disk, reviewable proposal; confirming it is a separate, later, explicit step.
6. **The proof script itself is not committed.** Run it from `/tmp/` or similar — discard it or
   leave it uncommitted when done.
7. **The proposal-queue write (Step 3) IS meant to persist for real** — unlike the Task 18 proof
   script's throwaway nature, this is the real, intended use of
   `append_entity_identity_proposals()` / `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl`,
   which is runtime state (same "never Git" classification as `03_STATE/`), not a disposable test
   artifact. Do not delete it afterward.

## Real, already-built pieces to reuse (do not reimplement any of these)

- `10_API/gmv_crawler_entity_resolver.py`: `resolve_entity_gmv_id()`, `propose_entity_identity()`,
  `EntityIdentityProposal`. Already committed and already used correctly by your own Task 18 work —
  reuse the exact same calling convention.
- `10_API/gmv_crawler_entity_identity_proposal_queue.py::append_entity_identity_proposals()` —
  confirmed present at line 102 of that file this session. Read its full docstring before calling
  it (JSONL append pattern, `queued_at` added on the envelope, file created only if something is
  actually queued).
- `10_API/gmv_crawler_candidate_extractor.py::extract_candidates()`,
  `10_API/gmv_crawler_extractor.py::extract_document()`, `10_API/gmv_evidence_pipeline.py::sha256_file()`,
  `10_API/gmv_dropbox_connector.py::DropboxConnector` — the same real functions and calling
  convention your Task 18 work already used (credentials from `~/.gmv_dropbox_oauth.json`,
  `temperature=0, seed=42`).

## Steps

### Step 1 — delete the stale proof artifact

Delete `03_STATE/ombra/GMV-ARTIST-FEDERICO-GARIBALDI.md`. Confirm it is gone
(`ls 03_STATE/ombra/` should then be empty or absent). This directory is gitignored/untracked
runtime state (`00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md:52`), so this is a plain filesystem delete,
not a git operation — do not run any `git` command against it.

### Step 2 — check for an existing Bucchi proposal first

Before running anything live, read `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl` in
full (it is not empty — confirmed non-trivial size this session) and check whether a proposal for
"Danilo Bucchi" (or a close variant) already exists from an earlier, unrelated run. If one already
exists, report its exact content and STOP — do not queue a duplicate, and do not proceed to Step 3.
Only continue to Step 3 if no existing Bucchi proposal is found.

### Step 3 — one-off proof script (not committed), Danilo Bucchi

Write and run a script (e.g. under `/tmp/`) that does, in order:

1. Download and extract the real Bucchi document via `DropboxConnector` / `extract_document()`:
   `/GMV_MASTER_SYSTEM/01_AREA35_MASTER/01_ARTISTS/BUCCHI_Danilo/10_MD_PROCESSED_FILES/09_TEMP_IMPORT__Danilo Bucchi cat.pdf.md`
   (verified to exist, per `opencode_task_13.md`'s own citation — confirm it still exists as your
   own first live check, since that citation predates today).
2. Run `extract_candidates()` on it (`temperature=0, seed=42`, same defaults as Task 18).
3. Call `resolve_entity_gmv_id("Danilo Bucchi", registry)` against the CURRENT real
   `00_CONFIG/gmv_entity_registry.json` (parsed fresh, not the Task 18 in-memory copy). **Confirm
   it returns `None`** (he is not yet registered) — if it unexpectedly resolves to something, STOP
   and report that instead of proceeding (it would mean the registry changed since this task was
   written).
4. Call `propose_entity_identity("Danilo Bucchi", registry, source_id=<the Dropbox locator>,
   evidence_excerpt=<a real short excerpt from the extracted text mentioning Bucchi>,
   suggested_entity_type="ARTIST")`. Confirm it returns a real `EntityIdentityProposal` (not `None`).
5. Call `append_entity_identity_proposals()` with that one proposal, writing to
   `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl`. Read the file back from disk
   afterward and print the new line — confirm it is real, on-disk, and matches what was proposed
   (not just trusting the in-memory object).
6. Stop here. Do not call `confirm_new_entity()` (constraint 5). Do not attempt atom
   building/materialization for Bucchi in this task — that requires a confirmed `gmv_id`, which
   does not exist yet after this task.

## What to report back when done

1. Confirmation Step 1 succeeded (file deleted).
2. Step 2's finding: whether a Bucchi proposal already existed, verbatim, and whether Step 3 ran
   as a result.
3. If Step 3 ran: the real extracted candidate propositions mentioning Bucchi (subject/predicate/
   object), confirmation `resolve_entity_gmv_id` returned `None`, and the exact queued JSONL line
   from Step 3.5, read back from disk.
4. The exact diff of every tracked file you changed (expected: none — this task only deletes
   gitignored state and appends to a gitignored queue) — `git status --short` should show nothing
   new in tracked paths.
5. Your own honest assessment of whether this proposal, once a human confirms it, looks ready to
   produce the subsystem's first real non-empty Monad — or whether you see a reason it might not
   (e.g. a predicate in the extracted propositions that is NOT actually `"partecipa"`, despite the
   task's expectation).
