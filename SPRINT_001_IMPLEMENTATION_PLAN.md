# Sprint 001 Implementation Plan

## 1. Sprint objective

Sprint 001 creates the safety foundation required for every later V2 sprint:

- a reproducible Python/tooling contract;
- an isolated test harness that cannot write to the live GMV database;
- characterization tests for the current schema and CLI;
- automated quality, security, and CI gates;
- a versioned migration baseline tested only on temporary databases;
- a canonical OID contract, validator, and transaction-safe allocator;
- shared CLI input/error primitives;
- explicit Core Integrity and no-premature-cache governance gates.

Sprint 001 must finish before every other sprint because all later work changes identity, schema, history, recovery, automation, or public contracts. Without isolated tests and migration proof, those changes would repeat the current pattern of manual confidence over a mutable live database.

### Sprint scope

Sprint 001 covers exactly these roadmap IDs:

`ROAD-001`, `ROAD-002`, `MAIN-001`, `MAIN-013`, `AUTO-001`, `AUTO-002`, `AUTO-012`, `DB-001`, `ARC-004`, `DB-007`, `DB-008`, `CLI-003`, `PERF-007`

### Safety constraints

1. No Sprint 001 test may open `~/.gmv_core/09_DATABASE/GMV.db` for writing.
2. No migration may run against the live database during Sprint 001.
3. Tests must use temporary GMV homes and disposable SQLite databases.
4. Scheduled processes must be placed in an approved maintenance window or their generated changes must be explicitly separated before implementation begins.
5. Each task is one reviewable change and must leave tests passing and the repository operational.
6. No feature from Sprint 002–007 may be pulled forward.
7. No application cache may be introduced.

## 2. Dependency graph

```text
S001-00 Protected baseline and writer inventory
├── S001-01 Core Integrity and no-cache gates
└── S001-02 Packaging and runtime contract
    └── S001-03 Python foundation package
        └── S001-04 Isolated test harness and live-write guard
            ├── S001-05 Characterization tests
            │   ├── S001-06 CI, lint, static, dependency, and secrets gates
            │   ├── S001-07 Migration runner and schema baseline
            │   │   ├── S001-08 Migration idempotence and rollback tests
            │   │   │   └── S001-10 Transaction-safe OID allocator
            │   │   └── S001-09 OID contract and validator
            │   │       ├── S001-10 Transaction-safe OID allocator
            │   │       └── S001-11 CLI validation and error primitives
            │   └── S001-11 CLI validation and error primitives
            └── S001-07 Migration runner and schema baseline

S001-01 through S001-11
└── S001-12 Sprint acceptance and governance closeout
```

### Dependency table

| Task | Direct dependencies | Why |
|---|---|---|
| S001-00 | None | Establishes whether work can begin without mixing scheduler/runtime changes into Sprint changes. |
| S001-01 | S001-00 | Governance changes must reflect a verified baseline. |
| S001-02 | S001-00 | Runtime/tool versions must be selected against the actual environment. |
| S001-03 | S001-02 | Package structure depends on packaging and runtime conventions. |
| S001-04 | S001-02, S001-03 | Test isolation depends on the package/config boundary. |
| S001-05 | S001-04 | Characterization must run only through isolated fixtures. |
| S001-06 | S001-05 | CI should gate a proven local test command, not an empty suite. |
| S001-07 | S001-04, S001-05 | The migration baseline needs disposable databases and characterization evidence. |
| S001-08 | S001-07 | Idempotence and rollback tests require a migration runner/baseline. |
| S001-09 | S001-04, S001-07 | The OID contract must be tested against the isolated schema. |
| S001-10 | S001-08, S001-09 | Allocation depends on migration support and finalized identity rules. |
| S001-11 | S001-03, S001-05, S001-09 | CLI validation uses shared package primitives, preserves characterized behavior, and enforces the OID contract. |
| S001-12 | S001-01 through S001-11 | Closeout requires all implementation evidence. |

## 3. Work breakdown

### S001-00 — Establish a protected baseline

- **Task ID:** S001-00
- **Related backlog IDs:** `AUTO-001`, `ROAD-001`, `ROAD-002`
- **Purpose:** Identify every active writer, separate pre-existing runtime changes from Sprint work, capture read-only database/repository fingerprints, and establish a maintenance-window rule.
- **Files that will probably be modified:** None. Evidence should be captured in task/CI output or an approved external work record, not a new project artifact in this task.
- **Estimated duration:** 30 minutes
- **Risk level:** High
- **Rollback strategy:** None required; the task is read-only. If a command unexpectedly writes, stop immediately, preserve evidence, and restore only through the approved backup process.
- **Validation commands:**

  ```bash
  git status --short
  shasum -a 256 09_DATABASE/GMV.db
  stat -f '%m %z %N' 09_DATABASE/GMV.db 04_LOGS/*
  launchctl list | grep com.gmv || true
  gmv doctor
  gmv status
  gmv object count
  ```

- **Definition of Done:** All pre-existing changes and active writers are identified; a maintenance window or separation strategy is approved; database hash/metadata and Git status are captured; no file was changed by the task.

### S001-01 — Declare Core Integrity and no-cache gates

- **Task ID:** S001-01
- **Related backlog IDs:** `ROAD-001`, `ROAD-002`, `PERF-007`
- **Purpose:** Correct the active phase, block Reasoning/autonomous workflow expansion until foundation gates pass, and explicitly defer application caching.
- **Files that will probably be modified:** `GMV_BACKLOG.md`, `GMV_SPRINT.md`, `GMV_ARCHITECTURE.md`, an ADR under a new or existing governance location, and `GMV_CHANGELOG.md` only after acceptance.
- **Estimated duration:** 45 minutes
- **Risk level:** Low
- **Rollback strategy:** Revert only the documentation change if review finds an inaccurate gate; do not change implementation or database state.
- **Validation commands:**

  ```bash
  rg -n "Core Integrity|Reasoning|autonomous|cache" GMV_*.md 00_CONFIG
  git diff --check
  git diff -- GMV_BACKLOG.md GMV_SPRINT.md GMV_ARCHITECTURE.md GMV_CHANGELOG.md
  gmv doctor
  gmv status
  gmv object count
  ```

- **Definition of Done:** Current phase is Core Integrity; deferred Intelligence work has explicit entry gates; no-cache rationale is recorded; no completed capability is overstated; only intended governance files changed.

### S001-02 — Add packaging and runtime contract

- **Task ID:** S001-02
- **Related backlog IDs:** `MAIN-013`, `AUTO-012`
- **Purpose:** Define supported Python/SQLite versions, project metadata, console-entrypoint intent, and pinned development tooling.
- **Files that will probably be modified:** `pyproject.toml` (new), a lock/constraints file if selected, `.gitignore`, and a concise development section in `README_CORE.md`.
- **Estimated duration:** 60 minutes
- **Risk level:** Medium
- **Rollback strategy:** Remove only newly added packaging files or revert the atomic task commit; the existing CLI must remain callable throughout.
- **Validation commands:**

  ```bash
  python3 --version
  sqlite3 --version
  python -m pip check
  python -m build
  git diff --check
  gmv doctor
  gmv status
  gmv object count
  ```

- **Definition of Done:** Supported runtimes are explicit; development dependencies are reproducible; package metadata builds; no existing command path changes; database and generated runtime data are untouched.

### S001-03 — Create the Python foundation package

- **Task ID:** S001-03
- **Related backlog IDs:** `MAIN-001`
- **Purpose:** Establish importable package boundaries for configuration, paths, typed errors, and future Core/repository code without migrating behavior prematurely.
- **Files that will probably be modified:** `gmv_core/__init__.py`, `gmv_core/config.py`, `gmv_core/paths.py`, `gmv_core/errors.py`, and `pyproject.toml` package configuration.
- **Estimated duration:** 60 minutes
- **Risk level:** Medium
- **Rollback strategy:** Revert the package skeleton; existing standalone scripts and Bash CLI remain the operational fallback.
- **Validation commands:**

  ```bash
  python -c "import gmv_core; import gmv_core.config; import gmv_core.errors"
  python -m pytest -q
  python -m ruff check gmv_core
  git diff --check
  gmv doctor
  gmv status
  gmv object count
  ```

- **Definition of Done:** Package imports cleanly; configuration supports an injected GMV home; importing modules performs no I/O or database writes; no current CLI behavior changed.

### S001-04 — Build an isolated test harness and live-write guard

- **Task ID:** S001-04
- **Related backlog IDs:** `AUTO-001`, `MAIN-001`
- **Purpose:** Guarantee that tests use temporary GMV homes/databases and fail before any write to the live Core.
- **Files that will probably be modified:** `tests/conftest.py`, `tests/helpers.py`, `tests/test_isolation.py`, `pyproject.toml`, and package configuration/path modules.
- **Estimated duration:** 90 minutes
- **Risk level:** Critical
- **Rollback strategy:** Revert the harness if isolation cannot be proven. Do not weaken the live-write guard to make tests pass.
- **Validation commands:**

  ```bash
  LIVE_DB_HASH_BEFORE="$(shasum -a 256 09_DATABASE/GMV.db)"
  python -m pytest -q tests/test_isolation.py
  LIVE_DB_HASH_AFTER="$(shasum -a 256 09_DATABASE/GMV.db)"
  test "$LIVE_DB_HASH_BEFORE" = "$LIVE_DB_HASH_AFTER"
  git diff --check
  gmv doctor
  gmv status
  gmv object count
  ```

- **Definition of Done:** Every test gets a disposable GMV home; live path writes raise a hard failure; database hash remains unchanged; fixtures clean themselves; tests are deterministic on repeated runs.

### S001-05 — Add schema and CLI characterization tests

- **Task ID:** S001-05
- **Related backlog IDs:** `AUTO-001`, `DB-001`, `CLI-003`
- **Purpose:** Capture current schema objects, views, indexes, version, representative data shape, CLI exit codes, and output before refactoring.
- **Files that will probably be modified:** `tests/characterization/test_schema.py`, `tests/characterization/test_cli.py`, sanitized fixtures under `tests/fixtures/`, and fixture-building helpers.
- **Estimated duration:** 90 minutes
- **Risk level:** High
- **Rollback strategy:** Revert incorrect expectations; never update snapshots blindly. Any expectation change must be tied to an approved behavior change.
- **Validation commands:**

  ```bash
  python -m pytest -q tests/characterization
  python -m pytest -q tests/characterization --maxfail=1
  git diff --check
  gmv doctor
  gmv status
  gmv object count
  ```

- **Definition of Done:** Tests describe current schema/version and representative CLI behavior; fixtures contain no sensitive live data; deliberate schema/output changes cause clear failures; all tests remain isolated.

### S001-06 — Add CI, lint, static, dependency, and secrets gates

- **Task ID:** S001-06
- **Related backlog IDs:** `AUTO-001`, `AUTO-012`, `MAIN-013`
- **Purpose:** Turn local checks into an automated release gate that fails on tests, lint, static/security findings, dependency problems, secrets, or whitespace defects.
- **Files that will probably be modified:** CI workflow/configuration, `pyproject.toml`, tool configuration, and narrowly scoped baseline/suppression files where existing debt cannot be corrected in Sprint 001.
- **Estimated duration:** 90 minutes
- **Risk level:** Medium
- **Rollback strategy:** Revert the CI change if it blocks for infrastructure reasons; do not globally suppress legitimate findings. Quarantine pre-existing debt with explicit owner and expiry.
- **Validation commands:**

  ```bash
  python -m pytest -q
  python -m ruff check .
  python -m pip check
  git diff --check
  git status --short
  ```

- **Definition of Done:** CI runs from a clean checkout; required checks fail the pipeline; no empty test gate exists; secrets/static findings are actionable; local and CI commands match.

### S001-07 — Implement migration runner and schema baseline

- **Task ID:** S001-07
- **Related backlog IDs:** `DB-001`, `MAIN-001`
- **Purpose:** Represent the current schema as an explicit versioned baseline and provide a runner that operates only on supplied database paths.
- **Files that will probably be modified:** `migrations/001_baseline.sql`, `gmv_core/migrations.py`, `tests/migrations/test_baseline.py`, fixture schema snapshots, and package metadata for migration resources.
- **Estimated duration:** 90 minutes
- **Risk level:** Critical
- **Rollback strategy:** Delete/recreate only disposable test databases. Revert the task if the baseline does not reproduce current schema. Never run rollback experiments on the live database.
- **Validation commands:**

  ```bash
  python -m pytest -q tests/migrations/test_baseline.py
  python -m pytest -q tests/test_isolation.py
  python -m ruff check gmv_core tests/migrations
  sqlite3 -readonly 09_DATABASE/GMV.db "PRAGMA user_version;"
  git diff --check
  gmv doctor
  gmv status
  gmv object count
  ```

- **Definition of Done:** Migration 001 creates an isolated schema structurally equivalent to the characterized current schema; runner requires an explicit target; live DB hash is unchanged; migration version is queryable in fixtures.

### S001-08 — Prove migration idempotence and rollback/recovery

- **Task ID:** S001-08
- **Related backlog IDs:** `AUTO-002`, `DB-001`
- **Purpose:** Verify empty install, current-shape adoption, repeated invocation, partial-failure behavior, and recovery without touching production.
- **Files that will probably be modified:** `tests/migrations/test_idempotence.py`, `tests/migrations/test_failure_recovery.py`, `tests/migrations/test_upgrade.py`, migration helpers, and sanitized fixture definitions.
- **Estimated duration:** 90 minutes
- **Risk level:** Critical
- **Rollback strategy:** Discard disposable databases and revert migration/test changes. If rollback is not safely supportable, document restore-based recovery rather than pretending rollback exists.
- **Validation commands:**

  ```bash
  python -m pytest -q tests/migrations
  python -m pytest -q tests/migrations --count=3
  python -m pytest -q tests/test_isolation.py
  git diff --check
  gmv doctor
  gmv status
  gmv object count
  ```

- **Definition of Done:** Empty install and current-shape adoption pass; repeated migration is deterministic; injected failure leaves no ambiguous version; recovery path is tested; live database remains byte-for-byte unchanged by tests.

### S001-09 — Define canonical OID contract and validator

- **Task ID:** S001-09
- **Related backlog IDs:** `ARC-004`, `DB-008`
- **Purpose:** Define supported prefixes/types, grammar, normalization, rejection rules, and validator behavior before changing allocation.
- **Files that will probably be modified:** `gmv_core/identity.py`, `tests/identity/test_validation.py`, `tests/fixtures/oids.*`, and one canonical identity contract document/ADR.
- **Estimated duration:** 90 minutes
- **Risk level:** High
- **Rollback strategy:** Revert validator/contract together if existing valid identities are rejected. Do not silently normalize persisted OIDs.
- **Validation commands:**

  ```bash
  python -m pytest -q tests/identity/test_validation.py
  python -m ruff check gmv_core/identity.py tests/identity
  python -m pytest -q tests/characterization/test_schema.py
  git diff --check
  gmv doctor
  gmv status
  gmv object count
  ```

- **Definition of Done:** Every current typed Object validates; malformed prefix/type/case/length inputs fail with typed errors; no existing OID is rewritten; contract has one owner and version.

### S001-10 — Implement transaction-safe OID allocation

- **Task ID:** S001-10
- **Related backlog IDs:** `ARC-004`, `DB-007`, `DB-008`
- **Purpose:** Replace `COUNT(*) + 1` with a monotonic, transaction-safe allocator proven against gaps, rollback, and concurrent creation.
- **Files that will probably be modified:** a new migration such as `migrations/002_oid_sequences.sql`, `gmv_core/identity.py`, `gmv_core/repositories/identity.py`, `10_API/import_service.py` or its narrow adapter, and `tests/identity/test_allocation.py`.
- **Estimated duration:** 90 minutes
- **Risk level:** Critical
- **Rollback strategy:** Revert the allocator integration and migration in isolated development. Before any future live rollout, require Sprint 002 verified backup; never restore by manually decrementing sequences.
- **Validation commands:**

  ```bash
  python -m pytest -q tests/identity/test_allocation.py tests/migrations
  python -m pytest -q tests/identity/test_allocation.py --count=10
  rg -n "COUNT\(\*\).*Resource|next_resource_oid" 10_API gmv_core
  python -m pytest -q tests/test_isolation.py
  git diff --check
  gmv doctor
  gmv status
  gmv object count
  ```

- **Definition of Done:** Sequential, gap, rollback, and concurrent tests produce no duplicate/reused OIDs; allocation and Object creation share a transaction; importer no longer uses row count; live DB is not migrated in Sprint 001.

### S001-11 — Add shared CLI validation and error primitives

- **Task ID:** S001-11
- **Related backlog IDs:** `CLI-003`, `ARC-004`, `MAIN-001`
- **Purpose:** Introduce typed validation for OIDs, numeric IDs, paths, statuses, and slugs plus one exit/error taxonomy, without redesigning the whole CLI or changing unrelated outputs.
- **Files that will probably be modified:** `gmv_core/validation.py`, `gmv_core/errors.py`, `tests/cli/test_validation.py`, selected narrow adapters in `10_API/`, and minimally `11_CLI/gmv` if needed to preserve exit propagation.
- **Estimated duration:** 90 minutes
- **Risk level:** High
- **Rollback strategy:** Revert one validator integration at a time; preserve characterized valid-input behavior and exit codes until a separately approved contract change.
- **Validation commands:**

  ```bash
  python -m pytest -q tests/cli/test_validation.py tests/characterization/test_cli.py
  python -m ruff check gmv_core tests/cli
  gmv object show INVALID-OID; test $? -ne 0
  gmv queue show not-a-number; test $? -ne 0
  git diff --check
  gmv doctor
  gmv status
  gmv object count
  ```

- **Definition of Done:** Invalid inputs fail before SQL/filesystem access; errors have stable type/message/exit status; valid command characterization remains unchanged; errors use the correct stream; full Bash CLI replacement and JSON output remain deferred.

### S001-12 — Run Sprint acceptance and governance closeout

- **Task ID:** S001-12
- **Related backlog IDs:** All Sprint 001 IDs
- **Purpose:** Prove global acceptance, reconcile implementation status, record evidence, and close only backlog items whose definitions are actually met.
- **Files that will probably be modified:** `GMV_BACKLOG.md`, `GMV_SPRINT.md`, `GMV_CHANGELOG.md`, implementation-status matrices/ADRs, and no source unless a failing check requires a separate preceding fix task.
- **Estimated duration:** 60 minutes
- **Risk level:** Medium
- **Rollback strategy:** Do not mark the Sprint complete if any gate fails. Revert only inaccurate closeout documentation and reopen the responsible task.
- **Validation commands:**

  ```bash
  python -m pytest -q
  python -m ruff check .
  python -m pip check
  gmv doctor
  gmv status
  gmv object count
  git diff --check
  git status --short
  ```

- **Definition of Done:** Every global acceptance criterion in section 6 is evidenced; all 13 Sprint backlog IDs have an explicit completed or carried-forward status; documentation matches reality; working tree is clean after the final atomic commit.

## 4. Safe execution order

Execute tasks in exactly this order:

1. **S001-00 — Protected baseline.** Stop if active writers cannot be separated or pre-existing changes cannot be attributed.
2. **S001-01 — Core Integrity/no-cache gates.** Correct priorities before adding infrastructure.
3. **S001-02 — Packaging/runtime contract.** Make tool versions reproducible without changing runtime behavior.
4. **S001-03 — Python foundation package.** Add inert, import-safe shared primitives only.
5. **S001-04 — Isolated test harness.** Prove tests cannot write the live Core.
6. **S001-05 — Characterization tests.** Freeze current behavior before refactoring.
7. **S001-06 — Automated CI/quality/security gates.** Make existing evidence mandatory.
8. **S001-07 — Migration runner/baseline.** Operate only against disposable databases.
9. **S001-08 — Migration idempotence/recovery.** Prove failure safety before identity migrations.
10. **S001-09 — OID contract/validator.** Finalize identity rules before allocation changes.
11. **S001-10 — OID allocator.** Implement and test allocation without live rollout.
12. **S001-11 — CLI validation/errors.** Reuse the finalized identity and package primitives.
13. **S001-12 — Acceptance/closeout.** Close only after every preceding task passes.

### Per-task repository rule

At the end of every implementation task:

1. run task-specific tests;
2. run the common validation commands;
3. inspect `git diff --check` and `git status --short`;
4. confirm the live database hash did not change when the task is test/tooling-only;
5. fix failures before continuing;
6. create one atomic commit only after validation passes;
7. start the next task from a clean working tree.

If scheduled processes create new runtime changes during a task, stop and separate those changes. Do not stage them with Sprint work.

## 5. Validation strategy

### Common validation after every task

```bash
python -m pytest -q
python -m ruff check .
gmv doctor
gmv status
gmv object count
git diff --check
git status --short
```

Until `ruff` and tests exist, tasks S001-00 through S001-02 run the available subset. From S001-04 onward, the complete test command is mandatory.

### Task-by-task validation matrix

| Task | Expected output | Possible failure modes | Recovery procedure |
|---|---|---|---|
| S001-00 | Attributed Git changes, recorded DB hash, known active writers, readable health output. | Scheduler mutates DB/logs during capture; unknown files appear; DB integrity fails. | Stop. Establish maintenance window; preserve output; do not clean, stage, or restore unknown changes automatically. |
| S001-01 | Governance diff contains only phase/gate/no-cache corrections; GMV read checks still pass. | Documentation claims implementation not present; unrelated documents change. | Revert inaccurate lines, re-read roadmap/backlog, and narrow the task. |
| S001-02 | Package builds; pinned tools install; existing `gmv` remains callable. | Unsupported Python metadata; dependency conflict; entrypoint shadows current CLI. | Revert metadata/entrypoint portion, pin compatible versions, keep current CLI authoritative. |
| S001-03 | Package imports with no output, directory creation, or database access. | Import-time I/O; circular import; HOME-dependent failure. | Revert offending module; move I/O behind explicit functions and injected configuration. |
| S001-04 | Isolation tests pass; before/after live DB hashes match. | Fixture resolves real HOME; subprocess ignores injected HOME; cleanup is nondeterministic. | Stop tests, inspect paths, strengthen guard, discard only temporary state, rerun from clean baseline. |
| S001-05 | Characterization suite deterministically captures schema/CLI behavior. | Sensitive data enters fixtures; brittle timestamps/paths; snapshot updated to hide regression. | Sanitize fixtures, normalize nondeterminism, review expected changes manually. |
| S001-06 | Local checks and CI produce the same pass/fail result. | Tool versions drift; CI lacks dependencies; blanket suppressions hide findings. | Pin versions, reproduce locally, scope each suppression with owner/reason/expiry. |
| S001-07 | Disposable DB matches characterized schema and reports migration version. | Baseline omits view/index; runner defaults to live path; partial migration. | Block merge; require explicit target; rebuild fixture; compare schema structurally. |
| S001-08 | Empty/adopt/reapply/failure/recovery tests all pass repeatedly. | Reapply duplicates data; version advances after failure; rollback loses rows. | Fix transaction/version ordering; use restore-based recovery if safe down migration is impossible. |
| S001-09 | Current OIDs validate; malformed OIDs fail with typed errors. | Existing identity rejected; validator silently normalizes; prefix/type map ambiguous. | Reopen contract decision; do not rewrite data; add explicit compatibility case only if approved. |
| S001-10 | Allocation tests show zero duplicates/reuse under gap, rollback, and concurrency. | Lock errors; sequence advances incorrectly; importer still uses `COUNT(*)`. | Fix transaction/locking; keep old runtime path until isolated tests pass; never patch live sequences manually. |
| S001-11 | Invalid inputs fail before I/O; valid characterization remains stable. | Exit codes change; error leaks to stdout; validation occurs after SQL/path access. | Revert one adapter, fix shared validation order, rerun command contract tests. |
| S001-12 | Full suite passes, docs match evidence, status is clean. | A backlog item lacks proof; generated files dirty status; live DB changed unexpectedly. | Do not close Sprint; attribute changes, restore through approved process if required, reopen failing task. |

### Live database protection check

For every task that should not mutate production, wrap validation with a stable baseline check during a writer-free maintenance window:

```bash
BEFORE="$(shasum -a 256 09_DATABASE/GMV.db)"
python -m pytest -q
AFTER="$(shasum -a 256 09_DATABASE/GMV.db)"
test "$BEFORE" = "$AFTER"
```

A hash mismatch is a stop condition. Do not assume the test caused it until scheduler writers are ruled out.

## 6. Global acceptance criteria

Sprint 001 is complete only when all conditions below are true.

### Repository and runtime

- A fresh checkout can install the declared development environment and run tests.
- Supported Python and SQLite versions are explicit.
- The `gmv_core` package imports without side effects.
- Existing operational CLI commands remain available.
- The working tree is clean after validation and generated runtime output is not mixed with Sprint changes.

### Test and CI foundation

- Tests use disposable GMV homes/databases only.
- A hard guard prevents writes to the live GMV database.
- Schema and CLI characterization tests are deterministic.
- CI runs tests, lint/static analysis, dependency checks, secrets checks, and whitespace checks.
- Deliberate test, lint, migration, or secret failures make CI fail.

### Migration foundation

- The current schema has one reviewed baseline migration.
- Migration runner requires an explicit database target.
- Empty install, current-shape adoption, reapplication, injected failure, and recovery are tested.
- Migration version is deterministic and no live migration was performed in Sprint 001.

### Identity foundation

- Canonical OID grammar and prefix/type map are documented and versioned.
- All current typed Objects pass validation.
- Invalid OIDs fail before persistence access.
- Resource allocation no longer depends on `COUNT(*) + 1` in the implemented path.
- Sequential, gap, rollback, and concurrency tests produce zero duplicate or reused OIDs.

### CLI foundation

- Shared validation exists for OIDs, numeric IDs, statuses, paths, and slugs in the Sprint scope.
- Invalid input has stable typed errors and nonzero exit codes.
- Existing valid-input behavior remains characterized.
- JSON output, full CLI rewrite, and broader UX work remain correctly deferred.

### Governance

- Active phase is Core Integrity.
- Reasoning and autonomous workflow work is blocked by explicit entry gates.
- No application cache was introduced.
- Every Sprint 001 backlog ID has evidence and an accurate status.
- Changelog/Sprint/Backlog updates describe actual implementation, not file existence.

## 7. Metrics

### Reliability

| Metric | Sprint 001 target |
|---|---:|
| Required CI jobs passing on the Sprint branch | 100% |
| Live database writes caused by tests | 0 |
| Live database hash changes during isolated test runs | 0 |
| Migration baseline reapplication failures in repeated test runs | 0 |
| Duplicate/reused OIDs in allocation stress tests | 0 |
| Tasks merged with failing common validation | 0 |

### Maintainability

| Metric | Sprint 001 target |
|---|---:|
| Supported runtime versions documented | 100% |
| New foundation modules with import-time I/O | 0 |
| New direct SQLite connection sites outside the migration/test boundary | 0 |
| Unowned lint/static suppressions | 0 |
| Sprint tasks delivered as independently reviewable changes | 13 of 13 |
| Tasks that leave unrelated files staged/modified | 0 |

### Observability

Sprint 001 does not implement the Sprint 002 observability system. Its measurable foundation is:

| Metric | Sprint 001 target |
|---|---:|
| CI checks with named pass/fail output | 100% |
| Test failures identifying task/domain and fixture | 100% |
| Migration failures reporting target, version, and failed step | 100% |
| OID validation/allocation failures using typed errors | 100% |
| Silent test/migration failures | 0 |

### Testability

| Metric | Sprint 001 target |
|---|---:|
| Tests requiring the live GMV database | 0 |
| Tests requiring Dropbox or LaunchAgents | 0 |
| Characterized schema/view/index objects relevant to current DB | 100% |
| Critical branch coverage for migration versioning, OID validation, and OID allocation | 100% |
| Repeated full-suite runs with nondeterministic failures | 0 of 10 |
| Fresh-checkout test execution documented and proven | 1 successful proof minimum |

### Technical debt reduction

| Metric | Sprint 001 target |
|---|---:|
| Sprint 001 backlog IDs completed with evidence | 13 of 13 |
| Count-based Resource OID allocation paths remaining | 0 in the migrated implementation path |
| Schema version in isolated migrated databases | Greater than 0 |
| Automated quality/security gates added | Tests, lint/static, dependency, secrets, whitespace |
| Application caches introduced | 0 |
| Intelligence/autonomy items started before gates | 0 |
| Unsupported completion claims added | 0 |

### Sprint decision threshold

Sprint 001 passes only if every Critical/High target above is met. Medium/Low findings may be carried forward only when they are documented, owned, do not weaken database/test isolation, and do not unblock Sprint 002 through a false exception.
