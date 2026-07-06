# GMV Handoff — Sprint 002 Final

## Current repository state

- Repository: `~/.gmv_core`
- Branch: `main`
- Sprint state: administratively closed at S002-14 on 2026-07-06
- Latest implementation commit: `ab051c6` — `fix: detect private paths in Markdown`
- Runtime directories: ignored and physically preserved
- Sanitized fixtures: tracked
- Staged files at handoff validation: none
- Working tree: no tracked modifications; documented pre-existing untracked
  governance/research/archive files remain listed below

The commit containing this handoff and `GMV_SPRINT_002_REVIEW.md` is the Sprint
closure commit and therefore follows the implementation commit above.

## Database state

- Path: `09_DATABASE/GMV.db` (ignored runtime state; physically present)
- SHA-256: `b0f403d9c47311a307a146c782fb6b2e58ea68bac7eb44d756e05084b37f77f0`
- Integrity: `ok`
- Foreign-key check: no rows
- Schema/user version: `0`
- Drift from S002-00 baseline: none
- File mode: `0644` (active strict-health failure; unresolved S002-19)

## Validation status

- Pytest: 100 passed
- Ruff: passed
- Python dependency check: passed
- Runtime-data Git policy: passed
- Secret gate: passed
- Git diff validation: passed
- Compatibility doctor: passed
- Strict doctor: expected nonzero, truthful `failed`
- Evidence-based status: expected nonzero, truthful `failed`

Strict-health blockers:

- historical engine run 2 stdout artifact unavailable;
- historical engine run 2 stderr artifact unavailable;
- database permissions are `0644`;
- service freshness records are unavailable;
- foreign-key enforcement is unavailable pending `DB-002`;
- backup freshness is unavailable pending S002-20.

## Remaining backlog

S002-15 (`ROAD-006`), S002-16 (`SEC-010`), S002-17 (`SEC-012`), S002-18
(`ROAD-007`), S002-19 (`SEC-005`), S002-20 (`AUTO-010`), S002-21 (`CLI-013`),
S002-22 (`SEC-009`), S002-23 (`DOC-008`), and S002-24 (`DOC-010`) are carried.
`DB-002` and later canonical Event work remain outside completed Sprint 002 scope.

## Known blockers

1. The Project Owner must approve numeric RPO/RTO, retention, recovery owner, and
   restore cadence before backup implementation.
2. No verified full-system backup or isolated restore proof exists.
3. Live database permissions fail the strict policy; no live chmod was authorized.
4. Historical artifact references cannot be repaired without approved evidence or
   reconciliation semantics.
5. Original Sprint 002 acceptance criteria are not fully met despite the explicit
   administrative close at S002-14.

## Documented untracked files

The following pre-existing paths were not created, modified, staged, or approved
by Sprint closure:

- `CURRENT_STATE.md`
- `GMV_ARCHITECTURE_RESEARCH.md`
- `GMV_DEVELOPMENT_PROTOCOL.md`
- `GMV_DOSSIER_ENGINE_ARCHITECTURE.md`
- `GMV_DOSSIER_ENGINE_V1_BLUEPRINT.md`
- `GMV_HANDOFF_NIGHT_001.md`
- `GMV_HANDOFF_W002.md`
- `GMV_HANDOFF_W004.md`
- `GMV_HANDOFF_W004_FINAL.md`
- `GMV_KNOWLEDGE_CONSTELLATION_V1.md`
- `GMV_NIGHT_001_DOCS.zip`
- `GMV_SPRINT_001_RETROSPECTIVE.md`
- `archive/reviews/GMV_CANONIZATION_REVIEW.md`
- `archive/reviews/GMV_GENESIS_CLOSURE_REVIEW.md`
- `archive/reviews/GMV_LEGACY_REVIEW_PHASE1.md`
- `archive/reviews/GMV_SESSION_FREEZE_2026_07_05.md`

## Next recommended mission

Run a Reliability carryover planning/approval mission limited to S002-15 through
S002-24, beginning with the human S002-18 recovery-objective decision and without
starting Sprint 003 implementation. After verified backup/restore and restrictive
permissions exist, perform a separate Sprint 003 readiness audit.

## Recovery procedure

1. Read `GMV_DEVELOPMENT_PROTOCOL.md`, `GMV_GOVERNANCE_INDEX.md`,
   `GMV_SPRINT_002_REVIEW.md`, this handoff, and the carried task definitions in
   `SPRINT_002_IMPLEMENTATION_PLAN.md`.
2. Run `git status --short --untracked-files=all`; do not stage the documented
   untracked files implicitly.
3. Confirm no `.git/index.lock` exists and record current `HEAD`.
4. Hash `09_DATABASE/GMV.db` and run read-only integrity, foreign-key, and
   `user_version` checks.
5. Run the full quality gate and capture strict doctor/status JSON.
6. If the database hash differs unexpectedly, stop and attribute active writers;
   do not restore, migrate, or patch it.
7. If rollback of a completed Sprint task is required, revert only its atomic
   commit and rerun its validation. Never restore ignored runtime artifacts from
   Git or overwrite the live database.
8. Obtain explicit Project Owner approval before S002-18 objectives, live
   permission changes, backup retention, or any external/LaunchAgent action.
