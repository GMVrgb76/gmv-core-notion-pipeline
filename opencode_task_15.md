# OpenCode Task 15 — wire identity-proposal generation into the real crawler pipeline

**Status: DRAFT TASK — not yet executed. Direct follow-up to Tasks 12-14
(commits `d2644137`, `d662bf37`, `1b2ba0a1`).**
**Read `GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md` (decisions 1-3) before starting.**

## Why this task exists, and why it is different from Tasks 12-14

Tasks 12-14 built and exposed the whole "propose an unresolved name -> queue it -> a human
confirms it" mechanism, but explicitly excluded the real crawler pipeline
(`10_API/gmv_crawler_orchestrator.py`, `automation/gmv_crawler_nightly_run.py`) from every change.
As a result, `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl` is empty even after a
real nightly run, because **nothing in the real pipeline ever calls `propose_entity_identity()`**.
This task closes exactly that gap -- the first task in this series to touch real, already-running
production files.

**This task does NOT touch the registry.** It only generates proposals and queues them. Confirming
a proposal (`confirm_new_entity()`/`confirm_entity_alias()`) stays a separate, human-triggered
action, unchanged from Task 13-14 -- this task must not be the one that breaks that boundary.

## Why this is a safe addition, not a risky rewrite

Verified: the 18-field ATOM schema has no `gmv_id` field yet
(`GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md`) -- identity resolution today is completely
orthogonal to atom-building. This change adds a new, independent, read-only observation over
entities `process_document()` already produces; it changes nothing about which atoms get built or
what they contain. No existing test's expectations about atoms should need to change.

## The exact precedent this mirrors -- read these real lines before writing anything

`entity_type_proposals_needing_verification` already flows through this exact path today:
1. `10_API/gmv_crawler_orchestrator.py`'s `ProcessDocumentResult` carries it as a field.
2. `process_document()` populates it (from `build_relation_atoms()`'s per-atom object type
   proposals, around lines 267-270 -- read the surrounding code to see the real current shape,
   line numbers may have drifted).
3. `automation/gmv_crawler_nightly_run.py` imports `append_entity_proposals` (around line 53) and
   calls it (around lines 308-309) on `result.entity_type_proposals_needing_verification` -- the
   orchestrator itself never touches the queue file; only this top-level script does.

Build the identical shape for identity instead of type. Do not invent a different architecture.

## Hard constraints

1. **Never call `confirm_new_entity()`/`confirm_entity_alias()` from
   `gmv_crawler_orchestrator.py` or `automation/gmv_crawler_nightly_run.py`.** Only
   `propose_entity_identity()` (read-only, proven not to write anything, Task 13) and
   `append_entity_identity_proposals()` (queues a proposal, never touches the registry, Task 13).
2. **No deduplication, no "did you mean" logic.** The same raw name appearing twice in one
   document's entities produces two queued proposals, not one -- consistent with
   `gmv_crawler_entity_identity_proposal_queue.py`'s own documented non-goal.
3. **The registry is read fresh per document, never cached across documents in one run.** A human
   may confirm a new entity mid-run via chat or a direct script; the next document processed in
   the same run should see it. Same reasoning `resolve_entity_gmv_id()`'s own docstring point 7
   already gives, and the same convention `_load_known_artists()`/`_load_known_institutions()`
   already use in the same file (no memoization).
4. **`price_list` documents are unaffected** -- they already return from `process_document()`
   before `extract_candidates()` runs, with `all_entities=()`. Every early-return branch that sets
   the other tuple-typed fields to `()` must also set the new field to `()`, explicitly -- do not
   rely on a default silently covering it if the branch constructs `ProcessDocumentResult` with
   all fields named explicitly (check the real code for how the existing early returns are
   written and match that style exactly).
5. **No new test file for `gmv_crawler_nightly_run.py`.** It has none today, by established
   convention (verified live rather than unit-tested, stated in its own module docstring). Real
   test coverage belongs in `tests/test_gmv_crawler_orchestrator.py`, which already tests
   `process_document()` extensively.
6. **The Step 5 proof script must never write to the real
   `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl` or the real
   `00_CONFIG/gmv_entity_registry.json`.** Use a temporary copy for any write-path exercise.

## Real, already-built pieces to reuse (do not reimplement)

- `10_API/gmv_crawler_entity_resolver.py::propose_entity_identity()`,
  `EntityIdentityProposal` (Task 13) -- read-only, unmodified by this task except for adding the
  new loader in Step 1.
- `10_API/gmv_crawler_entity_identity_proposal_queue.py::append_entity_identity_proposals()`
  (Task 13) -- unmodified.
- `10_API/gmv_crawler_entity_resolver.py::_load_known_artists()`/`_load_known_institutions()` --
  the exact style/pattern for Step 1's new loader (hardcoded path constant, no parameter, read
  fresh, no caching).
- `10_API/gmv_crawler_orchestrator.py::ProcessDocumentResult`,
  `process_document()`'s existing `entity_type_proposals_needing_verification` field -- the exact
  precedent to mirror in Step 2.
- `automation/gmv_crawler_nightly_run.py`'s existing `append_entity_proposals` import and call
  site -- the exact precedent to mirror in Step 3.
- `automation/gmv_crawler_review_tool.py`'s `ENTITY_IDENTITY_PROPOSAL_QUEUE_PATH` constant
  (Task 14, commit `1b2ba0a1`) -- reuse this EXACT path literal
  (`RUNTIME_DIR / "entity_identity_proposal_queue.jsonl"`) in Step 3 so both files agree on where
  the queue lives; do not invent a second path.

## Steps

### Step 1 — `_load_entity_registry()` in `10_API/gmv_crawler_entity_resolver.py`

Add, mirroring `_load_known_artists()`/`_load_known_institutions()` exactly:

```python
ENTITY_REGISTRY_PATH = REPO_ROOT / "00_CONFIG" / "gmv_entity_registry.json"

def _load_entity_registry() -> dict:
    """The real 00_CONFIG/gmv_entity_registry.json, read fresh every call --
    same no-memoization reasoning as resolve_entity_gmv_id()'s own point 7:
    a human may confirm a new entity between two documents in the same run."""
    return json.loads(ENTITY_REGISTRY_PATH.read_text(encoding="utf-8"))
```

Check the real module for where `REPO_ROOT` is already defined and reuse it; do not redefine it.

### Step 2 — `ProcessDocumentResult` gains a field, `process_document()` populates it

In `10_API/gmv_crawler_orchestrator.py`:
- Import `EntityIdentityProposal`, `propose_entity_identity`, `_load_entity_registry` from
  `gmv_crawler_entity_resolver`, alongside the existing `EntityTypeProposal` import.
- Add `entity_identity_proposals: tuple[EntityIdentityProposal, ...] = ()` to
  `ProcessDocumentResult`, after the existing default-valued fields (`price_entries`,
  `price_rejected`, `contract_summary`).
- In `process_document()`, right after the real call to `extract_candidates()` (find it -- it
  assigns `entities, propositions, extraction_rejected`), load the registry and compute:
  ```python
  registry = _load_entity_registry()
  identity_proposals = tuple(
      proposal for proposal in (
          propose_entity_identity(
              entity.name, registry,
              source_id=entity.source_id, evidence_excerpt=entity.evidence_excerpt,
          )
          for entity in entities
      )
      if proposal is not None
  )
  ```
  Pass `identity_proposals` into the final `ProcessDocumentResult(...)` construction as
  `entity_identity_proposals=identity_proposals`.
- Update every OTHER `ProcessDocumentResult(...)` construction in this function (the price_list
  early return, and any other early return) to also pass `entity_identity_proposals=()`
  explicitly, matching how those branches already set the other tuple fields.
- `suggested_entity_type` is `""` for every proposal generated here -- do not add a
  `classify_entity_types()` call in this function; that stays `build_relation_atoms()`'s job,
  scoped to relation objects only. Wiring the two together is explicitly out of scope for this
  task.

### Step 3 — wire the queue append in `automation/gmv_crawler_nightly_run.py`

- Import `append_entity_identity_proposals` from `gmv_crawler_entity_identity_proposal_queue`,
  alongside the existing `append_entity_proposals` import.
- Add `ENTITY_IDENTITY_PROPOSAL_QUEUE_PATH = RUNTIME_DIR / "entity_identity_proposal_queue.jsonl"`,
  matching `ENTITY_PROPOSAL_QUEUE_PATH`'s exact definition style and using the exact same path
  literal `automation/gmv_crawler_review_tool.py` already uses for the same constant name.
- Right after the existing `append_entity_proposals(...)` call, add:
  ```python
  append_entity_identity_proposals(
      result.entity_identity_proposals, ENTITY_IDENTITY_PROPOSAL_QUEUE_PATH, now=now,
  )
  ```

### Step 4 — tests

In `tests/test_gmv_crawler_orchestrator.py` (read its existing style first -- how it stubs
`extract_candidates` via `monkeypatch`, e.g. `test_price_list_routes_to_price_extractor_not_entities_claims`
and neighboring tests):
- A case where the stubbed entities include one name already resolvable in a test registry (no
  proposal for it) and one name that is not (exactly one proposal, with `raw_name`/`source_id`/
  `evidence_excerpt` matching the `CandidateEntity` verbatim, `suggested_entity_type == ""`).
- A price_list-document case asserting `result.entity_identity_proposals == ()`.
- A case with two entities sharing the same unresolved name, asserting TWO proposals are
  produced, not one (guards constraint 2, no silent deduplication).

Check whether `tests/test_gmv_crawler_entity_resolver.py` already has a test for the analogous
`_load_known_artists()`/`_load_known_institutions()` loaders; if so, add one for
`_load_entity_registry()` in the same style. If those loaders have no dedicated test, do not
invent a heavier test standard for this new one than the existing precedent has -- note this
rather than over-building.

### Step 5 — live proof (not committed)

One-off script, same convention as every prior task in this series (not committed, discard or
leave uncommitted after running):
1. Run `process_document()` on a real document known to contain a name not yet in the real
   registry (any real Area35 document not previously used to add an entry -- check
   `00_CONFIG/gmv_entity_registry.json` first for what's already there, e.g. Garibaldi/Bucchi may
   or may not already be present depending on what prior tasks left committed).
2. Confirm `result.entity_identity_proposals` contains a real, correct proposal for that name.
3. Call `append_entity_identity_proposals()` against a **temporary copy of the queue path**
   (e.g. `tmp_path / "entity_identity_proposal_queue.jsonl"`), never the real
   `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl` -- read the line back and confirm
   it round-trips correctly.
4. Do not touch the real registry file or the real runtime queue file with test data at any point.

### Step 6 — verify

`.venv/bin/python -m pytest tests/ -q` and `.venv/bin/python -m ruff check .` -- same bar as every
prior task: only the one pre-existing, unrelated
`tests/security/test_runtime_git_policy.py::test_current_tracked_tree_passes_policy` failure
allowed, nothing new.

## What to report back

1. Whether Step 5's live proof produced a real proposal -- paste it verbatim (the real
   `raw_name`/`source_id`/`evidence_excerpt` values), not paraphrased.
2. Confirmation the real registry and real runtime queue file were NOT touched by the proof
   script (e.g. `git status`/file-mtime check on those two real paths, before and after).
3. Full `.venv/bin/python -m pytest tests/ -q` summary line, and `ruff check .` result.
4. The complete `git diff` / `git status --short` -- every file changed, verbatim. Do not commit
   anything yourself; that is a separate, explicit step for a human to do after review.
