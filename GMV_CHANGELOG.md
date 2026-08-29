# GMV CHANGELOG

This document records the major milestones of GMV OS.
It is intended for humans and complements Git history.

Use reverse chronological order.

---

## 2026-07-04 — Sprint 001 Foundations

### Core Integrity

- Declared Core Integrity as the active phase and established gates for later Intelligence, Reasoning, Decision, and autonomous workflow work.
- Recorded the decision to defer application caching until authority and invalidation contracts exist.
- Added an import-safe Python foundation package and an explicit runtime/build contract.

### Safety and Verification

- Added isolated test homes, a hard live-database write guard, and deterministic schema and CLI characterization tests.
- Added CI gates for tests, Ruff, dependency integrity, secret detection, and whitespace integrity.
- Added an explicit-target migration runner, baseline migration, and idempotence/failure/recovery tests.
- Performed all Sprint migration and allocation testing against disposable databases; no live migration was run.

### Identity and CLI Foundations

- Defined and versioned the canonical OID contract.
- Added committed-identity, transaction-safe OID allocation and removed row-count allocation from the implemented importer path.
- Made the importer fail closed until migration 002 is explicitly applied.
- Added shared validators for OIDs, numeric IDs, paths, statuses, and slugs with stable CLI input-error semantics.

### Closeout

- Completed S001-00 through S001-12 as atomic implementation units.
- Recorded explicit completed or carried-forward status for all 13 Sprint-linked V2 backlog items.
- Preserved the live database hash throughout implementation validation.
- Carried broader package consolidation, universal Identity API adoption, database-level OID constraints, and global CLI validation adoption into later approved work.

---

## 2026-07-04 — Sprint 002 Milestone

### Infrastructure

- Import Queue integrated.
- Resource CLI implemented.
- Event CLI implemented.
- Timeline CLI implemented.
- Search CLI implemented.
- Queue CLI implemented.
- Snapshot CLI implemented.
- Service CLI implemented.
- Plugin CLI implemented.

### Development Process

- Git repository initialized.
- Codex integrated into the development workflow.
- Atomic commits adopted.
- Automated validation workflow established.

### Project Governance

- GMV_BACKLOG.md created.
- GMV_SPRINT.md created.
- GMV_ARCHITECTURE.md created.
- GMV_PRODUCT_VISION.md created.

### Notes

This marks the transition from experimental development to a structured software engineering workflow.
