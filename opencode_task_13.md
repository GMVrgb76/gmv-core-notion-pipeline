# OpenCode Task 13 — the "stop and ask" mechanism (propose + human-confirmed identity resolution)

**Status: DRAFT TASK — approved plan, not yet executed. Delegated for implementation.**
**Do not treat anything in this file as already true of the codebase except where it says "verified".**
**This is the direct follow-up to Task 12 (commit `d2644137`, then two small fixes committed
separately). Read `GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md` in full before starting — every
design decision this task implements is recorded there, dated 2026-09-26, decisions 1-3.**

## Why this task exists (context, verified this session)

Task 12 built `resolve_entity_gmv_id()` (`10_API/gmv_crawler_entity_resolver.py`) and proved the
identity-resolution chain works end-to-end for a name that ALREADY had a hand-written registry
entry. The real gap: when a name resolves to `None` today, **nothing happens** — it silently stays
unresolved forever. This task builds the actual "stop and ask" behavior: a name that fails to
resolve must produce a real, reviewable proposal, and a human confirming it must actually update
the registry. Nothing may ever write to the registry automatically.

This directly implements design decisions 1-3 already recorded in
`GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md`: `gmv_id` is sequential (`GMV-000001`, `GMV-000002`,
...), computed on demand (no stored counter), assigned the first time a name is seen -- but ONLY
as an immediate proposal, never an unattended write; the actual write always requires a human
confirmation, mirroring the exact pattern already used elsewhere in this project.

## Hard constraints — do not exceed this scope

1. **No automatic writes to the registry, ever.** Every write (new entity OR new alias) goes
   through a human-confirmed function that mirrors `automation/gmv_crawler_review_tool.py`'s
   `confirm_institution()` exactly (read the whole file, then check its lines ~177-196): read the
   JSON file, check for an existing match, append, write back. A proposal being generated and
   queued is NOT a write to the registry — it is a separate JSONL file.
2. **No automatic merging, no fuzzy matching, no LLM call anywhere in this task.** This task only
   detects "this name resolved to nothing" and lets a human decide what to do about it. It does
   NOT build any similarity/suggestion layer (that is a separate, deliberately deferred design
   decision -- do not build it here even if it seems like a small addition).
3. **No change to any production pipeline file.** Do not edit
   `automation/gmv_crawler_nightly_run.py`, `10_API/gmv_crawler_orchestrator.py`, or
   `10_API/gmv_crawler_entity_proposal_queue.py`. New functions only, exercised by a one-off
   script -- same as Task 12.
4. **The proof script is not committed**, same as Task 12. Discard it after running, or leave it
   uncommitted.
5. **Sequential `gmv_id`, no stored counter.** Compute the next id by scanning existing `gmv_id`
   values in the registry and taking the highest numeric suffix + 1 -- never a separate
   `"next_sequence"` field (verified reasoning already recorded in the audit doc: a separate
   counter is a second source of truth that can drift from hand-edits to the file).

## Two things this task starts by fixing, not building around

**A. The existing registry entry uses the wrong id format.** Task 12's proof used
`GMV-ARTIST-FEDERICO-GARIBALDI` (content-derived), which the audit doc's decision 1 explicitly
rejects in favor of sequential ids. Retrofit it to `GMV-000001` as Step 1 below, before writing
any "assign the next id" logic — building that logic against a registry whose only entry is
non-numeric is needlessly awkward, and there is no reason to keep the wrong format now that the
scheme is decided.

**B. The existing entity-proposal queue is NOT a general-purpose queue — do not extend or import
from it.** Read `10_API/gmv_crawler_entity_proposal_queue.py`'s own module docstring in full. It
states explicitly: "this queue stays SEPARATE from Task 7's rejection queue -- same JSONL
pattern, two different files for two different concerns... never merged into one," and its
`append_entity_proposals()` function is hard-coded to `EntityTypeProposal`'s exact 4 fields
(`entity_name, entity_type, confidence, source`). The new identity-resolution proposal needs a
**new, parallel file following the identical JSONL pattern** (Step 3 below) — do not try to widen
the existing module to accept a second proposal shape; that would violate its own stated design
principle.

## Real, already-built pieces to reuse (do not reimplement)

- `10_API/gmv_crawler_entity_resolver.py::resolve_entity_gmv_id()` — unmodified. Read its full
  docstring (7 numbered design decisions) before adding anything else to this file; new functions
  must not contradict any of them.
- `10_API/gmv_crawler_entity_proposal_queue.py` — read only, as the template pattern for Step 3
  (JSONL, one object per line, `queued_at` added on the envelope not the dataclass itself, file
  created only if something is actually queued, append never overwrite, path supplied by the
  caller, no hardcoded default path).
- `automation/gmv_crawler_review_tool.py::confirm_institution()` — the exact shape both new
  confirm functions (Step 4) must mirror.
- `10_API/gmv_crawler_candidate_extractor.py::extract_candidates()`,
  `10_API/gmv_crawler_extractor.py::extract_document()`, `10_API/gmv_evidence_pipeline.py::sha256_file()`,
  `10_API/gmv_dropbox_connector.py::DropboxConnector` — same real functions Task 12 already used;
  read Task 12's own diff/report if you need the exact calling convention (credentials from
  `~/.gmv_dropbox_oauth.json`, `temperature=0, seed=42`, etc.).
- `gmv_core/migration_sql/010_entity_registry.sql` lines 64-65 — the `gmv_id` format constraint
  (`GLOB 'GMV-*' AND length > length('GMV-')`) any generated id must satisfy.
- `00_CONFIG/crawler_predicate_text_mapping.json` — already has `"partecipa"` mapped to
  `participated_in`; relevant for Step 5's bonus check.

## Steps

### Step 1 — retrofit the existing registry entry

In `00_CONFIG/gmv_entity_registry.json`, change Federico Garibaldi's `gmv_id` from
`GMV-ARTIST-FEDERICO-GARIBALDI` to `GMV-000001`. Then open `tests/test_gmv_crawler_entity_resolver.py`
and search the WHOLE file (not from memory) for every occurrence of the old id string — the
`GARIBALDI` fixture dict and every assertion that compares against that literal — and update all
of them consistently. Run `.venv/bin/python -m pytest tests/ -q` and confirm it still shows only
the one pre-existing, unrelated failure
(`tests/security/test_runtime_git_policy.py::test_current_tracked_tree_passes_policy`, a
personal-absolute-path finding unrelated to this task) before moving to Step 2.

### Step 2 — `EntityIdentityProposal` + `propose_entity_identity()`

Add to `10_API/gmv_crawler_entity_resolver.py`, alongside `resolve_entity_gmv_id()`:

```python
@dataclass(frozen=True)
class EntityIdentityProposal:
    """A name that resolve_entity_gmv_id() could not resolve, worth a human's
    attention -- NEVER a decision. Mirrors EntityTypeProposal's own contract
    in this same file, for the identity question instead of the type
    question."""
    raw_name: str
    suggested_entity_type: str  # from classify_entity_types(), "" if unavailable
    source_id: str
    evidence_excerpt: str


def propose_entity_identity(
    name: str, registry: dict, *, source_id: str, evidence_excerpt: str,
    suggested_entity_type: str = "",
) -> EntityIdentityProposal | None:
    """None if `name` already resolves via resolve_entity_gmv_id() -- nothing
    to propose. Otherwise a real EntityIdentityProposal. Does NOT queue
    anything itself -- queueing stays the caller's explicit decision, the
    same principle gmv_crawler_entity_proposal_queue.py's own docstring
    already states for the type-proposal case."""
```

Match this file's existing docstring style (see `resolve_entity_gmv_id()` for the level of detail
expected: every non-obvious choice traced to a real precedent, not just described).

### Step 3 — parallel proposal queue module

New file `10_API/gmv_crawler_entity_identity_proposal_queue.py`. Read
`10_API/gmv_crawler_entity_proposal_queue.py` in full first and copy its real conventions exactly
(do not paraphrase from memory — re-read it). Build:

```python
def append_entity_identity_proposals(
    proposals: Sequence[EntityIdentityProposal], queue_path: Path, *, now: str,
) -> int:
    """Append each proposal as one JSON line (all 4 EntityIdentityProposal
    fields verbatim plus queued_at=now on the envelope). Creates the file
    and parent directories only if there is at least one proposal to write;
    an empty input leaves any existing file untouched. Append, never
    overwrite. Returns the number of lines written."""
```

Only add a summary/read-back function if Step 5 actually needs one to verify the queue's real
contents — do not build unused code speculatively.

### Step 4 — two human-confirmed write functions

Add to `10_API/gmv_crawler_entity_resolver.py`:

```python
def next_sequential_gmv_id(registry: dict) -> str:
    """max(existing numeric GMV-NNNNNN ids in registry) + 1, formatted as
    GMV-000001-style (6-digit zero-padded). Returns "GMV-000001" if the
    registry has no numeric-format ids yet. A non-numeric legacy id (there
    should be none after Step 1's retrofit) is ignored when computing the
    max, not treated as an error."""

def confirm_new_entity(canonical_name: str, entity_type: str, registry_path: Path) -> str:
    """Reads registry_path, computes next_sequential_gmv_id(), appends a new
    entity ({"gmv_id": ..., "entity_type": entity_type, "canonical_name":
    canonical_name, "aliases": [], "status": "ACTIVE"}), writes the file
    back. Mirrors confirm_institution()'s exact read-check-append-write
    shape. Returns the new gmv_id."""

def confirm_entity_alias(gmv_id: str, new_alias: str, registry_path: Path) -> str:
    """Reads registry_path, finds the entity with this exact gmv_id (raise a
    clear error if none exists -- do not silently no-op), appends new_alias
    to its aliases list if not already present (no-op with a clear return
    message if it's already there, mirroring confirm_institution()'s
    "was already in the list" case), writes the file back. Returns a short
    human-readable confirmation string."""
```

These two functions are the ONLY code in this whole task that writes to
`00_CONFIG/gmv_entity_registry.json`. Both are meant to be triggered by an explicit human action
(this task does not need to wire them into the Open WebUI chat tool -- that is a separate later
step; just build the functions themselves and call them directly from Step 5's proof script).

### Step 5 — second real proof (not committed)

One-off script (not committed, same convention as Task 12), proving the FULL loop on a second,
different real entity: **Danilo Bucchi**. Real Dropbox path, verified to exist:
`/GMV_MASTER_SYSTEM/01_AREA35_MASTER/01_ARTISTS/BUCCHI_Danilo/10_MD_PROCESSED_FILES/09_TEMP_IMPORT__Danilo Bucchi cat.pdf.md`.
His real predicate `"partecipa"` is already mapped to `participated_in` in
`00_CONFIG/crawler_predicate_text_mapping.json`, so — unlike Task 12's Garibaldi proof, which
produced zero atoms because none of that document's predicates were mapped — this proof should be
able to produce at least one real ATOM. That is worth checking (step 6 below) but is not this
task's main goal; the main goal is the propose → confirm → resolve loop itself.

1. Download and extract the document, run `extract_candidates()` on it (same real
   download/extract/candidate-extraction calls Task 12 used).
2. Call `resolve_entity_gmv_id("Danilo Bucchi", registry)` on the current (pre-Step-1-retrofit-
   unaffected) registry — confirm it returns `None` (he is not yet in the registry).
3. Call `propose_entity_identity()` for `"Danilo Bucchi"`, then
   `append_entity_identity_proposals()` to actually write it to a real queue file. Read the
   queued line back from disk and print it — confirm it is real, not just an in-memory object.
4. Call `confirm_new_entity("Danilo Bucchi", "ARTIST", registry_path)`. It MUST return
   `GMV-000002` — not `GMV-000001` (already used by Garibaldi after Step 1's retrofit). If it
   returns anything else, that is a real bug in `next_sequential_gmv_id()` to report, not to
   paper over.
5. Re-read the registry file from disk (a fresh read, not the in-memory dict from step 2) and
   call `resolve_entity_gmv_id("Danilo Bucchi", registry)` again — confirm it now returns
   `GMV-000002`. This is the actual proof the loop closes: unresolved → proposed → confirmed →
   resolved.
6. Bonus check, worth reporting but not required for this task to count as successful: run the
   candidates whose subject resolves to `GMV-000002` through `build_atoms()`/
   `build_relation_atoms()` (same functions Task 12 used) and report whether any real atom was
   built this time (expected: yes, at least one, via the already-mapped `partecipa` predicate) —
   if zero, report the exact rejection reason the same way Task 12's report did, don't guess.

### Step 6 — verify

`.venv/bin/python -m pytest tests/ -q` and `.venv/bin/python -m ruff check .` — same bar as
Task 12: only the one pre-existing, unrelated failure allowed, nothing new. Write tests for every
new function (`propose_entity_identity`, `append_entity_identity_proposals`,
`next_sequential_gmv_id`, `confirm_new_entity`, `confirm_entity_alias`) at the same rigor as the
10 tests already written for `resolve_entity_gmv_id()` in `tests/test_gmv_crawler_entity_resolver.py`
(one test per real guarantee, a docstring stating exactly what each test tries to break — read
those 10 tests first as the quality bar, don't write thinner tests than that).

## What to report back when done

Same shape as Task 12's report — a short, factual report, not a new markdown file unless asked:

1. Whether Step 5's loop actually closed, with the REAL values from your own run (not
   paraphrased): the exact `gmv_id` `confirm_new_entity()` returned, and confirmation that the
   fresh re-read resolved to that same id.
2. The result of Step 5.6 (the bonus atom check) — how many atoms, their real subject/predicate/
   object values, or the exact rejection reason if zero.
3. Confirmation that `.venv/bin/python -m pytest tests/ -q` shows only the one known pre-existing
   failure, nothing new — paste the actual summary line.
4. The exact `git diff` / `git status --short` — every file you changed, verbatim. Do not commit
   anything yourself; that is a separate, explicit step for a human to do after review.
