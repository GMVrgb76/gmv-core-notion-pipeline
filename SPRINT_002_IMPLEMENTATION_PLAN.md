# Sprint 002 Implementation Plan

Status: Approved on 2026-07-06 through S002-00. The dependency decisions,
acceptance scope, Wave boundaries, and Reliability-only constraint below are the
implementation authority for Sprint 002.

## S002-00 Approval and Protected Baseline

- **Approval:** The seven bounded interpretations in Section 3 are approved.
- **Authority:** Sprint 002 may implement only the Reliability work and sequence
  defined by this plan. No live migration, Dossier, Comparable, Valuation,
  Genesis, Canonization, Bootstrap, or later-Sprint work is authorized.
- **Baseline time:** `2026-07-06T12:03:12+0200`.
- **Repository:** branch `main`; HEAD `729cc80`; no Git index lock.
- **Live database SHA-256:**
  `b0f403d9c47311a307a146c782fb6b2e58ea68bac7eb44d756e05084b37f77f0`.
- **Live database checks:** `PRAGMA integrity_check` returned `ok`;
  `PRAGMA foreign_key_check` returned no rows; `PRAGMA user_version` returned
  `0`.
- **Inherited tracked runtime state:** `.DS_Store`, three files under
  `04_LOGS/`, and `09_DATABASE/GMV.db`. These remain preserved, unstaged, and
  outside Sprint commits.
- **Loaded scheduled writers:** `com.gmv.dailylog` at 06:30,
  `com.gmv.morningbrief` at 07:00, and `com.gmv.knowledge` at 07:45.
  `com.gmv.apprentice` is installed for 02:15 but was not loaded at baseline.
  No LaunchAgent change is authorized.
- **Maintenance-window rule:** a task requiring stable live state must obtain a
  separately approved writer-free window, capture fingerprints immediately
  before and after, and stop on unexpected mutation. S002-01 requires no live
  database or runtime write and therefore no maintenance window.
- **RPO/RTO decision owner:** the human GMV Project Owner. Numeric objectives
  and recovery acceptance remain the explicit scope of S002-18; agents must not
  invent them earlier.
- **Consistency check:** the backlog, V2 execution roadmap, Sprint 001 final
  handoff, and this plan agree that `CLI-016` is the first implementation slice
  and that Sprint 002 performs no live schema migration.

## 1. Sprint Objective

Make operational truth, process execution, runtime-state separation, security,
and full-system recovery credible before database consolidation or automation.
Sprint 002 must ensure that failures are visible, processes are bounded, backups
can be restored, and mutable state no longer contaminates source review.

## 2. Scope

The roadmap includes 23 backlog items:

`ARC-008`, `ARC-011`, `DB-023`, `SEC-001`, `SEC-004`, `SEC-005`, `SEC-007`,
`SEC-009`, `SEC-010`, `SEC-012`, `MAIN-010`, `DOC-008`, `DOC-010`, `AUTO-009`,
`AUTO-010`, `AUTO-011`, `CLI-001`, `CLI-002`, `CLI-013`, `CLI-016`, `ROAD-006`,
`ROAD-007`, and `ROAD-009`.

No Dossier, Comparable, Valuation, Sprint 003 schema consolidation, or live
migration belongs to this Sprint.

## 3. Planning Constraints and Dependency Decisions

The backlog contains cycles and later-Sprint dependencies. Implementation must
not begin until the following bounded interpretations are approved:

1. `SEC-001 ↔ ARC-008`: inventory and pin current entrypoints first; then remove
   shell execution; then complete reproducible packaging. `ARC-003` lifecycle
   management remains Sprint 003.
2. `ARC-011 ↔ MAIN-010/SEC-004`: approve the source/runtime classification and
   layout first; then stop tracking future mutable state. Historical rewriting is
   explicitly separate and requires approval.
3. `AUTO-010 ↔ SEC-005/SEC-009`, with later `DB-012`: define permissions,
   classification, RPO/RTO, and backup manifest first. V1 verifies current
   Resource references and files; immutable custody redesign remains Sprint 004.
4. `CLI-001 ↔ AUTO-011`: implement a reusable diagnostic runner first, expose it
   through `doctor --strict`, then add schedulable policy. Checks requiring
   `DB-002` are marked unavailable rather than fabricated.
5. `CLI-016 → MAIN-002`: the roadmap explicitly authorizes transitional Bash
   hardening before replacement. It must not become a Bash redesign.
6. `SEC-012 → DB-004/ARC-002`: Sprint 002 can specify threat model, log controls,
   and tamper detection for operational artifacts. Append-only canonical Event
   enforcement remains Sprint 003 and the full backlog item stays carried.
7. `SEC-010 → ARC-007`: existing static/dependency/secret gates can be completed
   and governed now; Plugin capability enforcement remains later work.

## 4. Execution Graph

```text
S002-00 Baseline and dependency approval
  |
  +--> S002-01 CLI-016 strict shell
  |
  +--> S002-02 ARC-008 inventory
         +--> S002-03 SEC-001 no shell=True
                +--> S002-04 SEC-007 bounded processes
                       +--> S002-05 ARC-008 reproducible boundary
  |
  +--> S002-06 AUTO-009 observability contract
         +--> S002-07 DB-023 stale artifacts
         +--> S002-08 CLI-001 strict doctor
                +--> S002-09 AUTO-011 scheduled health
                       +--> S002-10 CLI-002 evidence-based status
                              +--> S002-11 ROAD-009 operations gate
  |
  +--> S002-12 ARC-011 layout decision
         +--> S002-13 MAIN-010 mutable-state tracking
         +--> S002-14 SEC-004 data/Git policy
                +--> S002-15 ROAD-006 threat/retention plan
                +--> S002-16 SEC-010 security policy
                +--> S002-17 SEC-012 audit-integrity plan
  |
  +--> S002-18 ROAD-007 RPO/RTO
         +--> S002-19 SEC-005 permissions
         +--> S002-20 AUTO-010 backup/restore
                +--> S002-21 CLI-013 recovery commands
                +--> S002-22 SEC-009 backup protection
                       +--> S002-23 DOC-008 snapshot alignment

S002-11 + S002-15 + S002-23 --> S002-24 DOC-010 operations governance
S002-01..24 --> Sprint 002 Review
```

## 5. Common Task Contract

Every task is one implementation unit and one atomic commit. Before editing:

```bash
git status --short --untracked-files=all
shasum -a 256 09_DATABASE/GMV.db
test ! -e .git/index.lock
```

Every source task runs, at minimum:

```bash
PATH="$PWD/.venv/bin:$PATH" python -m pytest -q
PATH="$PWD/.venv/bin:$PATH" python -m ruff check .
PATH="$PWD/.venv/bin:$PATH" python -m pip check
gmv doctor
gmv status
gmv object count
git diff --check
git status --short
```

The before/after live database hashes must match unless a separately approved task
explicitly authorizes live mutation. This plan authorizes no live schema change.

Common recovery: revert only the current atomic task, preserve diagnostics, rerun
the previous committed validation, and never clean inherited runtime artifacts.
Operational Recovery applies only after implementation and validation succeed.

## 6. Work Breakdown

### S002-00 — Protected Reliability Baseline

- **Backlog:** All Sprint 002 IDs.
- **Objective:** Attribute active writers and artifacts, approve the seven bounded
  dependency decisions above, define maintenance windows, and record RPO/RTO
  decision owners before implementation.
- **Order/dependencies:** First; Sprint 001 handoff only.
- **Validation:** Git status/index/HEAD; database hash, integrity, foreign keys,
  user version; active writer inventory; canonical-doc consistency.
- **Recovery:** Read-only task; stop if any command writes.
- **Expected commit:** One governance commit only if the approved decisions require
  canonical documentation; otherwise no commit.
- **Expected Wave:** W005.

### S002-01 — Strict Transitional Shell

- **Backlog:** `CLI-016`.
- **Objective:** Add guarded strict behavior, dependency checks, and explicit
  optional-command handling without redesigning the dispatcher.
- **Order/dependencies:** After S002-00; roadmap-authorized transitional slice
  despite later `MAIN-002`.
- **Validation:** Shell syntax/static checks; regression tests for failed SQLite,
  missing dependencies, optional commands, existing valid CLI output, and exit
  propagation; common task contract.
- **Recovery:** Revert strict-mode changes if characterized valid commands change;
  retain explicit guards rather than disabling strictness globally.
- **Expected commit:** `fix: enforce strict transitional CLI behavior`.
- **Expected Wave:** W005.

### S002-02 — Inventory Legacy Engine Boundary

- **Backlog:** `ARC-008` (inventory slice).
- **Objective:** Record exact Morning Brief, Daily Log, and Market Engine source,
  versions, entrypoints, environments, data access, and ownership without copying
  external code or changing LaunchAgents.
- **Order/dependencies:** After S002-00; precedes SEC-001.
- **Validation:** Every registered legacy service resolves to a versioned inventory
  record or explicit unavailable state; no external/runtime file changed.
- **Recovery:** Documentation-only revert.
- **Expected commit:** `docs: inventory legacy engine boundaries`.
- **Expected Wave:** W005.

### S002-03 — Remove Shell Command Construction

- **Backlog:** `SEC-001`.
- **Objective:** Replace joined command strings and `shell=True` with validated
  argument vectors while preserving approved compatibility behavior.
- **Order/dependencies:** S002-01, S002-02.
- **Validation:** Injection/metacharacter tests, exact argv tests, spaces/unicode
  path tests, characterized success/failure, Ruff security gate, common checks.
- **Recovery:** Revert the compatibility adapter; never restore shell execution as
  an undocumented fallback.
- **Expected commit:** `security: remove shell command execution`.
- **Expected Wave:** W005.

### S002-04 — Bound Legacy Processes

- **Backlog:** `SEC-007`.
- **Objective:** Add timeout, cancellation, process-group termination, clean
  environment allowlist, and bounded stdout/stderr capture.
- **Order/dependencies:** S002-03.
- **Validation:** Hanging parent/child, oversized output, cancellation, timeout,
  environment leakage, and normal-exit tests on disposable processes.
- **Recovery:** Revert process wrapper atomically; kill only task-owned test
  processes and preserve timeout diagnostics.
- **Expected commit:** `security: bound legacy process execution`.
- **Expected Wave:** W006.

### S002-05 — Reproducible Legacy Entry Points

- **Backlog:** `ARC-008` (completion slice).
- **Objective:** Pin approved local release entrypoints and remove runtime
  dependence on uncontrolled Dropbox execution. LaunchAgent changes are excluded
  unless separately authorized.
- **Order/dependencies:** S002-02 through S002-04; `ARC-003` lifecycle features
  remain carried to Sprint 003.
- **Validation:** Clean-checkout path resolution, version/inventory match,
  deterministic environment, no Dropbox executable target, compatibility tests.
- **Recovery:** Restore the last committed local entrypoint mapping; do not fall
  back to arbitrary external code.
- **Expected commit:** `refactor: pin reproducible legacy engine entrypoints`.
- **Expected Wave:** W006.

### S002-06 — Structured Observability Contract

- **Backlog:** `AUTO-009`.
- **Objective:** Define run/correlation IDs, append-only structured operational
  records, error taxonomy, artifact references, freshness, and first-response
  runbook contracts.
- **Order/dependencies:** S002-00; implementation integration follows S002-04/05.
- **Validation:** Schema fixtures, append behavior, concurrent run IDs, redaction,
  bounded fields, missing artifact, and log-rotation tests.
- **Recovery:** Revert one logging adapter; preserve legacy logs untouched and do
  not fabricate missing records.
- **Expected commit:** `feat: add structured operational run records`.
- **Expected Wave:** W007.

### S002-07 — Reconcile Stale Artifact Paths

- **Backlog:** `DB-023`.
- **Objective:** Represent missing historical outputs as explicitly unavailable
  and detect future missing artifact references without fabricating files.
- **Order/dependencies:** S002-06 and approved migration/data-correction plan if
  persistence changes are required.
- **Validation:** Disposable-copy migration/reconciliation tests, missing/present
  path checks, Event/audit evidence, live database unchanged.
- **Recovery:** Restore disposable fixtures; no live row patching.
- **Expected commit:** `fix: make missing run artifacts explicit`.
- **Expected Wave:** W007.

### S002-08 — Truthful Strict Doctor

- **Backlog:** `CLI-001`.
- **Objective:** Build one diagnostic runner that aggregates named checks and
  returns nonzero for required failures; expose human and machine-stable results.
- **Order/dependencies:** S002-01, S002-06. Use current package boundary; full
  executable Core consolidation remains Sprint 003.
- **Validation:** Induced database/query/path/schema/artifact/permission failures;
  multiple simultaneous failures; clean fixture; output and exit contracts.
- **Recovery:** Revert checks individually; never restore unconditional success.
- **Expected commit:** `feat: add strict evidence-based doctor`.
- **Expected Wave:** W007.

### S002-09 — Schedulable Health Policy

- **Backlog:** `AUTO-011`.
- **Objective:** Define required/degraded/unavailable checks, stale thresholds,
  structured output, scheduling contract, and nonzero failure behavior.
- **Order/dependencies:** S002-08; backup checks complete after S002-20. Foreign-key
  enforcement requiring `DB-002` remains unavailable, not simulated.
- **Validation:** Scheduler-safe no-interaction execution, stale-service fixtures,
  unavailable-check semantics, timeout, structured output, exit aggregation.
- **Recovery:** Disable only the new scheduled adapter; retain strict diagnostics.
- **Expected commit:** `feat: make health checks schedulable`.
- **Expected Wave:** W007.

### S002-10 — Evidence-Based Status

- **Backlog:** `CLI-002`.
- **Objective:** Derive ready/degraded/failed state from diagnostic evidence and
  freshness policy; remove unconditional `SYSTEM READY`.
- **Order/dependencies:** S002-06, S002-08, S002-09.
- **Validation:** Ready/degraded/failed fixtures, query failure, stale service,
  pending queue, stale backup, stable output, nonzero failed-state exit.
- **Recovery:** Revert presentation adapter while preserving diagnostic runner;
  never reintroduce unconditional readiness.
- **Expected commit:** `feat: make status evidence based`.
- **Expected Wave:** W007.

### S002-11 — Operations and Observability Gate

- **Backlog:** `ROAD-009`.
- **Objective:** Define health indicators, failure budgets, alert ownership, and
  runbooks for service, ingestion, database, artifact, and backup failures.
- **Order/dependencies:** S002-06 through S002-10.
- **Validation:** Tabletop scenarios map every failure to a signal, owner, first
  command, escalation, and recovery evidence; no invented monitoring capability.
- **Recovery:** Documentation-only revert.
- **Expected commit:** `docs: establish reliability operations gate`.
- **Expected Wave:** W007.

### S002-12 — Source/Runtime Layout Decision

- **Backlog:** `ARC-011`.
- **Objective:** Classify source, configuration, governance, fixtures, live state,
  logs, reports, caches, snapshots, and external Resources; define ownership and
  migration sequence without moving data yet.
- **Order/dependencies:** S002-00.
- **Validation:** Every current top-level path has one class/owner/backup policy;
  proposed paths do not touch Dropbox or LaunchAgents.
- **Recovery:** Documentation-only revert.
- **Expected commit:** `docs: define source and runtime boundaries`.
- **Expected Wave:** W008.

### S002-13 — Stop Tracking Mutable State

- **Backlog:** `MAIN-010`.
- **Objective:** Keep future database/log/report/inventory/snapshot mutations out
  of source diffs while retaining sanitized fixtures and explicit runtime paths.
- **Order/dependencies:** S002-12. Existing data removal and history rewriting need
  separate approval and are not implicit.
- **Validation:** Disposable runtime produces no source diff; fresh checkout tests
  run with fixtures; tracked-file classification audit; backup still covers state.
- **Recovery:** Revert index/ignore/path changes; never delete runtime files.
- **Expected commit:** `chore: separate mutable runtime artifacts from source`.
- **Expected Wave:** W008.

### S002-14 — Runtime Data and Git Policy

- **Backlog:** `SEC-004`.
- **Objective:** Define sensitivity classes, prohibit new sensitive runtime data in
  Git, scan tracked content, and propose—but do not silently perform—history repair.
- **Order/dependencies:** S002-12, S002-13.
- **Validation:** Classification audit, secret/path fixture tests, no newly tracked
  protected artifacts, explicit report of historical exposure.
- **Recovery:** Revert policy/scanner config; do not restore sensitive artifacts to
  tracking merely for compatibility.
- **Expected commit:** `security: enforce runtime data Git policy`.
- **Expected Wave:** W008.

### S002-15 — Privacy, Security, and Retention Plan

- **Backlog:** `ROAD-006`.
- **Objective:** Produce threat model, data classes, access/retention rules, and
  security release gates for current single-user operation and future domains.
- **Order/dependencies:** S002-12 through S002-14, S002-16.
- **Validation:** Every protected data class has owner, location, access, retention,
  deletion exception, backup, and incident handling; gaps remain explicit.
- **Recovery:** Documentation-only revert.
- **Expected commit:** `docs: establish privacy security and retention controls`.
- **Expected Wave:** W008.

### S002-16 — Security Tooling and Policy

- **Backlog:** `SEC-010`.
- **Objective:** Close governance around existing Ruff, dependency, and secret
  gates; define exception ownership/expiry and security release criteria.
- **Order/dependencies:** Sprint 001 CI, S002-14. Plugin capability controls remain
  deferred until `ARC-007`.
- **Validation:** Deliberate secret, unsafe subprocess, dependency, and expired
  exception fixtures fail CI; baseline cannot silently absorb new findings.
- **Recovery:** Revert policy/tool configuration only after proving prior quality
  gate still passes.
- **Expected commit:** `security: govern automated security gates`.
- **Expected Wave:** W008.

### S002-17 — Audit Integrity Controls

- **Backlog:** `SEC-012` (Sprint 002 slice; item remains carried).
- **Objective:** Protect operational log writes, define tamper-evidence threat
  model, and specify the future append-only Event requirement.
- **Order/dependencies:** S002-06, S002-14. Canonical Event enforcement waits for
  `DB-004` and `ARC-002` in Sprint 003.
- **Validation:** Append-only writer tests where supported, permission checks,
  truncation/tamper detection fixtures, explicit unsupported guarantees.
- **Recovery:** Revert operational controls; preserve original evidence and never
  rewrite canonical Events.
- **Expected commit:** `security: add operational audit integrity controls`.
- **Expected Wave:** W008.

### S002-18 — Disaster-Recovery Objectives

- **Backlog:** `ROAD-007`.
- **Objective:** Approve RPO, RTO, backup scope, retention, restore frequency,
  recovery owner, and acceptance evidence before backup implementation.
- **Order/dependencies:** S002-00, S002-12, business approval.
- **Validation:** Tabletop loss scenarios cover database, source/config, governance,
  managed files, external references, credentials, and complete-host loss.
- **Recovery:** Documentation-only revert; no backup implementation before approval.
- **Expected commit:** `docs: define GMV recovery objectives`.
- **Expected Wave:** W009.

### S002-19 — Restrictive Data Permissions

- **Backlog:** `SEC-005`.
- **Objective:** Create databases, dumps, manifests, and recovery artifacts with
  restrictive modes and verify permissions through strict diagnostics.
- **Order/dependencies:** S002-12, S002-18; precedes backup creation despite the
  backlog's circular dependency on AUTO-010.
- **Validation:** umask/mode tests, existing-file warning behavior, atomic-create
  tests, multi-user-readable failure fixture; no live chmod without authorization.
- **Recovery:** Revert creation policy; restore only task-owned fixture modes.
- **Expected commit:** `security: restrict database and backup permissions`.
- **Expected Wave:** W009.

### S002-20 — Verified Full-System Backup and Restore

- **Backlog:** `AUTO-010`.
- **Objective:** Create an atomic backup with versioned manifest, hashes, source,
  configuration, governance, database, runtime metadata, and current Resource
  verification; prove isolated restore.
- **Order/dependencies:** S002-12, S002-14, S002-18, S002-19. `DB-012` custody
  redesign is not pulled forward; current external Resources are verified and
  reported as external dependencies.
- **Validation:** Interrupted creation leaves no valid backup; checksum corruption
  fails; isolated restore passes SQLite integrity/version/object counts and file
  manifest; retention dry run; no live overwrite.
- **Recovery:** Delete only incomplete task-owned temporary backup fixtures; restore
  testing targets an isolated directory, never live state.
- **Expected commit:** `feat: add verified full-system backup and restore`.
- **Expected Waves:** W009–W010 due to size; split manifest/create and verify/restore
  into separate atomic tasks if implementation exceeds one coherent unit.

### S002-21 — Snapshot Verify and Restore Commands

- **Backlog:** `CLI-013`.
- **Objective:** Expose inspect, verify, and isolated restore-check operations over
  the AUTO-010 contract before prune or destructive restore.
- **Order/dependencies:** S002-20.
- **Validation:** Valid/corrupt/missing manifest, wrong schema, isolated restore,
  human output, exit codes; no command may overwrite live state in Sprint 002.
- **Recovery:** Revert CLI adapter; keep backup format/API intact.
- **Expected commit:** `feat: add snapshot verification and restore checks`.
- **Expected Wave:** W010.

### S002-22 — Protect Backups and Inventories

- **Backlog:** `SEC-009`.
- **Objective:** Apply classification, redaction, retention, access controls, and
  optional approved encryption to backup and inventory artifacts.
- **Order/dependencies:** S002-14, S002-18 through S002-21.
- **Validation:** Sensitive-field fixtures, redaction determinism, key-unavailable
  fail-closed behavior, retention dry run, permission diagnostics.
- **Recovery:** Revert protection adapter; never decrypt or weaken existing backup
  artifacts silently.
- **Expected commit:** `security: protect backup and inventory artifacts`.
- **Expected Wave:** W010.

### S002-23 — Align Snapshot Contract

- **Backlog:** `DOC-008`.
- **Objective:** Make terminology distinguish database dump from verified
  full-system backup and document the exact manifest/restore guarantees.
- **Order/dependencies:** S002-20 through S002-22.
- **Validation:** CLI help, versioning policy, architecture, runbook, and tests use
  consistent terms; no capability claim exceeds implementation.
- **Recovery:** Documentation-only revert.
- **Expected commit:** `docs: align snapshot and backup contracts`.
- **Expected Wave:** W010.

### S002-24 — Operations and Data-Governance Closeout

- **Backlog:** `DOC-010`.
- **Objective:** Publish approved classification, retention, RPO/RTO, backup,
  incident, compatibility, and failure-response documentation and reconcile all
  Sprint 002 statuses.
- **Order/dependencies:** S002-11, S002-15, S002-18, S002-23.
- **Validation:** Governance cross-reference audit; every runbook command tested in
  a disposable environment; backlog items explicitly completed or carried.
- **Recovery:** Revert inaccurate closeout claims; do not close Sprint on failed
  evidence.
- **Expected commit:** `docs: close Sprint 002 reliability governance`.
- **Expected Wave:** W010.

## 7. Expected Waves

| Wave | Goal | Tasks | Expected commits |
|---|---|---|---:|
| W005 | Baseline, dependency approval, strict shell, command safety | S002-00–03 | 3–4 |
| W006 | Bounded and reproducible legacy execution | S002-04–05 | 2 |
| W007 | Observability, strict health, truthful status | S002-06–11 | 6 |
| W008 | Runtime/source separation and security governance | S002-12–17 | 6 |
| W009 | Recovery objectives, permissions, backup creation | S002-18–20 | 3–4 |
| W010 | Verify/restore CLI, backup protection, docs, review | S002-21–24 | 4 |

Expected total: 24–26 atomic commits, depending on whether S002-00 needs a commit
and whether AUTO-010 is split at its natural create/restore boundary.

## 8. Sprint Acceptance Criteria

- All implementation and quality tests pass from a clean checkout.
- Required command/query/path/process failures produce nonzero strict health.
- Status never reports ready when required evidence is failed or stale.
- No compatibility path uses `shell=True`; processes are bounded and cancellable.
- Mutable runtime state no longer creates ordinary source diffs.
- Backup manifest and checksums are atomic and permission-restricted.
- Isolated restore proves database integrity, schema version, object counts,
  manifest integrity, and current Resource-reference status.
- RPO/RTO, retention, classification, incident response, and runbooks are approved.
- Live database schema/content is unchanged unless a separately approved data task
  provides migration, backup, and restore evidence.
- Every Sprint backlog item is explicitly completed or carried; dependency-bound
  items are not overstated.
- Repository status is genuinely clean or every remaining operational exception is
  removed before Sprint closeout. Attribution alone is not a permanent substitute.

## 9. Stopping Conditions

Stop before or during any task if a dependency decision above is unapproved, a
live migration becomes necessary, LaunchAgent/Dropbox mutation is required,
runtime artifacts cannot be separated, validation fails, recovery evidence is
insufficient, or task scope crosses into a later Sprint.
