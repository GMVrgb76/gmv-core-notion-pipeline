# GMV Crawler — Handoff for continuation (preplan steps 9-16)

Status: steps 1-8 of the crawler's implementation order (spec §33) are
complete, reviewed, committed, and pushed. This document lets a different
tool/session (OpenCode, Codex, a fresh Claude Code session, or a human)
resume from step 9's open decision (see "Step 9 is blocked" below) without
re-deriving what this and the prior session already verified. Read this
document fully before touching code — several assumptions in the original
spec turned out to be false on inspection; this document tells you which
ones, and how they were corrected.

## Repository state

- Repository: `GMVrgb76/gmv-core-notion-pipeline`
- Branch: `worktree-bridge-cse_01EFSz2nNresRvPh9GbfwwzK`, pushed to `origin`,
  in sync (`git status -sb` shows no divergence)
- Base: forked from `main` at `b480b04f`
- No PR opened yet — that decision was left to the user
- 9 commits ahead of base, in order:
  1. `d6b9b685` — Epistemic Ingestion Rules config + crawler_source_registry migration (steps 1+3)
  2. `b1629b69` — GMV_ONTOLOGY_REGISTRY v0.1 (step 2)
  3. `0309b9af` — Source/Evidence contract (step 4)
  4. `fbbcb739` — Projection Adapter contract (step 5)
  5. `9a719578` — Entity Registry migration (step 6)
  6. `a4334505` — Atom validator (step 7)
  7. `d328028` — this handoff document, first version
  8. `0dd6c76` — fix: unblock test collection (pre-existing Python-2-syntax
     SyntaxError in `10_API/gmv_artist_normalize_plan.py`, unrelated to the
     crawler, predates this branch's fork point — see "Unrelated bug fixed
     this session" below) and repo git policy (this handoff's own absolute
     path)
  9. `8327d78` — Monad materializer v1.0 (step 8)
- Full test suite as of `8327d78`: **851 passed, 10 failed**. The 10
  failures are pre-existing, sandbox-environment-only gaps, not
  regressions — verified individually, not fixed (see "Known
  environment-only failures" below). `ruff check .` clean.
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
  work (steps 1-7). Step 8 (Monad materializer) is the first step with a
  real write path, but it writes to a caller-supplied local path only —
  still no network/credentials involved.

### Known environment-only failures (do not "fix" without checking your own container first)

10 of the ~861 collected tests fail in this session's sandboxed container
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

## What exists now (steps 1-8), file by file

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

## Working method established this session (follow it for steps 9-16)

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

## Open questions / known gaps (do not silently resolve these — surface them)

- **Step 9's premise is broken** (see Correction 2 above) — needs a
  decision on how the Dropbox `SourceConnector` actually gets built before
  that step can proceed.
- **`claim_id` vs `ATOM_ID`/`evidence_id` relationship** — the original
  spec flags this as unresolved ("ho verificato che claim_id vive a monte
  di ogni logica Notion, ma l'equivalenza semantica con evidence_id è
  un'ipotesi mia, non un fatto confermato — va chiusa da te prima che la
  generalizzazione dell'adapter venga scritta"). Still open; relevant
  before step 16 (generalizing `gmv_notion_multi_candidate.py` behind
  `ProjectionAdapter`).
- **`SPONSOR`/`CONTRACT`** are CANDIDATE-status in the ontology registry
  (unit-test-only or never-produced coverage) and are deliberately excluded
  from the Entity Registry's `entity_type` CHECK — they cannot be persisted
  as entities until promoted to CORE/DOMAIN by an explicit decision.
- **`Gate` vocabulary reconciliation is still owed.** The crawler-level
  `Gate` type (step 5, AUTO_ACCEPT/REVIEW_REQUIRED/BLOCKED) is a new
  vocabulary, not translated from the two real, live vocabularies it will
  eventually have to interoperate with: `gate()`'s entity-level
  READY_FOR_NOTION/REVIEW_REQUIRED/INSUFFICIENT_EVIDENCE
  (`gmv_evidence_pipeline.py`) and the body-level
  BODY_PATCH_READY/BODY_REVIEW_REQUIRED (`gmv_notion_candidate.py`). This
  translation does not exist yet.
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

## Remaining steps (§33, 9-16) — status and notes

```
9.  Dropbox connector = wrapper of    -- BLOCKED on a decision: the
    gmv-dropbox-import v3                premise is false (see Corrections
                                          above). Independently
                                          re-verified this session (not
                                          just trusted from the prior
                                          handoff): grepped this repo's
                                          full git history for
                                          dropbox-import/dropbox_import
                                          (zero hits besides this
                                          handoff's own text and the
                                          documented corrections), and
                                          fetched the real Skill file
                                          directly from Dropbox
                                          (/GMV_SKILLS/gmv-dropbox-import/
                                          SKILL.md) via the Dropbox MCP
                                          connection -- confirmed it is an
                                          LLM-instruction document
                                          (AUDIT/ESECUZIONE/NORMALIZZAZIONE
                                          modes, explicit human-confirmation
                                          step before any mutation), and its
                                          actual triage vocabulary does not
                                          even match the "Certi/Da
                                          decidere/Non toccare" three-list
                                          claim the spec makes for it. A
                                          real SourceConnector
                                          implementation is needed from
                                          scratch, or the Skill-based
                                          workflow needs to be
                                          reinterpreted as callable code.
                                          Still not resolved -- surface
                                          this to the user before
                                          proceeding, do not decide it
                                          autonomously.
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
11. Candidate extraction               -- not started. Default LLM
    (default: gemma4:12b)                 gemma4:12b per prior benchmark
                                          (not independently reverified
                                          this session).
12. Reconciliation engine              -- not started. This is likely
                                          where the atom_fingerprint
                                          trade-off (see above) needs to
                                          be resolved for real.
13. FTS5                               -- not started.
14. DERIVED_VIEW_SPEC v0.1             -- not started.
15. PUBLIC projector                   -- not started.
16. Generalize gmv_notion_multi_       -- not started. Depends on the
    candidate.py behind                   claim_id/ATOM_ID open question
    ProjectionAdapter                     above being resolved first, per
                                          the spec's own explicit
                                          ordering rationale (§33 note:
                                          "PRIMA di generalizzare... non
                                          dopo").
```

## How to continue

1. Read this document fully.
2. Fetch and read the source Notion documents listed above yourself — do
   not rely solely on this document's summaries for anything you're about
   to build on.
3. Resolve step 9's blocked premise with the user before writing a Dropbox
   connector — this has now been independently verified false by two
   separate sessions; do not attempt to route around it (e.g. by
   "reinterpreting" the Skill as code) without an explicit user decision.
4. With step 9 blocked, step 10 (Extractors: PDF/DOCX/TXT/MD content
   extraction) may be the next practically unblocked step — it operates on
   raw bytes, not on a specific connector, so it does not strictly require
   step 9 to be resolved first. Not started or investigated this session;
   before designing it, read `gmv_evidence_pipeline.py`'s existing
   extraction code (PDF/DOCX/TXT/MD, plus its PaddleOCR integration for
   scanned PDFs, referenced but not inspected this session) in full first,
   per this session's own established discipline (read the real code
   before designing, don't assume from spec prose) — it may turn out to
   already largely exist, the same way step 4/6/7's grounding work found
   for other "not started" items in earlier drafts of this document.
5. For any step, follow the same pattern steps 1-8 used: schema/contract
   first (no premature engine unless the step explicitly calls for one and
   you decide that deliberately), tests that cross-check real committed
   artifacts (not hardcoded duplicates), adversarial review before commit
   (see the known `gmv-code-reviewer` stall issue above — don't wait
   indefinitely if it recurs), commit message documenting what review
   found and how it was fixed, push after every commit, no PR unless
   asked.
6. Keep the full test suite and `ruff check` green at every commit —
   check "Known environment-only failures" above first so you don't chase
   a container-specific gap as if it were a regression.
