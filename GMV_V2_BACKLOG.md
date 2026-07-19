# GMV V2 BACKLOG

Source: `GMV_TECHNICAL_REVIEW.md`
Purpose: exhaustive remediation backlog extracted from the technical due diligence.
Effort scale: XS (hours), S (up to 2 days), M (up to 1 week), L (multiple weeks), XL (multi-milestone).

## Architecture

### ARC-001 — Implement an executable Core

- **Description:** The Core is currently a directory convention and SQLite file. There is no executable kernel, domain layer, transaction boundary, or stable internal API.
- **Severity:** Critical
- **Effort:** XL
- **Dependencies:** DB-001, DB-002, DB-003
- **Expected benefit:** Establishes one enforceable place for identity, transaction, validation, Event, and persistence rules.
- **Can be automated:** Partially
- **Recommended next action:** Define the minimum Core package boundaries and implement one end-to-end Object read/write use case through them.

### ARC-002 — Enforce the persistence boundary

- **Description:** CLI commands, Services, Engines, and Plugins open SQLite directly, contradicting the documented rule that all persistence access must pass through the Core API.
- **Severity:** Critical
- **Effort:** XL
- **Dependencies:** ARC-001, DB-001
- **Expected benefit:** Prevents bypassing invariants and stabilizes the internal contract.
- **Can be automated:** Partially
- **Recommended next action:** Add a repository/data-access layer, migrate callers incrementally, then add a static check that rejects direct `sqlite3.connect` outside the Core package.

### ARC-003 — Implement the Service Manager

- **Description:** No Service Manager exists. Service discovery, execution, lifecycle, status, version negotiation, authorization, and contract enforcement are absent.
- **Severity:** High
- **Effort:** L
- **Dependencies:** ARC-001, ARC-006, AUTO-008
- **Expected benefit:** Makes Services first-class, discoverable, observable, and consistently executable.
- **Can be automated:** Partially
- **Recommended next action:** Define a minimal Service manifest and registry contract, then implement list, inspect, and run through one manager.

### ARC-004 — Implement a canonical Identity API

- **Description:** OIDs are manually seeded or allocated with table row counts. There is no Identity API, canonical allocator, validator, or prefix/type enforcement.
- **Severity:** Critical
- **Effort:** L
- **Dependencies:** DB-001, DB-007, DB-008
- **Expected benefit:** Protects permanent identity, the central invariant of GMV OS.
- **Can be automated:** Yes
- **Recommended next action:** Specify allocation and validation rules, migrate existing identities, and route all creation through one transaction-safe API.

### ARC-005 — Eliminate multiple sources of truth

- **Description:** History is split between `events` and `timeline`; runs between `engine_runs` and `service_runs`; identity/state between SQLite, JSON, reports, and Git.
- **Severity:** Critical
- **Effort:** XL
- **Dependencies:** DB-005, DB-006, MAIN-011
- **Expected benefit:** Makes system state explainable and prevents divergent answers.
- **Can be automated:** Partially
- **Recommended next action:** Publish an authority matrix, reconcile each duplicate store, migrate data, and remove obsolete writers.

### ARC-006 — Unify Engine and Service models

- **Description:** Engine, Service, and Compatibility Service overlap without one canonical identity, lifecycle, execution record, or ownership model.
- **Severity:** High
- **Effort:** L
- **Dependencies:** ARC-003, DB-006
- **Expected benefit:** Removes duplicated registries and enables consistent execution and observability.
- **Can be automated:** Partially
- **Recommended next action:** Make Engine a Service capability/type, map existing ENG/SRV records, and deprecate the separate Engine registry.

### ARC-007 — Build an actual Plugin runtime

- **Description:** The Plugin System is only metadata and links. It has no manifest, loader, entrypoint validation, lifecycle, dependency model, installation, isolation, capability contract, or runtime dispatch.
- **Severity:** High
- **Effort:** XL
- **Dependencies:** ARC-001, ARC-003, SEC-010
- **Expected benefit:** Converts registry rows into a controlled extension system.
- **Can be automated:** Partially
- **Recommended next action:** Define a versioned manifest and capability model; implement validation before installation or execution.

### ARC-008 — Bring legacy Engines into a reproducible boundary

- **Description:** Morning Brief and Daily Log live under `~/.gmv_scripts`; Market Engine executes directly from Dropbox. The repository cannot build, test, restore, or audit them.
- **Severity:** High
- **Effort:** L
- **Dependencies:** SEC-001, ARC-003
- **Expected benefit:** Produces reproducible deployments and removes runtime dependence on uncontrolled external code.
- **Can be automated:** Partially
- **Recommended next action:** Inventory exact versions, vendor or package approved source, pin entrypoints, and replace Dropbox execution with local releases.

### ARC-009 — Apply the universal Object model consistently

- **Description:** Engines, runs, architecture decisions, queue records, and JSON state persist outside the claimed universal Object identity model; Events are documented as Objects but are not modeled as such.
- **Severity:** High
- **Effort:** L
- **Dependencies:** ARC-004, DB-020
- **Expected benefit:** Removes special-case identity systems and clarifies which records require OIDs.
- **Can be automated:** Partially
- **Recommended next action:** Decide which persistent concepts are Objects versus subordinate records and document/enforce that boundary.

### ARC-010 — Complete the Relation architecture

- **Description:** Relations have unrestricted predicate text and lack a type registry, direction semantics, validity interval, confidence, evidence, source Resource, status, versioning, and Event history.
- **Severity:** High
- **Effort:** L
- **Dependencies:** DB-002, DB-003, DB-021
- **Expected benefit:** Makes graph assertions traceable, queryable, and suitable for reasoning.
- **Can be automated:** Partially
- **Recommended next action:** Define relation assertion and evidence schemas before adding extraction automation.

### ARC-011 — Separate source, operational state, and generated artifacts

- **Description:** Source code, live database, logs, reports, migration output, state, snapshots, and governance documents coexist as tracked project content.
- **Severity:** High
- **Effort:** M
- **Dependencies:** MAIN-010, SEC-004
- **Expected benefit:** Enables clean builds, deployments, tests, and backups without committing mutable runtime state.
- **Can be automated:** Yes
- **Recommended next action:** Define repository/runtime layouts, move generated state outside source control, and provide fixtures for tests.

### ARC-012 — Reconcile documented and real project structure

- **Description:** Empty directories disappear in clones, `11_PLUGINS` is documented but absent, and `.DS_Store` is tracked.
- **Severity:** Low
- **Effort:** XS
- **Dependencies:** ARC-011
- **Expected benefit:** Makes fresh checkouts match the architecture and removes platform noise.
- **Can be automated:** Yes
- **Recommended next action:** Add deliberate placeholders/manifests for required empty directories, create or remove the Plugin directory from the spec, and untrack `.DS_Store`.

## Database

### DB-001 — Introduce schema migrations and versioning

- **Description:** `PRAGMA user_version` is zero and there is no migration ledger, rollback procedure, or reproducible schema evolution path.
- **Severity:** Critical
- **Effort:** L
- **Dependencies:** None
- **Expected benefit:** Makes schema changes deterministic, reviewable, testable, and recoverable.
- **Can be automated:** Yes
- **Recommended next action:** Baseline the current schema as migration 001, set a schema version, and add forward/rollback validation.

### DB-002 — Add and enable foreign keys

- **Description:** No foreign keys are declared and `PRAGMA foreign_keys` is disabled. Current lack of orphans is accidental, not enforced.
- **Severity:** Critical
- **Effort:** L
- **Dependencies:** DB-001, ARC-005
- **Expected benefit:** Prevents invalid Object, Event, Relation, Resource, Plugin, Queue, and Service references.
- **Can be automated:** Yes
- **Recommended next action:** Define deletion policies, rebuild affected tables under migration, enable foreign keys on every connection, and test violations.

### DB-003 — Add domain check constraints

- **Description:** Lexical OID format, Service Run outcomes, confidence range,
  compatibility flags, and non-self Relation rules are not constrained. Import
  Queue state/persistence is implemented by DB-010. Duplicated lifecycle status
  policy and checks are explicitly deferred to DB-013.
- **Severity:** High
- **Effort:** M
- **Dependencies:** DB-001, ARC-004. The accepted DB-003 decision contract
  defines the Import Queue state machine before DB-010 implementation; queue
  persistence enforcement remains owned by DB-010. Status normalization is not
  a DB-003 dependency because it is owned end-to-end by DB-013.
- **Expected benefit:** Rejects malformed state at the persistence boundary.
- **Can be automated:** Yes
- **Recommended next action:** After new explicit approval, repeat the
  controlled live preflight, create a fresh verified milestone at the remediated
  HEAD, apply migration 007 conditionally, and promote the default to v7 only
  after every post-cutover check passes. DB-010 adds the accepted confidence
  check during its Queue rebuild. Do not add lifecycle-status checks under
  DB-003.

### DB-004 — Enforce append-only Events

- **Description:** Events can be updated or deleted despite the append-only architecture. There is no correction/supersession mechanism.
- **Severity:** Critical
- **Effort:** M
- **Dependencies:** DB-001, DB-005
- **Expected benefit:** Protects audit history and makes derived state trustworthy.
- **Can be automated:** Yes
- **Recommended next action:** Add restricted write APIs/triggers and define compensating Event semantics.

### DB-005 — Migrate and remove legacy `timeline`

- **Description:** `events` and `timeline` duplicate five records and already diverge: four Events are missing from Timeline and two Timeline rows are missing from Events.
- **Severity:** Critical
- **Effort:** M
- **Dependencies:** DB-001, AUTO-003
- **Expected benefit:** Restores one canonical history and removes inconsistent reads/writes.
- **Can be automated:** Yes
- **Recommended next action:** Reconcile rows, migrate unique legacy records, switch all writers to Events, verify parity, then drop the table.

### DB-006 — Migrate execution history to `service_runs`

- **Description:** Five runs are duplicated in `engine_runs` and `service_runs`; newer runs diverge, and CLI deduplication relies on normalized names and exact timestamps.
- **Severity:** High
- **Effort:** M
- **Dependencies:** DB-001, ARC-006
- **Expected benefit:** Creates one reliable execution history and removes heuristic merging.
- **Can be automated:** Yes
- **Recommended next action:** Assign canonical Service identities, migrate missing rows, update writers, and retire `engine_runs`.

### DB-007 — Replace count-based OID allocation

- **Description:** Resource identity uses `COUNT(*) + 1`, which can reuse or collide under gaps, deletion, or concurrent import and becomes slower with growth.
- **Severity:** Critical
- **Effort:** M
- **Dependencies:** DB-001, ARC-004
- **Expected benefit:** Guarantees stable unique identity under concurrent ingestion.
- **Can be automated:** Yes
- **Recommended next action:** Implement a transactional sequence or monotonic ID allocator and add concurrency tests.

### DB-008 — Enforce OID prefix/type consistency

- **Description:** Current prefixes are convention only. Nothing prevents a Resource row from receiving a Service OID or duplicate identities across JSON and SQLite.
- **Severity:** High
- **Effort:** M
- **Dependencies:** ARC-004, DB-003
- **Expected benefit:** Detects identity corruption at creation time.
- **Can be automated:** Yes
- **Recommended next action:** Add a canonical validator plus migration checks for every existing Object and extension row.

### DB-009 — Make queue source identity deterministic

- **Description:** `source_path` is not unique and the importer updates only the first matching row, making duplicate-path behavior nondeterministic.
- **Severity:** High
- **Effort:** S
- **Dependencies:** DB-001, DB-010
- **Expected benefit:** Makes queue upserts idempotent and predictable.
- **Can be automated:** Yes
- **Recommended next action:** Define the queue identity key, deduplicate rows, add a unique constraint, and use a real UPSERT.

### DB-010 — Define one Import Queue state machine

- **Description:** `status` and `review_status` overlap without legal transitions or a single definition of “pending.”
- **Severity:** High
- **Effort:** M
- **Dependencies:** Accepted DB-003 Import Queue state decision contract
  (`00_CONFIG/ADR_DB003_IMPORT_QUEUE_STATE_MACHINE.md`) and DB-003 confidence
  domain (`00_CONFIG/ADR_DB003_AUTHORITATIVE_DOMAIN_SCOPE.md`), not completion
  of every non-queue DB-003 constraint.
- **Expected benefit:** Prevents contradictory states and supports reliable automation/review.
- **Can be automated:** Partially
- **Recommended next action:** Implement the accepted single-field state
  contract, legal-transition enforcement, Core transition API, Event emission,
  and atomic reader/writer cutover; do not infer authority from test fixtures.

### DB-011 — Add queue execution metadata

- **Description:** Queue rows lack lease/claim ownership, retry count, attempt history, next-attempt time, worker identity, transition history, and robust error records.
- **Severity:** High
- **Effort:** L
- **Dependencies:** DB-010, ARC-003
- **Expected benefit:** Enables safe concurrent workers, retries, diagnosis, and recovery.
- **Can be automated:** Yes
- **Recommended next action:** Add attempt and transition tables rather than overloading the queue row.

### DB-012 — Separate Resource content from locations

- **Description:** SHA-256 identifies content but each Resource supports only one path. Identical content at another path resolves to the old Resource while losing the new location.
- **Severity:** High
- **Effort:** L
- **Dependencies:** DB-001, ARC-009
- **Expected benefit:** Correctly models content identity, multiple locations, movement, and availability.
- **Can be automated:** Partially
- **Recommended next action:** Add `resource_locations` with path history, availability, timestamps, and uniqueness rules.

### DB-013 — Remove duplicated current-status fields

- **Description:** Object status is duplicated in Resources and Plugin metadata,
  allowing state drift and contradicting the claim that status is derived.
  DB-013 exclusively owns lifecycle-status authority, normalization, and future
  checks for these duplicated fields; DB-003 must not constrain them first.
- **Severity:** Medium
- **Effort:** M
- **Dependencies:** DB-005, ARC-009, and the accepted DB-003 scope decision
  (`00_CONFIG/ADR_DB003_AUTHORITATIVE_DOMAIN_SCOPE.md`).
- **Expected benefit:** Produces one authoritative current-state model.
- **Can be automated:** Partially
- **Recommended next action:** Decide whether status is stored or derived per
  entity, reconcile values, migrate redundant fields/views, and only then add
  lifecycle-status domain checks.

### DB-014 — Remove duplicated Service names from run records

- **Description:** `service_name` is copied into `service_runs`, so display-name changes can produce identity drift unless explicitly treated as an immutable snapshot.
- **Severity:** Medium
- **Effort:** S
- **Dependencies:** DB-006
- **Expected benefit:** Clarifies historical naming and prevents accidental joins on mutable text.
- **Can be automated:** Yes
- **Recommended next action:** Retain only `service_oid` or rename the field to an explicit historical snapshot with documented semantics.

### DB-015 — Standardize timestamps

- **Description:** Timestamps mix `T` and space separators, omit timezone, and use inconsistent generation paths.
- **Severity:** High
- **Effort:** M
- **Dependencies:** DB-001
- **Expected benefit:** Enables correct ordering, interoperability, audit, and cross-timezone processing.
- **Can be automated:** Yes
- **Recommended next action:** Adopt UTC RFC 3339, normalize existing values, and centralize timestamp creation.

### DB-016 — Add workload indexes

- **Description:** Only automatic primary/unique indexes exist. Event, Relation, Queue, run-history, and Resource-location queries perform full scans and temporary sorts.
- **Severity:** High
- **Effort:** M
- **Dependencies:** DB-001, PERF-001, PERF-002, PERF-003
- **Expected benefit:** Removes known scaling cliffs before ingestion volume grows.
- **Can be automated:** Yes
- **Recommended next action:** Add measured indexes for Events, Relations in both directions, Queue state/time, Service runs, legacy Engine runs, and Resource locations.

### DB-017 — Add FTS5 search indexing

- **Description:** Substring search applies `lower()` and `instr()` across entire tables and cannot rank results.
- **Severity:** Medium
- **Effort:** M
- **Dependencies:** DB-001, PERF-001
- **Expected benefit:** Enables scalable, ranked full-text search with predictable query latency.
- **Can be automated:** Yes
- **Recommended next action:** Define indexed content/provenance, build FTS5 tables, and test synchronization and ranking.

### DB-018 — Remove ordering from view contracts

- **Description:** Views embed `ORDER BY`, which is not a reliable external ordering contract and can cause unnecessary work.
- **Severity:** Low
- **Effort:** S
- **Dependencies:** DB-001
- **Expected benefit:** Makes callers explicitly control order and improves query planning.
- **Can be automated:** Yes
- **Recommended next action:** Remove view-level ordering and add explicit ordering in repository queries.

### DB-019 — Define SQLite concurrency policy

- **Description:** The database uses DELETE journal mode, one-off connections, no busy timeout, no retry strategy, and no worker concurrency rules.
- **Severity:** High
- **Effort:** M
- **Dependencies:** DB-001, ARC-001
- **Expected benefit:** Prevents lock failures and partial ingestion under concurrent workloads.
- **Can be automated:** Yes
- **Recommended next action:** Evaluate WAL, set busy timeouts, centralize connection settings, and add concurrent write tests.

### DB-020 — Implement missing knowledge-model tables

- **Description:** Attributes, Documents, Tags, Sources, metadata, and metrics described by the architecture do not exist; JSON contains data with no database representation.
- **Severity:** High
- **Effort:** XL
- **Dependencies:** ARC-009, DB-001
- **Expected benefit:** Makes the documented Object model persistable and queryable.
- **Can be automated:** Partially
- **Recommended next action:** Prioritize provenance and attributes first; design each extension from real ingestion use cases rather than creating empty generic tables.

### DB-021 — Extend Relation assertions with provenance

- **Description:** The current uniqueness model cannot represent repeated or independently sourced assertions and has no evidence, confidence, temporal validity, or status.
- **Severity:** High
- **Effort:** L
- **Dependencies:** ARC-010, DB-012, DB-020
- **Expected benefit:** Supports explainable graph construction and conflict resolution.
- **Can be automated:** Partially
- **Recommended next action:** Separate canonical Relations from source assertions/evidence records.

### DB-022 — Deduplicate architecture decisions

- **Description:** Architecture decision rows contain repeated decisions and are weakly constrained.
- **Severity:** Low
- **Effort:** S
- **Dependencies:** DOC-007
- **Expected benefit:** Removes ambiguous governance history.
- **Can be automated:** Partially
- **Recommended next action:** Reconcile duplicate rows and make text ADRs canonical before changing the database representation.

### DB-023 — Repair stale stored file paths

- **Description:** Two run records point to missing `05_OUTPUT/bridge` stdout/stderr files.
- **Severity:** Medium
- **Effort:** S
- **Dependencies:** ARC-011, AUTO-009
- **Expected benefit:** Restores run traceability and detects future artifact loss.
- **Can be automated:** Yes
- **Recommended next action:** Reconcile the missing artifacts or mark them unavailable, then add path-existence checks to health diagnostics.

### DB-024 — Backfill Import Queue coverage

- **Description:** The existing Resource has no Import Queue row, so the queue does not represent all imported files.
- **Severity:** Medium
- **Effort:** S
- **Dependencies:** DB-009, DB-010
- **Expected benefit:** Establishes complete ingestion state before workers and review logic are introduced.
- **Can be automated:** Yes
- **Recommended next action:** Write an idempotent backfill migration after queue identity and transition semantics are finalized.

## Performance

### PERF-001 — Replace scan-based Search

- **Description:** Search scans four tables with non-indexable `lower()`/`instr()` expressions and has no ranking or result limit.
- **Severity:** High
- **Effort:** M
- **Dependencies:** DB-017, CLI-011
- **Expected benefit:** Predictable latency and useful ranking at knowledge-base scale.
- **Can be automated:** Yes
- **Recommended next action:** Benchmark current queries, implement FTS5, and add capped/paginated result contracts.

### PERF-002 — Optimize Event and Relation access paths

- **Description:** Event history scans/sorts all Events; Relation lookup uses an unindexed source-or-target predicate.
- **Severity:** High
- **Effort:** S
- **Dependencies:** DB-016
- **Expected benefit:** Fast Object timelines and graph traversal.
- **Can be automated:** Yes
- **Recommended next action:** Add directional indexes and regression benchmarks for representative graph sizes.

### PERF-003 — Optimize Queue and run-history queries

- **Description:** Pending Queue scans/sorts all rows; Service run merging performs normalization and a correlated `NOT EXISTS` across duplicate tables.
- **Severity:** High
- **Effort:** M
- **Dependencies:** DB-006, DB-010, DB-016
- **Expected benefit:** Efficient workers, operations views, and stable run-history latency.
- **Can be automated:** Yes
- **Recommended next action:** Remove duplicated run tables and index the final queue/run access patterns.

### PERF-004 — Consolidate CLI database sessions

- **Description:** `status` and `doctor` spawn multiple SQLite processes instead of using one connection and consistent read snapshot.
- **Severity:** Medium
- **Effort:** M
- **Dependencies:** ARC-001, CLI-001
- **Expected benefit:** Lower process overhead and internally consistent diagnostics.
- **Can be automated:** Yes
- **Recommended next action:** Move diagnostics into one Python/Core command with a single read transaction.

### PERF-005 — Remove repeated per-command plumbing

- **Description:** Every Python CLI process opens a new connection and repeats argument parsing, formatting, and error handling.
- **Severity:** Medium
- **Effort:** M
- **Dependencies:** MAIN-001, MAIN-002
- **Expected benefit:** Less startup overhead, less code, and consistent behavior.
- **Can be automated:** Partially
- **Recommended next action:** Centralize CLI context, connection management, and renderers in one package.

### PERF-006 — Add batch ingestion and transaction retries

- **Description:** There is no folder batching, worker concurrency model, bulk transaction strategy, or retry policy.
- **Severity:** High
- **Effort:** L
- **Dependencies:** DB-019, AUTO-005, AUTO-006
- **Expected benefit:** Efficient, recoverable ingestion of real document volumes.
- **Can be automated:** Yes
- **Recommended next action:** Define batch size, claim semantics, retryable errors, and throughput tests.

### PERF-007 — Avoid premature application caching

- **Description:** Caching inconsistent state would preserve current source-of-truth defects. Future cache invalidation requirements are undefined.
- **Severity:** Medium
- **Effort:** XS
- **Dependencies:** ARC-005
- **Expected benefit:** Prevents complexity and stale knowledge while the canonical model is unstable.
- **Can be automated:** No
- **Recommended next action:** Record a decision that caching is deferred until authority, Events, and invalidation rules are complete.

### PERF-008 — Add only evidence-based derived caches

- **Description:** Future useful caches—FTS, graph metrics, content-hash metadata, materialized summaries—lack explicit invalidation designs.
- **Severity:** Low
- **Effort:** L
- **Dependencies:** ARC-005, DB-017, AI-006
- **Expected benefit:** Supports scale without sacrificing consistency.
- **Can be automated:** Partially
- **Recommended next action:** Introduce caches individually with source Event/version tracking and rebuild tests.

## Security

### SEC-001 — Remove `shell=True` command execution

- **Description:** Compatibility execution joins command-line arguments and passes them to a shell, creating a direct command-injection path.
- **Severity:** Critical
- **Effort:** M
- **Dependencies:** ARC-008
- **Expected benefit:** Eliminates the most immediate remote/local command execution risk.
- **Can be automated:** Yes
- **Recommended next action:** Accept argument vectors, reject shell metacharacter semantics, and add injection regression tests.

### SEC-002 — Restrict file import roots and types

- **Description:** Import can read and persist metadata for any readable file. There is no allowed-root policy, sensitive-file exclusion, size limit, quarantine, or content validation.
- **Severity:** Critical
- **Effort:** L
- **Dependencies:** DB-012, AUTO-005
- **Expected benefit:** Prevents secret ingestion, denial-of-service files, and uncontrolled data capture.
- **Can be automated:** Yes
- **Recommended next action:** Define approved roots, exclusions, size/MIME rules, quarantine, and explicit override behavior.

### SEC-003 — Harden import against source replacement

- **Description:** Import resolves, stats, reads, and stats paths separately, leaving a time-of-check/time-of-use window.
- **Severity:** Medium
- **Effort:** M
- **Dependencies:** SEC-002
- **Expected benefit:** Ensures recorded metadata and hash refer to the same file content.
- **Can be automated:** Yes
- **Recommended next action:** Open once, inspect through the file descriptor, and verify identity before commit.

### SEC-004 — Remove sensitive runtime data from Git

- **Description:** The live database, personal paths, logs, reports, state, inventories, snapshots, and `.DS_Store` are tracked in permanent history.
- **Severity:** High
- **Effort:** L
- **Dependencies:** ARC-011, DOC-001
- **Expected benefit:** Reduces privacy exposure and separates source history from operational data.
- **Can be automated:** Partially
- **Recommended next action:** Define a data classification/Git policy, stop new tracking, then decide whether history rewriting is justified.

### SEC-005 — Restrict database and snapshot permissions

- **Description:** The live database and SQL snapshot are mode `0644`, exposing knowledge metadata to other local users.
- **Severity:** High
- **Effort:** S
- **Dependencies:** AUTO-010
- **Expected benefit:** Protects local confidentiality.
- **Can be automated:** Yes
- **Recommended next action:** Create data with restrictive umask/modes and add permission checks to strict diagnostics.

### SEC-006 — Add authorization for Core mutations

- **Description:** Any process running as the user can mutate SQLite directly; no authorization or capability boundary exists.
- **Severity:** High
- **Effort:** XL
- **Dependencies:** ARC-001, ARC-002
- **Expected benefit:** Limits accidental and malicious changes as automation expands.
- **Can be automated:** Partially
- **Recommended next action:** Start with process/API boundaries and least-privilege filesystem permissions before designing multi-user auth.

### SEC-007 — Control legacy process execution

- **Description:** External commands have no timeout, cancellation, process-tree control, environment isolation, or output-size limit.
- **Severity:** High
- **Effort:** M
- **Dependencies:** SEC-001, ARC-003
- **Expected benefit:** Prevents hangs, runaway children, environment leakage, and disk exhaustion.
- **Can be automated:** Yes
- **Recommended next action:** Add explicit timeout, process group termination, clean environment, resource limits, and bounded capture.

### SEC-008 — Escape terminal and machine output

- **Description:** Filenames, descriptions, and other stored values can contain pipes, newlines, or terminal control characters that corrupt output or manipulate terminals.
- **Severity:** Medium
- **Effort:** M
- **Dependencies:** UX-001, CLI-003
- **Expected benefit:** Safe human display and reliable machine parsing.
- **Can be automated:** Yes
- **Recommended next action:** Implement structured JSON and a sanitizing text renderer with adversarial fixtures.

### SEC-009 — Protect snapshots and inventories

- **Description:** Snapshots are unencrypted; inventories expose Dropbox, LaunchAgent, contact, deal, and runtime metadata; command strings and absolute paths are logged.
- **Severity:** High
- **Effort:** L
- **Dependencies:** SEC-004, AUTO-010
- **Expected benefit:** Reduces leakage from backups, reports, and operational records.
- **Can be automated:** Partially
- **Recommended next action:** Classify fields, redact where possible, encrypt protected backups, and define retention/access controls.

### SEC-010 — Add security tooling and policy

- **Description:** No secrets scanning, dependency scanning, static analysis, audit-log protection, Plugin capability policy, or security release gate exists.
- **Severity:** High
- **Effort:** L
- **Dependencies:** AUTO-001, ARC-007
- **Expected benefit:** Detects regressions before deployment and constrains extensions.
- **Can be automated:** Yes
- **Recommended next action:** Add lightweight secret/static/dependency scans first, then define signed/validated Plugin capabilities.

### SEC-011 — Define destructive-operation safeguards

- **Description:** Current commands are mostly non-destructive, but there is no confirmation, authorization, dry-run, or recovery framework for future archive/delete/restore operations.
- **Severity:** Medium
- **Effort:** M
- **Dependencies:** CLI-003, AUTO-010
- **Expected benefit:** Prevents irreversible operator mistakes as write commands expand.
- **Can be automated:** Partially
- **Recommended next action:** Define command risk levels and require dry-run/explicit confirmation for destructive actions.

### SEC-012 — Enforce audit-log integrity

- **Description:** Events and logs can be edited or deleted, and no checksum, signature, chain, or restricted write path protects audit evidence.
- **Severity:** High
- **Effort:** L
- **Dependencies:** DB-004, ARC-002
- **Expected benefit:** Makes traceability credible rather than advisory.
- **Can be automated:** Partially
- **Recommended next action:** Enforce append-only Events first, then evaluate hash chaining or signed release snapshots based on threat model.

## Maintainability

### MAIN-001 — Create one Python application package

- **Description:** Configuration, connections, repositories, formatting, errors, and command behavior are spread across standalone scripts.
- **Severity:** High
- **Effort:** L
- **Dependencies:** ARC-001
- **Expected benefit:** Provides a testable, reusable foundation and reduces per-feature duplication.
- **Can be automated:** Partially
- **Recommended next action:** Establish package structure and migrate one vertical command without changing its contract.

### MAIN-002 — Replace the monolithic Bash dispatcher

- **Description:** The 451-line CLI requires manual case/help edits, has no strict mode, and contradicts the intended discoverable Service architecture.
- **Severity:** High
- **Effort:** L
- **Dependencies:** MAIN-001, ARC-003
- **Expected benefit:** Enables declarative commands, shared validation, generated help, and consistent errors.
- **Can be automated:** Partially
- **Recommended next action:** Choose a Python CLI framework or small internal registry and port commands incrementally.

### MAIN-003 — Merge Event and Timeline implementations

- **Description:** `event_service.py` and `timeline_service.py` duplicate queries and rendering; Timeline should be a view/presentation over Events.
- **Severity:** Medium
- **Effort:** S
- **Dependencies:** DB-005, MAIN-001
- **Expected benefit:** Removes duplicated code and clarifies semantics.
- **Can be automated:** Yes
- **Recommended next action:** Create one Event repository and expose Timeline as an alias/presentation layer.

### MAIN-004 — Centralize query-service boilerplate

- **Description:** Every service repeats the DB path, connection function, row formatting, argument parsing, and error behavior.
- **Severity:** Medium
- **Effort:** M
- **Dependencies:** MAIN-001
- **Expected benefit:** Reduces defects and makes output/error behavior uniform.
- **Can be automated:** Partially
- **Recommended next action:** Extract configuration, repository base, renderer, and typed exception utilities.

### MAIN-005 — Retire duplicate Plugin implementations

- **Description:** `plugin_manager.py` and `plugin_service.py` overlap; the former is no longer wired to the CLI.
- **Severity:** Low
- **Effort:** S
- **Dependencies:** ARC-007, MAIN-001
- **Expected benefit:** Removes ambiguity over the canonical Plugin interface.
- **Can be automated:** Yes
- **Recommended next action:** Preserve required behavior in the canonical implementation, test it, then deprecate the unused file.

### MAIN-006 — Resolve overlapping Queue CLIs

- **Description:** `gmv import queue/pending` and `gmv queue list/pending` expose the same data with different columns and implementations.
- **Severity:** Medium
- **Effort:** S
- **Dependencies:** DB-010, UX-001
- **Expected benefit:** Establishes one public Queue contract.
- **Can be automated:** Yes
- **Recommended next action:** Select canonical commands, add compatibility aliases if necessary, and document deprecation.

### MAIN-007 — Remove or adopt `BaseService`

- **Description:** `BaseService` has no consumers and already defines output semantics inconsistent with active Services.
- **Severity:** Low
- **Effort:** XS
- **Dependencies:** MAIN-001
- **Expected benefit:** Eliminates dead abstraction or turns it into a deliberate shared component.
- **Can be automated:** Yes
- **Recommended next action:** Do not migrate code into it blindly; replace it with the new canonical infrastructure or remove it after tests.

### MAIN-008 — Remove unused imports and obsolete dependencies

- **Description:** Runtime scripts have unused imports, while deprecated tables and paths remain active dependencies.
- **Severity:** Low
- **Effort:** S
- **Dependencies:** DB-005, DB-006
- **Expected benefit:** Reduces noise and makes real dependencies visible.
- **Can be automated:** Yes
- **Recommended next action:** Add linting, remove unused imports, and track deprecated dependencies to zero.

### MAIN-009 — Refactor top-level and multi-responsibility code

- **Description:** Knowledge Engine executes at import time; `import_file()` mixes validation, hashing, identity, persistence, queue changes, Events, and presentation.
- **Severity:** High
- **Effort:** M
- **Dependencies:** MAIN-001, ARC-002
- **Expected benefit:** Enables unit testing, reuse, transaction clarity, and safer failure handling.
- **Can be automated:** Partially
- **Recommended next action:** Separate pure domain operations, repositories, orchestration, and CLI presentation.

### MAIN-010 — Stop tracking mutable artifacts as source

- **Description:** Database, logs, reports, compatibility outputs, inventories, and snapshots create noisy diffs and couple runtime mutation to Git state.
- **Severity:** High
- **Effort:** M
- **Dependencies:** ARC-011, SEC-004
- **Expected benefit:** Produces clean working trees and meaningful code reviews.
- **Can be automated:** Yes
- **Recommended next action:** Define ignored runtime roots and retain only sanitized fixtures/release artifacts.

### MAIN-011 — Reconcile JSON and SQLite state identities

- **Description:** `OBJECT-0000001` and `PER-000001` identify the same person, and JSON contains state with no synchronization or database equivalent.
- **Severity:** Critical
- **Effort:** L
- **Dependencies:** ARC-004, ARC-005, DB-020
- **Expected benefit:** Restores permanent identity and one authoritative state model.
- **Can be automated:** Partially
- **Recommended next action:** Freeze new JSON writes, map identities, migrate authoritative fields, and remove or clearly demote derived files.

### MAIN-012 — Standardize naming, status, timestamp, and error conventions

- **Description:** Names overlap across Engine/Service concepts; statuses vary in case/meaning; timestamps vary; errors use inconsistent streams and formats.
- **Severity:** Medium
- **Effort:** M
- **Dependencies:** DB-015, UX-001, ARC-006
- **Expected benefit:** Makes behavior predictable for maintainers and automation.
- **Can be automated:** Yes
- **Recommended next action:** Publish conventions and enforce them through schemas, renderers, lint checks, and contract tests.

### MAIN-013 — Add packaging and dependency metadata

- **Description:** There is no project package definition, dependency lock, supported Python/SQLite declaration, installation process, or build contract.
- **Severity:** High
- **Effort:** M
- **Dependencies:** MAIN-001
- **Expected benefit:** Makes environments reproducible and dependencies auditable.
- **Can be automated:** Yes
- **Recommended next action:** Add a minimal `pyproject.toml`, supported runtime versions, console entrypoint, and locked development tools.

### MAIN-014 — Replace fragile Service-run deduplication

- **Description:** `service_service.list_runs()` deduplicates by normalized display name and exact timestamp, which is not a stable identity relationship.
- **Severity:** High
- **Effort:** S
- **Dependencies:** DB-006
- **Expected benefit:** Prevents missing or duplicated operational history.
- **Can be automated:** Yes
- **Recommended next action:** Remove the merge logic after canonical run migration; use Service OIDs throughout.

## Documentation

### DOC-001 — Mark implementation status in normative documents

- **Description:** Documentation presents planned architecture as implemented fact, creating a widening gap between specifications and code.
- **Severity:** High
- **Effort:** M
- **Dependencies:** ROAD-001
- **Expected benefit:** Lets maintainers distinguish contract, target, partial implementation, and deprecation.
- **Can be automated:** Partially
- **Recommended next action:** Add implemented/partial/planned/deprecated matrices and owners to each foundational document.

### DOC-002 — Correct Backlog completion claims

- **Description:** Core, Knowledge Engine, Import Service, and Queue are marked DONE although the Core API is absent, Knowledge Engine is bootstrap code, and ingestion automation is empty.
- **Severity:** High
- **Effort:** S
- **Dependencies:** ROAD-001
- **Expected benefit:** Prevents prioritization based on false completion.
- **Can be automated:** No
- **Recommended next action:** Reopen incomplete components with explicit acceptance criteria tied to tests and architecture invariants.

### DOC-003 — Reconcile Sprint and Changelog status

- **Description:** Sprint 002 has an empty Completed section while the Changelog declares a Sprint 002 milestone.
- **Severity:** Medium
- **Effort:** XS
- **Dependencies:** ROAD-001
- **Expected benefit:** Restores trustworthy governance history.
- **Can be automated:** Partially
- **Recommended next action:** Define milestone versus sprint completion and update both documents from one reviewed status source.

### DOC-004 — Correct the automated-validation claim

- **Description:** The Changelog claims an automated validation workflow, but no test suite, CI, or reproducible fixture exists.
- **Severity:** High
- **Effort:** XS
- **Dependencies:** AUTO-001
- **Expected benefit:** Prevents unsupported assurance claims.
- **Can be automated:** Partially
- **Recommended next action:** Mark current validation as manual until CI and tests satisfy a documented gate.

### DOC-005 — Correct Event-traceability claims

- **Description:** Architecture says every action creates an Event, yet no Events record the feature/documentation work after 2026-07-03.
- **Severity:** High
- **Effort:** S
- **Dependencies:** DB-004, AUTO-004
- **Expected benefit:** Aligns the traceability promise with actual system behavior.
- **Can be automated:** Partially
- **Recommended next action:** Define which actions require Events and only claim coverage after write paths enforce it.

### DOC-006 — Correct universal-OID claims

- **Description:** Architecture says everything has an OID, but Engines, runs, decisions, Queue rows, and JSON state do not follow one universal identity rule.
- **Severity:** High
- **Effort:** S
- **Dependencies:** ARC-009
- **Expected benefit:** Removes ambiguity over entity versus subordinate-record identity.
- **Can be automated:** Partially
- **Recommended next action:** Document the precise identity boundary and update the model after implementation decisions.

### DOC-007 — Make text ADRs canonical

- **Description:** Architecture decisions live in a weakly constrained database table with duplicates instead of reviewable version-controlled ADRs.
- **Severity:** Medium
- **Effort:** M
- **Dependencies:** DB-022
- **Expected benefit:** Preserves rationale with normal code review and immutable Git history.
- **Can be automated:** Partially
- **Recommended next action:** Create an ADR directory/template, migrate unique decisions, and link database Events to ADR identifiers if needed.

### DOC-008 — Align Snapshot specification and implementation

- **Description:** Versioning defines a snapshot as code, documentation, configuration, and database; the CLI creates only a SQLite dump.
- **Severity:** High
- **Effort:** S
- **Dependencies:** AUTO-010
- **Expected benefit:** Prevents operators from assuming incomplete backups are full-system snapshots.
- **Can be automated:** Partially
- **Recommended next action:** Rename the current operation “database dump” or implement the documented full manifest.

### DOC-009 — Document deprecation and compatibility exits

- **Description:** Deprecated `engines`, `engine_runs`, and `timeline` remain active without removal criteria or dates.
- **Severity:** Medium
- **Effort:** S
- **Dependencies:** DB-005, DB-006, ARC-008
- **Expected benefit:** Prevents temporary compatibility structures from becoming permanent architecture.
- **Can be automated:** Partially
- **Recommended next action:** Add owners, migration steps, usage counters, and exit acceptance criteria.

### DOC-010 — Add operational and data-governance documentation

- **Description:** Privacy, retention, source licensing, provenance, recovery objectives, runbooks, failure budgets, and compatibility guarantees are missing.
- **Severity:** High
- **Effort:** L
- **Dependencies:** SEC-004, AUTO-009, AUTO-010
- **Expected benefit:** Makes operation and stewardship reviewable rather than implicit.
- **Can be automated:** No
- **Recommended next action:** Prioritize data classification, backup/recovery objectives, and incident/runbook documentation.

## Automation

### AUTO-001 — Establish an automated test suite and CI gate

- **Description:** There are zero test files, no test runner configuration, no CI, and no reproducible fixture. “Tests pass” means manual command execution.
- **Severity:** Critical
- **Effort:** L
- **Dependencies:** MAIN-013
- **Expected benefit:** Replaces subjective confidence with repeatable release evidence.
- **Can be automated:** Yes
- **Recommended next action:** Add a test runner, isolated database fixture, and CI checks for lint, schema, unit, integration, and CLI contracts.

### AUTO-002 — Add migration and rollback tests

- **Description:** Schema evolution and rollback are neither implemented nor verified.
- **Severity:** Critical
- **Effort:** M
- **Dependencies:** DB-001, AUTO-001
- **Expected benefit:** Prevents production data loss during Core changes.
- **Can be automated:** Yes
- **Recommended next action:** Test empty install, current-schema upgrade, repeated migration, rollback where supported, and snapshot restore before upgrade.

### AUTO-003 — Add Event/Timeline reconciliation tests

- **Description:** No regression test detects writers to legacy Timeline or divergence from Events.
- **Severity:** High
- **Effort:** S
- **Dependencies:** DB-005, AUTO-001
- **Expected benefit:** Guarantees one history during migration.
- **Can be automated:** Yes
- **Recommended next action:** Add fixtures for all legacy/current records and fail CI on direct Timeline writes.

### AUTO-004 — Automate canonical Event emission

- **Description:** Writes do not consistently create Events with actor, correlation ID, source, schema version, and payload.
- **Severity:** Critical
- **Effort:** L
- **Dependencies:** ARC-002, DB-004
- **Expected benefit:** Creates reliable audit, reconstruction, and downstream automation.
- **Can be automated:** Yes
- **Recommended next action:** Make Event append part of the Core transaction API rather than an optional caller action.

### AUTO-005 — Implement Watch Folder and bulk ingestion

- **Description:** No Engine watches import roots or supports folder/batch ingestion, dry-run, quarantine, or controlled archive destinations.
- **Severity:** High
- **Effort:** L
- **Dependencies:** SEC-002, DB-010, DB-012
- **Expected benefit:** Delivers the Sprint goal of autonomous ingestion safely.
- **Can be automated:** Yes
- **Recommended next action:** Build a polling V0 against one approved root after queue/state/custody contracts are stable.

### AUTO-006 — Implement a Queue worker

- **Description:** No worker claims rows, retries failures, records attempts, or advances legal Queue transitions.
- **Severity:** High
- **Effort:** L
- **Dependencies:** DB-010, DB-011, DB-019
- **Expected benefit:** Turns Import Queue storage into an operational pipeline.
- **Can be automated:** Yes
- **Recommended next action:** Implement one idempotent single-worker loop, then add lease/recovery and concurrency tests.

### AUTO-007 — Implement Review and Archive automation

- **Description:** Approve, reject, assign, retry, archive, and custody transitions are missing from Services and CLI.
- **Severity:** High
- **Effort:** L
- **Dependencies:** AUTO-006, DB-012, CLI-010
- **Expected benefit:** Completes the human-in-the-loop ingestion lifecycle without losing documents.
- **Can be automated:** Partially
- **Recommended next action:** Specify review outcomes and archive side effects before adding commands.

### AUTO-008 — Implement scheduler orchestration

- **Description:** No Core scheduler coordinates Services; current execution relies on external LaunchAgents and wrappers.
- **Severity:** High
- **Effort:** XL
- **Dependencies:** ARC-003, ARC-008, SEC-007
- **Expected benefit:** Centralizes schedules, retries, dependencies, ownership, and run history.
- **Can be automated:** Yes
- **Recommended next action:** Start with registry-backed schedules and manual triggering; avoid replacing stable LaunchAgents until parity is tested.

### AUTO-009 — Add observability and runbooks

- **Description:** There is no structured logging, correlation, metrics, alerting, error record model, failure budget, or recovery runbook; Knowledge Engine overwrites its log.
- **Severity:** High
- **Effort:** L
- **Dependencies:** ARC-003, AUTO-004
- **Expected benefit:** Makes failures diagnosable and recoverable.
- **Can be automated:** Partially
- **Recommended next action:** Define structured run/event IDs, append-only logs, error taxonomy, and alerts for failed/stale Services and missing artifacts.

### AUTO-010 — Build verified full-system backup and restore

- **Description:** Dumps lack manifests, checksums, atomic creation, retention, compression, encryption options, restore commands/tests, and external Resource verification; the only committed dump predates Import Queue.
- **Severity:** Critical
- **Effort:** L
- **Dependencies:** DB-001, DB-012, SEC-005, SEC-009
- **Expected benefit:** Provides credible disaster recovery and long-term preservation.
- **Can be automated:** Yes
- **Recommended next action:** Define RPO/RTO and manifest scope, then automate atomic backup, checksum, isolated restore, integrity check, and retention.

### AUTO-011 — Make health checks strict and schedulable

- **Description:** Health commands can succeed after failed checks and do not cover schema version, all orphan classes, duplicate histories, snapshot freshness, path validity, or permissions.
- **Severity:** Critical
- **Effort:** M
- **Dependencies:** CLI-001, DB-002, AUTO-010
- **Expected benefit:** Enables reliable monitoring and deployment gates.
- **Can be automated:** Yes
- **Recommended next action:** Return aggregated structured failures and nonzero status; add a strict mode to CI and scheduled monitoring.

### AUTO-012 — Add static, dependency, and secrets checks

- **Description:** No linting, static analysis, dependency audit, or secrets scan exists; unused imports and dangerous shell use are undetected automatically.
- **Severity:** High
- **Effort:** S
- **Dependencies:** AUTO-001, MAIN-013
- **Expected benefit:** Catches common defects and security regressions cheaply.
- **Can be automated:** Yes
- **Recommended next action:** Add minimal pinned tools and run them in CI with scoped suppressions.

## AI

### AI-001 — Reclassify the current Knowledge Engine

- **Description:** The “Knowledge Engine” is schema/bootstrap code that inserts fixed records and reports; it performs no knowledge acquisition or reasoning.
- **Severity:** High
- **Effort:** S
- **Dependencies:** DB-001, DOC-002
- **Expected benefit:** Removes misleading maturity claims and separates bootstrap from intelligence work.
- **Can be automated:** Partially
- **Recommended next action:** Move initialization into migrations/seeds and rename the remaining health/report behavior.

### AI-002 — Implement document/OCR extraction

- **Description:** No current Engine extracts text from scanned or native documents; OCR Agent remains missing.
- **Severity:** High
- **Effort:** XL
- **Dependencies:** DB-012, AUTO-005, SEC-002
- **Expected benefit:** Converts managed documents into processable evidence.
- **Can be automated:** Yes
- **Recommended next action:** Define supported formats, provenance-preserving text artifacts, quality metrics, and a manual-review fallback.

### AI-003 — Implement entity extraction

- **Description:** No Engine identifies candidate Objects, types, attributes, or mentions from Resources.
- **Severity:** High
- **Effort:** XL
- **Dependencies:** AI-002, DB-020, AUTO-004
- **Expected benefit:** Builds structured knowledge from imported content.
- **Can be automated:** Partially
- **Recommended next action:** Start with one domain/schema and persist candidates separately from approved Objects.

### AI-004 — Implement entity resolution and merge/split policy

- **Description:** No capability reconciles extracted mentions with existing Objects or governs duplicates, merges, splits, aliases, and identity corrections.
- **Severity:** Critical
- **Effort:** XL
- **Dependencies:** ARC-004, AI-003, DB-021
- **Expected benefit:** Prevents graph fragmentation and permanent identity corruption.
- **Can be automated:** Partially
- **Recommended next action:** Define candidate matching, confidence thresholds, human review, reversible merge Events, and golden evaluation cases.

### AI-005 — Implement relation extraction with evidence

- **Description:** No Engine proposes Relations from Resources, and the current Relation schema cannot preserve assertion evidence or independent sources.
- **Severity:** High
- **Effort:** XL
- **Dependencies:** AI-003, AI-004, DB-021
- **Expected benefit:** Expands the graph while retaining explainability.
- **Can be automated:** Partially
- **Recommended next action:** Complete the assertion/evidence model before training or prompting extraction.

### AI-006 — Implement graph quality and reconciliation

- **Description:** No Engine measures completeness, contradiction, confidence, provenance coverage, stale facts, or graph consistency.
- **Severity:** High
- **Effort:** L
- **Dependencies:** AI-004, AI-005, DB-021
- **Expected benefit:** Prevents automated ingestion from degrading knowledge quality.
- **Can be automated:** Partially
- **Recommended next action:** Define quality rules and dashboards using approved domain fixtures.

### AI-007 — Implement reasoning only after Core integrity

- **Description:** No Reasoning Engine exists, and reasoning over divergent identity/history/state would produce untraceable conclusions.
- **Severity:** High
- **Effort:** XL
- **Dependencies:** ARC-005, AUTO-004, AI-006
- **Expected benefit:** Enables defensible inference grounded in canonical facts and evidence.
- **Can be automated:** Partially
- **Recommended next action:** Block reasoning development until identity, Events, provenance, and quality gates pass.

### AI-008 — Implement Decision support with explanations

- **Description:** No Decision Engine, recommendation model, explanation record, approval workflow, or outcome feedback exists.
- **Severity:** Medium
- **Effort:** XL
- **Dependencies:** AI-007, AUTO-007
- **Expected benefit:** Advances Product Vision from storage to actionable, auditable recommendations.
- **Can be automated:** Partially
- **Recommended next action:** Define a narrow decision use case with explicit inputs, alternatives, rationale, approval, and outcome Event.

### AI-009 — Add model and prompt governance

- **Description:** There is no model evaluation, prompt/model versioning, confidence calibration, reproducibility record, or rollback policy.
- **Severity:** High
- **Effort:** L
- **Dependencies:** AUTO-009, AI-003
- **Expected benefit:** Makes AI outputs comparable, reproducible, and safe to evolve.
- **Can be automated:** Yes
- **Recommended next action:** Persist model/prompt/version parameters on every AI run and establish golden evaluation datasets.

### AI-010 — Add human review and confidence policy

- **Description:** No calibrated threshold or human-review protocol governs extracted entities, Relations, OCR quality, reasoning, or decisions.
- **Severity:** Critical
- **Effort:** L
- **Dependencies:** AUTO-007, AI-003, AI-005, AI-009
- **Expected benefit:** Prevents low-confidence automation from becoming accepted knowledge.
- **Can be automated:** Partially
- **Recommended next action:** Define candidate/approved/rejected states, threshold policy, reviewer evidence, and feedback capture.

### AI-011 — Define continuous-learning controls

- **Description:** Continuous learning is a Product objective but no feedback dataset, evaluation gate, drift monitoring, or safe promotion process exists.
- **Severity:** Medium
- **Effort:** XL
- **Dependencies:** AI-009, AI-010, AUTO-009
- **Expected benefit:** Enables improvement without silently changing system truth or behavior.
- **Can be automated:** Partially
- **Recommended next action:** Treat feedback as versioned evidence and require offline evaluation before any model/prompt promotion.

### AI-012 — Implement Research Agent only on governed sources

- **Description:** Research Agent is listed but no source policy, citation model, freshness tracking, licensing, or ingestion boundary exists.
- **Severity:** Medium
- **Effort:** XL
- **Dependencies:** DB-020, DB-021, AI-009, SEC-009
- **Expected benefit:** Adds externally sourced knowledge without losing provenance or legal context.
- **Can be automated:** Partially
- **Recommended next action:** Define source/citation/licensing records and one constrained research workflow before general web automation.

## UX

### UX-001 — Define one output contract

- **Description:** List commands emit raw pipes, show commands emit labels, empty results vary, and `BaseService` defines another behavior.
- **Severity:** High
- **Effort:** M
- **Dependencies:** MAIN-004
- **Expected benefit:** Makes every command predictable for humans and scripts.
- **Can be automated:** Yes
- **Recommended next action:** Specify text/table/JSON schemas and enforce them with snapshot contract tests.

### UX-002 — Add headers and schema discovery

- **Description:** Pipe output has no headers or declared column schema.
- **Severity:** Medium
- **Effort:** S
- **Dependencies:** UX-001
- **Expected benefit:** Makes output understandable without reading source.
- **Can be automated:** Yes
- **Recommended next action:** Add optional/default headers for humans and stable field names in JSON.

### UX-003 — Define empty-result behavior

- **Description:** Empty queries usually print nothing, making “no data” indistinguishable from suppressed or failed output.
- **Severity:** Medium
- **Effort:** XS
- **Dependencies:** UX-001
- **Expected benefit:** Removes operator ambiguity.
- **Can be automated:** Yes
- **Recommended next action:** Define explicit human messages and empty JSON arrays while retaining successful exit status.

### UX-004 — Standardize error presentation

- **Description:** Errors generally go to stdout, usage differs, and no stable machine-readable error envelope or recovery hint exists.
- **Severity:** High
- **Effort:** M
- **Dependencies:** UX-001, CLI-003
- **Expected benefit:** Improves diagnosis and automation reliability.
- **Can be automated:** Yes
- **Recommended next action:** Define error codes, stderr behavior, JSON errors, and consistent recovery guidance.

### UX-005 — Add pagination and explicit limits

- **Description:** Lists and Search have no configurable limit/offset; Event latest silently hard-codes ten rows.
- **Severity:** Medium
- **Effort:** M
- **Dependencies:** DB-016, PERF-001
- **Expected benefit:** Prevents unbounded output and makes large datasets navigable.
- **Can be automated:** Yes
- **Recommended next action:** Add global `--limit`, cursor/offset semantics, and returned-count metadata.

### UX-006 — Make help complete and generated

- **Description:** No standard help/version behavior exists; duplicated help is inconsistent and Object/Relation help includes unrelated Import commands.
- **Severity:** Medium
- **Effort:** M
- **Dependencies:** MAIN-002
- **Expected benefit:** Reduces user error and documentation drift.
- **Can be automated:** Yes
- **Recommended next action:** Generate top-level and subcommand help from command definitions and test it.

### UX-007 — Clarify ambiguous command semantics

- **Description:** Resource count groups by status instead of clearly returning a total; Relation show fails for valid Objects with no Relations; Event versus Timeline and Import Queue versus Queue distinctions are unclear.
- **Severity:** Medium
- **Effort:** S
- **Dependencies:** MAIN-003, MAIN-006, UX-001
- **Expected benefit:** Makes command names match user expectations.
- **Can be automated:** Partially
- **Recommended next action:** Publish exact command contracts and compatibility behavior before changing outputs.

### UX-008 — Remove blank Plugin service rows

- **Description:** Plugin Services emits a blank mapping for Area35 because the view uses a left join.
- **Severity:** Low
- **Effort:** XS
- **Dependencies:** ARC-007
- **Expected benefit:** Avoids presenting absence as a malformed service record.
- **Can be automated:** Yes
- **Recommended next action:** Filter mappings by default and expose unlinked Plugins through a separate status/validation field.

## CLI

### CLI-001 — Make `gmv doctor` truthful and strict

- **Description:** Doctor continues after failed SQLite commands, checks only two orphan classes, and always prints completion; it misses Relations, Resources, Plugins, Queue, Timeline divergence, snapshot freshness, paths, permissions, and schema version.
- **Severity:** Critical
- **Effort:** M
- **Dependencies:** AUTO-011, ARC-001
- **Expected benefit:** Produces a reliable operational and CI gate.
- **Can be automated:** Yes
- **Recommended next action:** Implement a single diagnostic runner that aggregates named checks and exits nonzero on any failure.

### CLI-002 — Make `gmv status` evidence-based

- **Description:** Status directly queries SQLite, invokes `launchctl`, ignores query failures, and unconditionally prints `SYSTEM READY` without queue, snapshot, path, or Service freshness checks.
- **Severity:** Critical
- **Effort:** M
- **Dependencies:** CLI-001, AUTO-009
- **Expected benefit:** Prevents false readiness and supports monitoring.
- **Can be automated:** Yes
- **Recommended next action:** Define readiness criteria and compute them through the Core with structured degraded/failure states.

### CLI-003 — Add global validation and error semantics

- **Description:** OIDs, numeric IDs, statuses, paths, and slugs are not validated; exit codes and stdout/stderr behavior are inconsistent.
- **Severity:** High
- **Effort:** M
- **Dependencies:** MAIN-002, UX-004, ARC-004
- **Expected benefit:** Rejects bad input early and makes automation dependable.
- **Can be automated:** Yes
- **Recommended next action:** Implement typed argument validators and a shared error/exit-code taxonomy.

### CLI-004 — Add JSON output

- **Description:** The CLI specification requires text and JSON, but every command is text-only.
- **Severity:** High
- **Effort:** M
- **Dependencies:** UX-001, MAIN-002
- **Expected benefit:** Provides a stable machine interface and removes delimiter ambiguity.
- **Can be automated:** Yes
- **Recommended next action:** Add global `--json` with versioned field schemas and contract tests.

### CLI-005 — Add help and version commands

- **Description:** `gmv help`, `gmv version`, and standard `--help` behavior are missing.
- **Severity:** Medium
- **Effort:** S
- **Dependencies:** MAIN-002, UX-006
- **Expected benefit:** Improves discoverability and release diagnostics.
- **Can be automated:** Yes
- **Recommended next action:** Generate help from the command registry and source version from one canonical release file.

### CLI-006 — Complete Object commands

- **Description:** Object CLI lacks create, update, archive, filters, pagination, JSON, and aggregated Timeline/Relation inspection.
- **Severity:** High
- **Effort:** L
- **Dependencies:** ARC-001, ARC-004, CLI-003, CLI-004
- **Expected benefit:** Makes Objects operable through the official boundary.
- **Can be automated:** Partially
- **Recommended next action:** Implement create and archive through Core transactions before general update/search features.

### CLI-007 — Complete Resource commands

- **Description:** Resource CLI lacks total-count clarity, path/hash verification, locations, missing-file state, provenance, and archive/custody operations.
- **Severity:** High
- **Effort:** L
- **Dependencies:** DB-012, AUTO-007
- **Expected benefit:** Makes Resource preservation observable and actionable.
- **Can be automated:** Yes
- **Recommended next action:** Add verify and locations first, then archive after custody semantics are defined.

### CLI-008 — Complete Relation commands

- **Description:** Relation CLI lacks create/remove, incoming/outgoing filters, evidence, and relation-type validation.
- **Severity:** High
- **Effort:** L
- **Dependencies:** ARC-010, DB-021, CLI-003
- **Expected benefit:** Enables controlled graph maintenance and inspection.
- **Can be automated:** Partially
- **Recommended next action:** Implement evidence-backed create and compensating remove/archive Events.

### CLI-009 — Consolidate Event and Timeline commands

- **Description:** Event and Timeline are duplicate surfaces; Event lacks ID/time/type/actor/source filters and uses an unconfigurable latest limit.
- **Severity:** Medium
- **Effort:** M
- **Dependencies:** DB-005, MAIN-003, UX-005
- **Expected benefit:** Provides one coherent historical interface.
- **Can be automated:** Yes
- **Recommended next action:** Make Timeline a documented Event query view and add filters/pagination to the canonical command.

### CLI-010 — Complete Import and Review commands

- **Description:** Import lacks folder/watch/review, allowlists, dry-run, retry/error visibility, concurrency safety, quarantine, and archive destination controls.
- **Severity:** High
- **Effort:** XL
- **Dependencies:** AUTO-005, AUTO-006, AUTO-007, SEC-002
- **Expected benefit:** Delivers a complete safe ingestion workflow.
- **Can be automated:** Partially
- **Recommended next action:** Add `import folder --dry-run` only after Queue and custody contracts are implemented.

### CLI-011 — Complete Search commands

- **Description:** Search lacks limits, ranking, pagination, field filters, OID search, FTS, and safe escaping of pipes/newlines.
- **Severity:** High
- **Effort:** L
- **Dependencies:** DB-017, PERF-001, SEC-008
- **Expected benefit:** Produces scalable and reliable knowledge retrieval.
- **Can be automated:** Yes
- **Recommended next action:** Define result schema/ranking and migrate to FTS5 with field filters.

### CLI-012 — Complete Queue commands

- **Description:** Queue CLI is read-only and lacks approve, reject, retry, assign, claim, archive, and transition-history operations.
- **Severity:** High
- **Effort:** L
- **Dependencies:** DB-010, DB-011, AUTO-007
- **Expected benefit:** Enables human and automated queue operations.
- **Can be automated:** Partially
- **Recommended next action:** Add show-history and approve/reject after legal transitions and Event semantics are finalized.

### CLI-013 — Complete Snapshot commands

- **Description:** Snapshot CLI lacks verify, restore, inspect, prune, checksum, manifest, and full-system operations.
- **Severity:** High
- **Effort:** L
- **Dependencies:** AUTO-010, DOC-008
- **Expected benefit:** Makes recovery operable rather than theoretical.
- **Can be automated:** Yes
- **Recommended next action:** Add verify and isolated restore commands before prune or retention automation.

### CLI-014 — Complete Service commands

- **Description:** Service CLI lacks run, status, info, enable, disable, and contract display; run history is based on fragile duplicate-table reconciliation.
- **Severity:** High
- **Effort:** L
- **Dependencies:** ARC-003, DB-006, MAIN-014
- **Expected benefit:** Makes Service lifecycle controllable through the official CLI.
- **Can be automated:** Yes
- **Recommended next action:** Implement info/status from canonical manifests, then run after execution isolation is complete.

### CLI-015 — Complete Plugin commands

- **Description:** Plugin CLI lacks validate, install, enable, disable, path, manifest, dependency, and capability operations.
- **Severity:** High
- **Effort:** XL
- **Dependencies:** ARC-007, SEC-010
- **Expected benefit:** Enables safe extension lifecycle management.
- **Can be automated:** Partially
- **Recommended next action:** Implement manifest validation before installation or execution commands.

### CLI-016 — Add strict shell/dependency behavior during transition

- **Description:** The Bash CLI lacks `set -euo pipefail` and dependency checks, allowing failures to be ignored.
- **Severity:** High
- **Effort:** S
- **Dependencies:** CLI-001, MAIN-002
- **Expected benefit:** Reduces false success before the Bash dispatcher is replaced.
- **Can be automated:** Yes
- **Recommended next action:** Add guarded strict mode, explicit optional-command handling, and shell regression tests.

## Roadmap

### ROAD-001 — Reset the current phase to Core Integrity

- **Description:** Backlog says Intelligence Layer, while Product Vision and Sprint show unfinished Core/Ingestion work. The accurate phase is Core foundation with partial ingestion scaffolding.
- **Severity:** Critical
- **Effort:** S
- **Dependencies:** None
- **Expected benefit:** Stops feature expansion from outrunning data integrity and testing.
- **Can be automated:** No
- **Recommended next action:** Declare a Core Integrity milestone containing DB-001 through DB-008, AUTO-001, ARC-001, and AUTO-010.

### ROAD-002 — Pause Reasoning and autonomous workflow expansion

- **Description:** Reasoning or autonomy on divergent identity, history, state, false health, and unverified backups would produce untraceable or unsafe outcomes.
- **Severity:** Critical
- **Effort:** XS
- **Dependencies:** ROAD-001
- **Expected benefit:** Avoids building expensive intelligence on an untrustworthy substrate.
- **Can be automated:** Partially
- **Recommended next action:** Add explicit architecture gates that must pass before AI-007, AI-008, or workflow execution starts.

### ROAD-003 — Add a schema/data-governance workstream

- **Description:** Migrations, ownership, provenance, quality, retention, and reconciliation are absent from the roadmap.
- **Severity:** High
- **Effort:** L
- **Dependencies:** ROAD-001, DB-001
- **Expected benefit:** Establishes durable stewardship of long-term knowledge.
- **Can be automated:** Partially
- **Recommended next action:** Assign ownership and acceptance metrics for identity, Events, Resources, Relations, and migrations.

### ROAD-004 — Add provenance, evidence, and licensing work

- **Description:** Source evidence and licensing are not modeled, blocking explainable extraction, research, Relations, and decisions.
- **Severity:** High
- **Effort:** L
- **Dependencies:** DB-020, DB-021
- **Expected benefit:** Makes knowledge defensible and legally traceable.
- **Can be automated:** Partially
- **Recommended next action:** Define Source, citation, evidence span, license, and retrieval-date records.

### ROAD-005 — Add entity resolution and data-quality work

- **Description:** Merge/split policy, duplicate control, confidence calibration, contradiction handling, and quality metrics are missing.
- **Severity:** Critical
- **Effort:** XL
- **Dependencies:** AI-003, AI-004, AI-006
- **Expected benefit:** Prevents automated ingestion from corrupting permanent identity and graph quality.
- **Can be automated:** Partially
- **Recommended next action:** Create a dedicated milestone with golden datasets and human-review acceptance criteria.

### ROAD-006 — Add privacy, security, and retention work

- **Description:** The roadmap omits data classification, secrets, access control, filesystem permissions, retention, and Plugin security.
- **Severity:** High
- **Effort:** L
- **Dependencies:** SEC-004, SEC-006, SEC-010
- **Expected benefit:** Makes the system safe for sensitive multi-domain knowledge.
- **Can be automated:** Partially
- **Recommended next action:** Perform a threat model and data-classification exercise before broad ingestion.

### ROAD-007 — Add disaster-recovery objectives

- **Description:** No RPO/RTO, restore drill, retention plan, or full-system recovery milestone exists.
- **Severity:** Critical
- **Effort:** L
- **Dependencies:** AUTO-010
- **Expected benefit:** Makes “never lose information” measurable and testable.
- **Can be automated:** Yes
- **Recommended next action:** Set RPO/RTO and require automated isolated restore evidence for releases.

### ROAD-008 — Add release engineering and compatibility guarantees

- **Description:** Test strategy, CI, release channels, dependency/runtime support, rollback, and compatibility policy are not operationalized.
- **Severity:** High
- **Effort:** L
- **Dependencies:** AUTO-001, MAIN-013, DB-001
- **Expected benefit:** Produces repeatable releases and controlled evolution.
- **Can be automated:** Yes
- **Recommended next action:** Define a release checklist and make CI artifacts, migration proof, changelog, and restore proof mandatory.

### ROAD-009 — Add observability and operations work

- **Description:** Alerting, failure budgets, runbooks, stale-Service detection, incident response, and artifact-health monitoring are absent.
- **Severity:** High
- **Effort:** L
- **Dependencies:** AUTO-009, AUTO-011
- **Expected benefit:** Supports reliable unattended operation.
- **Can be automated:** Partially
- **Recommended next action:** Define service-level health indicators and first-response runbooks for ingestion, database, and backup failures.

### ROAD-010 — Add AI governance and evaluation work

- **Description:** Model/prompt versioning, evaluation datasets, confidence calibration, human review, drift, and promotion controls are absent from the roadmap.
- **Severity:** High
- **Effort:** XL
- **Dependencies:** AI-009, AI-010, AI-011
- **Expected benefit:** Makes future AI behavior measurable, reproducible, and governable.
- **Can be automated:** Partially
- **Recommended next action:** Define governance requirements before selecting models or implementing general-purpose Agents.

### ROAD-011 — Add Plugin and legacy deprecation milestones

- **Description:** Plugin capability/security boundaries and the removal plan for legacy Engines/tables have no scheduled milestones or exit criteria.
- **Severity:** High
- **Effort:** L
- **Dependencies:** ARC-007, ARC-008, DOC-009
- **Expected benefit:** Prevents temporary compatibility code from becoming permanent architecture.
- **Can be automated:** Partially
- **Recommended next action:** Assign owners, deadlines, usage metrics, and deletion gates for each legacy component.

### ROAD-012 — Add immutable Resource custody as a product milestone

- **Description:** The roadmap promises preservation but does not schedule managed archive custody, multiple locations, verification, or missing-document recovery.
- **Severity:** Critical
- **Effort:** XL
- **Dependencies:** DB-012, AUTO-010, CLI-007
- **Expected benefit:** Makes the core preservation promise operational.
- **Can be automated:** Partially
- **Recommended next action:** Define custody tiers and prove ingest-to-archive-to-restore for one Resource type.

### ROAD-013 — Define measurable milestone exit criteria

- **Description:** Components are marked done based on file/command existence rather than architecture compliance, test coverage, data correctness, operability, and recovery evidence.
- **Severity:** High
- **Effort:** M
- **Dependencies:** DOC-001, AUTO-001, ROAD-001
- **Expected benefit:** Prevents roadmap self-deception and makes progress auditable.
- **Can be automated:** Partially
- **Recommended next action:** Require explicit acceptance tests, schema invariants, health checks, documentation status, and restore proof for every milestone.
