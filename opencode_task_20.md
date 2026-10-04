# OpenCode Task 20 — attempt the first real non-empty Monad (Danilo Bucchi, now GMV-000002)

**Status: DRAFT TASK — approved plan, not yet executed. Delegated for implementation.**
**Do not treat anything in this file as already true of the codebase except where it says "verified".**

## Context (verified this session, directing Claude session, commit `e26cbf10`)

`00_CONFIG/gmv_entity_registry.json` now has two entities: `GMV-000001` (Federico Garibaldi) and
**`GMV-000002` (Danilo Bucchi, entity_type `ARTIST`, status `ACTIVE`, no aliases)**, committed in
`e26cbf10 feat: confirm Danilo Bucchi as GMV-000002 (ARTIST)`. This was a deliberate, explicit
human confirmation (via `confirm_new_entity()`, called directly, not by an unattended pipeline) —
not something this task needs to re-decide or re-justify.

Your own Task 19 report (verified independently by the directing session: real file reads, no
assumptions) established:
- `03_STATE/ombra/` is currently empty — no Monad file exists for Bucchi or anyone else.
- A real identity proposal for "Danilo Bucchi" already exists in
  `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl` (queued 2026-09-26, from a real
  extraction run on his real document), alongside 206 other names from the same document —
  **this task re-runs the extraction rather than reusing that queued data**, because the queue only
  stored names, not full `CandidateProposition`s (predicate/object/evidence), which is what atom
  building actually needs.
- The one real open risk you yourself flagged: `EMERGENZE FESTIVAL` and `XVI Biennale di Venezia
  di Architettura` (the real RELATION objects for Bucchi's `"partecipa"` propositions) are not in
  any known roster, so they go to `gemma4:12b` for type classification, and that model is
  documented elsewhere in this project as non-deterministic across runs for the same real name.
  **This task's whole point is to find out, live, whether that risk materializes this time** — do
  not treat success or failure as a bug in your own work either way; report the real outcome.

## Hard constraints — do not exceed this scope

1. **No SQL migration.** Do not touch `gmv_core/migration_sql/` or `ENTITY_REGISTRY_VERSION`.
2. **No fuzzy matching anywhere.** `resolve_entity_gmv_id()` (exact match) is the only identity
   lookup used. The ONE LLM call this task makes is `classify_entity_types()`'s existing,
   already-built, already-deliberately-scoped model fallback for entity TYPE (not identity) — do
   not add any other model call.
3. **No `reconcile()` wiring, no change to any production pipeline file**
   (`automation/gmv_crawler_nightly_run.py`, `10_API/gmv_crawler_orchestrator.py`).
4. **No further registry writes.** Do not call `confirm_new_entity()` or `confirm_entity_alias()`
   in this task — Bucchi is already confirmed; nothing else should be.
5. **The proof script itself is not committed.** Run it from `/tmp/` or similar.
6. **The output `.md` file under `03_STATE/ombra/` is not committed** (gitignored runtime state,
   per `00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md:52` — same as Task 18).
7. **If `materialize_monad()` raises `MonadMaterializationError`, print the full blocker list and
   stop.** Do not loosen any validation or hand-edit data to force a pass — a real failure here
   (e.g. an object entity misclassified outside `participated_in`'s range) is itself the
   reportable finding this task exists to surface, not a problem to route around.

## Real, already-built pieces to reuse (do not reimplement any of these)

Same inventory as Task 18 (already proven to work end-to-end on this subsystem):
`10_API/gmv_monad_materializer.py` (`materialize_monad()`, `MonadDocument`, `SourceManifestEntry`),
`10_API/gmv_crawler_public_projector.py::project_public()`,
`10_API/gmv_crawler_candidate_extractor.py::extract_candidates()`,
`10_API/gmv_crawler_extractor.py::extract_document()`, `10_API/gmv_evidence_pipeline.py::sha256_file()`,
`10_API/gmv_dropbox_connector.py::DropboxConnector`, `10_API/gmv_crawler_extractor.py::STATUS_VALUES`.
Plus, new to this task:
- `10_API/gmv_crawler_entity_resolver.py::resolve_entity_gmv_id()` — resolve `"Danilo Bucchi"`
  against the now-updated registry; expect `GMV-000002`.
- `10_API/gmv_crawler_entity_resolver.py::classify_entity_types()` — the ONE permitted model call,
  for the RELATION objects' entity types. Pass `temperature=0, seed=42` (same determinism
  convention as every other Ollama call in this subsystem).
- `10_API/gmv_crawler_relation_atom_builder.py::build_relation_atoms()` — this document's real
  propositions are RELATION-class (`participated_in`), not ATTRIBUTE-class, so this is the builder
  to use, not `gmv_crawler_atom_builder.py::build_atoms()` (Task 18 used the latter only because
  nothing in the Garibaldi document resolved to a mapped predicate at all).
- `00_CONFIG/crawler_predicate_text_mapping.json` — confirms `"partecipa"` → `participated_in`;
  read it to find the real mapping function/loader already used elsewhere
  (`gmv_crawler_relation_atom_builder.py` itself is the real precedent for how to load and apply
  it — read that file's existing callers rather than inventing a new loading path).

## Steps

### Step 1 — one-off proof script (not committed)

1. Download and extract the same real Bucchi document used by the 2026-09-26 run:
   `/GMV_MASTER_SYSTEM/01_AREA35_MASTER/01_ARTISTS/BUCCHI_Danilo/10_MD_PROCESSED_FILES/09_TEMP_IMPORT__Danilo Bucchi cat.pdf.md`.
   Compute its real hash via `sha256_file()`.
2. Run `extract_candidates()` on it (`temperature=0, seed=42`). Print every resulting
   `CandidateProposition` whose predicate text matches `"partecipa"` (case-insensitive) — there
   should be at least the two already known (EMERGENZE FESTIVAL, XVI Biennale di Venezia di
   Architettura), possibly more or fewer if the model's output varies from the 2026-09-26 run
   (report any difference honestly, do not assume the old queue's 207 names are what you'll get
   today).
3. Call `resolve_entity_gmv_id("Danilo Bucchi", registry)` on the CURRENT real registry (parsed
   fresh). **Confirm it returns `GMV-000002`** — if not, stop and report (would mean something
   about the registry or this call is wrong).
4. For the `"partecipa"` propositions' objects (the RELATION targets), call
   `classify_entity_types()` on them as `CandidateEntity` objects (construct minimally — name +
   whatever else that dataclass requires, check its real definition). Print the real returned
   `entity_type`/`confidence`/`source` for each. This is the one step whose outcome is genuinely
   unknown — report it exactly as returned, including if it lands OUTSIDE
   `participated_in`'s governed range (`EVENT`/`EXHIBITION`/`PROJECT`).
5. Build relation atoms via `build_relation_atoms()` for the resolved `"partecipa"` propositions,
   using the real predicate mapping from `crawler_predicate_text_mapping.json` and the real
   classified object types from step 4. Let it reject/validate normally — do not pre-filter to
   only the propositions you expect to succeed.
6. Build one real `SourceManifestEntry` (same shape/fields as Task 18 Step 2.6: real
   `size`/`modified` from `DropboxConnector.metadata()`, real `hash_value`, `extraction_status`
   `"SUCCESS"`, `epistemic_level` `"UNVERIFIED_PLACEHOLDER"` with the same note as before).
7. Call `project_public()` on whatever atoms actually passed validation (may be zero, one, or
   more — do not force a particular count).
8. Assemble a `MonadDocument` with `gmv_id="GMV-000002"`, `entity_type="ARTIST"`,
   `canonical_name="Danilo Bucchi"`, `status="active"`.
9. Call `materialize_monad(document, target_path=Path("03_STATE/ombra/GMV-000002.md"))`. Per
   constraint 7, report any `MonadMaterializationError` in full rather than working around it.

### Step 2 — verify by inspection (only if Step 1.9 succeeded)

Read the resulting file. Confirm: the YAML/IDENTITY block matches, the ATOMS table has the real
rows from step 5 (not zero, if any passed), every atom's `PREDICATE_CLASS` matches the ontology
registry, the SOURCES row has real non-placeholder size/modified/hash.

### Step 3 — regression check

`.venv/bin/python -m pytest tests/ -q` — confirm only the one pre-existing, unrelated failure
(`test_current_tracked_tree_passes_policy`), nothing new.

## What to report back when done

1. The real `"partecipa"` propositions extracted today (subject/predicate/object/evidence) —
   compare informally to the 2026-09-26 queue's two known cases; note any difference.
2. The real `classify_entity_types()` output for each RELATION object — this is the load-bearing
   finding of this whole task.
3. Whether `materialize_monad()` succeeded or raised, verbatim either way.
4. If it succeeded: how many real atoms, their full field values, and the rendered file's content
   in full.
5. If it raised: the full blocker list, and your own read on whether the cause is a real modeling
   gap (something this project doesn't yet handle) or a one-off model inconsistency (might pass on
   a re-run) — distinguish these, do not conflate them.
6. `git status --short` / `git diff --stat` — expected empty (nothing tracked should change).
7. Step 3's pytest result.
