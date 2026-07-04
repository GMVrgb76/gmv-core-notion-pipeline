# GMV Sprint 001

## Goal

Establish the Core Integrity foundation required for safe schema, identity, CLI, and automation work.

## Scope

The authoritative task breakdown and execution order are defined in `SPRINT_001_IMPLEMENTATION_PLAN.md`.

Current governance constraints:

- no Sprint 002–007 feature may be pulled forward;
- Reasoning, Decision, and autonomous workflow expansion remain paused behind their roadmap gates;
- no application cache may be introduced;
- no live database migration may run during Sprint 001.

## Definition of Done

- All Sprint 001 task acceptance criteria are evidenced.
- Required validation commands pass.
- The live database is not modified by Sprint work.
- Runtime and generated artifacts remain separate from commits.
- Documentation describes implemented status without overstating capability.
- Each implementation unit is represented by one atomic commit.

## Completed

- S001-00 — Protected baseline and writer inventory (`df8e1b4`).
- S001-01 — Core Integrity and no-cache governance gates (`9edd5fc`).
- S001-02 — Packaging and runtime contract (`5e24b64`).
- S001-03 — Python foundation package (`b20d17e`).
- S001-04 — Isolated test harness and live-write guard (`7222544`).
- S001-05 — Schema and CLI characterization tests (`e5dfca9`).
- S001-06 — Automated quality gates (`730edf3`).
- S001-07 — Explicit-target migration runner and baseline (`16ef653`).
- S001-08 — Migration idempotence and recovery evidence (`d59e71d`).
- S001-09 — Canonical OID contract and validator (`7fa410b`).
- S001-10 — Transaction-safe OID allocation (`4cd449b`).
- S001-11 — Shared CLI validation and error primitives (`d5a7733`).
- S001-12 — Sprint acceptance and governance closeout (this closeout commit).

## Acceptance Evidence

- Full isolated suite: 49 tests passed.
- Ruff repository scan: passed.
- Python dependency check: no broken requirements.
- `gmv doctor`, `gmv status`, and `gmv object count`: completed successfully.
- Live database SHA-256 remained `da4621d0b1ae12318f229efefbc24218f2be3e9a68bcbd7e535de6ead93b63e8` throughout Sprint implementation validation.
- No live migration ran; the operational database remains at schema version 0.
- Every implementation commit contains only its authorized Sprint files.

## Backlog Disposition

The 13 Sprint-linked V2 backlog IDs have explicit status:

- Completed: `ROAD-001`, `ROAD-002`, `PERF-007`, `MAIN-013`, `AUTO-001`, `AUTO-002`, `AUTO-012`, `DB-001`, `DB-007`.
- Carried forward: `MAIN-001`, `ARC-004`, `DB-008`, `CLI-003`.

Carried-forward items have working Sprint foundations but broader V2 acceptance
criteria that were deliberately outside Sprint 001. They must not be represented
as globally complete.

## Repository Continuity

Sprint-owned source and governance changes are committed atomically and leave no
unstaged implementation diff. The working tree still contains the attributed
runtime/database artifacts and pre-existing untracked architecture, protocol, and
handoff documents recorded at the protected baseline. They remain unmodified,
unstaged, and excluded under the Runtime and Log Safety Rules. This operational
state is not a clean Git status and remains an explicit repository-hygiene risk;
it does not indicate an uncommitted Sprint implementation.
