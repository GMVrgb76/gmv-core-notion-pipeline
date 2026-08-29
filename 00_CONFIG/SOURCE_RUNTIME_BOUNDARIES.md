# GMV Source and Runtime Boundaries

Status: Approved Sprint 002 layout decision (`ARC-011`)

## Decision

The repository contains source, governance, disposable build products, and live
operational state. Their physical coexistence is transitional; their authority
is not. This decision classifies current paths without moving, deleting, copying,
or rewriting anything. Dropbox and LaunchAgents are outside this decision and
must not be modified.

## Classes

| Class | Meaning | Canonical authority | Default backup policy |
|---|---|---|---|
| Source | Deterministic executable or test input | Reviewed Git commit | Git; release artifacts are reproducible |
| Configuration | Reviewed contracts and non-secret settings | Reviewed Git commit | Git |
| Governance | Normative or historical project documentation | Canonical reviewed document | Git for canonical material; archive for historical evidence |
| Fixture | Sanitized, deterministic test evidence | Reviewed Git commit | Git; never copied from live state without sanitization |
| Live state | Mutable canonical operational data | Runtime owner and database/resource contracts | Full-system backup after S002-20; never Git |
| Runtime output | Mutable logs, reports, snapshots, inventories, and staging | Producing Service; not canonical Knowledge | Backup only when retention policy requires; never Git by default |
| Cache/build | Reproducible derived data | No authority | Exclude; rebuild |
| Local tooling | Machine-local environment | No project authority | Exclude; recreate from pinned inputs |
| Repository metadata | Version-control and CI control plane | Git/repository maintainer | Git remote/administrative backup |
| Legacy evidence | Superseded but retained historical material | Informative only unless canonized | Archive with provenance; no runtime authority |

## Current top-level path inventory

Each current top-level entry has one primary class, an accountable owner role,
and a backup treatment. “Git if canonical” does not authorize staging currently
untracked documents; canonicalization remains a separate governance decision.

| Current path | Class | Owner | Backup policy |
|---|---|---|---|
| `.git/` | Repository metadata | Repository maintainer | Administrative Git backup; never runtime backup content |
| `.github/` | Repository metadata | Repository maintainer | Git |
| `.gitignore` | Configuration | Repository maintainer | Git |
| `.secrets.baseline` | Configuration | Security owner / Project Owner | Git only if verified to contain fingerprints, not secrets |
| `.DS_Store` | Cache/build | Local operating system | Exclude and regenerate |
| `.pytest_cache/` | Cache/build | Test tooling | Exclude and regenerate |
| `.ruff_cache/` | Cache/build | Quality tooling | Exclude and regenerate |
| `.venv/` | Local tooling | Developer/operator | Exclude; recreate from `pyproject.toml` and requirements |
| `00_CONFIG/` | Configuration | Core maintainer / Project Owner | Git; secrets prohibited |
| `01_RUNTIME/` | Source | Runtime maintainer | Git for code and pinned legacy entrypoints; generated content prohibited |
| `02_INDEXES/` | Runtime output | Index owner | Future full-system backup only when not reproducible; never Git by default |
| `03_STATE/` | Live state | Runtime state owner | Full-system backup after S002-20; never Git |
| `04_LOGS/` | Runtime output | Producing Service owner | Retention-controlled operational backup; never Git |
| `05_OUTPUT/` | Runtime output | Producing Service owner | Retain only approved evidence/reports; never Git by default |
| `06_CACHE/` | Cache/build | Producing Service owner | Exclude and regenerate |
| `07_IMPORT/` | Runtime output | Import Service owner | Quarantine/staging retention policy; never Git |
| `08_BACKUP_LOCAL/` | Runtime output | Backup owner / Project Owner | Backup catalog target, not Git; protection defined by S002-20/22 |
| `09_DATABASE/` | Live state | Database custodian / Project Owner | Verified full-system backup after S002-20; never Git |
| `10_API/` | Source | Core maintainer | Git |
| `11_CLI/` | Source | CLI maintainer | Git |
| `12_SCHEDULER/` | Source | Runtime maintainer | Git for scripts only; scheduler state and LaunchAgents remain external |
| `archive/` | Legacy evidence | Governance owner / Project Owner | Preserved archive with provenance; Git if approved as project evidence |
| `dist/` | Cache/build | Release tooling | Exclude; rebuild from reviewed source |
| `gmv_core/` | Source | Core maintainer | Git |
| `gmv_core.egg-info/` | Cache/build | Packaging tooling | Exclude and regenerate |
| `quality/` | Governance | Quality owner | Git |
| `reviews/` | Governance | Governance owner | Git if canonically approved; otherwise archive as evidence |
| `scripts/` | Source | Quality/runtime maintainer | Git |
| `tests/` | Fixture | Test owner | Git; live data prohibited |
| `pyproject.toml` | Configuration | Core maintainer | Git |
| `requirements-dev.txt` | Configuration | Quality owner | Git |
| `README_CORE.md` | Governance | Governance owner | Git |
| `CURRENT_STATE.md` | Governance | Session/governance owner | Git only when approved as canonical current-state entry point |
| `GMV_ARCHITECTURE.md` | Governance | Architecture owner | Git |
| `GMV_ARCHITECTURE_RESEARCH.md` | Governance | Research owner | Git if approved; otherwise archive evidence |
| `GMV_BACKLOG.md` | Governance | Product owner | Git; superseded status must remain explicit |
| `GMV_CHANGELOG.md` | Governance | Release owner | Git |
| `GMV_DEVELOPMENT_PROTOCOL.md` | Governance | Governance owner | Git |
| `GMV_DOSSIER_ENGINE_ARCHITECTURE.md` | Governance | Architecture owner | Git if approved; no runtime authority |
| `GMV_DOSSIER_ENGINE_V1_BLUEPRINT.md` | Governance | Architecture owner | Git if approved; no runtime authority |
| `GMV_GOVERNANCE_INDEX.md` | Governance | Governance owner | Git |
| `GMV_HANDOFF_NIGHT_001.md` | Legacy evidence | Session/governance owner | Archive or Git as approved historical evidence |
| `GMV_HANDOFF_W002.md` | Legacy evidence | Session/governance owner | Archive or Git as approved historical evidence |
| `GMV_HANDOFF_W004.md` | Legacy evidence | Session/governance owner | Archive or Git as approved historical evidence |
| `GMV_HANDOFF_W004_FINAL.md` | Governance | Session/governance owner | Git while it is the approved handoff; archive when superseded |
| `GMV_KNOWLEDGE_CONSTELLATION_V1.md` | Governance | Architecture owner | Git if approved; no runtime authority |
| `GMV_NIGHT_001_DOCS.zip` | Legacy evidence | Governance owner | Archive outside normal source; do not treat as canonical text |
| `GMV_PRODUCT_VISION.md` | Governance | Product owner | Git |
| `GMV_SPRINT.md` | Governance | Product owner | Git; superseded status must remain explicit |
| `GMV_SPRINT_001_RETROSPECTIVE.md` | Legacy evidence | Sprint owner | Archive or Git as historical evidence |
| `GMV_TECHNICAL_REVIEW.md` | Governance | Architecture owner | Git as review baseline until superseded, then archive |
| `GMV_V2_BACKLOG.md` | Governance | Product owner | Git |
| `GMV_V2_EXECUTION_ROADMAP.md` | Governance | Product owner / Architecture owner | Git |
| `SPRINT_001_IMPLEMENTATION_PLAN.md` | Legacy evidence | Sprint owner | Git or archive as completed execution evidence |
| `SPRINT_002_IMPLEMENTATION_PLAN.md` | Governance | Sprint owner | Git; current implementation authority |

## External Resource boundary

Dropbox and every other external Resource location are outside `~/.gmv_core`.
They are external evidence stores, not executable or implicit backup targets. GMV
may retain OID-based Resource references and verify existence/checksums under an
approved contract. This layout decision authorizes no external read, write, move,
copy, deletion, or LaunchAgent change.

## Ownership rules

1. Source/configuration owners may change reviewed files but cannot mutate live
   state as a side effect of import, tests, status, or diagnostics.
2. Runtime owners may write only their declared state/output paths and cannot
   promote output into Knowledge or Git automatically.
3. Database and Resource custodians preserve identity, provenance, transactions,
   and rollback evidence; authority is never inferred from filesystem access.
4. Governance owners approve authority and lifecycle; documentation cannot itself
   grant runtime capabilities outside the Sprint plan.
5. Cache/build and local-tooling paths are disposable and must never be required
   to reconstruct canonical state.

## Migration sequence

1. S002-12 records this boundary without moving data.
2. S002-13 changes Git tracking/ignore policy for future mutable database, log,
   report, inventory, and snapshot changes while retaining sanitized fixtures.
3. S002-14 assigns sensitivity classes and scans tracked history/current content;
   history rewriting remains separately approved work.
4. S002-15/16/17 establish retention, security-gate, and audit-integrity controls.
5. S002-18 through S002-23 approve recovery objectives and implement protected,
   verified backup/restore behavior.
6. Any later physical relocation requires its own migration, compatibility,
   rollback, and operator approval. No relocation is approved here.
