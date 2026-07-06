# GMV Sprint 002 Review

Status: Closed by explicit Project Owner directive on 2026-07-06, with S002-15
through S002-24 carried as unresolved Reliability work.

## Objectives

Sprint 002 set out to make health reporting, legacy execution, observability,
runtime/source separation, security controls, and recovery credible before later
database consolidation or automation. This closure completed the approved work
through S002-14. It does not claim that the original backup, recovery, retention,
permission, or operational-readiness exit criteria were met.

## Completed tasks

| Task | Backlog | Result | Commit |
|---|---|---|---|
| S002-00 | Sprint baseline | Approved scope, writer inventory, database/repository baseline, and decision ownership | `45edc65` |
| S002-01 | CLI-016 | Strict transitional shell behavior and failure propagation | `1a76f42` |
| S002-02 | ARC-008 inventory | Legacy Engine boundaries and ownership inventoried | `5d21303` |
| S002-03 | SEC-001 | Shell command construction removed | `6b6d757` |
| S002-04 | SEC-007 | Legacy processes bounded, cancellable, and output-limited | `cd51825` |
| S002-05 | ARC-008 completion | Reproducible local legacy entrypoints pinned | `098c00b` |
| S002-06 | AUTO-009 | Structured operational record contract added | `60ef8ef` |
| S002-07 | DB-023 | Missing historical run artifacts represented as unavailable | `bd5deb2` |
| S002-08 | CLI-001 | Strict evidence-based doctor added | `dc39670` |
| S002-09 | AUTO-011 | Scheduler-safe structured health policy added | `9ad1dc7` |
| S002-10 | CLI-002 | Status now derives failed/degraded/ready from evidence | `983862d` |
| S002-11 | ROAD-009 | Reliability operations gate and response matrix established | `cfa9eeb` |
| S002-12 | ARC-011 | Source/runtime boundaries and ownership classified | `c9f4f12` |
| S002-13 | MAIN-010 | Mutable runtime artifacts removed from the current Git index and ignored | `6bd8a8c` |
| S002-14 | SEC-004 | Runtime-data Git policy, scanner, fixtures, historical-exposure report, and Markdown-path regression coverage added | `7a993a3`, `ab051c6` |

## Commit sequence

1. `45edc65` — `docs: approve Sprint 002 reliability baseline`
2. `1a76f42` — `fix: enforce strict transitional CLI behavior`
3. `5d21303` — `docs: inventory legacy engine boundaries`
4. `6b6d757` — `security: remove shell command execution`
5. `cd51825` — `security: bound legacy process execution`
6. `098c00b` — `refactor: pin reproducible legacy engine entrypoints`
7. `60ef8ef` — `feat: add structured operational run records`
8. `bd5deb2` — `fix: make missing run artifacts explicit`
9. `dc39670` — `feat: add strict evidence-based doctor`
10. `9ad1dc7` — `feat: make health checks schedulable`
11. `983862d` — `feat: make status evidence based`
12. `cfa9eeb` — `docs: establish reliability operations gate`
13. `c9f4f12` — `docs: define source and runtime boundaries`
14. `6bd8a8c` — `chore: separate mutable runtime artifacts from source`
15. `7a993a3` — `security: enforce runtime data Git policy`
16. `ab051c6` — `fix: detect private paths in Markdown`

## Validation summary

- Pytest: 100 passed.
- Ruff: passed.
- Dependency check: no broken requirements.
- Runtime-data Git policy: passed with zero findings.
- Secret gate: passed against the reviewed baseline.
- SQLite `integrity_check`: `ok`.
- SQLite `foreign_key_check`: no rows.
- SQLite `user_version`: `0`.
- Live database SHA-256 remained
  `b0f403d9c47311a307a146c782fb6b2e58ea68bac7eb44d756e05084b37f77f0`.
- Runtime directories are ignored; no runtime path remains tracked.
- `tests/fixtures/current_schema.sql` and `tests/fixtures/oids.json` remain tracked.
- Legacy `gmv doctor` passes its compatibility checks.
- Strict doctor and evidence-based status correctly exit nonzero because active
  operational findings remain; they are not counted as passing readiness.

## Regressions

No automated test regression was detected. CLI characterization was deliberately
updated where unconditional `SYSTEM READY` behavior was replaced by structured
evidence. Runtime files remained present on disk after index removal. No database
schema/content drift was observed.

## Unresolved and carried items

| Task | Backlog | Reason carried |
|---|---|---|
| S002-15 | ROAD-006 | Privacy, security, and retention controls were not authorized by this closure mission. |
| S002-16 | SEC-010 | Security-tool exception lifecycle and release governance remain incomplete. |
| S002-17 | SEC-012 | Audit tamper-evidence controls and future canonical Event guarantees remain incomplete. |
| S002-18 | ROAD-007 | RPO/RTO and recovery ownership require explicit human approval. |
| S002-19 | SEC-005 | Restrictive creation modes were not implemented; the live database remains mode `0644`. |
| S002-20 | AUTO-010 | Verified full-system backup and isolated restore do not exist. |
| S002-21 | CLI-013 | Snapshot inspect/verify/restore-check commands do not exist. |
| S002-22 | SEC-009 | Backup/inventory protection and retention remain undefined. |
| S002-23 | DOC-008 | Snapshot versus full-system-backup terminology remains unaligned. |
| S002-24 | DOC-010 | Full Reliability governance closeout criteria remain unmet. |

Active strict-health findings are missing historical run 2 stdout/stderr
artifacts and database mode `0644`. Service freshness evidence is unavailable
because no `04_LOGS/operations.jsonl` exists. Foreign-key enforcement (`DB-002`)
and backup freshness (`S002-20`) remain explicitly unavailable.

## Lessons learned

- Health output must distinguish test success from live operational readiness.
- Git index cleanup is operationally distinct from filesystem deletion and needs
  explicit metadata authority.
- Structured unavailable states are safer than fabricated recovery evidence.
- Secret scanning requires reviewed treatment of deterministic source hashes;
  baselines cannot be refreshed without explaining every new finding.
- Generated/runtime separation materially improves repository signal, but it is
  not a substitute for backup and retention.

## Risks

- The original Sprint acceptance criteria for verified backup/restore, RPO/RTO,
  restrictive permissions, and complete governance are not satisfied.
- Git history retains the database, logs, generated reports, snapshots, and state
  that S002-13 removed from the current index.
- The live database is group/other readable (`0644`).
- Historical artifact references remain unavailable.
- Existing untracked governance/research documents have not been canonized or
  security-scanned as proposed commits.

## Recommendation for Sprint 003

Do not begin Sprint 003 database consolidation until the Project Owner explicitly
decides how S002-15 through S002-24 will be scheduled and approves S002-18
recovery objectives. The recommended next mission is a bounded Reliability
carryover that resolves permissions, verified backup/restore, and recovery
governance before any Sprint 003 schema work.

## Review verdict

Sprint 002 is administratively closed at S002-14 by explicit owner direction.
Its completed implementation is validated and repository/database continuity is
preserved. Operational readiness is **failed**, and the carried items above remain
mandatory prerequisites rather than completed Sprint outcomes.
