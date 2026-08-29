# GMV BACKLOG

## CURRENT PHASE

Core Integrity

GMV OS currently has a Core foundation with partial ingestion scaffolding. Intelligence, Reasoning, Decision, and autonomous workflow capabilities are not current-phase deliverables.

## HIGH PRIORITY

- Reproducible runtime and development tooling
- Isolated automated tests and CI gates
- Versioned database migrations
- Canonical OID rules and transaction-safe allocation
- Typed CLI validation
- Database protection and recovery evidence

## SPRINT 001 DISPOSITION

Sprint 001 completed its approved foundation scope. The status below applies to
the full V2 backlog item, not merely to the Sprint task that contributed to it.

| Backlog ID | Status | Sprint 001 evidence or remaining scope |
|---|---|---|
| `ROAD-001` | Completed | The active phase is Core Integrity across canonical governance documents. |
| `ROAD-002` | Completed | Reasoning, Decision, and autonomous workflow entry gates are explicit. |
| `PERF-007` | Completed | ADR-S001-01 defers application caching behind authority and invalidation gates. |
| `MAIN-013` | Completed | Runtime support, package metadata, pinned development tools, and build contract are defined; Bash remains the approved runtime entrypoint. |
| `AUTO-001` | Completed | Isolated pytest fixtures and the CI quality gate are operational. |
| `AUTO-002` | Completed | Empty, adopt, reapply, injected-failure, and recovery migration paths are tested. |
| `AUTO-012` | Completed | CI runs pinned lint, dependency, secrets, and whitespace checks. |
| `DB-001` | Completed | Explicit-target migrations and reviewed baseline migration 001 exist; live rollout remains prohibited pending Sprint 002 recovery controls. |
| `DB-007` | Completed | The implemented import path uses transactional sequences instead of row counts and fails closed before migration 002. |
| `MAIN-001` | Carried forward | The importable foundation package exists, but standalone services have not yet been consolidated into one application package. |
| `ARC-004` | Carried forward | Canonical validation and allocation exist for the implemented path; routing every future Object creator through the Identity API remains open. |
| `DB-008` | Carried forward | Validation and existing-data checks exist; database-level prefix/type constraints await the approved constraint workstream. |
| `CLI-003` | Carried forward | Shared typed primitives and two narrow adapters exist; global adoption across every CLI command remains future work. |

## PHASE GATES

- Reasoning work remains paused until the Core Integrity, Reliability, Data / Database, Automation, and governed Knowledge exit criteria are proven.
- Decision work remains paused until governed Reasoning evaluation, evidence, approval, and human-review policies are operational.
- Autonomous workflow execution remains paused until canonical identity and Events, verified recovery, strict health checks, queue claim/retry controls, and authorization boundaries are operational.
- Application caching remains deferred until authoritative state, Event-driven invalidation, measured need, and deterministic rebuild tests exist.

## LATER ROADMAP

- Watch Folder
- Import Queue Automation
- Review Queue
- Archive Engine
- Entity Extraction Engine
- Relation Extraction Engine
- Knowledge Graph Expansion
- Reasoning Engine
- Decision Engine
- Workflow Engine
- Scheduler Engine
- Research Agent
- OCR Agent

## LOW PRIORITY

- Web Dashboard
- REST API
- Multi-user
- Notification Center
- Mobile Companion

## IMPLEMENTED SURFACES

The following surfaces exist, but their presence does not establish phase completion or full architecture compliance:

- Core bootstrap
- Knowledge Engine V0
- Object Service surface
- Relation Service surface
- Import Service surface
- Resource CLI
- Event CLI
- Timeline CLI
- Search CLI
- Queue CLI
- Snapshot CLI
- Service CLI
- Plugin CLI
