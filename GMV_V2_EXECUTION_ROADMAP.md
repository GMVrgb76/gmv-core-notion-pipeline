# GMV V2 Execution Roadmap

## 1. Executive Summary

GMV OS V2 must be executed as a Core Integrity program, not as an intelligence-feature program.

The technical review identified 141 backlog items. This roadmap assigns every item to one of seven implementation sprints or to an explicit defer list. The sequence is deliberate:

1. establish a reproducible delivery and migration foundation;
2. make health, logs, recovery, and legacy execution trustworthy;
3. repair the data model and eliminate split sources of truth;
4. build safe ingestion automation;
5. add controlled AI extraction and Dossier capability;
6. standardize the user and CLI contracts;
7. reconcile governance and formalize release discipline.

The roadmap prioritizes fragility reduction, observability, database protection, recovery, and safe automation. It does not prioritize cosmetic cleanup, broad Plugin capabilities, general reasoning, autonomous decisions, continuous learning, or speculative caching.

### Source limitation

The requested source files `PROJECT_VISION.md` and `PROJECT_ROADMAP.md` do not exist in the project. They were not silently substituted. Prioritization therefore uses:

- `GMV_TECHNICAL_REVIEW.md`;
- all 141 items in `GMV_V2_BACKLOG.md`;
- `GMV_CHANGELOG.md`.

The missing vision/roadmap inputs should be resolved during Sprint 007 governance work.

### Execution rules

- Each backlog ID is implemented through one or more small commits; unrelated IDs must not share a commit.
- Every database change starts with a migration and an isolated test. No manual live-schema edits are allowed.
- Every write path must be transactionally safe and emit one canonical Event once Sprint 003 is complete.
- Existing LaunchAgents remain unchanged until replacement behavior has explicit parity tests.
- Each sprint must leave the working tree clean, tests passing, documentation accurate, and recovery evidence captured.
- A sprint does not pass because commands exist. It passes only when its exit criteria are proven.

## 2. Top 25 Priority Items

| Rank | Backlog ID | Priority outcome | Why it comes now | Sprint |
|---:|---|---|---|---:|
| 1 | ROAD-001 | Reset execution to Core Integrity | Prevents further feature work from increasing structural risk. | 001 |
| 2 | AUTO-001 | Automated test suite and CI gate | No risky refactor is acceptable without repeatable evidence. | 001 |
| 3 | DB-001 | Versioned schema migrations | Every subsequent database repair depends on reproducible migration. | 001 |
| 4 | CLI-001 | Truthful strict `gmv doctor` | Current health checks can report success after failures. | 002 |
| 5 | CLI-002 | Evidence-based `gmv status` | Operators need real readiness, not unconditional `SYSTEM READY`. | 002 |
| 6 | AUTO-010 | Verified full-system backup and restore | Database and project state must be recoverable before migration. | 002 |
| 7 | ARC-005 | Eliminate multiple sources of truth | Split histories and state invalidate later automation. | 003 |
| 8 | DB-005 | Collapse legacy Timeline into Events | History already diverges and will become harder to repair. | 003 |
| 9 | DB-006 | Collapse Engine Runs into Service Runs | Execution history must have one identity and one store. | 003 |
| 10 | DB-002 | Add and enable foreign keys | Current referential integrity is accidental. | 003 |
| 11 | DB-003 | Add domain constraints | Invalid statuses, confidence values, and references must be rejected. | 003 |
| 12 | ARC-004 | Canonical Identity API | Permanent identity cannot remain convention-driven. | 001 |
| 13 | DB-007 | Transaction-safe OID allocation | `COUNT(*) + 1` risks permanent identity collisions. | 001 |
| 14 | MAIN-011 | Reconcile JSON and SQLite identities | `OBJECT-0000001` and `PER-000001` violate the core identity promise. | 003 |
| 15 | DB-004 | Enforce append-only Events | Audit history must be protected before automation writes at volume. | 003 |
| 16 | ARC-001 | Implement an executable Core | A real transaction/invariant boundary is required for safe growth. | 003 |
| 17 | ARC-002 | Enforce the persistence boundary | Direct SQLite access currently bypasses every architectural rule. | 003 |
| 18 | AUTO-004 | Canonical Event emission | Every accepted write must become traceable and reconstructable. | 004 |
| 19 | SEC-001 | Remove `shell=True` | This is the most direct command-execution vulnerability. | 002 |
| 20 | SEC-004 | Remove sensitive runtime data from Git | Live database, logs, paths, and snapshots should not be source history. | 002 |
| 21 | SEC-005 | Restrict database/snapshot permissions | Local knowledge is currently world-readable on a multi-user host. | 002 |
| 22 | AUTO-009 | Structured observability and runbooks | Failures must be diagnosable before services become autonomous. | 002 |
| 23 | DB-010 | One Import Queue state machine | Automation cannot safely run against ambiguous state fields. | 004 |
| 24 | DB-012 | Resource locations and custody | “Never lose a document” requires managed custody and location history. | 004 |
| 25 | AUTO-006 | Queue worker with claims/retries | This is the first safe automation layer after Core integrity. | 004 |

## 3. Items Explicitly Deferred

These items remain valid backlog entries but are outside the initial V2 execution path.

| Backlog ID | Deferred item | Reason for deferral | Reconsider when |
|---|---|---|---|
| ARC-007 | Full Plugin runtime | Large extension surface with little value before Core/API stability. | Core API, Service Manager, security policy, and manifest contracts are stable. |
| PERF-008 | Derived application caches | Caching would preserve inconsistent state and introduces invalidation debt. | Authoritative state and Event-driven invalidation are proven under measured load. |
| AUTO-008 | Core scheduler orchestration | Existing LaunchAgents should not be replaced before service parity and recovery are proven. | Service Manager, run history, timeouts, retries, and observability are stable. |
| AI-007 | General Reasoning Engine | Reasoning over unstable identity/provenance would be untraceable. | Sprint 005 graph quality and provenance gates pass. |
| AI-008 | Decision Engine | Autonomous recommendations require governed reasoning, approvals, and outcome tracking. | Reasoning evaluation and human-review policy are operational. |
| AI-011 | Continuous learning | No drift, evaluation, or safe promotion system exists. | Versioned evaluation and model-governance controls are mature. |
| AI-012 | General Research Agent | Source licensing, citation, freshness, and provenance are not yet complete. | Governed sources and evidence records are implemented. |
| CLI-015 | Full Plugin lifecycle CLI | It depends on the deferred Plugin runtime. | ARC-007 is accepted into an implementation milestone. |

Deferral does not permit architectural shortcuts. Interfaces should avoid blocking these capabilities, but no speculative framework should be built for them.

## 4. Sprint Structure

## Sprint 001: Foundations

### Goal

Create a reproducible development, test, migration, identity, and release baseline before changing live behavior.

### Included backlog IDs

`ROAD-001`, `ROAD-002`, `MAIN-001`, `MAIN-013`, `AUTO-001`, `AUTO-002`, `AUTO-012`, `DB-001`, `ARC-004`, `DB-007`, `DB-008`, `CLI-003`, `PERF-007`

### Expected benefit

- Every future change can be tested in isolation.
- Schema changes become versioned and reversible.
- OID creation becomes deterministic and collision-safe.
- Invalid CLI inputs fail before touching persistence.
- The project stops claiming Intelligence maturity while Core integrity is incomplete.

### Dependencies

- Clean baseline or explicit separation of scheduler-generated runtime changes.
- A sanitized database fixture derived from the current schema/data shape.
- Agreement on supported Python and SQLite versions.
- No production schema mutation until backup evidence exists; Sprint 001 migration work should be developed and tested against isolated copies.

### Small-step execution sequence

1. Implement `MAIN-013`: package metadata, pinned development tools, and a console-entrypoint plan.
2. Implement the minimal test fixture and CI gate for `AUTO-001` and `AUTO-012`.
3. Capture the current schema as migration baseline `DB-001`; add idempotence and rollback/restore tests under `AUTO-002`.
4. Define OID grammar and authority under `ARC-004` and `DB-008`.
5. Replace count-based Resource allocation in isolated tests under `DB-007`.
6. Add typed CLI input validation and error semantics under `CLI-003` without changing unrelated command output.
7. Update phase gates for `ROAD-001`, `ROAD-002`, and record `PERF-007` as an explicit no-cache decision.

### Exit criteria

- Tests run from a fresh checkout without the live database.
- CI fails on test, lint, migration, or secrets/static-check failure.
- Migration baseline reproduces the current schema exactly in an isolated database.
- Reapplying migrations is safe and deterministic.
- OID allocator passes sequential, gap, rollback, and concurrent-allocation tests.
- OID/type validation rejects malformed fixtures.
- No application cache has been introduced.
- Working tree is clean and generated runtime files are excluded from test assertions.

### Validation commands

```bash
python -m pytest -q tests/migrations tests/identity tests/cli/test_validation.py
python -m ruff check .
gmv doctor
gmv status
gmv object count
git diff --check
git status --short
```

## Sprint 002: Reliability

### Goal

Make health reporting, logs, legacy execution, security controls, and full-system recovery trustworthy before database consolidation.

### Included backlog IDs

`ARC-008`, `ARC-011`, `DB-023`, `SEC-001`, `SEC-004`, `SEC-005`, `SEC-007`, `SEC-009`, `SEC-010`, `SEC-012`, `MAIN-010`, `DOC-008`, `DOC-010`, `AUTO-009`, `AUTO-010`, `AUTO-011`, `CLI-001`, `CLI-002`, `CLI-013`, `CLI-016`, `ROAD-006`, `ROAD-007`, `ROAD-009`

### Expected benefit

- Health commands return reliable success/failure.
- The project can prove that database, source, configuration, documentation, and managed Resources are recoverable.
- Legacy processes cannot inject arbitrary shell commands or hang indefinitely.
- Runtime data stops contaminating source-control state.
- Missing logs, unsafe permissions, stale services, and stale backups become visible.

### Dependencies

- Sprint 001 test/CI foundation.
- A defined backup RPO/RTO.
- Inventory of external Morning Brief, Daily Log, and Market Engine versions.
- A safe retention decision for already tracked sensitive runtime data.

### Small-step execution sequence

1. Make Bash transitional behavior strict under `CLI-016` with regression tests.
2. Remove `shell=True`, add timeouts/process control, and pin local Engine entrypoints under `SEC-001`, `SEC-007`, and `ARC-008`.
3. Implement structured run IDs, append-only logs, error taxonomy, and stale-artifact checks under `AUTO-009` and `DB-023`.
4. Implement strict diagnostic aggregation under `CLI-001` and `AUTO-011`; remove unconditional readiness from `CLI-002`.
5. Separate runtime/generated state from Git under `ARC-011`, `MAIN-010`, and `SEC-004`.
6. Enforce restrictive permissions and protected backup/inventory handling under `SEC-005`, `SEC-009`, and `SEC-010`.
7. Implement full manifest, checksums, atomic creation, verify, isolated restore, and retention under `AUTO-010` and `CLI-013`.
8. Align the Snapshot and operations documentation under `DOC-008`, `DOC-010`, `ROAD-006`, `ROAD-007`, and `ROAD-009`.

### Exit criteria

- Induced database/query/path failures make `gmv doctor --strict` return nonzero.
- `gmv status` never prints ready when a required dependency is failed or stale.
- Compatibility execution contains no `shell=True`, has bounded runtime/output, and terminates process trees.
- Full-system backup has a manifest and checksums and is created atomically with restricted permissions.
- An isolated restore passes SQLite integrity, schema version, object count, file-manifest, and Resource checks.
- Runtime logs/database changes no longer create ordinary source diffs.
- Missing legacy log references are repaired or explicitly marked unavailable.
- Operational runbooks cover failed Service, locked database, missing Resource, and failed restore.

### Validation commands

```bash
python -m pytest -q tests/reliability tests/security tests/backup
gmv doctor --strict
gmv status
gmv snapshot verify "$(gmv snapshot list | head -n 1)"
gmv snapshot restore --check "$(gmv snapshot list | head -n 1)"
git diff --check
git status --short
```

## Sprint 003: Data / Database

### Goal

Create one authoritative identity, Event history, Service-run history, and constrained knowledge schema behind an enforceable Core persistence boundary.

### Included backlog IDs

`ARC-001`, `ARC-002`, `ARC-005`, `ARC-006`, `ARC-009`, `ARC-010`, `DB-002`, `DB-003`, `DB-004`, `DB-005`, `DB-006`, `DB-013`, `DB-014`, `DB-015`, `DB-016`, `DB-019`, `DB-020`, `DB-021`, `PERF-002`, `PERF-003`, `PERF-004`, `PERF-005`, `SEC-006`, `MAIN-003`, `MAIN-004`, `MAIN-009`, `MAIN-011`, `MAIN-012`, `MAIN-014`, `AUTO-003`

### Expected benefit

- One identity system, one history, and one execution ledger.
- Foreign keys and constraints protect graph integrity.
- All writes pass through one Core transaction boundary.
- JSON/SQLite identity divergence is resolved.
- Event, Relation, and Service queries have viable access paths.
- Provenance-ready schemas exist before AI extraction begins.

### Dependencies

- Sprint 001 migration/test foundation.
- Sprint 002 verified backup and restore evidence.
- Frozen writes during each production migration window.
- Reviewed reconciliation rules for conflicting Timeline/Event and Engine/Service Run rows.
- Explicit authority decision for JSON state versus SQLite.

### Small-step execution sequence

1. Implement the minimal Core package/repository boundary under `ARC-001`, `ARC-002`, `MAIN-001`, and `MAIN-004`.
2. Reconcile JSON/Object identities under `MAIN-011`; reject new parallel state writes.
3. Migrate Timeline into Events under `DB-005` and `AUTO-003`; update all writers before table removal.
4. Enforce append-only canonical Events under `DB-004`.
5. Migrate Engine Runs to Service Runs and unify Engine/Service identity under `DB-006`, `ARC-006`, and `MAIN-014`.
6. Add foreign keys and domain constraints under `DB-002`, `DB-003`, `DB-008`, and `SEC-006`.
7. Normalize status, names, and timestamps under `DB-013`, `DB-014`, `DB-015`, and `MAIN-012`.
8. Define the minimum Attributes/Documents/Sources/metadata schema under `DB-020`; avoid speculative generic tables.
9. Extend Relation assertions and evidence under `ARC-010` and `DB-021`.
10. Add measured indexes and concurrency settings under `DB-016`, `DB-019`, and `PERF-002` through `PERF-005`.
11. Merge Event/Timeline code and refactor import orchestration under `MAIN-003` and `MAIN-009`.

### Exit criteria

- `timeline` no longer receives writes and is removed or reduced to a view over Events.
- `engine_runs` no longer receives writes; all execution history resolves through Service OIDs.
- No JSON and SQLite record represent the same entity under different active identities.
- Foreign keys are enabled on every connection and negative integrity tests pass.
- Events cannot be mutated/deleted through supported APIs.
- All writes from migrated components use the Core transaction boundary.
- UTC RFC 3339 is the only accepted timestamp format.
- Relation assertions retain source/evidence and can represent independent claims.
- Required indexes are confirmed by query-plan tests.
- Backup created before migration restores successfully after migration.

### Validation commands

```bash
python -m pytest -q tests/core tests/database tests/events tests/relations tests/services
gmv doctor --strict
gmv status
gmv event latest
gmv service runs
sqlite3 -readonly ~/.gmv_core/09_DATABASE/GMV.db "PRAGMA integrity_check; PRAGMA foreign_key_check; PRAGMA user_version;"
git diff --check
git status --short
```

## Sprint 004: Automation

### Goal

Complete a safe, observable, human-reviewable ingestion pipeline from approved folder to managed Resource custody.

### Included backlog IDs

`ARC-003`, `DB-009`, `DB-010`, `DB-011`, `DB-012`, `DB-024`, `PERF-006`, `SEC-002`, `SEC-003`, `SEC-011`, `AUTO-004`, `AUTO-005`, `AUTO-006`, `AUTO-007`, `CLI-007`, `CLI-010`, `CLI-012`, `CLI-014`, `ROAD-012`

### Expected benefit

- Watch Folder ingestion is idempotent and bounded to approved roots.
- Queue workers claim, retry, fail, and recover deterministically.
- Human review controls acceptance and archive transitions.
- Resources have managed custody, multiple location history, provenance, and verification.
- Every transition creates one canonical Event and one observable Service Run.

### Dependencies

- Sprint 003 Core API, canonical Events, foreign keys, OID allocator, and Relation/Source foundations.
- Sprint 002 observability, process controls, and backup.
- Approved import roots, archive policy, file-size/MIME limits, and destructive-operation policy.

### Small-step execution sequence

1. Finalize the Queue state machine and unique source identity under `DB-009` and `DB-010`.
2. Add claims, leases, attempts, retries, worker identity, and transition history under `DB-011`.
3. Implement content/location separation and managed custody under `DB-012`, `ROAD-012`, and `CLI-007`.
4. Harden single-file import against root/type/size and TOCTOU risks under `SEC-002` and `SEC-003`.
5. Implement one idempotent single-worker loop under `AUTO-006`; add concurrency and retry tests before parallelism.
6. Add Watch Folder and batch/dry-run processing under `AUTO-005` and `PERF-006`.
7. Add Review/Archive transitions and safeguards under `AUTO-007`, `SEC-011`, `CLI-010`, and `CLI-012`.
8. Route Service execution and every state change through `ARC-003`, `CLI-014`, and `AUTO-004`.
9. Backfill the existing Resource only after final Queue semantics under `DB-024`.

### Exit criteria

- Importing the same file/path repeatedly is idempotent.
- Concurrent workers cannot claim the same row.
- Retryable and terminal failures are distinguished and tested.
- Every Queue transition has actor, timestamp, reason, correlation ID, and canonical Event.
- Files outside allowed roots and disallowed/oversized content are rejected safely.
- Managed copies survive source move/delete and verify against SHA-256.
- Resource location history preserves all observed locations.
- Approve/reject/retry/archive commands enforce legal transitions and destructive safeguards.
- Existing Resource is represented by the finalized Queue/backfill policy.
- End-to-end import-to-review-to-archive test passes from a temporary fixture.

### Validation commands

```bash
python -m pytest -q tests/import tests/queue tests/resources tests/integration/test_ingestion_pipeline.py
gmv doctor --strict
gmv queue pending
gmv resource verify --all
gmv service runs
git diff --check
git status --short
```

## Sprint 005: AI / Dossier Engine

### Goal

Build a constrained Dossier pipeline that extracts text, entities, and evidence-backed Relation candidates from managed Resources with human approval and measurable quality.

“Dossier Engine” is treated as a bounded composition of backlog-defined OCR, extraction, resolution, evidence, quality, model governance, and review capabilities. It is not a general Reasoning or Decision Engine.

### Included backlog IDs

`AI-001`, `AI-002`, `AI-003`, `AI-004`, `AI-005`, `AI-006`, `AI-009`, `AI-010`, `ROAD-004`, `ROAD-005`, `ROAD-010`

### Expected benefit

- Managed documents become provenance-preserving text and structured candidates.
- Entity identity is protected through candidate/review/merge policies.
- Relations retain evidence spans, source Resources, confidence, and model versions.
- AI changes are evaluated and reversible.
- Human reviewers control promotion into canonical knowledge.

### Dependencies

- Sprint 004 complete ingestion/custody/review pipeline.
- Sprint 003 Source, metadata, Relation evidence, canonical Event, and Identity APIs.
- Golden test dossiers with approved expected output.
- Defined supported formats, domain schema, licensing policy, and reviewer role.

### Small-step execution sequence

1. Reclassify current bootstrap behavior under `AI-001`; do not build on the existing Knowledge Engine name.
2. Implement OCR/text extraction for one controlled format under `AI-002`, preserving source hashes and extraction provenance.
3. Add candidate entity extraction for one domain under `AI-003`; candidates are never canonical Objects automatically.
4. Define aliases, duplicate candidates, merge/split Events, and reversible resolution under `AI-004` and `ROAD-005`.
5. Add evidence-backed Relation candidates under `AI-005` and `ROAD-004`.
6. Implement quality/contradiction/provenance checks under `AI-006`.
7. Persist model, prompt, version, parameters, and evaluation results under `AI-009` and `ROAD-010`.
8. Add calibrated confidence and human approval/rejection under `AI-010`.

### Exit criteria

- One representative dossier processes from managed Resource to reviewed candidates without direct database access.
- Extracted text links to exact source Resource/version and preserves OCR quality metadata.
- No extracted entity or Relation becomes canonical without policy-compliant review.
- Entity merges/splits are reversible and Event-traced.
- Relation candidates include evidence, source, confidence, model/prompt version, and reviewer outcome.
- Golden-dataset precision/recall thresholds are defined and met for the selected domain.
- Re-running the same dossier/version is idempotent.
- Model/prompt changes cannot be promoted without evaluation results.
- General Reasoning, Decision, Continuous Learning, and Research Agent work remains disabled.

### Validation commands

```bash
python -m pytest -q tests/ai tests/dossier tests/evaluation tests/integration/test_dossier_pipeline.py
gmv doctor --strict
gmv event latest
gmv queue pending
gmv relation show <TEST-OID>
git diff --check
git status --short
```

## Sprint 006: UX / CLI

### Goal

Replace the fragile Bash/user-output layer with a consistent, validated, documented, machine-readable CLI over the Core API.

### Included backlog IDs

`DB-017`, `DB-018`, `PERF-001`, `SEC-008`, `MAIN-002`, `MAIN-005`, `MAIN-006`, `MAIN-007`, `MAIN-008`, `UX-001`, `UX-002`, `UX-003`, `UX-004`, `UX-005`, `UX-006`, `UX-007`, `UX-008`, `CLI-004`, `CLI-005`, `CLI-006`, `CLI-008`, `CLI-009`, `CLI-011`

### Expected benefit

- Commands have one validation, error, text, and JSON contract.
- Help is complete and generated from command definitions.
- Search is ranked, paginated, and scalable.
- Duplicate Event/Timeline, Queue, and Plugin surfaces are removed or clearly aliased.
- Object and Relation operations are available only through safe Core transactions.

### Dependencies

- Sprint 003 Core API and canonical Event/Relation models.
- Sprint 004 Resource/Queue write operations.
- Stable command compatibility decisions and JSON schema versioning.
- Measured Search corpus and ranking expectations.

### Small-step execution sequence

1. Define text/table/JSON/error contracts under `UX-001` through `UX-005`, `SEC-008`, and `CLI-004`.
2. Introduce a structured command registry and generated help/version under `MAIN-002`, `UX-006`, and `CLI-005`.
3. Port commands one family at a time with contract tests; keep compatibility aliases temporarily.
4. Consolidate Event/Timeline and Queue surfaces under `CLI-009`, `MAIN-006`, and `UX-007`.
5. Resolve Plugin duplication/dead abstractions under `MAIN-005`, `MAIN-007`, `MAIN-008`, and `UX-008` without implementing the deferred Plugin runtime.
6. Add controlled Object/Relation operations under `CLI-006` and `CLI-008`.
7. Implement FTS5 Search, ranking, filters, limits, and pagination under `DB-017`, `DB-018`, `PERF-001`, and `CLI-011`.

### Exit criteria

- Every command supports consistent help and error behavior.
- Every read command supports versioned JSON or has a documented exception.
- Text output safely handles pipes, newlines, Unicode, and terminal control characters.
- Empty results are explicit and successful; missing entities are distinct errors.
- Global limits/pagination prevent unbounded output.
- Event/Timeline and Queue aliases return the same canonical data contract.
- Search uses FTS5, has deterministic ranking tests, and no view relies on embedded ordering.
- Object/Relation writes validate input and emit canonical Events.
- Bash dispatcher is removed or reduced to a compatibility shim.

### Validation commands

```bash
python -m pytest -q tests/cli tests/search tests/contracts
gmv --help
gmv version
gmv doctor --strict --json
gmv search "GMV Core" --json --limit 10
gmv object list --json --limit 10
git diff --check
git status --short
```

## Sprint 007: Documentation / Governance

### Goal

Make architecture, status, decisions, roadmap, release evidence, and deprecation plans accurately describe the implemented V2 system.

Documentation must be updated during every prior sprint. Sprint 007 is the final reconciliation and governance gate, not permission to defer documentation until the end.

### Included backlog IDs

`ARC-012`, `DB-022`, `DOC-001`, `DOC-002`, `DOC-003`, `DOC-004`, `DOC-005`, `DOC-006`, `DOC-007`, `DOC-009`, `ROAD-003`, `ROAD-008`, `ROAD-011`, `ROAD-013`

### Expected benefit

- Normative documents distinguish implemented, partial, planned, and deprecated behavior.
- Backlog, Sprint, Changelog, architecture, and code report the same maturity.
- Architecture decisions are reviewable and deduplicated.
- Legacy exits and release criteria are measurable.
- Fresh checkouts reproduce the documented project structure.

### Dependencies

- Evidence and final state from Sprints 001–006.
- Resolution of the missing `PROJECT_VISION.md` and `PROJECT_ROADMAP.md` names/ownership.
- Owners and dates for every compatibility/deprecation exit.
- Release artifacts, migration proof, test results, and restore evidence.

### Small-step execution sequence

1. Add implementation-status matrices under `DOC-001` and correct phase/completion claims under `DOC-002` through `DOC-006`.
2. Reconcile Sprint/Changelog milestones and replace the unsupported automated-validation claim with current evidence.
3. Create canonical text ADRs under `DOC-007`, reconcile duplicate database decisions under `DB-022`, and define linkage.
4. Document deprecation exits under `DOC-009`, `ROAD-011`, and explicitly preserve the deferred Scheduler/Plugin work.
5. Add data-governance and release workstreams under `ROAD-003` and `ROAD-008`.
6. Define measurable exit criteria under `ROAD-013` and apply them to the V2 release.
7. Reconcile documented directories and actual checkout structure under `ARC-012`.

### Exit criteria

- Every foundational document has implementation status, owner, version, and last-review date.
- Backlog DONE items have linked acceptance evidence.
- Sprint Completed and Changelog entries agree.
- All architectural claims about Events, OIDs, validation, backup, and automation match code and tests.
- Unique ADRs exist in version-controlled text; database duplicates are resolved through migration.
- Every legacy Engine/table has an owner, usage metric, exit criterion, and target milestone.
- Release checklist requires CI, migration proof, strict doctor, clean status, changelog, and isolated restore proof.
- Required directories survive a fresh checkout and undocumented directories are removed from normative diagrams.
- All 141 V2 backlog IDs are either completed, explicitly carried forward, or retained in the defer register.

### Validation commands

```bash
python -m pytest -q tests/documentation tests/contracts tests/release
gmv doctor --strict
gmv status
gmv version
git diff --check
git status --short
git log --oneline -10
```

## 5. Backlog Disposition Summary

All 141 backlog items are assigned exactly once:

| Disposition | Item count |
|---|---:|
| Sprint 001 | 13 |
| Sprint 002 | 23 |
| Sprint 003 | 30 |
| Sprint 004 | 19 |
| Sprint 005 | 11 |
| Sprint 006 | 23 |
| Sprint 007 | 14 |
| Explicitly deferred | 8 |
| **Total** | **141** |

Sprint ordering is mandatory. Work inside a sprint may be split further, but a later sprint must not bypass an unmet dependency or exit criterion from an earlier sprint.

## 6. Risk Analysis

| Risk | Likelihood | Impact | Mitigation | Stop condition |
|---|---|---|---|---|
| Migration corrupts the only live database | High | Critical | Verified pre-migration backup, isolated migration rehearsal, transaction, rollback/restore test. | Restore proof is absent or checksum/integrity fails. |
| Scheduler mutates DB/logs during migration | High | High | Maintenance window, writer inventory, explicit freeze, post-migration reconciliation. | Any unaccounted writer remains active. |
| Timeline/Event reconciliation loses history | Medium | Critical | Preserve both originals in backup, deterministic reconciliation report, row-level review, parity tests. | Unexplained conflicting records remain. |
| OID reconciliation merges distinct entities | Medium | Critical | Candidate mapping, manual approval, reversible Events, golden identity fixtures. | Identity mapping is ambiguous. |
| Runtime data remains in Git history | High | High | Stop new tracking first; classify sensitivity; decide history rewrite separately with backup. | History rewrite lacks tested recovery or stakeholder approval. |
| Strict Doctor breaks existing automation | High | Medium | Add strict mode first, update callers, then make strict default after compatibility window. | Required callers cannot distinguish warning from failure. |
| Legacy command hardening changes behavior | Medium | High | Capture current command vectors/output, parity tests, timeouts with explicit overrides. | Required Engine cannot run without unsafe shell semantics and no safe adapter exists. |
| Full backup omits external Resources | High | Critical | Manifest every managed/external Resource, verify existence/hash, report exclusions explicitly. | Backup claims complete while manifest has unresolved required files. |
| Core refactor becomes a big-bang rewrite | Medium | High | Vertical slices, compatibility adapters, one command/write path per commit. | A change cannot be validated independently. |
| Queue automation duplicates or loses work | Medium | Critical | Unique identity, leases, idempotency keys, attempts, retry policy, concurrency tests. | Same row can be claimed twice or terminal work can disappear. |
| Managed custody duplicates sensitive files unsafely | Medium | High | Approved roots, classification, restrictive permissions, encryption policy, retention. | Custody destination cannot meet confidentiality requirements. |
| AI promotes incorrect knowledge | High | Critical | Candidate states, evidence, confidence calibration, human review, golden evaluation, reversible promotion. | Canonical writes bypass review or lack provenance. |
| Dossier scope expands into general reasoning | Medium | High | Sprint charter explicitly excludes AI-007/008/011/012; gate scope in review. | Work requires deferred reasoning/decision capabilities. |
| CLI compatibility breaks scripts | Medium | Medium | Versioned JSON, compatibility aliases, contract tests, deprecation window. | Existing critical automation has no migration path. |
| Documentation again overstates completion | High | High | Acceptance evidence per DONE item, status matrices, Sprint 007 audit. | A milestone is marked complete without tests and recovery evidence. |
| Seven sprints become too large | High | Medium | Split each included ID into atomic tasks/commits; preserve sprint exit gate rather than calendar promise. | Review queue or unvalidated diff grows beyond one coherent task. |

## 7. Recommended First Implementation Task

### Task: Create an isolated characterization-test harness for the current schema and CLI

Primary backlog ID: `AUTO-001`
Supporting IDs: `MAIN-013`, `DB-001`

This is the first task because every high-impact change modifies identity, schema, history, health, or recovery. Implementing those changes without a reproducible isolated baseline would repeat the current pattern of manual confidence.

### Exact scope

1. Add minimal package/test metadata with pinned development dependencies.
2. Create a temporary GMV home/database fixture; never point tests at `~/.gmv_core/09_DATABASE/GMV.db`.
3. Capture current schema objects, views, indexes, `user_version`, and representative seed rows as characterization expectations.
4. Add CLI characterization tests for current exit codes and output of `doctor`, `status`, `object count`, and one missing-entity command.
5. Add a guard that fails tests if the live GMV path is opened for writing.
6. Add CI that runs the isolated tests and `git diff --check`.

### Explicit non-goals

- Do not repair schema defects in this task.
- Do not change the live database.
- Do not rewrite the Bash CLI.
- Do not change command contracts yet.
- Do not add AI, Queue workers, or Plugin features.

### Acceptance criteria

- The test suite passes from a clean checkout using only temporary state.
- The live database modification timestamp and hash remain unchanged during tests.
- A deliberate schema mismatch causes a clear test failure.
- A deliberate CLI nonzero dependency failure is captured as current behavior, ready for Sprint 002 correction.
- CI publishes a deterministic pass/fail result.
- The working tree remains clean after the test run.

### Validation commands

```bash
python -m pytest -q tests/characterization
python -m ruff check .
gmv doctor
gmv status
gmv object count
git diff --check
git status --short
```
