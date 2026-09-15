# GMV Crawler — Preplan complete (all 16 steps, spec v0.2 §33)

**Status: all 16 steps of the crawler's implementation order are
complete, adversarially reviewed, committed, and pushed.** This document
is now a completion record and a map of real, disclosed follow-up work —
not a "resume from step N" handoff, though it still serves that purpose
for anyone extending the crawler beyond this preplan. Read it fully
before touching any of this code: several assumptions in the original
spec turned out to be false on inspection (§0's corrections below), and
several real gaps were found only by executing code, not by reading it —
this document tells you which, and exactly how each was resolved,
disclosed, or deliberately left open pending a decision only a human can
make.

**Read "What exists now" below in full before extending any of this.**
In particular: any future virtual-table-based index (e.g. a vector
index via `sqlite-vec` or similar) will very likely hit the same
SEC-006/ARC-002 security boundary step 13 already resolved once — don't
re-litigate it from scratch. And before building on step 16's Notion
adapter, read its own section below: it closes the `claim_id`/`ATOM_ID`
identity question by explicit user decision (2026-09-15), but discloses
a real, live gap (the crawler's governed predicates and the real Notion
pipeline's routing hints are completely disjoint vocabularies) that
means every atom this adapter routes today falls through to free-text
body content, never structured fields/relations, until someone builds
that mapping.

**What "complete" means here, precisely:** every step in §33's order has
a real, tested, adversarially-reviewed artifact — not that the crawler
is production-ready end-to-end. No orchestration loop wires these 16
pieces together into a running pipeline (steps 1-16 are schema/contract/
thin-translation-layer work throughout, deliberately, per this session's
own "no premature engine" discipline); several steps are explicitly
scoped narrower than the spec's original ambition, with the gap disclosed
in that step's own docstring/tests, not silently absorbed. The
"Open questions" and each step's own "known gaps" below are the real
list of what a production run would still need.

## Repository state

- Repository: `GMVrgb76/gmv-core-notion-pipeline`
- Branch: `worktree-bridge-cse_01EFSz2nNresRvPh9GbfwwzK`, pushed to `origin`,
  in sync (`git status -sb` shows no divergence)
- Base: forked from `main` at `b480b04f`
- No PR opened yet — that decision was left to the user
- 29 commits ahead of base (`git log b480b04f..HEAD`), one per step's
  feature commit plus its own handoff-doc update and any review-driven
  fix, in order:
  1. `d6b9b685` — Epistemic Ingestion Rules config + crawler_source_registry migration (steps 1+3)
  2. `b1629b69` — GMV_ONTOLOGY_REGISTRY v0.1 (step 2)
  3. `0309b9af` — Source/Evidence contract (step 4)
  4. `fbbcb739` — Projection Adapter contract (step 5)
  5. `9a719578` — Entity Registry migration (step 6)
  6. `a4334505` — Atom validator (step 7)
  7. `d3280282` — this handoff document, first version
  8. `0dd6c767` — fix: unblock test collection (pre-existing Python-2-syntax SyntaxError, unrelated to the crawler)
  9. `8327d786` — Monad materializer v1.0 (step 8)
  10. `9fa5d999` — docs: handoff update for step 8 completion / step 9 re-verification
  11. `dc76fb02` — docs: resolve Ombra canonical directory decision (`03_STATE/ombra/`)
  12. `60543d0d` — feat: Extractors module (step 10)
  13. `5caef21d` — chore: reviewer lesson from step 10
  14. `909d3b38` — feat: real Dropbox SourceConnector against Dropbox API v2 (step 9)
  15. `93778b2b` — docs: handoff update for step 9 completion
  16. `f5f429ee` — fix: credential-assignment false-positive in DropboxConnector (security scanner, not a real secret leak)
  17. `fffa556f` — feat: Candidate extraction (step 11) — two adversarial-review rounds
  18. `60840d63` — docs: handoff update for step 11 completion
  19. `0c6d4a36` — feat: Reconciliation engine (step 12) — scoped to 3/6 outcomes
  20. `d6a43d90` — docs: handoff update for step 12 completion
  21. `2154f497` — feat: full-text index (step 13) — hit SEC-006/ARC-002 boundary, user decision required
  22. `90b3792a` — docs: handoff update for step 13 completion
  23. `a58d8933` — feat: Derived View Spec (step 14) — two adversarial-review rounds
  24. `f9638b01` — docs: handoff update for step 14 completion
  25. `985a493c` — docs: process-improvement retrospective (6 recurring bug shapes distilled from steps 9-14)
  26. `d187e824` — feat: PUBLIC projector (step 15) — one adversarial-review round found a real grounding bug
  27. `b8c1214f` — chore: reviewer lesson from step 15
  28. `00391613` — docs: handoff update for step 15 completion
  29. `e0452408` — feat: Notion ProjectionAdapter (step 16, **final step**) — two adversarial-review rounds, two real BLOCK bugs found and closed at contract level, see "What exists now" below
- Full test suite as of `e0452408`, run locally with `GMV_CORE_ROOT` set
  to this checkout: **1029 passed, 0 failed**. The two
  container-specific gap classes this document has tracked all session
  (`test_gmv_artist_import.py`'s `~/.gmv_core` dependency, soffice
  portability in `test_gmv_evidence_pipeline.py`) have flipped between
  passing and failing across different sessions/containers more than
  once already — **do not trust either state without re-running
  yourself**; see "Known environment-only failures" below before
  assuming a pass or fail on those specific tests means anything about
  this branch's own correctness. `ruff check .` clean.
  Re-run before continuing: `<repo-root>/.venv/bin/python -m pytest tests/ -q`
  and `... -m ruff check .` — see "Environment" below on which venv to use.

## Environment

- No committed venv exists in this repository (`.venv/` is gitignored,
  per `00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md`'s own "Local tooling"
  classification). The prior session's handoff pointed at
  `~/.gmv_core/.venv/bin/python` — a path specific to that session's own
  machine, not portable. This session created a fresh venv at the repo
  root (`python3 -m venv .venv && .venv/bin/pip install -r
  requirements-dev.txt`) and used that throughout. Do the same in a new
  session/container rather than assuming any specific path exists.
- No network/Notion/Dropbox credentials needed for the schema/contract
  work (steps 1-7), nor for step 8 (Monad materializer writes to a
  caller-supplied local path only), nor for step 10 (Extractors run on
  local bytes). Step 9 (`10_API/gmv_dropbox_connector.py`) is the first
  step that talks to a real external API and needs a credential:
  `DROPBOX_ACCESS_TOKEN` (a static access token, read via
  `credentials.get_token()`). The connector's own test suite never needs
  a real token (a fake `requests.Session` is injected), but any real
  invocation against actual Dropbox content — which no step 11+ work has
  done yet — will need this env var set.

### Known environment-only failures (do not "fix" without checking your own container first)

As of `909d3b38` these failures are **not currently reproducing** (see
"Repository state" above) — likely because PR #18 was merged. Keeping
this section because the underlying causes are container-specific, not
proven fixed for every container, and could reappear in a fresh sandbox:
up to 10 of the ~903 collected tests can fail in a sandboxed container
for reasons confirmed to be container setup, not code:
- 8 in `tests/test_gmv_artist_import.py`: the tool under test shells out to
  an installed copy at `~/.gmv_core/10_API/gmv_folder_report.py`, which
  does not exist in this container (no such path, no install script in the
  repo populates it).
- 2 in `tests/test_gmv_evidence_pipeline.py` (DOC extraction via
  LibreOffice): `soffice` is present but non-functional in this sandbox —
  confirmed independently of pytest: `soffice --headless --convert-to txt
  test.txt` fails with "source file could not be loaded" even on a plain
  text file, outside any test. A container config gap (missing fonts,
  no D-Bus, sandboxing), not a code defect.
Before assuming either of these is fixed or newly broken in a future
session, check whether `~/.gmv_core` exists and whether `soffice
--headless --convert-to txt:Text <any .txt file>` actually works in your
own container — do not just compare pass counts.

## Unrelated bug fixed this session (not crawler work, but blocked everything)

`10_API/gmv_artist_normalize_plan.py:369` had `except MigrationError,
TypeError:` — Python 2 syntax, a `SyntaxError` under Python 3. This
predates this branch's fork point (`main` at `b480b04f` already has it),
so **`main` itself currently has broken pytest collection**: one
`SyntaxError` anywhere aborts the entire collection run
(`Interrupted: 1 error during collection`, zero tests executed), despite
the recent `fix/ci-quality-gate-broken-since-sept3` PR. Fixed by
parenthesizing the tuple (`except (MigrationError, TypeError):`), matching
the identical pattern already used at line 708 of the same file — no
behavior change, `normalized_relative()` only ever raises
`MigrationError` in practice. Not something this branch caused; worth
raising on `main` directly, independent of the crawler work.

## What the GMV Crawler is (one paragraph)

A compiler subsystem of GMV Core (not a separate app, not the orchestrator)
that turns raw Dropbox evidence into canonical GMV Monads:
`DISCOVER → REGISTER → DETECT CHANGE → EXTRACT → SEGMENT → BUILD EVIDENCE →
EXTRACT CANDIDATES → RESOLVE ENTITIES → NORMALIZE PREDICATES → VALIDATE
EPISTEMICALLY → BUILD ATOMS → RECONCILE → MATERIALIZE MONADS → REBUILD
DERIVED INDEXES → AUDIT`. Non-negotiable invariant: no ATOM without SOURCE,
no SOURCE without a canonical locator, no proposition stronger than its
evidence. It runs *inside* the existing GMV Run Ledger as a sequence of
stages, not as a second execution engine, and is itself orchestrated by
something else (Hermes/OpenClaw/Codex/Claude Code) — it is not the
orchestrator.

## Source documents (fetch these yourself before continuing — do not trust summaries alone)

All on the user's Notion workspace. Fetch via the Notion MCP connection if
available; otherwise ask the user.

- **"GMV Crawler — Specifica di Implementazione v0.2"** (Notion page id
  `3d95a429-a028-8111-bb14-e5811a4d3f9c`) — the primary spec. §33 has the
  16-step implementation order this handoff follows. §0 has 7 "corrections"
  against v0.1's false assumptions — read these; some are themselves now
  further corrected by this session (see below).
- **"GMV Crawler — Documento Base Pre-Plan"** (id `3d65a429-a028-8119-8c40-d15f8e71a722`)
  — the informal v0.1 concept doc the above corrects. Still useful for the
  original MVP scope and entity/predicate wishlist (§6.5/§6.7), but several
  of its assumptions (e.g. entity extraction list) are unvalidated wishlist,
  not fact — treat accordingly.
- **"🛡️ Epistemic Ingestion Constitution v0.1"** (id `3b95a429-a028-8145-8c06-fcaf938c5eb3`)
  — the 15 mandatory rules, transcribed into
  `00_CONFIG/EPISTEMIC_INGESTION_RULES_v0.2.json` (step 1). Its own
  "Prossima azione" field says v0.2 must add 4 integrations from real-corpus
  failures — also transcribed (rules EIC-16 through EIC-19).
- **"GMV_KNOWLEDGE_MONAD_SPEC_v1.0"** (id `3b95a429-a028-8116-a236-d8867862d077`)
  — FROZEN canonical spec for the Monad/ATOM format. The 18-field ATOM
  schema, the 6 frozen PREDICATE_CLASS values, WORK≠ARTWORK_INSTANCE,
  tombstoning rule, all come from here. Any future work touching Monad
  materialization (step 8) must ground itself in this document, not guess.
- **"GMV Monad Research & Execution Protocol v1.0"** (id `3b95a429-a028-81ee-b138-f9891d5429fa`)
  — historical but load-bearing: §7 "Controlled vocabulary v0.1" is the
  source for `00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json`'s initial
  entity/predicate seed (step 2).
- **"GMV Knowledge Monad — Real Corpus Validation 001 — Federico Garibaldi"**
  (id `3b95a429-a028-8189-bf3f-fb433ade1a38`) — the real-corpus test that
  produced the WORK/ARTWORK_INSTANCE split and the tombstoning/object-time
  findings folded into step 1's rules.

## Corrections this session made to the spec's own §0 corrections

The spec's §0 already corrected 7 false assumptions in the original v0.1
draft by reading the real repo. This session found that **one of those
7 corrections was itself wrong**, plus several new facts the spec never
checked:

1. **Correction 2 of the spec ("gmv-dropbox-import v3 is an already-validated
   Dropbox connector to wrap") is FALSE.** Verified: `gmv-dropbox-import` is
   not code anywhere in this repo or its git history. It is a **Claude
   Skill** (`~/Library/CloudStorage/Dropbox/GMV_SKILLS/gmv-dropbox-import/SKILL.md`)
   — an LLM-guided manual Dropbox folder-reorganization workflow (AUDIT/
   ESECUZIONE/NORMALIZZAZIONE modes, via MCP tool calls), not a deterministic
   `list/metadata/download/revision/content_hash` API. There is no triage
   "tre liste" logic anywhere. **Step 9 ("Dropbox connector = wrapper of
   gmv-dropbox-import v3") as originally planned is not achievable as
   stated** — a real `SourceConnector` implementation (the contract is
   already built, step 4) must be written from scratch against the Dropbox
   API directly, or the Skill's manual workflow needs to be reconceived as
   something a connector could call. This needs a decision before step 9,
   not silent reinterpretation.
2. `gmv_run_ledger.py` is generic (no hardcoded stage names) — the specific
   `10_EXTRACT/20_ADAPT/...` sequence belongs to `gmv_pipeline.py` (Area35
   QA), not the ledger itself. The crawler defines its own stage names
   reusing the same generic mechanism — not yet done (would happen when an
   actual crawler engine/orchestration loop is written, likely alongside or
   after step 8).
3. `area35_validator.py` has 7 rule functions (`REGOLE`), not the 8
   "families" the spec claimed; its `Record` dataclass is shaped for
   already-exported Notion pages and is structurally incompatible with the
   ATOM schema — this is why step 7 became a new module instead of a literal
   edit to `r_monade()`. See step 7 detail below.
4. `gmv_notion_multi_candidate.py::write_entity_bundle()` already writes
   `NOTION_PATCH.json`/`NOTION_PAYLOAD.json` in the format
   `gmv_notion_publish.py::load_bundle()` expects — the format divergence a
   prior memory/session flagged as open is resolved in the real code.
5. Three separate content-hash identity mechanisms coexist in this repo:
   `FILE_INDEX.jsonl` (file-based, `gmv_evidence_pipeline.py`),
   `gmv_core/repositories/resources.py` (Core, OID `RES-*`), and now
   `crawler_source_registry` (step 3, migration 009). Decision made: the
   new registry does not invent a fourth meaning — it anchors to `resources`
   via FK (`resource_oid` nullable, populated at REGISTER stage), and does
   not attempt to unify the other two pre-existing mechanisms (out of
   scope).
6. `gmv_core/identity.py`'s OID system is a closed 6-value enum
   (Core/Person/Plugin/Resource/Service/System — infrastructure bookkeeping,
   not domain knowledge). The Entity Registry (step 6) deliberately does
   NOT integrate with it — `gmv_id` has its own separate `"GMV-*"` scheme.
7. `INSTITUTION` vs `ORGANIZATION`: the real, operational Notion pipeline
   (`notion_page_templates.json`, `gmv_notion_multi_candidate.py`) treats
   `istituzione` as the actually-implemented entity type, with its own page
   template and normalization mapping. `ORGANIZATION` has never been
   instantiated anywhere. The ontology registry (step 2) registers
   `INSTITUTION` as its own DOMAIN class, not folded into `ORGANIZATION`
   — an earlier draft of that file got this backwards and was caught by
   review before commit.

## What exists now (all 16 steps), file by file

All under `00_CONFIG/`, `gmv_core/`, `10_API/`, `tests/` of the repo root.

| Step | Artifact | What it is |
|---|---|---|
| 1 | `00_CONFIG/EPISTEMIC_INGESTION_RULES_v0.2.json` | 19 rules (15 from Constitution v0.1 + 4 real-corpus integrations), each with severity (BLOCKING/DEFECT), family, source_reference |
| 1 | `tests/characterization/test_epistemic_ingestion_rules.py` | Shape/classification guards for the above |
| 2 | `00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json` | Entity classes (CORE/DOMAIN/CANDIDATE/DEPRECATED) + predicates (with domain/range/aliases), reuse-before-invention governance |
| 2 | `tests/characterization/test_ontology_registry.py` | Shape guards + cross-check against `notion_page_templates.json`'s real entity keys |
| 3 | `gmv_core/migration_sql/009_crawler_source_registry.sql` | `crawler_source_registry` table: change-detection state (NEW/UNCHANGED/MODIFIED/MOVED/DELETED/FAILED), content_hash PK, nullable `resource_oid` FK to Core's `resources` |
| 3 | `gmv_core/migrations.py` | Wires migration 9 (and later 10) as reachable-only-via-explicit-`target_version`, never `CURRENT_SCHEMA_VERSION` |
| 3 | `tests/migrations/test_crawler_source_registry.py` | Full migration test suite incl. fault-injection rollback |
| 4 | `10_API/gmv_crawler_contracts.py` | `SourceConnector` (Protocol: list/metadata/download/revision/content_hash), `EvidenceUnit` (frozen dataclass, crawler spec §8's 13 fields) |
| 4 | `tests/test_gmv_crawler_contracts.py` | Contract tests, incl. one that executes the real SQL CHECK from migration 009 and compares to the Python validator input-by-input |
| 5 | `10_API/gmv_projection_adapter_contracts.py` | `ProjectionAdapter` (Protocol: supports/project/publish/reconcile_correction), `TargetPayload`, `PublishResult`, `ProposedPatch` |
| 5 | `tests/test_gmv_projection_adapter_contracts.py` | Tests that execute real `gmv_notion_multi_candidate.py`/`gmv_notion_candidate.py` functions to ground vocabulary claims, not self-referential comparisons |
| 6 | `gmv_core/migration_sql/010_entity_registry.sql` | `entities` + `entity_aliases` tables, `gmv_id` (own scheme, not Core OID), status ACTIVE/MERGE_CANDIDATE/MERGED, anti-cycle merge trigger |
| 6 | `tests/migrations/test_entity_registry.py` | Full migration test suite incl. cross-check against the ontology registry's CORE/DOMAIN class_ids |
| 7 | `10_API/gmv_atom_validator.py` | `AtomCandidate` (frozen 18-field dataclass), `validate_atom()` (mechanically-checkable subset of the 19 EIC rules — `UNENFORCED_RULE_IDS` lists what is NOT covered and why), `compute_atom_fingerprint()` (reuses `area35_validator._forma()`/`Issue`/`SEV` by import) |
| 7 | `tests/test_gmv_atom_validator.py` | Full rule coverage, incl. a test proving a known accepted trade-off (fingerprint collisions on reordered non-person text) rather than hiding it |
| 8 | `10_API/gmv_monad_materializer.py` | `MonadDocument`/`SourceManifestEntry` (frozen dataclasses), `render_monad_markdown()` (pure function -> canonical `.md` text, §19 skeleton), `materialize_monad()` (validates via `find_materialization_blockers()` — BLOCKER-only gate reusing `validate_atom()` — then writes atomically via `secure_storage.atomic_write_text`). No canonical Monad directory decided; caller supplies `target_path`. PUBLIC text is caller-supplied verbatim, not computed here (that is step 15) |
| 8 | `tests/test_gmv_monad_materializer.py` | Cross-checks gmv_id/entity_type gates against real migration 010 SQL (not a second hardcoded list), rendering/escaping tests, materialize_monad atomicity/idempotency/permission tests |
| 9 | `10_API/gmv_dropbox_connector.py` | `DropboxConnector` — real HTTP client (via `requests`) against Dropbox API v2, satisfying `SourceConnector` structurally. Auth: static token via `DROPBOX_ACCESS_TOKEN` (reuses `credentials.get_token()`, not a new mechanism). `content_hash()`/`metadata()` download and compute a real single-pass SHA-256 rather than reusing Dropbox's own differently-algorithmed `content_hash` field (deliberate correctness choice — see module docstring). Network failures normalized to `DropboxConnectorError`. Known v1 gaps, documented not fixed: no streaming for large files (full response body held in memory), no 429/rate-limit backoff |
| 9 | `tests/test_gmv_dropbox_connector.py` | 21 tests against an injected fake `requests.Session` (no real network calls, no HTTP-mocking dependency added) — pagination, non-file/deleted filtering, Authorization header actually sent, content_hash independence from Dropbox's own field, network-exception wrapping |
| 10 | `10_API/gmv_crawler_extractor.py` | `ExtractionDocument` + `extract_document()`, a thin wrapper around `gmv_evidence_pipeline.py`'s existing `_extract()` (PDF/DOCX/DOC/TXT/MD/HTML/CSV/JSON incl. PaddleOCR fallback) — reused, not reimplemented. Adds a source_hash staleness gate before extraction |
| 10 | `tests/test_gmv_crawler_extractor.py` | 21 tests incl. a cross-check against `_extract()`'s real source for every `EvidenceError` code it can raise |
| 11 | `10_API/gmv_crawler_candidate_extractor.py` | `CandidateEntity`/`CandidateProposition` (frozen dataclasses) + `extract_candidates()`, a thin wrapper around `gmv_evidence_pipeline.py`'s existing `ollama_extract()` — reused, not reimplemented. Only two candidate shapes exist, not the spec's five (Relation/Event/Measure sub-typing needs an unbuilt NORMALIZE PREDICATES stage — documented gap, not silently invented). `status` is free text, not validated against any closed vocabulary (see below). `evidence_ids` is caller-supplied (no BUILD EVIDENCE engine exists yet). Returns `(entities, propositions, rejected)` — a malformed candidate is excluded individually with its reason recorded in `rejected`, never crashes the whole batch |
| 11 | `tests/test_gmv_crawler_candidate_extractor.py` | 21 tests, `ollama_extract` monkeypatched (no real network/Ollama calls). Two are explicit regression tests for the two review rounds below |

**Two adversarial-review rounds on step 11, both real, non-cosmetic bugs:**
round 1 returned **BLOCK** — an early draft validated `status` against
`gmv_evidence_pipeline.STATUS_PRECEDENCE` as a closed vocabulary, raising
`ValueError` on anything else; that list's own source comment says it
exists for tolerant ranking (`_better_status()`), never as a rejection
gate, and a realistic LLM status value (`"DOCUMENTATO"`, reproduced
empirically) crashed extraction for an entire document via a `tuple(...
for ...)` comprehension — destroying every other valid candidate in the
same batch. Fixed by dropping the closed-vocabulary check (status is now
only checked non-empty). Round 2 (re-verification) confirmed the fix but
found a narrower residual trigger of the *same* all-or-nothing pattern:
an explicitly empty-string status is legal under `SEMANTIC_OUTPUT_SCHEMA`
(no `minLength`, not `required`) and still crashed the whole batch —
rated a non-blocking WARNING with a recommended fix, applied proactively:
`extract_candidates()` now isolates each candidate's construction
(`try`/`except` per item) and returns a third `rejected` tuple of
reasons instead of letting one malformed item propagate. **If a future
step adds more validation to these dataclasses, keep this per-item
isolation — do not go back to a comprehension that raises on first
failure.**

| 12 | `10_API/gmv_crawler_reconciliation.py` | `ReconciliationOutcome` (Literal, all 6 crawler-spec values named) + `ReconciliationResult` + `reconcile()`. Classifies a new `AtomCandidate` (step 7) against caller-supplied `existing_atoms` using the real `compute_atom_fingerprint()` (step 7, reused). **Only NEW/IDENTICAL/SUPPORTING are reachable — CONFLICTING/SUPERSEDING/CORRECTING are named but never produced.** IDENTICAL = same fingerprint + same SOURCE (redundant); SUPPORTING = same fingerprint + different SOURCE (independent corroboration, both atoms stay valid); NEW = no fingerprint match. Never applies the frozen tombstoning rule (STATUS=INVALIDATED/END_REASON=CORRECTED/SUPERSEDES) — no outcome this version produces requires it |
| 12 | `tests/test_gmv_crawler_reconciliation.py` | 16 tests, incl. a cross-check against the real `ReconciliationOutcome.__args__` (not a duplicated hardcoded set — an earlier draft made exactly that tautology mistake, caught by review) and pinned-behavior tests for two edge cases below |

**Why step 12 stops at 3 of 6 outcomes.** CONFLICTING/SUPERSEDING/CORRECTING
all need a "slot" identity key (SUBJECT+PREDICATE, ignoring OBJECT) to
even detect a candidate pair worth comparing — fingerprint-based matching
(SUBJECT+PREDICATE+OBJECT together) can never surface them, since a
genuine contradiction or update has a *different* OBJECT by definition,
hence a different fingerprint. No such slot key, and no governed policy
for when a same-slot/different-object pair is a legitimate temporal
update vs. a human correction vs. an unresolved contradiction (which
would itself depend on PREDICATE_CLASS — some RELATION-class predicates
may legitimately hold multiple simultaneous values, others may not),
exists anywhere in this repo. Verified by reading `area35_validator.py::r_duplicati()`
(only flags duplicates, D01/D02, never reconciles) and
`gmv_evidence_pipeline.py::consolidate_claims()` (groups by the full
subject/predicate/object triple, never subject+predicate alone) — this
step is genuinely new design, not a wrapper of existing logic, unlike
steps 9-11.

**Two things this step's own review found worth knowing before extending it:**
1. `SUPPORTING` inherits step 7's known `compute_atom_fingerprint()`
   collision risk for non-person OBJECT text (`_forma()` is word-order-
   invariant, not OBJECT_TYPE-aware — "Venice Biennale" and "Biennale
   Venice" fingerprint identically). `GMV_CRAWLER_HANDOFF.md` had already
   named this step as "likely where the atom_fingerprint trade-off needs
   to be resolved for real" — **it is not resolved here**, only
   explicitly documented as inherited (module docstring). A real fix
   needs OBJECT_TYPE-aware normalization in `compute_atom_fingerprint()`
   itself (step 7), not something this module can fix locally.
2. If `existing_atoms` (caller-supplied — no `atoms_runtime` store exists
   yet) contains two atoms that already share both the candidate's
   fingerprint and its SOURCE, `reconcile()`'s IDENTICAL result can only
   report one of them (`ReconciliationResult`'s own invariant: IDENTICAL
   carries exactly one matched atom) — the other is silently not
   reported. Pinned by `test_multiple_existing_atoms_same_source_as_candidate_keeps_only_one_witness`,
   not fixed; a caller relying on `matched_atoms` to enumerate *every*
   redundant atom should not assume completeness for IDENTICAL.

| 13 | `10_API/gmv_crawler_fulltext_index.py` | `open_index()`/`index_atom()`/`search_atoms()` — a standalone FTS5 virtual table (`atoms_fts`, tokenizer `unicode61 remove_diacritics 2`) indexing ATOM SUBJECT/PREDICATE/OBJECT, reusing `AtomCandidate` (step 7) directly. **Does NOT use `gmv_core.database`/`gmv_core.migrations` at all** — see the boundary-collision account below before touching this file or building any future virtual-table-based index |
| 13 | `tests/test_gmv_crawler_fulltext_index.py` | 11 tests against real sqlite3/FTS5 (not mocked) incl. a diacritics-removal grounding test ("città"/"citta") and pinned-behavior tests for both documented v1 gaps (no dedup, unsanitized `MATCH` query) |

**Read this before building any future virtual-table-based index (e.g. a
vector index) — it will very likely hit the identical wall. This is not
step 14** (§33 numbers step 14 as DERIVED_VIEW_SPEC v0.1 — a rules/config
artifact, most likely, not an engine, and unlikely to touch SQLite at
all; a vector index has no numbered step in §33 at all, since §31
explicitly excludes "infrastruttura vettoriale completa" from this
crawler's first cycle). `gmv_core/authorization.py`'s SEC-006
write-capability authorizer denies `SQLITE_CREATE_VTABLE` *unconditionally*,
for every caller, by explicit design — confirmed by actually running a
migration against it, not just reading the code. An FTS5 (or, later, any
`sqlite-vec`/virtual-table-based vector index) table cannot be created
through `gmv_core.database.connect_path()`/`gmv_core.migrations.migrate()`
at all, ever, regardless of the caller. `10_API/gmv_crawler_fulltext_index.py`
therefore manages its own plain, unguarded `sqlite3.connect()` to a
separate file — **but this collides with a second, real, actively-enforced
repo boundary**: `tests/test_sqlite_connection_boundary.py`'s
`test_only_core_factory_calls_sqlite_connect()` statically asserts
*exactly one* raw `sqlite3.connect()` owner exists in tracked production
code repo-wide (`gmv_core/database.py`). An earlier draft of this
module's docstring cited that boundary's governing ADR
(`00_CONFIG/ADR_CORE_PERSISTENCE_BOUNDARY.md`) incompletely — it quoted
only the original Decision §3 ("the check is deferred") and missed that
same file's own 2026-07-21 addendum, which closes that clause and
confirms the check has been continuously active and enforced since
2026-07-19. Adversarial review reproduced the break **empirically**
(staged the new file, re-ran the suite, watched it fail) — this was not
caught by reading the ADR, only by reading it to the end and then
verifying against the real test.

**A second, distinct static check needed the identical fix and was
almost missed on the first review pass:** `tests/test_write_authorization.py::test_dml_capability_matrix_matches_source()`
independently inventories every `INSERT`/`UPDATE`/`DELETE` call site in
tracked production code, regardless of which connection type executes
it — so `index_atom()`'s `INSERT INTO atoms_fts` needed its own fix
there too, not just in the connection-boundary test.

**Resolution, by explicit user decision (2026-09-15), among three
options adversarial review presented (a full ADR amendment; relocating
the module outside the three guarded production roots
`01_RUNTIME/`/`10_API/`/`gmv_core/`; a named, justified whitelist
entry):** the user chose the whitelist. Both static checks now carry a
second, explicitly named and justified exception
(`FTS_INDEX_OWNER`/`_NON_CORE_DML_SITES`) for this one file only — both
remain strict equality checks, so a third undocumented file doing the
same thing would still fail loudly. Confirmed (by the reviewer,
independently): this whitelist entry was **not** mirrored into
`gmv_core.authorization.DML_CAPABILITIES` (the live SEC-006 runtime
matrix) — that would have been the mirror-image mistake, granting a real
runtime write capability to a module that never uses an
`AuthorizingConnection` at all.

**For any future virtual-table-based index (vector or otherwise): do not
re-litigate this from scratch.** The same three options apply; if the user again prefers a named
whitelist, the pattern to copy is exactly `FTS_INDEX_OWNER` +
`_NON_CORE_DML_SITES` above. If a *fourth* similar step needs the same
treatment, that itself might be the signal that option (a) — a real ADR
amendment excluding derived/rebuildable indexes from `ARC-002`'s scope
generally — is overdue rather than repeating a per-file whitelist
indefinitely; that judgment call was not made this session and is worth
raising with the user directly rather than assumed.

| 14 | `10_API/gmv_crawler_derived_views.py` | `derive_timeline()` (sort by VALID_FROM), `derive_ledger()` (sort by INGESTED_AT — deliberately distinct ordering from TIMELINE), `derive_relations()` (filter PREDICATE_CLASS==RELATION), `derive_claims()` (identity — no distinguishing criterion exists in the spec), `derive_current_state()` (per-slot VALID-atom resolution, never a silent pick on ambiguity), `CurrentStateEntry`, `DerivedViews`, `derive_views()`. **PUBLIC excluded** — already step 15's job per `gmv_monad_materializer.py`'s own docstring |
| 14 | `tests/test_gmv_crawler_derived_views.py` | 21 tests, incl. regression tests for both review-found bugs below and a real-alias cross-check (`source_for`/`evidences`, `GMV_ONTOLOGY_REGISTRY_v0.1.json`) |

**Two adversarial-review rounds on step 14, both real bugs in `derive_current_state()`, reproduced empirically:** round 1 returned **BLOCK** for two bugs in the function's core "never a silent pick" guarantee — (1) the slot key used the raw `predicate` string, so two atoms using different real, registered aliases of the same predicate (`source_for`/`evidences`) were reported as two separate `RESOLVED` facts instead of one `AMBIGUOUS`; (2) no dedup by `atom_id` before grouping, so the same atom appearing twice in the input produced a false `AMBIGUOUS` against itself. Fixed: predicate is now resolved to its ontology-registry canonical id (reusing `gmv_atom_validator._known_predicates()`) before use as the grouping key, and atoms are deduplicated by `atom_id` first. Also fixed in the same round: `derive_relations()`'s `"RELATION"` literal was claimed "imported" in the docstring but `FROZEN_PREDICATE_CLASSES` was never actually imported into the module (only the test file) — now genuinely imported with a fail-at-import-time guard. Round 2 (re-verification) confirmed both fixes with independently-constructed reproductions and returned **PASS_WITH_WARNINGS** — two minor, non-blocking notes: the module's "no I/O" claim needed correcting (`derive_current_state()` now reads `GMV_ONTOLOGY_REGISTRY_v0.1.json` by default unless a caller injects an already-loaded `registry`, fixed in the docstring), and the new `atom_id`-based dedup assumes `atom_id` uniqueness (an upstream-bug edge case, not addressed, not worse than assumptions already implicit elsewhere in this repo).

**Two risks inherited, not fixed, disclosed in the module's own docstring:**
`STATUS=DISPUTED` atoms produce no `CURRENT_STATE` entry at all (indistinguishable from "never asserted" in this view alone); `_forma()` on SUBJECT inherits the same word-order-collision risk already accepted for OBJECT in `compute_atom_fingerprint()` (step 7) — structurally harder to bound here since the frozen 18-field ATOM schema has an `OBJECT_TYPE` field but no `SUBJECT_TYPE` field.

| 15 | `10_API/gmv_crawler_public_projector.py` | Computes what `gmv_monad_materializer.MonadDocument.public_text` (step 8) should contain — step 8 writes `public_text` verbatim, never computes it. `select_public_atoms()` reuses `derive_current_state()` (step 14) for STATUS=VALID filtering/dedup/alias-aware slot resolution, adding VISIBILITY=="PUBLIC" and a not-blocked-source gate. `render_public_text()` renders one deterministic line per eligible atom (subject/predicate/object, sorted by `atom_id`) — literal fact enumeration, not NLG. `project_public()` composes both |
| 15 | `tests/test_gmv_crawler_public_projector.py` | 25 tests, incl. regression tests for the round-1 review-found bug below, the disclosed RELATION multi-value AMBIGUOUS trade-off pinned end-to-end, and cross-checks against real committed vocabularies (`gmv_crawler_extractor.STATUS_VALUES`, every sibling test file's `visibility` fixture default) |

**§14's six PUBLIC exclusion rules, mapped explicitly (see module docstring for the full account):** "fatti INTERNAL" and "claim UNVERIFIED non attribuite" are both closed by requiring STATUS=VALID (reused from `derive_current_state()`) + VISIBILITY=="PUBLIC" (this module's own decision — **no governed VISIBILITY vocabulary exists anywhere in this repo**, confirmed by grep; `"PUBLIC"` is the one value every other crawler-step test fixture already defaults to, not a transcription of a real enum). "Historical states presented as current" is closed two ways: STATUS=VALID already excludes SUPERSEDED/INVALIDATED, and — **this module's own deliberate decision, since step 14 left this explicitly undefined** — `derive_current_state()`'s `AMBIGUOUS` slots are excluded from PUBLIC entirely, never one competing atom silently chosen. This inherits step 14's own disclosed limitation: a RELATION predicate able to legitimately hold several simultaneous true values (e.g. `participated_in` several exhibitions) collides into one SUBJECT+PREDICATE slot and is suppressed even though nothing is actually contested — a known, accepted v1 under-publication trade-off, pinned by its own test (`test_select_under_publishes_legitimately_multi_valued_relation_as_disclosed`), not a silent gap; no governed per-predicate "may hold multiple simultaneous values" policy exists anywhere in this repo to fix it with. "Inferenze da fonti bloccate" is closed by excluding any atom whose SOURCE resolves to a SOURCES-manifest row with `extraction_status` other than `"SUCCESS"` — see the review account below for how this gate's grounding was first wrong, then fixed. **Two of the six rules are honestly NOT enforced**, disclosed in the module docstring rather than silently dropped: "bozze contrattuali e dati economici privati" (no classification/sensitivity field exists anywhere in the frozen ATOM schema or the SOURCES manifest — the crawler spec's own "Punti di attenzione aperti" #2 already names this as open and undecided, not something to guess a heuristic for) and "scheduled events presented as occurred" (identical class of gap to EIC-05/EIC-06, already declined at atom-validation time in step 7 for the same reason — a finished VALID atom looks structurally identical whether an occurrence promotion was correct or not).

**One adversarial-review round on step 15, a real grounding bug, fixed and re-verified:** round 1 returned **BLOCK** — an early draft's blocked-source gate used a standalone literal, `BLOCKED_EXTRACTION_STATUS = "BLOCKED"`, whose docstring claimed it "matches the real, live literal `gmv_evidence_pipeline.py:538` already writes." That claim was checked and found false: line 538 writes the whole-run manifest `status` field for the *SEMANTIC* (LLM entity/claim extraction) stage — an unrelated field on an unrelated pipeline stage, not any per-source `extraction_status`. The real, closed, already-committed per-source vocabulary this crawler subsystem actually produces (`gmv_crawler_extractor.STATUS_VALUES`, step 10: `SUCCESS`/`OCR_REQUIRED`/`UNSUPPORTED_FORMAT`/`EXTRACTION_FAILED`/`EXTRACTION_ABORTED_STALE_HASH`) contains no `"BLOCKED"` value at all — the gate was dead code against any real data this pipeline can produce, and its own grounding test only substring-matched the wrong file/field, so it passed while proving nothing (the same "grounding test that reads the right file but the wrong field" failure mode already flagged once before this session, per the reviewer's own memory). Fixed: `BLOCKED_EXTRACTION_STATUSES` is now `frozenset(STATUS_VALUES - {"SUCCESS"})`, imported and computed from the real vocabulary (so it cannot silently drift if a future status value is added upstream), not a second hardcoded literal; the docstring was rewritten to document the correction explicitly and to distinguish this content-extraction-stage concept from `crawler_source_registry.state` (migration 009, step 3) — that table's own real closed vocabulary is `NEW`/`UNCHANGED`/`MODIFIED`/`MOVED`/`DELETED`/`FAILED`, no `BLOCKED` either; crawler spec §24's prose use of the word "BLOCKED" for an unreadable source refers to that different, DETECT-CHANGE-stage concept (real literal `FAILED`), and must not be conflated with this gate. Tests against real pipeline-producible statuses (`EXTRACTION_FAILED`, `UNSUPPORTED_FORMAT`, `SUCCESS`) were added, along with the RELATION multi-value trade-off and CRLF-collapse cases round 1 flagged as missing coverage. Round 2 (re-verification, same reviewer): **PASS** — confirmed the fix fires correctly against real data (and, independently, that `gmv_crawler_candidate_extractor.py:231` already writes a real `extraction_status` field from this exact vocabulary, corroborating it as the right one to key off), confirmed no circular import (`gmv_crawler_extractor` imports only `gmv_crawler_contracts`/`gmv_evidence_pipeline`, neither imports back), no other issues found. **No production code constructs a real `SourceManifestEntry` yet** (confirmed by repo-wide grep, both review rounds) — this gate has no live caller today; it is grounded and ready for whichever future step wires a real SOURCES manifest through, not exercised end-to-end in this crawler yet.

| 16 | `10_API/gmv_notion_projection_adapter.py` | `MultiCandidateNotionAdapter` — the first concrete `ProjectionAdapter` (step 5), wrapping `route_claim()`/`build_entity_patch()`/`build_entity_body()`/`gate()`/`compare_entity()`/`load_bundle()`/`publish_bundle()` exactly as they already exist. `supports()`/`project()`/`publish()`/`reconcile_correction()`. `CRAWLER_ENTITY_TYPE_TO_LEGACY` closes the entity_type case/language gap step 5 flagged as unresolved. `claim_id = atom.atom_id` closes the claim_id/ATOM_ID identity question (user decision). `project()` filters to `STATUS=VALID` atoms only (same policy step 15 already established) and does NOT replicate `discover_entities()`'s multi-entity fan-out — see its own docstring for why that's the Entity Registry's (step 6) job going forward, not this adapter's |
| 16 | `10_API/gmv_projection_adapter_contracts.py` | **Modified**, not just step 16's own file: `TargetPayload` gained three fields step 5's original draft was missing, all found empirically while wiring `publish()` for real — `name` (required), `existing_target_reference`, `keep_properties` (the last one closing a real BLOCK: without it, `notion_publish.py::check_staleness()` silently never detects a page edited on Notion since the payload was built) |
| 16 | `tests/test_gmv_notion_projection_adapter.py` | 32 tests, incl. cross-checks of `CRAWLER_ENTITY_TYPE_TO_LEGACY` against the real ontology registry and page templates, a regression test proving the predicate-vocabulary mismatch is real, and — added after round-1 review — tests executing the real `check_staleness()`/`plan_requests()` (`notion_publish.py`) against bundles this module wrote, not just asserting `load_bundle()` doesn't crash |

**Two adversarial-review rounds on step 16 (the final step), both real BLOCK bugs, both closed at the contract level, not patched locally in the adapter:** round 1 returned **BLOCK** for two bugs, both reproduced by executing the real `notion_publish.py` functions against bundles the adapter had written, not by reading the code: (1) `build_entity_patch()`'s `"keep"` block — computed specifically to feed `check_staleness()`, per a prior session's own fix to the sibling module (`gmv_notion_candidate.py`, referenced in `project_gmv_multi_candidate_integration.md`) — had no home on `TargetPayload` and was silently dropped, making `check_staleness()` a permanent no-op (`stale` always `False`, even against a live Notion page with completely different values) for every bundle this adapter could ever produce; (2) `body_gate` was never written to `NOTION_PATCH.json`, so `plan_requests()`/`apply_patch()` never append body text regardless of gate value — the safe direction (never over-publishes), but a real, undisclosed dead path. Round 1 also found: no filter excluded `INVALIDATED`/`DISPUTED`/`SUPERSEDED` atoms from being proposed as Notion content (fixed with the same `STATUS=VALID`-only policy step 15 already established); and the module's own justification for `claim_id = atom.atom_id` was factually wrong — it claimed step 12's `reconcile()` would already have deduplicated equivalent atoms by the time one reaches this adapter, but `reconcile()`'s own docstring is explicit that its `SUPPORTING` outcome keeps *both* atoms distinct (never merges to one `atom_id`), and `reconcile()` is not called by any production code path in this repository today (grepped) — the docstring was corrected to the real, simpler justification ("the only stable identity this adapter has, full stop," not "reconciliation already handled it"). Fixed: `TargetPayload` gained `keep_properties`; `_write_bundle()` now writes both `keep` and a properly-translated `body_gate`; `project()` filters to `STATUS=VALID`; the docstring no longer overclaims what `reconcile()` guarantees. Round 2 (re-verification, same reviewer, deliberately using different fixtures than the fix's own tests — a different Notion property type, `DISPUTED`/`SUPERSEDED` statuses in addition to `INVALIDATED`): **PASS_WITH_WARNINGS**, confirmed both blockers closed by executing `check_staleness()`/`plan_requests()` directly against freshly-written bundles, not by trusting the new tests. Two non-blocking style notes left as-is: one test's predicate literal isn't among the ontology registry's real 13 (validates the mechanism, not a reachable real-data scenario — should be labeled as such, not a code defect); `_write_bundle()`'s bundle-folder naming convention (crawler entity_type) differs stylistically from `write_entity_bundle()`'s (legacy Italian entity_type) without affecting `load_bundle()`.

**Known, disclosed, not-fixed-here limitations for whoever builds on step 16:**
- **The predicate-vocabulary mismatch is real and unresolved, pinned by its own test** (`test_predicate_vocabulary_mismatch_is_real_not_just_documented`, checked against both real files): the crawler's governed predicates (`participated_in`, `source_for`, `exhibited_at`, ...) and the real Notion pipeline's routing hints (`"is the author of"`, `"uses technique"`) are completely disjoint vocabularies. Every atom this adapter routes today falls through to `route_claim()`'s free-text body layer — the relation/field structured-routing this adapter exists to provide is, in practice, unreachable until a future step builds an explicit predicate → hint-phrase mapping (real domain judgment, not something this session had grounds to invent).
- **No multi-entity fan-out.** `project()` takes one `MonadDocument` and returns one `TargetPayload` for that entity only — it does not replicate `discover_entities()`'s capability to propose *other* entities merely mentioned in the claims. That capability is superseded, going forward, by the crawler's own Entity Registry (step 6) resolving those other entities into their own Monads; a future engine step calling `project()` once per resolved Monad is how multi-entity output should work against this contract, not built here.
- **`reconcile_correction()` raises `NotImplementedError`.** No real implementation exists anywhere in this repository for the correction-flow crawler spec §30 describes; step 5's own contract docstring already said so, unchanged by step 16.
- **No relation-writer**, preserved exactly as inherited: every relation-type claim this adapter routes stays `CONFLICT` (`build_entity_patch()`'s own real, unmodified behavior).
- **`FieldOperation.field` holds a resolved Notion property name, not a generic ontology id** — a disclosed divergence from that field's own docstring, because `build_entity_patch()` does not preserve the generic key in its real output and editing that proven, corpus-validated function to add one would be exactly the "riscrittura" §33 rules out.
- **The `atom_fingerprint` word-order/OBJECT_TYPE weakness (step 7) is still unresolved**, inherited unchanged through steps 12/14/15/16 — see step 12/14's own sections above. This is the real fix needed if two differently-worded extractions of the same fact should ever be recognized as one atom before reaching this adapter.

## Working method established this session (follow it for any future work)

Each step followed this discipline; deviating from it is how the false
Correction-2 assumption made it into the spec in the first place:

1. **Read the real code the step depends on, in full, before designing
   anything.** Do not trust spec prose about what code does — verify by
   opening the file. This caught the `gmv-dropbox-import`,
   `area35_validator.py`/ATOM mismatch, `gate()` vocabulary, and
   `OperationAction` vocabulary errors, all of which the spec or an early
   draft got wrong.
2. **Schema/contract only, no premature engine.** Steps 3-7 all added a
   migration or a `typing.Protocol` + dataclasses, never a working
   pipeline/orchestration loop. Follow the same discipline for remaining
   steps unless a step explicitly calls for an engine (step 8 Monad
   materializer likely does — decide deliberately, don't default into it).
3. **New migrations are reachable via explicit `target_version` only**,
   never `CURRENT_SCHEMA_VERSION`/`SUPPORTED_SCHEMA_VERSIONS`, until the
   crawler subsystem that consumes them actually runs. This avoids any
   existing caller of `migrate(db)` being silently affected. See
   `gmv_core/migrations.py`'s `CRAWLER_SOURCE_REGISTRY_VERSION`/
   `ENTITY_REGISTRY_VERSION` for the pattern to copy.
4. **Cross-check new artifacts against already-committed ones with a real
   test, not a second hardcoded list.** E.g. the Entity Registry's
   `entity_type` CHECK is tested against the real, loaded
   `GMV_ONTOLOGY_REGISTRY_v0.1.json`, not a duplicated Python set. Several
   reviews caught drift bugs that a self-referential test would have
   missed.
5. **Full test suite (`pytest tests/ -q`) and `ruff check` must stay green
   before every commit.** No exceptions made this session.
6. **Independent adversarial review before every commit**, via the
   `gmv-code-reviewer` subagent, given only the diff and file contents —
   not this conversation's context, to avoid sharing its blind spots. Every
   single step 1-7 had a review round; **5 of 7 found real,
   non-cosmetic bugs** (wrong vocabulary claims, a SQL CHECK that only
   constrained one character position, an indirect merge-cycle gap, a
   docstring claiming an enforcement that had no code behind it). Treat a
   clean first-pass review as unlikely, not the norm.
   **Known issue this session hit twice on step 8:** the `gmv-code-reviewer`
   subagent (launched via the `Agent` tool, `run_in_background: true`)
   stalled both times — status stayed "running" with an elapsed-time
   readout that did not advance reliably, for 25+ minutes the first
   attempt and 10+ minutes the second, with no result either time.
   Both were stopped via `TaskStop` rather than waited on indefinitely.
   Step 8 was reviewed by the primary session doing the adversarial pass
   directly instead (reading the new files cold against every file they
   import from/claim to be consistent with) — it found one real gap this
   way (see step 8's commit message). If this recurs in a future session,
   don't wait past ~10-15 minutes on a single review attempt; a retry is
   worth one attempt, but a second stall means do the review directly
   rather than looping indefinitely.
7. **When a review returns BLOCK, fix and send back to the same reviewer
   for re-verification before committing** — do not just trust your own
   fix. This caught at least one case (step 7) where a fix for one
   mislabeled check reintroduced the identical mislabeling pattern in a
   different function added in the same fix.
8. **Commit message documents what the review found and how it was fixed**,
   not just what was added — future readers (including a future agent
   continuing this work) need to know which claims were already
   independently checked and which weren't.
9. **Push after every commit** (`git push`), no PR opened unless asked.

### Process improvements from steps 9-14's review history (apply starting step 15)

A retrospective across the 6 most recent adversarial-review rounds
(steps 9/11/12/13/14, several taking 2 rounds) shows the same few bug
*shapes* recurring, not random defects. Apply these proactively — the
goal is fewer review round-trips on step 15/16, not a new process:

1. **A claim in a docstring that something is "imported"/"reused" is
   only true if you can point at the literal `from X import Y` line in
   *this* file.** Two separate findings (step 9's credentials.py claim,
   step 14's `FROZEN_PREDICATE_CLASSES` claim) were docstring prose that
   sounded true and referenced a real thing, but the actual import
   didn't exist in the module making the claim. Before sending anything
   for review, grep your own new file for every "imported"/"reused"/
   "not reimplemented" claim and verify the corresponding `import` line
   exists in that same file, not just somewhere in the codebase.
2. **When grouping/comparing by a governed vocabulary field (a
   PREDICATE, an entity type, a status), resolve through the registry's
   alias/canonical mapping before using the raw string as a key.** Step
   14's worst bug (governance-equivalent predicate aliases treated as
   unrelated facts) is exactly this. Step 15 (PUBLIC projector) will
   almost certainly filter/group atoms by PREDICATE and VISIBILITY —
   apply this check there from the first draft, not after a review finds
   it.
3. **Before adding any new call site with a repo-wide shape (a new raw
   `sqlite3.connect`, a new `INSERT`/`UPDATE`/`DELETE`, a new file-write
   pattern), search for a static boundary test first**
   (`tests/test_sqlite_connection_boundary.py`,
   `tests/test_write_authorization.py`, `tests/security/`) — step 13
   discovered this the expensive way, empirically, after already writing
   a draft that broke CI. Step 15/16 are unlikely to need a new
   connection type, but if either does, check first.
4. **When citing an ADR or governance doc as justification, read it to
   the literal end, including any "Addendum"/"Amendment" section, before
   treating any clause as current.** Step 13's docstring cited
   `ADR_CORE_PERSISTENCE_BOUNDARY.md`'s original Decision §3 ("deferred")
   and missed the same file's own addendum that closed it 2 days later —
   caught only because review reproduced the break empirically, not by
   reading further in the same file. This generalizes beyond that one
   ADR: any `00_CONFIG/ADR_*.md`/`00_CONFIG/GMV_CRAWLER_HANDOFF.md`-style
   document with dated sections may have a later section superseding an
   earlier one.
5. **Before shipping a function that makes an explicit "never X" or
   "always Y" guarantee (never silently picks a winner, always
   validates, never overwrites), write one adversarial test yourself
   that tries to break exactly that guarantee — duplicates, aliases,
   empty/malformed input, out-of-order input — before sending it to
   review.** Steps 11 and 14's core bugs were both violations of a
   guarantee the function's own docstring/tests already claimed to
   uphold; the adversarial case (duplicate item, aliased predicate) was
   findable by asking "what real-world input would break my own stated
   guarantee?", not just by writing the happy-path tests first.
6. **The `gmv-code-reviewer` subagent's tool-result is frequently
   truncated to a one-line summary** (a recurring environment quirk, not
   a content problem) — always follow up with a `SendMessage` to the
   same agent asking it to repost the full report before acting on a
   verdict. This has been necessary in most rounds this session; budget
   for it rather than treating it as an exception. **Update from step 15:**
   both review rounds this time returned a full, non-truncated report on
   the first ask (no follow-up `SendMessage` needed) — so this is not a
   universal failure mode, just frequent enough to budget for; do not
   treat one clean round as proof it stopped happening.

### Retrospective: how these 6 items held up on step 15, plus a 7th

Items 1, 2, 3, 4, and 5 were applied proactively from the first draft
(grep-verified every "imported"/"reused" claim before review; resolved
STATUS/VISIBILITY, not just PREDICATE, through the most defensible
grounding available rather than a raw string; no new SQL/DML call site
so item 3 was a quick no-op check, not skipped; re-read
`GMV_KNOWLEDGE_MONAD_SPEC_v1.0` §14 and crawler spec §15-20 fully via
fresh Notion fetches before designing, not from memory/paraphrase;
wrote the AMBIGUOUS-exclusion adversarial test, the "fails every gate
simultaneously" test, and the RELATION multi-value trade-off test
myself before sending to review). None of these caught the round-1 bug
— it was a new failure *shape*, not a repeat of 1-6, worth naming
explicitly as a 7th item for step 16 and beyond:

7. **A claim that a literal/constant "matches" or "is grounded in" a
   real value elsewhere in the codebase is only true if the cited
   location is the same field, on the same concept, at the same
   pipeline stage — not just a textually similar key somewhere in the
   right file.** Step 15's `BLOCKED_EXTRACTION_STATUS = "BLOCKED"`
   grounding test asserted the literal string `"BLOCKED"` appeared
   somewhere in `gmv_evidence_pipeline.py` — true, but the match was the
   *semantic-stage run-manifest's* `status` field, not the *per-source*
   `extraction_status` field the module's own gate actually reads. A
   substring match across an entire file proves a string exists
   somewhere, never that it exists in the right field on the right
   object. Before writing a grounding test for a "this constant matches
   a real precedent" claim: name the exact field/attribute the runtime
   code actually reads (here: `SourceManifestEntry.extraction_status`),
   then verify the cited precedent populates *that same field/attribute*
   on *the same kind of object*, not just that the literal appears in
   the same file. A dict key match (`"status"` vs. `"extraction_status"`)
   is not a coincidence to wave away — it is exactly the signal that the
   two things are different concepts.

## Open questions / known gaps (do not silently resolve these — surface them)

- **RESOLVED this session.** Step 9's premise was broken (see Correction 2
  above) — the user chose to write a real `SourceConnector` from scratch
  against the Dropbox API v2 (vs. an OAuth2 refresh-token flow, or
  reinterpreting the Skill as callable code). `10_API/gmv_dropbox_connector.py`
  implements this; see the "What exists now" table above and its own
  module docstring for the design decisions (static-token auth reusing
  `credentials.get_token()`, real SHA-256 content_hash instead of
  Dropbox's own blockwise algorithm). Not yet exercised against a real
  Dropbox account/token in any session — only against an injected fake
  session in tests. **New open item this resolution creates:** nothing in
  the crawler yet constructs a `DropboxConnector` and drives it through
  `list()`/`metadata()`/`download()` against a real folder — that
  end-to-end wiring (likely alongside whatever step first needs an actual
  running crawler loop, not a schema/contract step) has not been done or
  investigated.
- **RESOLVED this session (2026-09-15), by explicit user decision.**
  `claim_id` and `ATOM_ID`/`evidence_id` are related but structurally
  distinct (`claim_id` keys off resolved entity identity, `ATOM_ID`/
  `compute_atom_fingerprint()` off normalized text) — concretely realized
  in step 16 as `FieldOperation.claim_id = AtomCandidate.atom_id`, not a
  re-derivation of the legacy computation. See step 16's own section in
  "What exists now" above for the full account, including the docstring
  correction adversarial review forced (the first justification
  overclaimed what `reconcile()`, step 12, actually guarantees). **This
  decision does not, by itself, fix the underlying `atom_fingerprint`
  word-order/OBJECT_TYPE weakness (step 7)** — see that item below,
  still open, now the most concrete lever for closing this properly.
- **`SPONSOR`/`CONTRACT`** are CANDIDATE-status in the ontology registry
  (unit-test-only or never-produced coverage) and are deliberately excluded
  from the Entity Registry's `entity_type` CHECK — they cannot be persisted
  as entities until promoted to CORE/DOMAIN by an explicit decision.
- **RESOLVED this session (step 16).** The crawler-level `Gate` type
  (step 5, AUTO_ACCEPT/REVIEW_REQUIRED/BLOCKED) is now translated both
  directions against both real, live vocabularies:
  `gmv_notion_projection_adapter.py::_entity_gate_to_crawler_gate()`/
  `_crawler_gate_to_entity_gate` (entity-level, `gate()`'s
  READY_FOR_NOTION/REVIEW_REQUIRED/INSUFFICIENT_EVIDENCE) and
  `_body_gate_to_crawler_gate()`/`_crawler_gate_to_body_gate()`
  (body-level, `gmv_notion_candidate.py`'s
  BODY_PATCH_READY/BODY_REVIEW_REQUIRED). Note the entity-level forward
  mapping is not a straight lookup: `READY_FOR_NOTION` only becomes
  `AUTO_ACCEPT` when no operation is `CONFLICT` (a real combination
  `gate()` itself can produce, since it never inspects `operations`) —
  otherwise it downgrades to `REVIEW_REQUIRED`, enforcing
  `TargetPayload`'s own invariant rather than violating it.
- **`text_hash` format is undecided** (`EvidenceUnit.text_hash`, step 4) —
  the one real precedent in this repo (`gmv_evidence_pipeline.py:297`) uses
  bare hex, `content_hash` uses a `sha256:` prefix. Left unvalidated on
  purpose; decide before a real consumer writes `EvidenceUnit` rows.
- **Atom fingerprint trade-off** (step 7): `compute_atom_fingerprint()`
  reuses `_forma()` (word-order-invariant normalization) for every
  SUBJECT/OBJECT regardless of entity type, which can collide on
  multi-word non-person text where order is meaningful (e.g. "Venice
  Biennale" vs "Biennale Venice"). Documented and tested as a known,
  accepted v1 limitation, not fixed — a real fix needs OBJECT_TYPE-aware
  normalization, deferred to whichever step actually consumes fingerprints
  for real deduplication (likely step 12, Reconciliation engine).
- **`OBJECT_TYPE` governance in the Atom validator is partial**: checked
  against the specific predicate's declared `range` in the ontology
  registry (step 7), not against the full `entity_classes` list generally.
  This was a deliberate, more-precise design choice (avoids false positives
  on ATTRIBUTE predicates with literal-type ranges), not an oversight — but
  worth knowing if a future step assumes broader OBJECT_TYPE validation
  exists.
- **SOURCES manifest column set (step 8)**: `GMV_KNOWLEDGE_MONAD_SPEC_v1.0`
  §2.4 (prose) and §19 (worked example) disagree — §2.4 lists 11 fields
  incl. FILENAME and "DUPLICATE / DERIVATION STATUS", §19's actual table
  header has only 9, missing both. Not in §20's freeze list, so §2.4's own
  text authorizes evolution. `gmv_monad_materializer.py` follows §19's
  literal 9-column table for v1.0. If a future step needs FILENAME or
  duplicate/derivation tracking on SOURCES rows, that is an intentional,
  spec-sanctioned manifest evolution, not a schema-freeze violation — add
  the column(s), update `SOURCE_COLUMNS`/`SourceManifestEntry`/
  `_source_row()` together.
- **RESOLVED this session.** The canonical on-disk directory for
  materialized Monad `.md` files (the "Ombra") is `03_STATE/ombra/` — a
  user decision, applied and documented in
  `00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md` (new row under the existing
  `03_STATE/` "Live state" entry — a sub-path of an already-classified
  top-level path, not a new governance class) and in
  `10_API/gmv_monad_materializer.py`'s own module docstring.
  `materialize_monad()` still takes an explicit `target_path` from its
  caller rather than hardcoding a location — that part of step 8's design
  is unchanged and deliberate; the decision only fixes what a real caller
  should pass. `tests/test_gmv_monad_materializer.py`'s illustrative
  `target` paths were updated from `tmp_path / "monads" / ...` to
  `tmp_path / "03_STATE" / "ombra" / ...` to reflect this (still under
  `tmp_path` for test isolation, never writing to the repo's real
  `03_STATE/`).

## §33 implementation order — final status, all 16 steps DONE

```
9.  Dropbox connector = wrapper of    -- DONE. Not a wrapper (the premise
    gmv-dropbox-import v3                was false, see Corrections
                                          above) -- 10_API/gmv_dropbox_
                                          connector.py is a real client
                                          against Dropbox API v2, user's
                                          explicit choice of static-token
                                          auth over OAuth2 refresh-token.
                                          Adversarial review found no
                                          blockers; one real non-blocking
                                          issue (docstring falsely claimed
                                          no credential-storage precedent
                                          existed -- credentials.py's
                                          get_token() does, now reused)
                                          fixed before commit. Not yet
                                          exercised against a real Dropbox
                                          account -- see "Open questions"
                                          above for what remains.
10. Extractors                        -- DONE this session.
                                          10_API/gmv_crawler_extractor.py:
                                          `ExtractionDocument` (spec v0.2
                                          §7's own field set, snake_case)
                                          + `extract_document()`, a thin
                                          wrapper around
                                          gmv_evidence_pipeline.py's
                                          existing `_extract()` (PDF/DOCX/
                                          DOC/TXT/MD/HTML/CSV/JSON, incl.
                                          the PaddleOCR fallback and
                                          LibreOffice .doc subprocess) --
                                          reused, not reimplemented, per
                                          this session's established
                                          discipline. Adds a source_hash
                                          staleness gate (mirrors
                                          `extract()`'s own
                                          `sha256_file(path) != row["sha256"]`
                                          check) before calling
                                          `_extract()`, narrowing (not
                                          replacing -- no Run Ledger
                                          integration exists yet) the
                                          EXTRACT-before-DETECT-CHANGE
                                          ordering risk Correction 6 flags.
                                          `language` and `structural_units`
                                          are honest v1 gaps (always
                                          `None`/`()`) -- no language
                                          detection built, and
                                          segmentation is the next pipeline
                                          stage (SEGMENT), not this one.
                                          tests/test_gmv_crawler_extractor.py
                                          (21 tests) incl. a cross-check
                                          that inspects `_extract()`'s real
                                          source for every `EvidenceError`
                                          code it can raise, not a
                                          duplicated hardcoded list.
                                          **One real bug found, caught
                                          twice independently (self-review,
                                          then confirmed by
                                          `gmv-code-reviewer`):**
                                          `_extract()`'s plain-text branch
                                          (.txt/.md/.html/.csv/.json) has
                                          no try/except of its own and can
                                          raise a bare `UnicodeDecodeError`
                                          on non-UTF-8 content;
                                          `gmv_evidence_pipeline.extract()`
                                          already guards this with `except
                                          (OSError, UnicodeError)`, but the
                                          first draft of
                                          `extract_document()` only caught
                                          `EvidenceError`, contradicting its
                                          own "never raises" docstring
                                          claim. Caught first by this
                                          session's own adversarial re-read
                                          of the first draft (reproduced
                                          with a real latin1-encoded
                                          fixture before fixing, not just
                                          inferred from reading the code) and
                                          fixed -- widened the except clause
                                          to `(EvidenceError, OSError,
                                          UnicodeError)`, matching
                                          `extract()`'s own set exactly --
                                          before the independent
                                          `gmv-code-reviewer` background
                                          agent's result was available. That
                                          review (launched
                                          `run_in_background`, this time
                                          completing within the session,
                                          unlike step 8's two stalls)
                                          returned a **BLOCK** identifying
                                          the identical bug with the
                                          identical minimal fix, landing
                                          after the fix and its regression
                                          test (`test_extract_document_non_utf8_text_fails_explicitly_instead_of_crashing`)
                                          were already committed and pushed
                                          -- re-verify-the-fix step therefore
                                          already satisfied by construction,
                                          not skipped. The review's only
                                          other note was non-blocking: the
                                          source-inspection cross-check test
                                          (`test_status_values_cover_every_real_extract_error_code`)
                                          is, by its own regex-based design,
                                          blind to a non-`EvidenceError`
                                          exception type by construction --
                                          correctly flagged as a real limit
                                          of that specific test, not a
                                          defect to fix (the bug it would
                                          have missed was caught by the two
                                          adversarial reads instead). Full
                                          suite re-verified after the fix:
                                          880 passed (only the 2 documented
                                          soffice-portability failures, PR
                                          #18 not yet merged); `ruff check`
                                          clean.
11. Candidate extraction               -- DONE. 10_API/gmv_crawler_
    (default: gemma4:12b)                 candidate_extractor.py wraps
                                          the real, existing
                                          ollama_extract() rather than
                                          reimplementing LLM-calling
                                          logic. Two adversarial-review
                                          rounds found and fixed a real
                                          all-or-nothing batch-crash bug
                                          (see "What exists now" above
                                          for the full account) -- not a
                                          cosmetic finding, reproduced
                                          empirically twice. Only two
                                          candidate shapes built (Entity/
                                          generic Proposition), not the
                                          spec's five -- Relation/Event/
                                          Measure sub-typing needs
                                          NORMALIZE PREDICATES, an
                                          unbuilt stage with no numbered
                                          step in §33. gemma4:12b default
                                          still not independently
                                          reverified by any session.
12. Reconciliation engine              -- DONE, scoped to 3/6 outcomes
                                          (NEW/IDENTICAL/SUPPORTING).
                                          CONFLICTING/SUPERSEDING/
                                          CORRECTING need a "slot" key
                                          (subject+predicate, object-
                                          agnostic) that does not exist
                                          governed anywhere -- see "What
                                          exists now" above. Does NOT
                                          resolve the atom_fingerprint
                                          trade-off despite being the
                                          step this handoff previously
                                          named for that -- inherits it,
                                          documents it, does not fix it
                                          (fix belongs in step 7's
                                          compute_atom_fingerprint()).
13. FTS5                               -- DONE. Standalone FTS5 table,
                                          outside gmv_core entirely (SEC-006
                                          denies CREATE_VTABLE
                                          unconditionally -- discovered
                                          empirically, not assumed). Hit
                                          and resolved a real collision
                                          with the ARC-002 sqlite3.connect
                                          boundary -- user decision
                                          required, see "What exists now"
                                          above. Any FUTURE virtual-table-
                                          based index (e.g. vector -- not
                                          itself a numbered step, excluded
                                          from this crawler's first cycle
                                          by §31) will very likely hit the
                                          exact same wall -- read that
                                          section first.
14. DERIVED_VIEW_SPEC v0.1             -- DONE. 5 pure derivation
                                          functions (TIMELINE/LEDGER/
                                          RELATIONS/CLAIMS/CURRENT_STATE)
                                          from AtomCandidate lists. PUBLIC
                                          excluded (step 15's job). Two
                                          real bugs found and fixed in
                                          derive_current_state() -- see
                                          "What exists now" above before
                                          touching this file.
15. PUBLIC projector                   -- DONE. 10_API/gmv_crawler_
                                          public_projector.py computes
                                          MonadDocument.public_text (step
                                          8 writes it verbatim, never
                                          computes it). Reuses
                                          derive_current_state() (step
                                          14) for STATUS=VALID/dedup/
                                          alias-aware slot resolution;
                                          adds VISIBILITY=="PUBLIC" and a
                                          not-blocked-source gate.
                                          AMBIGUOUS slots -- left
                                          undefined by step 14 on purpose
                                          -- are now deliberately excluded
                                          from PUBLIC entirely, a decision
                                          this step made and documented,
                                          not step 14's. One adversarial-
                                          review round found a real
                                          grounding bug (a "BLOCKED"
                                          literal that matched the wrong
                                          field of the wrong pipeline
                                          stage, making the blocked-source
                                          gate dead code) -- fixed by
                                          keying off the real
                                          gmv_crawler_extractor.
                                          STATUS_VALUES vocabulary
                                          instead; round 2 returned PASS.
                                          See "What exists now" above for
                                          the full account.
16. Generalize gmv_notion_multi_       -- DONE (final step). The
    candidate.py behind                   claim_id/ATOM_ID/evidence_id
    ProjectionAdapter                     question that blocked this step
                                          in the previous handoff revision
                                          was resolved by explicit user
                                          decision (2026-09-15): claim_id
                                          and ATOM_ID are related but
                                          structurally distinct (claim_id
                                          keys off resolved entity
                                          identity, ATOM_ID/
                                          compute_atom_fingerprint() off
                                          normalized text) -- concretely
                                          realized as FieldOperation.
                                          claim_id = atom.atom_id, not a
                                          re-derivation of the legacy
                                          computation. 10_API/gmv_notion_
                                          projection_adapter.py wraps
                                          route_claim()/build_entity_
                                          patch()/build_entity_body()/
                                          gate()/compare_entity()/
                                          load_bundle()/publish_bundle()
                                          exactly as they exist. Two
                                          adversarial-review rounds found
                                          and closed two real BLOCK bugs
                                          (staleness check silently
                                          neutralized; body-publish path
                                          silently dead) at the TargetPayload
                                          contract level, not patched
                                          locally. See "What exists now"
                                          above for the full account,
                                          including the real, disclosed,
                                          unresolved predicate-vocabulary
                                          mismatch and the other
                                          known limitations a future
                                          session needs before this is
                                          production-usable.
```

## How to continue

**There is no next numbered step — §33's order is fully built.** What
follows is the real, prioritized list of what stands between this
preplan and an actual running crawler, for whoever picks this up next
(a future session, OpenCode, Codex, or a human):

1. Read this document fully, especially "What exists now" above — most
   of what looks like an open TODO below is already precisely scoped and
   disclosed there, not a fresh discovery.
2. Fetch and read the source Notion documents listed above yourself — do
   not rely solely on this document's summaries for anything you're
   about to build on; they may have moved since this was written.
3. **No orchestration loop exists.** Steps 1-16 are schema/contracts/
   thin translation layers, deliberately — nothing wires DISCOVER through
   AUDIT (§3) into one running pipeline against the Run Ledger
   (Correction 1). This is very likely the single largest remaining
   piece of real engineering, and was out of scope for every step in
   this preplan on purpose ("no premature engine").
4. **The predicate-vocabulary mismatch (step 16) blocks the crawler's
   Notion output from being useful in practice today** — every atom
   currently falls through to free-text body content, never structured
   fields/relations, because the crawler's governed predicates and the
   real Notion pipeline's routing hints share no vocabulary. Closing
   this needs real domain review (which registry predicate corresponds
   to which of the real hint phrases, per entity type), not code.
5. **The `atom_fingerprint` word-order/OBJECT_TYPE weakness (step 7) is
   still unresolved**, inherited unchanged through steps 12/14/15/16.
   Fix belongs in `compute_atom_fingerprint()` itself — key normalization
   on resolved entity identity (Entity Registry, step 6) rather than
   normalized text, the direction the user's 2026-09-15 claim_id/ATOM_ID
   decision pointed at but step 16 did not itself need to implement (see
   its own section above for why).
6. **CONFLICTING/SUPERSEDING/CORRECTING (step 12) are still unreachable**
   — need a "slot" identity (subject+predicate, object-agnostic) plus a
   PREDICATE_CLASS-dependent multiplicity policy that exists nowhere yet.
7. **No multi-entity fan-out** — step 16's adapter projects one Monad at
   a time; `discover_entities()`'s old capability to propose *other*
   entities merely mentioned in claims needs to become the Entity
   Registry's (step 6) job, not rebuilt inside a projection adapter.
8. **`DropboxConnector` (step 9) has never been driven end-to-end
   against a real Dropbox account/token** — only tested against an
   injected fake session. Budget time to verify the real API's response
   shapes (`path_lower`, `server_modified` format, pagination) before
   trusting it in a longer pipeline.
9. **No relation-writer exists anywhere** (inherited from the pre-crawler
   pipeline, preserved unchanged through step 16) — every relation claim
   stays `CONFLICT`. A real design, not an extension by analogy with
   simple properties (crawler spec §4-bis/§29 already warn about this).
10. **`reconcile_correction()` (step 16) raises `NotImplementedError`** —
    crawler spec §30 describes the intended flow; nothing implements it.
11. Any future virtual-table-based index (vector or otherwise) will hit
    the same SEC-006/ARC-002 boundary step 13 already resolved once — see
    "What exists now" above (step 13 section) for how to resolve it
    again without re-litigating from scratch.
12. For any future work here, follow the same pattern steps 1-16 used:
    schema/contract first (no premature engine unless a step explicitly
    calls for one and you decide that deliberately), tests that
    cross-check real committed artifacts (not hardcoded duplicates),
    adversarial review before commit (see the known `gmv-code-reviewer`
    stall/truncation issues above — don't wait indefinitely, and always
    request the full report if the tool result is a one-line summary),
    commit message documenting what review found and how it was fixed,
    push after every commit, no PR unless asked.
13. Keep the full test suite and `ruff check` green at every commit —
    check "Known environment-only failures" above first so you don't
    chase a container-specific gap as if it were a regression, and
    re-verify its current state yourself rather than trusting this
    document's last snapshot (it has flipped between sessions already).
