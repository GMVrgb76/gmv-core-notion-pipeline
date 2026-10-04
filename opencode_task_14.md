# OpenCode Task 14 — expose the identity propose/confirm loop in the Open WebUI tool

**Status: DRAFT TASK — not yet executed. Direct follow-up to Task 13 (commit `d662bf37`).**
**Read `GMV_CRAWLER_MONAD_MATERIALIZATION_AUDIT.md` (decisions 1-3) and Task 13's own report
before starting if anything below is unclear.**

## Why this task exists

Task 13 built a real, tested propose/confirm identity-resolution loop
(`10_API/gmv_crawler_entity_resolver.py`: `propose_entity_identity()`, `confirm_new_entity()`,
`confirm_entity_alias()`; `10_API/gmv_crawler_entity_identity_proposal_queue.py`), but the only way
to call any of it today is a one-off Python script. The human confirmation step this whole design
depends on (decision 3: every write is human-triggered, never automatic) has no real interface yet
-- there is no way for the user to see a pending identity proposal or confirm one from the chat
tool they already use daily. This task closes that gap the same way `confirm_institution()`/
`confirm_predicate_mapping()` already did for institutions and predicates: by adding the matching
functions to `automation/gmv_crawler_review_tool.py`.

**This task does NOT wire anything into the nightly crawler or orchestrator** -- it only exposes
the already-built, already-tested Task 13 functions to a human, via chat. Whether/how the crawler
itself starts calling `propose_entity_identity()` on real documents is separate, later work, not
this task.

## Hard constraints

1. **No new logic.** Every function this task adds is a thin wrapper calling the real functions
   already built and tested in Task 13 (`10_API/gmv_crawler_entity_resolver.py`,
   `10_API/gmv_crawler_entity_identity_proposal_queue.py`). Do not reimplement resolution,
   sequencing, or file I/O here -- import and call.
2. **Mirror `confirm_institution()`'s exact shape and tone** (read `automation/gmv_crawler_review_tool.py`
   lines ~294-322 in full first): a short Italian docstring telling the calling LLM exactly when to
   use it and, critically, the same explicit instruction pattern -- "Usa questa funzione SOLO
   quando l'utente ha confermato esplicitamente... non decidere da solo, non dedurlo dal contesto."
   Every new function here needs that same instruction, adapted to its own action.
3. **No change to `10_API/gmv_crawler_entity_resolver.py`,
   `10_API/gmv_crawler_entity_identity_proposal_queue.py`, or any other file already built in
   Tasks 12-13.** Import from them, do not modify them.
4. **This file (`automation/gmv_crawler_review_tool.py`) is the one this project already has a
   documented workaround for**: direct SQLite/DB writes are blocked by a Claude Code permission
   classifier in some sessions, but this is a plain Python file edit — no special handling needed
   here, just edit it normally with your own tools.

## Real, already-built pieces to reuse

- `10_API/gmv_crawler_entity_resolver.py::confirm_new_entity(canonical_name, entity_type, registry_path) -> str`
  (returns the new `gmv_id`)
- `10_API/gmv_crawler_entity_resolver.py::confirm_entity_alias(gmv_id, new_alias, registry_path) -> str`
  (returns a confirmation message)
- `10_API/gmv_crawler_entity_resolver.py::VALID_ENTITY_TYPES` — the governed vocabulary
  `confirm_new_entity()` already validates `entity_type` against; surface it to the reviewing LLM
  the same way `list_known_governed_predicates()` (line ~539) surfaces the predicate vocabulary,
  so it can be told the valid values rather than guessing.
- `10_API/gmv_crawler_entity_identity_proposal_queue.py` — read-only here (no summary function
  exists yet per Task 13's own documented choice not to build one speculatively); read the queue's
  raw JSONL lines directly in the new listing function below, the same way
  `list_unrecognized_predicates()` (line ~257) reads `REJECTION_QUEUE_PATH` directly without a
  dedicated summary module.
- Existing constants already in this file to copy the pattern from: `INSTITUTIONS_PATH`,
  `ENTITY_PROPOSAL_QUEUE_PATH`, `API_DIR` (already inserted into `sys.path`, so importing from
  `10_API` needs no new path setup).

## Steps

### Step 1 — new path constants

Add near the existing ones (after `ENTITY_PROPOSAL_QUEUE_PATH`, line ~23):

```python
ENTITY_REGISTRY_PATH = REPO_ROOT / "00_CONFIG" / "gmv_entity_registry.json"
ENTITY_IDENTITY_PROPOSAL_QUEUE_PATH = RUNTIME_DIR / "entity_identity_proposal_queue.jsonl"
```

### Step 2 — import the real functions

Near the top of the file, alongside any other `10_API` imports already there (check if there are
none yet at module scope — if imports currently happen inline inside methods like
`run_crawler_on_files`, follow that same existing convention instead of introducing a new style).
Import with explicit names to avoid shadowing the new tool methods of the same name:

```python
from gmv_crawler_entity_resolver import (
    VALID_ENTITY_TYPES,
    confirm_entity_alias as _confirm_entity_alias,
    confirm_new_entity as _confirm_new_entity,
)
```

### Step 3 — `list_pending_entity_identities()`

New method on `Tools`, same file, near `list_entities_needing_verification()`:

```python
def list_pending_entity_identities(self) -> str:
    """Elenca i nomi che il crawler ha incontrato ma non e' riuscito a
    collegare a nessuna entita' gia' conosciuta -- ognuno aspetta una
    decisione umana: e' una persona nuova, o e' un altro modo di scrivere
    il nome di qualcuno gia' registrato? USA SEMPRE questa funzione prima
    di confirm_new_entity/confirm_entity_alias, per mostrare all'utente il
    contesto reale (dove e' stato trovato il nome, con quale frase) prima
    di decidere -- mai confermare alla cieca."""
```

Read `ENTITY_IDENTITY_PROPOSAL_QUEUE_PATH` the same defensive way `list_unrecognized_predicates()`
reads its own queue (handle the file not existing yet: return a clear "nessuna proposta in
sospeso" message, do not raise). Each line has `raw_name`, `suggested_entity_type`, `source_id`,
`evidence_excerpt`, `queued_at` (Task 13's `_QUEUE_KEYS` plus the envelope field) — show all of
them per entry so the reviewer has the real evidence, not just the name.

### Step 4 — `list_known_entities()`

New method, mirroring `list_known_institutions()` (line ~294) exactly, but reading
`ENTITY_REGISTRY_PATH`'s `entities` list instead of `institutions`. Show `gmv_id`,
`canonical_name`, `aliases`, `entity_type` per entry — the reviewer needs to see existing aliases
to judge whether an unresolved name might already belong to one of them.

### Step 5 — `confirm_new_entity()` and `confirm_entity_alias()` tool methods

```python
def confirm_new_entity(self, canonical_name: str, entity_type: str) -> str:
    """Conferma che 'canonical_name' e' una persona/entita' NUOVA, mai
    registrata prima, e le assegna un gmv_id stabile. 'entity_type' deve
    essere uno dei valori governati (usa list_known_governed_entity_types
    se non sei sicuro). Usa questa funzione SOLO quando l'utente ha
    confermato esplicitamente, in questa conversazione, che si tratta
    davvero di un'entita' nuova -- non decidere da solo, non dedurlo dal
    contesto (stesso principio gia' applicato a confirm_institution).
    Se il nome esiste gia' o e' ambiguo tra piu' entita', questa funzione
    rifiuta con un errore chiaro invece di scrivere qualcosa di sbagliato
    -- riporta quell'errore all'utente cosi' com'e', non nasconderlo."""
    try:
        gmv_id = _confirm_new_entity(canonical_name, entity_type, ENTITY_REGISTRY_PATH)
    except ValueError as exc:
        return f"ERRORE: {exc}"
    return f"Confermato: '{canonical_name}' registrata come nuova entita' con id {gmv_id}."


def confirm_entity_alias(self, gmv_id: str, new_alias: str) -> str:
    """Conferma che 'new_alias' e' un altro modo di scrivere il nome
    dell'entita' che ha gia' l'id 'gmv_id' (usa list_known_entities per
    trovare l'id giusto). Usa questa funzione SOLO dopo conferma esplicita
    dell'utente che sono davvero la stessa entita' -- mai una tua
    deduzione. Se il gmv_id non esiste, questa funzione rifiuta con un
    errore chiaro elencando gli id realmente presenti -- riportalo
    all'utente, non inventare un id."""
    try:
        return _confirm_entity_alias(gmv_id, new_alias, ENTITY_REGISTRY_PATH)
    except ValueError as exc:
        return f"ERRORE: {exc}"
```

Add a small `list_known_governed_entity_types()` method too if `VALID_ENTITY_TYPES` isn't already
surfaced anywhere in this file — one line per value, same minimal style as
`list_known_governed_predicates()`.

### Step 6 — verify

1. `python3 -m py_compile automation/gmv_crawler_review_tool.py` — must succeed.
2. `.venv/bin/python -m pytest tests/ -q` — same bar as Tasks 12-13: only the one pre-existing,
   unrelated `test_current_tracked_tree_passes_policy` failure allowed (this file already has a
   `personal_absolute_path` finding pre-dating this task; adding more lines to it does not need to
   fix that finding, just not add a NEW kind of test failure).
3. **Live check, not just import**: write a short one-off script (not committed) that imports
   `Tools` from this file and calls each new method directly against real data — at minimum,
   `list_known_entities()` should show the real `GMV-000001`/`GMV-000002` entries from Tasks 12-13,
   and `list_pending_entity_identities()` should show whatever is currently in
   `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl` (if Task 13's proof run left a
   real queue file there — check first; if not, that's fine, report "queue empty" honestly rather
   than fabricating a line to show it "works").

## What to report back

Same shape as Tasks 12-13: whether each new method was exercised against real data (paste the
actual real output, not paraphrased), the `.venv/bin/python -m pytest tests/ -q` summary line,
and the complete `git diff` / `git status --short`. Do not commit anything yourself.

## Files touched

- Modified: `automation/gmv_crawler_review_tool.py` (Steps 1-5)
- New, not committed: the Step 6.3 one-off verification script
- Untouched: everything in `10_API/`, all of Tasks 12-13's own files
