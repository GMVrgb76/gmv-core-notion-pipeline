# GMV Crawler — Monad Materialization Wiring Audit

**Date**: 2026-09-25
**Scope**: what is actually needed to wire `materialize_monad()` (`10_API/gmv_monad_materializer.py`) into a real production pipeline, starting from `atoms_built.jsonl`. Verified by direct code reading on branch `worktree-bridge-cse_01EFSz2nNresRvPh9GbfwwzK` (HEAD `7e9e6f09`). No code was written to produce this document — it is a pre-implementation audit, requested explicitly instead of a rushed wiring attempt.

**Why this document exists**: `GMV_CRAWLER_HANDOFF.md` already states (lines 30-33) that the 16 preplan steps are "schema/contract/thin-translation-layer work", not a wired orchestration loop. This document goes one level deeper: for each required field of `MonadDocument`, it records what exists, what is missing, and in what order the missing pieces should be built — a level of granularity the handoff does not provide.

## 1. `MonadDocument` — required fields and their real status

`materialize_monad()` (`10_API/gmv_monad_materializer.py:427`) accepts a `MonadDocument` (lines 180-193):

```python
gmv_id: str
entity_type: str
canonical_name: str
status: str
public_text: str
atoms: tuple[AtomCandidate, ...]
sources: tuple[SourceManifestEntry, ...]
```

### 1.1 `gmv_id` — **MISSING PRODUCER. No entity resolution exists.**

- Schema exists: `gmv_core/migration_sql/010_entity_registry.sql` — `entities` table (PK `gmv_id TEXT CHECK(gmv_id GLOB 'GMV-*' ...)`) + `entity_aliases`.
- **The table is never created in production.** `ENTITY_REGISTRY_VERSION = 10` (`gmv_core/migrations.py:33`) is explicitly declared **not** in `CURRENT_SCHEMA_VERSION`/`SUPPORTED_SCHEMA_VERSIONS` — reachable only via an explicit `migrate(db, target_version=10)`. `automation/gmv_crawler_nightly_run.py:373` migrates its own `registry.db` **only** to `CRAWLER_SOURCE_REGISTRY_VERSION` (9), **never** to `ENTITY_REGISTRY_VERSION` (10). Verified: `grep -n "ENTITY_REGISTRY_VERSION" automation/gmv_crawler_nightly_run.py` → no match. The `entities` table does not exist in any real database today, in any environment.
- `grep -rn "INSERT INTO entities"` across the whole repo → **only in `tests/`** (`tests/test_gmv_monad_materializer.py`, `tests/migrations/test_entity_registry.py`). No production caller.
- **`AtomCandidate` (`10_API/gmv_atom_validator.py:168-192`) has no `gmv_id` field at all.** `subject`/`object` are raw strings. `gmv_crawler_atom_builder.py:188` builds the atom with `subject=proposition.subject_raw,  # verbatim, no normalization`.
- **Explicit confirmation, in the code itself, that entity resolution does not exist**: `10_API/gmv_crawler_atom_builder.py:174` — real comment, not mine: *"only ATTRIBUTE predicates are supported in this v0 slice (the rest need entity resolution, which does not exist yet)"*.
- `10_API/gmv_crawler_entity_resolver.py` exists but does **only TYPE classification** (`classify_entity_types()`, line 229: PERSON vs ARTIST via roster + LLM fallback with `needs_verification=True`) — **it does not assign identity, does not group aliases, does not produce a `gmv_id`**. A different module for a different purpose.
- `compute_atom_fingerprint()` (`gmv_atom_validator.py`) accepts `subject_gmv_id`/`object_gmv_id` as **optional external parameters**, never computed internally — a declared extension point, not an implementation.
- **Elsewhere in the repo, as explicitly checked**: `gmv_evidence_pipeline.py::resolve_claims()` (line 702) resolves `resolved_subject_id`/`resolved_object_id` — but against **Notion page IDs** (`row["id"]`, line 707: `candidates.setdefault(name, []).append(row["id"])`), requires a pre-downloaded Notion snapshot as its candidate pool (`notion_rows`), and is designed to match claims to **already-existing** Notion pages, not to generate an independent canonical-identity registry. **Not directly reusable**: different id scheme (Notion page id vs `GMV-*`), dependency on Notion as a source of truth (in tension with the decision already made in migration 010 not to couple `gmv_id` to pre-existing identity schemes, comment lines 12-23 of that SQL file).

**Verdict**: this is the largest missing piece. Not a wiring gap — a component that does not exist and must be designed and built from scratch.

### 1.2 `public_text` — **the module exists and is more complete than expected, but is not wired**

- `10_API/gmv_crawler_public_projector.py` (step 15) **exists in full**: `select_public_atoms()` (line 220), `render_public_text()` (line 263), `project_public()` (line 281, composes both). Tested in `tests/test_gmv_crawler_public_projector.py`.
- **Never called outside tests** — `grep -rn "project_public(\|select_public_atoms(\|render_public_text("` → only `tests/test_gmv_crawler_public_projector.py` and docstring references in `gmv_notion_projection_adapter.py:421`.
- The module docstring (lines 30-32) explicitly states: *"Of §14's six exclusion rules, four are mechanically enforced here, two are honestly not"*. The two not enforced (disclosed, not hidden):
  1. "contract drafts and private economic data" — no sensitivity/classification field exists in either the 18-field ATOM schema or `SourceManifestEntry`; the module declares this a known gap, already cited in crawler spec v0.2's own "open attention points".
  2. "scheduled events presented as having happened" — same kind of gap already declared in `gmv_atom_validator.UNENFORCED_RULE_IDS` for EIC-05/EIC-06: no ATOM field distinguishes a correctly-promoted event from a premature one.
- **`GMV_KNOWLEDGE_MONAD_SPEC_v1.0` §14 does not exist in full in any repo file.** `grep -rln "§14"` finds only citations/paraphrases in `README.md`, `GMV_CRAWLER_HANDOFF.md`, `00_CONFIG/SYSTEM_MAP.md`, `00_CONFIG/STABILIZATION_EXIT_CRITERIA.md`, and the `gmv_crawler_public_projector.py` docstring itself (which summarizes the 6 exclusion rules, not a verbatim transcript). The full text lives **only on Notion** (page id `3b95a429-a028-8116-a236-d8867862d077`, "FORMAL FREEZE 11 August 2026") and must be re-fetched by whoever extends this module — not verifiable offline today.
- `VISIBILITY` has no governed vocabulary anywhere in the repo (no entry in `GMV_ONTOLOGY_REGISTRY_v0.1.json`, no CHECK constraint) — the module treats `"PUBLIC"` as a hardcoded literal (`PUBLISHABLE_VISIBILITY = "PUBLIC"`), explicitly declared as "this module's own decision, not a transcription of a governed enum that does not yet exist".

**Verdict**: the only one of the three pieces that is "ready to be wired" — needs only a real caller, not substantial new logic (aside from the two exclusions declared inapplicable without new schema fields).

### 1.3 `sources: tuple[SourceManifestEntry, ...]` — **raw data partially available, no assembly exists**

`SourceManifestEntry` (`gmv_monad_materializer.py:150-159`) requires: `source_id, path, source_type, size, modified, hash_value, epistemic_level, extraction_status, notes`.

- `size`/`modified`/hash are **actually available** today in `SourceMetadata` (`10_API/gmv_crawler_contracts.py:57-70`, `SourceConnector.metadata()` contract), implemented by `gmv_dropbox_connector.py` (lines 227-244: `size=entry["size"]`, `modified_at=_parse_dropbox_timestamp(entry["server_modified"])`, real Dropbox API data, not placeholders).
- **But `crawler_source_registry` (migration 009, the only crawler table actually created in production via `nightly_run.py:373`) does NOT persist `size` or `modified`** — real schema (`gmv_core/migration_sql/009_crawler_source_registry.sql`): only `content_hash, connector, canonical_locator, resource_oid, remote_revision, state, discovered_at, last_seen_at, deleted_at`. Whoever builds a `SourceManifestEntry` in the future must either re-query the connector (`metadata(locator)`) at materialization time, or extend the registry schema to persist these fields — neither has been done.
- **No production code ever constructs a real `SourceManifestEntry`** — confirmed by an explicit grep cited inside `gmv_crawler_public_projector.py` itself (in its "inferences from blocked sources" section: *"No production code constructs a real SourceManifestEntry yet (verified by repo-wide grep)"*), consistent with independent verification here.
- `extraction_status` already has a real, reusable closed vocabulary: `gmv_crawler_extractor.STATUS_VALUES` (step 10: `SUCCESS/OCR_REQUIRED/UNSUPPORTED_FORMAT/EXTRACTION_FAILED/EXTRACTION_ABORTED_STALE_HASH`) — should not be reinvented.
- `source_id`: `AtomCandidate.source` today is populated with `proposition.source_id`, which is itself `locator` (the Dropbox path, see `automation/gmv_crawler_nightly_run.py:242`: `extract_document(tmp_path, source_id=locator, ...)`). If a future `SourceManifestEntry.source_id` does not use exactly this same value, the `select_public_atoms()`↔manifest matching (which compares by `source_id`) breaks silently.
- `epistemic_level`: **no equivalent field exists anywhere in the crawler's data structures today** — not populable from existing data, requires a new design decision (see §2 below).

**Verdict**: partially ready. The raw data (size/modified/hash) exists at the edge (connector), but no code collects it, persists it, or assembles it into `SourceManifestEntry` — and one of the 9 fields (`epistemic_level`) has no data source at all today.

## 2. Open design questions (for a human to decide — no invented answers here)

1. **`gmv_id` generation scheme**: sequential, content-derived, UUIDv7? Migration 010 explicitly leaves this undecided ("NOT decided by this migration"). Who/when assigns a new `gmv_id` — the first atom that mentions a never-seen entity, or only after a human review pass?
2. **Entity-resolution matching algorithm**: what signals decide that "Federico Garibaldi" and "F. Garibaldi" are the same entity? Known roster (`00_CONFIG/area35_known_artists.json`, already used by `gmv_crawler_entity_resolver.py` for TYPE) + fuzzy match? Local LLM with mandatory human verification (a pattern already used elsewhere in the crawler, e.g. `gmv_crawler_entity_resolver.py`'s two-category "MATCHED_KNOWN_ARTIST_ROSTER vs MODEL_INFERENCE", never an automatic merge)? The rule "never fuzzy-match → automatic merge" is already written in migration 010's comments — but the concrete algorithm is not.
3. **Who writes to `entities`/`entity_aliases`?** Does this need a new explicit module (`gmv_crawler_entity_registrar.py`?) or an extension of `gmv_crawler_entity_resolver.py`? No decision made.
4. **`epistemic_level` for `SourceManifestEntry`**: what vocabulary, and who assigns it (deterministic per connector type — Dropbox=ARCHIVE? — or per document)? No precedent in the repo.
5. **VISIBILITY governance**: formalize a closed vocabulary (like `PREDICATE_CLASS`) or accept the projector's hardcoded `"PUBLIC"` literal as the permanent current state?
6. **Sensitive-data classification** (contracts/economic data) on the ATOM or on the SOURCE — no field exists; does it need to be added to the 18-field schema (a freeze to respect, see `GMV_KNOWLEDGE_MONAD_SPEC_v1.0` §20) or handled upstream, at extraction time?
7. **`size`/`modified` persistence**: extend `crawler_source_registry` (migration 009, already live) with two columns, or re-query the connector at materialization time (costs a network call per source, for every regenerated Monad)?
8. **Who orchestrates the real loop?** Today `process_document()` only produces `atoms_built.jsonl`; nothing calls `reconcile()` (step 12, never wired) before considering a batch of atoms "ready" for a Monad. Must be decided whether `reconcile()` is a blocking prerequisite for this work or a later improvement.

## 3. Concrete work sequence, ordered by dependency

**Do not skip pieces — each phase depends on the previous one.**

1. **Decide (not build) questions 1-3 and 5-6 above** — these are blocking design decisions; no code makes sense without these answers.
2. **Build entity resolution / `gmv_id` assignment** (the largest gap, §1.1): new module, real writes to `entities`/`entity_aliases` (which requires first activating `ENTITY_REGISTRY_VERSION=10` in `nightly_run.py`'s `registry.db` migration, never reached today). Without this, `MonadDocument.gmv_id` is not obtainable for any real atom.
3. **Wire `reconcile()` (step 12) into the production loop**, before grouping atoms under a `gmv_id` — otherwise Monads get materialized with duplicate/contradictory atoms that were never reconciled (the same risk already flagged in the earlier report on Notion-as-a-source, same underlying principle here).
4. **Extend `crawler_source_registry` with `size`/`modified`** (or decide to re-fetch from the connector) — low technical dependency, but must happen before step 5 because `SourceManifestEntry` needs it.
5. **Build the `SourceManifestEntry` assembly module** from `crawler_source_registry` + `gmv_crawler_extractor.STATUS_VALUES` + the `epistemic_level` decision (question 4).
6. **Write the real caller**: a new module/function (does not exist yet) that, for each resolved `gmv_id`, groups its atoms from `atoms_built.jsonl`, calls `project_public()` (already ready, §1.2) to get `public_text`, assembles `sources` (step 5), and calls `materialize_monad()`.
7. **Wire this caller into `automation/gmv_crawler_nightly_run.py`** (or a separate new step, if decoupling materialization from the nightly ingestion cron is preferred) — writing under `03_STATE/ombra/`, already decided and documented (`00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md:52`).
8. **Only after that**, optionally: `gmv_crawler_derived_views.py`/`gmv_crawler_fulltext_index.py` to make materialized Monads queryable beyond `show_artist_data`.

## 4. Honest readiness estimate

| Piece | Status | Ready vs. to build |
|---|---|---|
| `materialize_monad()` / `render_monad_markdown()` | Complete, tested | ~100% ready — no work needed |
| `project_public()` (public_text) | Complete, tested, never wired | ~90% ready — just needs a caller; 2 exclusion rules remain unenforced by design (a known schema gap, not a bug) |
| `SourceManifestEntry` assembly | Raw data partially available (size/modified via connector, not persisted); no assembly | ~30% ready — needs schema extension + a new assembly module, not just wiring |
| Entity resolution / `gmv_id` | Only SQL schema exists (never migrated to production); no producer; `gmv_crawler_entity_resolver.py` covers only TYPE, not identity | ~5% ready — effectively built from scratch, including the design decisions (§2, questions 1-3) |
| `reconcile()` wiring | Complete module, tested, never called from production | ~80% ready as a module, 0% wired |
| End-to-end orchestration (real loop) | Does not exist | 0% — new module |

**Honest conclusion**: the piece named first when this work was proposed (`gmv_id`) is also the real bottleneck and the largest piece of work, not a wiring detail. `public_text` is almost free. `SourceManifestEntry` is medium, well-scoped work. Without entity resolution, "wiring `materialize_monad()` into the real pipeline" is not even well-defined conceptually, because there is not yet any way to know which atoms in `atoms_built.jsonl` belong to the same Monad.
