# GMV OS Technical Due Diligence

Review date: 2026-07-04
Reviewer role: Chief Technical Reviewer
Scope: all 70 tracked project files under `~/.gmv_core`, logical Git history, generated artifacts, and the complete live SQLite schema and data. Raw `.git` object files were excluded; repository history and tracked-file state were reviewed through Git.

## 1. Executive Summary

### Current maturity

GMV OS is a pre-alpha architecture prototype. It is not yet a Knowledge Operating System.

The project currently consists of:

- a well-articulated conceptual model;
- a small SQLite catalog with 12 Objects, 9 Relations, 9 current Events, 1 Resource, and 0 Import Queue rows;
- a 451-line Bash CLI that exposes read-only database queries and one import operation;
- 16 small Python scripts, mostly direct SQLite adapters;
- three compatibility wrappers around external legacy programs;
- extensive foundational documentation and migration inventory;
- no automated test suite, no migration framework, no CI, no package definition, and no enforceable service/API boundary.

The database passes `PRAGMA integrity_check`, and the currently populated references have no detected orphans. That is the strongest operational fact in the project. It should not be confused with production readiness. Integrity exists because the dataset is tiny and manually controlled, not because the schema enforces it.

### Overall score

**3.5 / 10**

Score interpretation:

- Conceptual architecture: 6/10
- Implemented architecture: 3/10
- Data integrity controls: 2/10
- Code quality: 4/10
- Testing and release assurance: 0/10
- Security: 2/10
- Operability: 3/10
- Product/roadmap coherence: 4/10

### Main strengths

1. **The core idea is coherent.** Permanent identity, event history, explicit relations, resource provenance, and model independence are the correct primitives for a durable knowledge system.
2. **SQLite is an appropriate initial persistence layer.** The current scale does not justify distributed infrastructure.
3. **The project has adopted small, named Git commits.** The 13-commit history is legible and changes are narrowly scoped.
4. **Most SQL inputs are parameterized.** The newer query services do not expose obvious SQL injection paths.
5. **The live dataset has no detected orphan Events, Relations, Resources, Plugin links, or Service Runs.** Resource hash verification also matches the referenced file.
6. **The compatibility strategy is pragmatic.** Wrapping legacy engines is reasonable during migration if the compatibility layer is explicitly temporary.
7. **The project documents intent unusually well.** The specifications expose architectural goals and make implementation drift visible.

### Main weaknesses

1. **The specifications describe a system that does not exist.** There is no Core API, Service Manager, Identity API, migration layer, plugin runtime, workflow engine, reasoning layer, or autonomous ingestion pipeline.
2. **There are multiple sources of truth.** `events` and `timeline` both persist history; `engine_runs` and `service_runs` both persist executions; JSON state and SQLite use different OIDs for the same person.
3. **The database does not enforce the architecture.** There are no foreign keys, check constraints, triggers, append-only protections, or schema version.
4. **There are no tests.** “Tests pass” currently means manually invoking commands. There is no test file, test runner configuration, CI workflow, or reproducible fixture.
5. **The CLI can report success when dependencies or queries fail.** `gmv doctor` and `gmv status` continue after SQLite errors and end with unconditional success text.
6. **The “Knowledge Engine” is a bootstrap script.** It creates three legacy tables, inserts one fixed Event, and emits a report. It performs no knowledge acquisition, extraction, reconciliation, inference, or graph expansion.
7. **The project tracks mutable runtime data in Git.** The live database, logs, reports, compatibility output, snapshot, migration inventories, and `.DS_Store` are committed.
8. **The only existing snapshot predates the Import Queue schema.** The current database cannot be restored from the committed snapshot without losing that schema.

### Main technical risks

1. **Silent false health:** `gmv doctor` can print “COMPLETED” and exit successfully after failed checks.
2. **Identity collision:** Resource OIDs are allocated using `COUNT(*) + 1`, which is unsafe under deletion, gaps, or concurrent imports.
3. **Historical divergence:** four current Events are absent from legacy `timeline`, while two legacy Timeline rows are absent from `events`.
4. **Unenforced referential integrity:** a single bad write can create permanent orphaned graph data.
5. **Document loss despite the stated invariant:** Resources are referenced by path and hash but are not copied into managed custody. A moved or deleted source disappears.
6. **Command execution exposure:** the compatibility layer uses `subprocess.run(..., shell=True)` on a command assembled from command-line arguments.
7. **No recovery proof:** snapshots lack checksums, manifests, retention, full-system coverage, and automated restore verification.
8. **Roadmap self-deception:** foundational stubs are marked “DONE,” while the actual ingestion pipeline remains empty and the Sprint `Completed` section is blank.

## 2. Architecture Review

### Core

The Core is currently a directory convention plus a SQLite file. There is no executable kernel, domain layer, transaction boundary, or stable internal API. Every service opens SQLite directly. This directly violates `00_CONFIG/10_API.md`, which states that no Service or Plugin may access persistence directly.

The conceptual Core is sound; the implemented Core is absent.

### Database

SQLite is the correct choice for the current single-user scale. The schema is not production-grade. It is a sequence of bootstrap tables without migrations, foreign keys, constraints, or explicit ownership of writes. Deprecated tables remain active and are still written by current engines.

### CLI

The CLI is a manually expanded Bash dispatcher. It delegates most commands to Python scripts but directly queries SQLite for `status` and `doctor`, contradicting the documented CLI boundary. Every new capability requires editing the monolithic `case` statement, contradicting the claim that the CLI discovers Services through a Service Manager.

### Services

The so-called Services are procedural query scripts. They have no shared contract, dependency injection, structured errors, transaction abstraction, logging, telemetry, version negotiation, or authorization. `BaseService` exists but is unused. Service registration is only a view over Objects; most fields required by `SERVICE_SPECIFICATION.md` are stored separately in the deprecated `engines` table or nowhere.

### Engines

Only the Knowledge Engine and legacy inventory source are present. Morning Brief, Daily Log, and Market Engine are external dependencies reached through wrappers. The project therefore cannot be built, tested, or restored from this repository alone.

### Plugin System

The plugin system is a registry, not a plugin system. It stores four metadata records and four service links. There is no loader, manifest, entrypoint validation, isolation boundary, lifecycle, dependency model, installation mechanism, capability contract, or runtime dispatch. Three plugin paths are null. Area35 is active but has no linked Service.

### Import Queue

The queue schema exists, but the live queue has zero rows and no backfill for the existing Resource. It has two overlapping state fields (`status` and `review_status`) without a defined state machine. There is no uniqueness constraint on `source_path`, no foreign key to Resources, no lease/claim model, no retry count, no attempt history, no worker ownership, and no transition Events.

`import_service.py` updates only the first matching queue row for a path. Because the schema permits duplicates, behavior becomes nondeterministic once duplicate paths exist.

### Snapshot System

`gmv snapshot create` produces a database SQL dump. The versioning specification defines a milestone snapshot as documentation, database, configuration, and code. The implementation snapshots only SQLite.

The only committed dump is older than the Import Queue schema. There is no manifest, checksum, encryption, compression, retention policy, atomic temporary-file protocol, restore command, restore test, or external Resource verification. A failed dump can leave a partial file that looks valid by name.

### Project structure

The numeric directory structure is understandable but mixes four concerns:

- source code;
- operational state;
- generated output;
- version-controlled governance documents.

This prevents clean builds and clean deployments. Empty directories such as `06_CACHE`, `07_IMPORT`, and `08_BACKUP_LOCAL` are not represented in Git and will disappear in a clone. `11_PLUGINS`, documented in the architecture, does not exist. The tracked `.DS_Store` is pure noise.

### State management

State is split among SQLite, JSON files, generated reports, logs, and Git. `03_STATE/objects/OBJECT-0000001_GMV.json` identifies the owner as `OBJECT-0000001`; SQLite identifies the same person as `PER-000001`. `02_INDEXES/OBJECT_INDEX.json` points to the JSON identity. This is a direct breach of permanent identity and single-source-of-truth principles.

The JSON state also contains attributes, relations, timeline, documents, and metrics that have no equivalent tables in SQLite. There is no synchronization mechanism. It is impossible to state which representation is authoritative in practice.

### OID model

Typed OID prefixes are readable and useful. The implementation lacks a centralized allocator and validator. Resource OIDs use row count. Other OIDs appear bootstrapped manually. No database constraint verifies prefix/type compatibility. `engines`, runs, architecture decisions, and queue records persist independently of the universal Object model.

### Event model

The design says Events are append-only and Timeline is derived. The database persists both `events` and `timeline`. Current CLI commands read `events`; the active Knowledge and compatibility engines write `timeline`. The two histories have already diverged.

There is no append-only enforcement, causal identifier, actor OID, correlation ID, schema/version field, payload structure, correction mechanism, or event uniqueness policy. No Event has been recorded since 2026-07-03 despite 12 subsequent feature/documentation commits on 2026-07-04. “Every action creates an Event” is not implemented.

### Relation model

Relations correctly reference OIDs and current rows have valid endpoints. The schema does not enforce those endpoints. `relation_type` is unrestricted text. There is no relation-type registry, direction semantics, validity interval, confidence, source Resource, evidence pointer, status, version, or Event history. The uniqueness constraint prevents representing repeated or independently sourced assertions of the same relationship.

## 3. Code Quality

### Quantitative profile

- 1,737 lines across Python, Bash CLI, and scheduler wrappers.
- 16 Python files.
- 451-line monolithic Bash CLI.
- 0 automated test files.
- 0 CI configuration files.
- 0 dependency or packaging manifests.

### Duplicated code

1. `event_service.py` and `timeline_service.py` duplicate the same queries and output logic.
2. Every query service repeats `DB`, `connect()`, row formatting, argument parsing, error handling, and output conventions.
3. `plugin_manager.py` and `plugin_service.py` overlap substantially; the former is no longer wired to the CLI.
4. `import queue` and top-level `queue` expose overlapping functionality with different columns and different implementations.
5. `engine_runs` and `service_runs` duplicate five execution records.
6. `events` and `timeline` duplicate five historical records but disagree on the remainder.
7. Architecture decisions 1–5 are repeated by decisions 6–12; four decision names are exact duplicates.
8. The legacy inventory exists as both a 74 KB JSON file and a 46 KB Markdown rendering of the same 282 records.

### Dead or obsolete code and files

- `BaseService` has no consumers.
- `plugin_manager.py` has been superseded by `plugin_service.py`.
- `engines`, `engine_runs`, and `timeline` are declared deprecated in `architecture_decisions` but remain active dependencies.
- `legacy_inventory.py` imports `os` but does not use it.
- `gmv_compatibility.py` imports `json` and `os` but does not use them.
- `.DS_Store` is tracked.
- Multiple historical logs and reports are committed as source artifacts.
- Two database paths reference missing `05_OUTPUT/bridge` log files.

### Large or complex functions

There are no algorithmically large Python functions. The complexity is structural:

- `11_CLI/gmv` is a 451-line dispatcher with duplicated help text and no strict shell mode.
- `knowledge_engine.py` executes all behavior at module import/top level, making it difficult to test or reuse.
- `import_file()` combines validation, hashing, identity allocation, Resource persistence, Event persistence, queue mutation, and presentation.
- `service_service.list_runs()` contains fragile legacy deduplication logic based on normalized display names and exact timestamps.

### Inconsistent naming and representation

- `OBJECT-0000001` and `PER-000001` identify the same person.
- `Event` and `Timeline` are both table names and conceptual aliases.
- `Engine`, `Service`, and `Compatibility Service` overlap without a single canonical model.
- `status` is lowercase for Objects/Plugins, uppercase for run outcomes, and split across two fields in the queue.
- Timestamps mix `2026-07-03T12:10:25` with `2026-07-03 10:10:25` and have no timezone.
- CLI `show` commands use labeled output; list commands use raw pipes; empty results usually print nothing; `BaseService` would print `Empty`.
- Errors are printed to stdout in most newer services but stderr in the compatibility usage path.

### Technical debt

The primary debt is not formatting. It is unimplemented architecture presented as completed architecture. The next development cycle must stop adding thin CLI wrappers and establish real persistence, migration, validation, event, and test boundaries.

## 4. Database Review

### Current schema and data

The live database contains:

| Entity | Rows |
|---|---:|
| Objects | 12 |
| Engines | 4 |
| Engine Runs | 7 |
| Service Runs | 5 |
| Legacy Timeline | 7 |
| Events | 9 |
| Relations | 9 |
| Resources | 1 |
| Import Queue | 0 |
| Plugin Metadata | 4 |
| Plugin Services | 4 |
| Architecture Decisions | 12 |

`PRAGMA integrity_check` returns `ok`. Current application-level orphan checks return zero. `PRAGMA foreign_keys` returns `0`; there are no declared foreign keys, so `foreign_key_check` proves nothing.

### Schema defects

1. `PRAGMA user_version` is `0`; there is no schema-version table or migration ledger.
2. No foreign keys exist.
3. No check constraints define allowed statuses, OID formats, confidence ranges, or non-self relations.
4. No triggers protect append-only Events.
5. No unique constraint exists on Import Queue source identity.
6. No indexes exist beyond primary-key and unique auto-indexes.
7. Views include `ORDER BY`, which is not a stable API contract and can force unnecessary sorting.
8. Timestamps are untyped text with inconsistent formats and no timezone.
9. `objects.status` duplicates `resources.status` and `plugin_metadata.status`.
10. `service_name` is duplicated into `service_runs`, allowing historical identity drift.

### Normalization

The Object/extension-table approach is reasonable. It is incomplete and inconsistently applied.

- Services are Objects, but Engines are a separate identity system.
- Plugins are Objects plus metadata, which is appropriate.
- Resources are Objects plus physical metadata, but a Resource supports only one path.
- Events are not Objects despite the documentation listing Event as an Object type.
- Architecture decisions are persistent entities without OIDs.
- Attributes, Documents, Tags, Sources, and metadata/metrics tables described in the architecture do not exist.

The Resource design conflates content identity and file location. Deduplication by SHA-256 means identical content at a new path resolves to the existing Resource, but the Resource retains only the original path. A separate `resource_locations` table is required.

### OID consistency

Current typed rows use internally consistent prefixes. The allocator is not safe. There is no canonical OID sequence, UUID/ULID strategy, or central allocation transaction. `COUNT(*) + 1` can reuse or collide with IDs. JSON state already demonstrates a second incompatible identity scheme.

### Indexes and query plans

SQLite query plans confirm full scans and temporary sorting for:

- Events by OID/time;
- Relations by source or target;
- pending queue entries;
- substring Search.

At current scale this is irrelevant. At knowledge-graph scale it becomes a hard limit.

Minimum required indexes:

- `events(oid, event_at DESC, id DESC)`;
- `events(event_type, event_at DESC)`;
- `relations(source_oid, relation_type, target_oid)` plus `relations(target_oid, relation_type, source_oid)`;
- `service_runs(service_oid, run_at DESC)`;
- `engine_runs(engine, run_at DESC)` during migration;
- `import_queue(status, review_status, created_at)`;
- unique or explicitly versioned queue source identity;
- `resources(path)` or a new indexed location table.

Substring search should move to SQLite FTS5 rather than indexed scalar columns.

### Scalability

SQLite can support substantially more data if WAL mode, busy timeout, migrations, indexes, and disciplined transactions are introduced. The current `DELETE` journal mode, one-off connections, no busy timeout, no concurrency policy, and scan-heavy search will fail under concurrent ingestion.

### Required improvements

1. Introduce numbered, idempotent migrations and set `user_version`.
2. Rebuild tables with foreign keys and checks; enable foreign keys on every connection.
3. Migrate legacy `timeline` into `events` and remove all writers to `timeline`.
4. Migrate `engine_runs` into `service_runs` and remove name-based deduplication.
5. Create a transaction-safe OID allocator.
6. Add Resource locations and managed storage custody.
7. Define Import Queue transitions and uniqueness.
8. Add indexes and FTS5.
9. Standardize UTC RFC 3339 timestamps.
10. Add backup/restore verification and migration rollback tests.

## 5. CLI Review

### Command-by-command assessment

| Command | Assessment |
|---|---|
| `gmv status` | Directly queries SQLite, invokes `launchctl`, and unconditionally prints `SYSTEM READY`. It does not prove readiness and can return success after query failures. |
| `gmv doctor` | Checks SQLite integrity and two orphan classes, but ignores Relation, Resource, Plugin, Queue, legacy Timeline, snapshot freshness, path validity, schema version, and duplicate histories. It is not a doctor; it is a report. |
| `gmv object list/show/count` | Adequate read-only inspection. Missing OID validation, pagination, filters, JSON, create/update/archive, and timeline/relations aggregation. |
| `gmv resource list/show/count` | Useful basic inspection. Count is grouped by status rather than returning an unambiguous total. No path validation, hash recheck, location list, missing-file status, archive operation, or provenance view. |
| `gmv relation list/show/count` | Basic graph inspection only. `show` returns failure when an existing Object has no Relations. Missing create/remove, incoming/outgoing filters, evidence, and relation-type validation. |
| `gmv event latest/show/count` | Works against `events`, but duplicates Timeline functionality. `latest` has a hard-coded limit of 10 with no option. Missing event ID lookup, time filters, type filters, actor/source filters, and JSON. |
| `gmv timeline latest/show` | Near-total duplicate of Event CLI and service code. The distinction between Event and Timeline is not communicated. |
| `gmv import file` | Hashes and registers a file, but does not take custody of it. Missing allowlist, size limits, symlink policy, retry/error recording, concurrency safety, dry-run, bulk import, and archive destination. |
| `gmv import queue/pending` | Overlaps top-level Queue commands and exposes a different column set, including source path. Two public contracts exist for the same data. |
| `gmv queue list/pending/show` | Read-only queue inspection. Pending logic uses `status='pending' OR review_status='pending_review'`, which exposes the undefined two-state model. Missing approve/reject/retry/assign/archive transitions. |
| `gmv search <query>` | Safe parameter binding and useful V0 output. It performs full scans, has no limit, ranking, pagination, field filters, OID search, FTS, or escaping for pipes/newlines in stored content. |
| `gmv snapshot create/list` | Database-only dump/list. Missing verify, restore, inspect, prune, checksums, manifests, and full-system snapshots. |
| `gmv service list/runs/show` | Read-only registry view. Runs merge two histories using name normalization and timestamp equality, which is fragile. Missing run/status/info/enable/disable and contract display. |
| `gmv plugin list/services/show` | Useful registry inspection. `services` emits an empty service row for Area35 because of the left-join view. Missing install/validate/enable/disable/path/manifest/capability operations. |

### UX and consistency defects

1. No `gmv help`, `gmv version`, or standard `--help` behavior.
2. No JSON output despite the CLI specification requiring text and JSON.
3. No headers or schema declaration for pipe output.
4. Pipe-delimited values are not escaped; data containing `|` or newlines corrupts the format.
5. No pagination, limits, or machine-readable error envelope.
6. Missing arguments return code 2, absent entities return 1, but errors generally go to stdout.
7. Empty results silently print nothing.
8. Top-level and subcommand help are manually duplicated and already inconsistent; Object and Relation help include unrelated Import commands.
9. The CLI does not validate OID formats, numeric IDs, status values, paths, or slugs before querying.
10. No strict Bash mode (`set -euo pipefail`) or dependency checks.

### Missing commands

Highest-value missing commands:

- `gmv version`, `gmv help`, `gmv doctor --strict`;
- `gmv object create/update/archive`;
- `gmv relation create/remove`;
- `gmv event show-id/filter`;
- `gmv import folder/watch/review`;
- `gmv queue approve/reject/retry/assign`;
- `gmv resource verify/locations/archive`;
- `gmv snapshot verify/restore/prune`;
- `gmv service run/status/info/enable/disable`;
- `gmv plugin validate/install/enable/disable`;
- global `--json`, `--limit`, `--offset`, and stable error output.

## 6. Engine Review

### Knowledge Engine

**Maturity: bootstrap script, not an Engine.**

It creates legacy tables if absent, inserts a fixed Person and fixed Timeline event, records an Engine Run, writes a JSON report, and overwrites a one-line log. It does not process knowledge. Re-running it creates repeated initialization Events. It writes to deprecated `timeline`, not `events`, and to `engine_runs`, not `service_runs`. It can create a new empty database accidentally if the configured database is missing.

Required simplification: stop calling this a Knowledge Engine until it performs extraction/reconciliation. Convert current behavior into a schema bootstrap/migration and health fixture.

### Legacy Inventory

**Maturity: one-shot migration utility.**

It scans broad external locations, catches generic exceptions, and writes duplicated JSON/Markdown inventories. The recorded inventory contains 282 files: 219 Dropbox files, 56 `.gmv_*` files, and 7 LaunchAgent files. It has no incremental mode, content hashing, duplicate detection, sensitivity classification, or stable inventory ID.

Required simplification: move it to explicit migration tooling, not runtime Engines.

### Compatibility Layer

**Maturity: functional but unsafe transition wrapper.**

It captures stdout/stderr and exit status, which is useful. It uses `shell=True`, writes legacy tables, does not record `service_runs` or current `events`, and accepts arbitrary command text. It has no timeout, environment isolation, cancellation, output-size limit, or process-tree control.

Required simplification: accept an argument vector, not shell text; register one canonical Service Run and Event through the Core API.

### Morning Brief

**Maturity: external legacy dependency; source not auditable in this project.**

The wrapper calls `~/.gmv_scripts/genera_morning_brief.sh`. Logs show successful email delivery. The repository cannot reproduce or test the implementation. It depends on external state and likely Dropbox, contradicting local runtime independence.

### Daily Log

**Maturity: external legacy dependency; source not auditable in this project.**

The wrapper calls `~/.gmv_scripts/genera_daily_log.sh`. Logs show direct output to Dropbox. Two recorded bridge log paths no longer exist. The run history is duplicated across two tables.

### Market Engine

**Maturity: external Dropbox-hosted program; architecturally noncompliant.**

The scheduler executes Python source directly from Dropbox. This explicitly violates the rule that no Engine should depend on Dropbox to run. The code is not versioned in this repository, so the committed wrapper is not a reproducible Service.

### Missing engine capabilities

No current Engine performs:

- watch-folder ingestion;
- queue claiming and retries;
- OCR;
- entity extraction;
- entity resolution;
- relation extraction;
- provenance/evidence linking;
- graph quality checks;
- reasoning;
- decision support;
- workflow execution;
- scheduler orchestration.

## 7. Security Review

### Critical findings

1. **Shell command execution:** `gmv_compatibility.py` joins user arguments and executes them with `shell=True`. This is command injection by design if the script is reachable with untrusted input.
2. **Arbitrary file ingestion:** `gmv import file` can read and hash any file readable by the user, then persist its absolute path and filename. There is no allowed-root policy or sensitive-file exclusion.
3. **World-readable persistence:** the database and SQL snapshot are mode `0644`. On a multi-user machine, local users can read knowledge metadata and paths.
4. **Sensitive data in Git:** the live database, absolute personal paths, logs, state, reports, and snapshots are permanently stored in repository history.
5. **No authorization model:** every process running as the user can mutate the Core directly.

### Other findings

- SQL parameterization is generally sound in newer scripts. Dynamic SQL fragments are constants, not user-controlled.
- Foreign keys are disabled, allowing malicious or accidental integrity corruption.
- No input limits protect against huge files, terminal control characters, newlines, or pipe characters.
- Import performs multiple path/stat/read operations without defending against source replacement during hashing.
- Snapshot creation uses default file permissions and has no encryption.
- Legacy inventory exposes metadata for Dropbox, LaunchAgents, contacts, deals, and personal runtime files.
- Compatibility command strings and absolute paths are persisted in the database and logs.
- No timeout exists for external commands; a hung legacy Engine can hang indefinitely.
- No Resource quarantine or content-type validation exists.
- No secrets scanning, dependency scanning, static analysis, or audit-log protection exists.
- Current commands are mostly non-destructive, but there is no framework for confirmation, authorization, or dry-run when destructive commands arrive.

## 8. Performance Review

Performance is acceptable only because the dataset is microscopic.

### Slow query risks

- Search applies `lower()` and `instr()` to every row in four tables.
- Event history scans and sorts the entire Events table.
- Relation lookup with `source_oid=? OR target_oid=?` scans Relations.
- Queue pending scans and sorts the queue.
- Service run merging scans two run tables, normalizes names row by row, and executes a correlated `NOT EXISTS` check.
- CLI `status` and `doctor` spawn multiple separate `sqlite3` processes instead of using one connection and one consistent snapshot.

### Duplicate work

- Every Python CLI invocation opens a new connection and repeats formatting logic.
- Event and Timeline execute identical queries.
- Five execution records are stored twice.
- Five historical records are stored twice.
- Legacy inventory is rendered twice.
- The same object/service/plugin data is stored in Objects, extension tables, reports, and state JSON.

### Import performance

One-megabyte hash chunks are reasonable. OID allocation by `COUNT(*)` is both unsafe and increasingly expensive. There is no batching for folder ingestion, no worker concurrency model, and no transaction retry policy.

### Caching

Do not add application caching now. The project first needs one authoritative model and indexes. Premature caching would preserve inconsistencies. The eventual useful caches are:

- FTS5 indexes for Search;
- derived graph metrics with explicit invalidation;
- content-hash reuse for known file metadata;
- materialized summaries only after event consistency exists.

## 9. Maintainability

### One-year outlook

At the current trajectory, maintainability in one year will be poor. Each feature adds another script, another CLI case, and another direct SQL contract. Schema changes are manual. Generated files accumulate in Git. Documentation increasingly describes intended behavior rather than actual behavior. Once real data volume arrives, correcting identity and event history will become expensive and risky.

The codebase is small enough to fix now. That window will close after autonomous ingestion begins.

### Refactor now

1. Create one Python package with configuration, database connection, migrations, repositories, output formatting, and typed error primitives.
2. Replace the Bash dispatcher with a structured Python CLI or generated command registry.
3. Merge Event and Timeline query code; Timeline should be a presentation over Events.
4. Retire `plugin_manager.py` and `BaseService` unless they become the canonical abstractions.
5. Move bootstrapping out of Engines and into migrations/seeds.
6. Separate source, tests, migrations, runtime data, and generated output.
7. Stop versioning the live database and mutable logs as ordinary source files; define controlled fixtures and release snapshots instead.
8. Introduce a real test pyramid: schema/migration tests, repository tests, CLI contract tests, import integration tests, and restore tests.

### Documentation maintenance

Documentation is currently a liability because it is normative but false in key areas. Each document needs a status banner distinguishing:

- implemented;
- partially implemented;
- planned;
- deprecated.

Architecture Decision Records should live in version-controlled text, not only in a weakly constrained database table with duplicates.

## 10. Roadmap Review

### Alignment

The Product Vision and architecture agree on the long-term direction: persistent memory, explicit Objects, Relations, Events, Resources, and eventual reasoning/workflows. The high-level sequence from Core to Ingestion to Knowledge to Reasoning to Decision is correct.

The execution documents are not aligned with reality:

1. `GMV_BACKLOG.md` declares the current phase “GMV Intelligence Layer,” while `GMV_SPRINT.md` is still completing ingestion and the Product Vision places Ingestion before Knowledge.
2. The Backlog marks Core and Knowledge Engine “DONE,” but the Core API does not exist and the Knowledge Engine is a bootstrap script.
3. The Backlog marks Import Service and Queue CLI done, but the live queue has zero rows, no worker, no review transitions, and no archive custody.
4. `GMV_SPRINT.md` has an empty `Completed` section, while the Changelog calls the same date a Sprint 002 milestone.
5. The Changelog claims an “automated validation workflow,” but there is no test suite or CI. Repeated manual execution is not automation.
6. Architecture says every action creates an Event; no Event exists for any 2026-07-04 project work.
7. Architecture says everything has an OID; persisted Engines, runs, decisions, queue records, and state JSON do not follow one universal identity mechanism.

### Missing roadmap workstreams

- Schema migration and data governance.
- Provenance, evidence, and source licensing.
- Entity resolution and merge/split policy.
- Data quality metrics and reconciliation.
- Privacy, secrets, access control, and retention.
- Backup disaster recovery objectives and restore drills.
- Test strategy, CI, release channels, and compatibility guarantees.
- Observability, alerting, failure budgets, and runbooks.
- Model evaluation, prompt/model versioning, confidence calibration, and human review.
- Plugin security and capability boundaries.
- Resource custody and immutable archive policy.
- Deprecation plan for legacy Engines and tables.

### Correct phase statement

GMV OS is in **Phase 1: Core foundation**, with partial Phase 2 ingestion scaffolding. It is not in the Intelligence Layer.

## 11. Priorities

| Rank | Technical priority | Impact | Difficulty |
|---:|---|---|---|
| 1 | Introduce reproducible schema migrations, schema versioning, foreign keys, check constraints, and migration tests. | Prevents irreversible data corruption and makes every later feature safe to ship. | Large |
| 2 | Collapse `timeline` into `events`; migrate data, update all writers, and enforce append-only history. | Restores one historical truth before more Events accumulate. | Medium |
| 3 | Build an automated test suite and CI gate covering migrations, CLI contracts, import transactions, and snapshot restore. | Replaces false confidence with repeatable evidence. | Large |
| 4 | Implement a real Core data-access/API layer and prohibit direct SQLite access from CLI, Engines, and Plugins. | Enforces invariants and stabilizes contracts. | Large |
| 5 | Replace `COUNT(*) + 1` with a transaction-safe central OID allocator and validate prefix/type consistency. | Protects permanent identity, the system's primary invariant. | Medium |
| 6 | Define Resource custody: managed immutable storage, multiple locations, hash verification, missing-file detection, and provenance. | Makes “never lose a document” technically credible. | Large |
| 7 | Define and implement the Import Queue state machine, uniqueness, claims, retries, errors, review transitions, and Events. | Turns an empty table into an ingestion pipeline. | Large |
| 8 | Make `gmv doctor` strict: aggregate failures, return nonzero, remove unconditional readiness, and cover all integrity classes. | Prevents operational false positives. | Medium |
| 9 | Make every write produce one canonical Event with actor, correlation ID, source, schema version, and payload. | Creates actual traceability and auditability. | Large |
| 10 | Add required indexes and FTS5; define query limits and pagination. | Removes known scaling cliffs before ingestion volume arrives. | Medium |
| 11 | Migrate `engine_runs` to `service_runs`, retire `engines`, and remove heuristic name/timestamp deduplication. | Eliminates another split source of truth. | Medium |
| 12 | Remove `shell=True`; run legacy commands as argument vectors with timeouts, controlled environments, and output limits. | Closes the most direct security and reliability defect. | Medium |
| 13 | Build verified full-system backup/restore: manifest, checksums, atomic creation, retention, encryption option, and restore drills. | Makes recovery and long-term preservation real. | Large |
| 14 | Standardize CLI output, errors, OID validation, `--json`, `--limit`, help, and version behavior. | Creates a stable public interface for humans and automation. | Medium |
| 15 | Consolidate duplicate query services and replace the monolithic Bash dispatcher with a command registry. | Reduces per-feature duplication and drift. | Medium |
| 16 | Reconcile or remove JSON state/index identities and declare one authoritative state model. | Eliminates the existing `OBJECT-0000001` versus `PER-000001` identity breach. | Medium |
| 17 | Define a real Plugin manifest, loader, lifecycle, capability model, validation, and isolation policy. | Converts registry rows into an extensible system. | Large |
| 18 | Implement structured logging, run correlation, error records, metrics, alerting, and operational runbooks. | Makes Engines observable and recoverable. | Medium |
| 19 | Harden filesystem and data security: permissions, import roots, sensitive-file rules, terminal escaping, secrets scanning, and Git data policy. | Reduces exposure of personal and operational knowledge. | Medium |
| 20 | Correct Backlog/Sprint/Changelog maturity claims and add implementation-status matrices to architecture documents. | Stops governance documents from driving decisions with false status. | Small |

## 12. Final Verdict

**Can GMV OS become a long-term Knowledge Operating System? Yes, but not by continuing the current implementation pattern.**

The durable value is in the chosen primitives: immutable identity, explicit relations, append-only events, resource provenance, model independence, and a local-first database. Those are credible foundations for a long-lived personal or organizational knowledge system.

The present code does not implement those foundations reliably. It simulates architectural progress through thin CLI surfaces over an unconstrained database. Adding more Engines, Agents, or reasoning now would amplify inconsistency. A reasoning layer built on divergent identity, history, and state would produce untraceable conclusions. An autonomous workflow layer built on a false-positive doctor and unverified backups would be reckless.

The project should pause feature expansion after the current review. The next milestone must be **Core Integrity**, not Intelligence:

1. one identity system;
2. one event history;
3. one Service execution history;
4. one enforced database schema with migrations;
5. one tested API boundary;
6. one verified document-custody and recovery model.

If those six conditions are met, SQLite and the current local-first design can carry the project through substantial growth. If they are not met, GMV OS will become a collection of scripts, duplicate metadata, and impressive documents that cannot guarantee the preservation or truth of the knowledge they claim to manage.

The concept is viable. The current implementation is not yet trustworthy.
