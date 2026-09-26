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

1. **DECIDED 2026-09-26: `gmv_id` generation scheme is sequential** (`GMV-000001`, `GMV-000002`, ...), not content-derived and not UUIDv7. Rationale: the Implementation Spec v0.2 §11-§12 states `gmv_id` must be "stabile e indipendente dal nome corrente" (stable and independent of the current name) — a content-derived scheme (e.g. `GMV-ARTIST-FEDERICO-GARIBALDI`, derived from `canonical_name`) would break that guarantee the moment a name is corrected, since the id would either have to change with it (violating stability) or silently drift out of sync with the entity it was derived from. Sequential has no such coupling. **Known inconsistency this decision creates**: the 2026-09-26 proof-of-concept registry (`00_CONFIG/gmv_entity_registry.json`, commit `d2644137`) used the now-rejected content-derived scheme (`GMV-ARTIST-FEDERICO-GARIBALDI`) — left as-is, since that file is explicitly labeled a one-entity proof artifact, not production data; a future real registry must use the sequential scheme decided here, not copy that file's id format. **DECIDED 2026-09-26: no separate counter state.** The next sequence number is computed on demand by scanning the existing `gmv_id` values already in the registry file and taking max+1 — never stored as its own field (e.g. `"next_sequence"`). Rationale: a separate counter is a second source of truth that can drift from the entries themselves (someone hand-edits the file without updating it) — the exact class of duplicated state this project avoids elsewhere (e.g. `confirm_institution`/`confirm_predicate_mapping` in the Open WebUI tool read-check-append-write a single file, never maintain a parallel counter). Consistent with the registry's own "human-curated... never auto-populated" rule already on record. **DECIDED 2026-09-26: a new `gmv_id` is assigned at first sighting** — the first time `resolve_entity_gmv_id()` returns `None` for a name, a new entity gets minted immediately, not held for human review first. This is safe under Constitution rule 8 ("if the source establishes an entity but not its class, use a type-neutral identifier and record the typing issue") and is a different act from the already-forbidden "fuzzy-match → automatic merge": minting a new id for an unrecognized name never links two things together, it only ever creates one. **Real consequence, stated not hidden**: this design accepts eager splitting over eager merging as the safer failure mode — if a real entity's second document uses a name variant not yet in its `aliases` (e.g. "F. Garibaldi" before anyone adds it to the registry), it gets its own new `gmv_id`, temporarily splitting one real entity into two records, rather than risking a wrong automatic merge. This is deliberately not prevented upfront; it is corrected afterward, by a human, using the `MERGE_CANDIDATE`/`MERGED`/`merged_into` status machinery `010_entity_registry.sql` already defines for exactly this reason (lines 64-65, 93-117) — a real, already-designed repair path for a real, accepted risk, not an unhandled edge case. Design question 1 is now fully decided.
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

## 5. What existing GMV governance documents already answer

Added after searching Dropbox and Notion directly (2026-09-25), after §1-4 above were already written. These are real, authoritative sources this audit's first pass did not have — they narrow several of §2's open questions, though none fully closes them.

### The full `GMV_KNOWLEDGE_MONAD_SPEC_v1.0` text (Notion, FORMAL FREEZE 11 Aug 2026)

Now readable in full (previously only paraphrased in code docstrings). Confirms §1.2's finding almost exactly: §14's six PUBLIC exclusion rules match `gmv_crawler_public_projector.py`'s own summary. One addition the code docstring omits: rule 6, "historical states presented as current" — a THIRD unenforced exclusion, not just the two the module discloses. The spec leaves `gmv_id` as a bare format placeholder (`GMV-...`) in its worked example — confirms design question 1 is genuinely open even at the frozen-spec level, not an oversight of this audit.

### "GMV Crawler — Specifica di Implementazione v0.2" (Notion)

Directly narrows design questions 1-3 and §3's work sequence:

- **§11-§12, Entity resolution e GMV ID**: confirms a registry shape — `ENTITY_REGISTRY` with `gmv_id, entity_type, canonical_name, aliases[], status, created_at` — and the rule "never fuzzy-match → automatic merge", consistent with migration 010's SQL comments. Note a real discrepancy: this spec keeps `aliases[]` inline on the entity row, while `010_entity_registry.sql` (the only artifact actually migrated toward, though never reached) splits it into a separate `entity_aliases` table — two documented shapes for the same registry, never reconciled. The exact matching **algorithm** is still not specified here either — design question 2 narrows (schema is settled) but is not closed.
- **§33, canonical implementation order**: an authoritative 16-step sequence exists and should supersede this audit's invented 8-step sequence in §3, not sit beside it as an equally-weighted alternative. Relevant excerpt: `1. Constitution v0.1→v0.2 config → 2. Ontology Registry → 3. Registry SQLite schema → 4. Source/Evidence contract → 5. Projection Adapter contract (generic) → 6. Entity Registry → 7. Atom validator → 8. Monad materializer → 9. Dropbox connector → ... → 15. PUBLIC projector → 16. Generalize gmv_notion_multi_candidate.py behind ProjectionAdapter`. This confirms Entity Registry (6) before Atom validator (7) and Monad materializer (8), consistent with §3's dependency reasoning here, but places `reconcile()`-equivalent (12) AFTER materialization (8) — the opposite order §3 of this audit assumed. That ordering conflict is unresolved and should be a design question in its own right.
- **§29, Human review**: real production code (`gmv_notion_multi_candidate.py`) never auto-promotes any entity, even high-confidence ones — always `REVIEW_REQUIRED`. Relevant precedent for design question 3 (who writes to `entities`/`entity_aliases`): likely human-gated by the same established convention, not automatic.
- **Open attention point 5** (the spec's own words, not this audit's): "Governance delle promozioni nell'Ontology Registry... chi promuove un predicate da CANDIDATE a CORE" — an already-recorded open question, parallel to (but distinct from) this audit's design question 1.

### "Epistemic Ingestion Constitution v0.1" (Notion, REQUIRED, ACTIVE)

The 15 mandatory ingestion rules `project_public()`/the atom builder already partially encode. Rule 8 is directly relevant to §1.1: "Entity types must be evidence-supported. If the source establishes an entity but not its class, use a type-neutral identifier and record the typing issue" — a real, existing rule for exactly the gap `gmv_crawler_entity_resolver.py` already implements (`needs_verification=True`), confirming that module's design choice was constitutionally motivated, not an ad hoc shortcut.

### "2026-08-13 GMV Core Ingestion Runtime Handoff" (Dropbox, found misfiled under `GARIBALDI_Federico/09_TEMP_IMPORT/` — a system-wide architecture document, not artist-specific content)

The formal handoff that framed this whole problem, predating this audit by six weeks; no response/deliverable document was found alongside it in Dropbox. §5 independently arrives at the same 5-way problem split §1 of this audit uses (document classification / entity resolution / canonical placement / semantic promotion / physical mutation) and states explicitly: "Entity resolution... non è risolta dal solo tipo documentale e può richiedere confronto con più fonti" — independent confirmation this is a real, recognized gap, not one this audit invented. §6 Fase 3 proposes a concrete 5-step resolution algorithm never yet implemented: (1) deterministic rules/exact lookup, (2) match against existing canonical entities/paths, (3) match against Notion as a knowledge interface (never elevated above SUM), (4) local model if calibrated useful, (5) human review or cloud escalation for persistent ambiguity. This is a real, actionable answer to design question 2 — untested, unimplemented, but not invented here. §2's canonical authority hierarchy (SUM/Dropbox = canonical evidence > Monad.md > Notion = structured interface > derived indexes = rebuildable) is also the strongest documented answer yet to the earlier "Notion as a crawler source" question from this same session: Notion is explicitly ranked below the Monad, and a Notion/SUM conflict must be flagged, never auto-resolved in Notion's favor.

## Sources

- `10_API/gmv_monad_materializer.py`
- `10_API/gmv_crawler_public_projector.py`
- `10_API/gmv_crawler_atom_builder.py`
- `10_API/gmv_crawler_entity_resolver.py`
- `10_API/gmv_evidence_pipeline.py`
- `gmv_core/migration_sql/010_entity_registry.sql`
- `gmv_core/migrations.py`
- `automation/gmv_crawler_nightly_run.py`
- `GMV_CRAWLER_HANDOFF.md`
- [GMV_KNOWLEDGE_MONAD_SPEC_v1.0](https://app.notion.com/p/3b95a429a0288116a236d8867862d077) (Notion, full text fetched 2026-09-25)
- [GMV Crawler — Specifica di Implementazione v0.2](https://app.notion.com/p/3d95a429a0288111bb14e5811a4d3f9c) (Notion)
- [Epistemic Ingestion Constitution v0.1](https://app.notion.com/p/3b95a429a02881458c06fcaf938c5eb3) (Notion)
- [2026-08-13 GMV Core Ingestion Runtime Handoff](https://www.dropbox.com/scl/fi/eh5rc3crep9h34dw5tgsw) (Dropbox, found under `GARIBALDI_Federico/09_TEMP_IMPORT/`)
