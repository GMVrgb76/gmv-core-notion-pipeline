# GMV Reliability Operations Gate

Status: Sprint 002 operational policy (`ROAD-009`)

## Purpose and authority

This gate defines the minimum observable evidence and first response required for
GMV Reliability operations. It does not create a scheduler, alert transport,
backup system, incident platform, or automatic repair authority. Until an owner
is explicitly delegated, the human GMV Project Owner is accountable for every
escalation and approval named below.

Operational status is derived from `gmv status`; required diagnostics are exposed
by `gmv doctor --strict`; scheduler-safe structured evidence is exposed by
`10_API/health_service.py --json`. Legacy `gmv doctor` remains a compatibility
command and is not a readiness gate.

## Health states and failure budgets

| Evidence class | State | Exit behavior | Reliability budget |
|---|---|---:|---|
| Required check passes | `PASS` | zero | Required failures have a budget of zero. |
| Required check fails | `FAIL` | nonzero | Any occurrence exhausts readiness immediately. |
| Recoverable operating condition | `DEGRADED` | zero | One unresolved stale Service or pending-review queue condition is a budget breach until reviewed. |
| Capability not implemented | `UNAVAILABLE` | zero | It must remain visible and cannot be counted as proof. |

The compatibility-Service freshness threshold is 86,400 seconds and is bounded
by each operational record's `fresh_until`. A non-`OK` latest record is degraded
immediately. Queue entries with `pending` or `pending_review` status are degraded
until processed or explicitly reviewed. Backup freshness and foreign-key
enforcement remain unavailable until S002-20 and `DB-002`; no substitute signal
is permitted.

No automated alert delivery or historical failure-budget counter exists in this
Sprint slice. Operators must inspect structured output. Scheduling the health
adapter requires a separate approved runtime change.

## Response matrix

| Domain and failure | Current signal | Owner | First command | Escalation | Required recovery evidence |
|---|---|---|---|---|---|
| Service latest run is non-`OK` | `service.freshness.<service>` is `DEGRADED`; operational record has status/error code | Service owner named in `LEGACY_ENGINE_INVENTORY.md`; Project Owner if unassigned | `10_API/health_service.py --json` | Project Owner before retrying an external or mutating command | A new valid `OK` operational record, fresh artifact hashes, and status no longer degraded |
| Service record is stale | `service.freshness.<service>` reports the expired timestamp | Same as failed Service | `10_API/health_service.py --json` | Project Owner if the expected run window has passed | Fresh `OK` record with a new run ID and unexpired `fresh_until` |
| Ingestion is pending or awaiting review | `queue.pending` is `DEGRADED`; `gmv queue pending` identifies rows | Import Service owner; Project Owner until assigned | `gmv queue pending` | Project Owner before changing queue state | Reviewed queue state and a subsequent `gmv status --json` result without that pending condition |
| Ingestion query/schema fails | `database.schema`, `database.queries`, or `queue.pending` is `FAIL` | Database custodian; Project Owner until assigned | `gmv doctor --strict --json` | Immediate Project Owner approval before repair or migration | Read-only integrity and schema checks pass on the affected database; any repair has an approved rollback record |
| Database missing, corrupt, or unreadable | Required `database.*` check is `FAIL` and status exits nonzero | Database custodian; Project Owner until assigned | `gmv doctor --strict --json` | Immediate; do not initialize, migrate, or replace the live database | `PRAGMA integrity_check` is `ok`, foreign-key check has no rows, expected schema checks pass, and the database fingerprint is recorded |
| Database is locked | Status/doctor query returns a lock error and exits nonzero | Database custodian; Project Owner until assigned | `gmv doctor --strict --json` | Project Owner if the writer cannot be attributed without mutation | Writer attribution, lock release by the owning process, unchanged database fingerprint where expected, and passing read-only diagnostics |
| Recorded run artifact is missing | `artifacts.references` is `FAIL` and identifies run/stream | Owning Service owner | `10_API/artifact_audit.py --json` | Project Owner if evidence was deleted or retention is unknown | Artifact restored with provenance, or an approved explicit-unavailable record; fabricated replacement is forbidden |
| Managed Resource path is missing | No automated Sprint 002 signal yet; manual Resource/path reconciliation is required | Resource custodian; Project Owner until assigned | `gmv resource list` | Project Owner before altering Resource metadata or files | Original Resource restored or an approved reconciliation record with provenance; database integrity remains unchanged |
| Backup evidence absent or freshness unknown | `backup.freshness` is `UNAVAILABLE` | Project Owner | `10_API/health_service.py --json` | S002-18 RPO/RTO approval and S002-20 implementation required | None available yet; do not claim recovery readiness |
| Backup creation or verification fails | No implemented signal before S002-20 | Project Owner | `10_API/health_service.py --json` | Immediate after S002-20; before then this is an unavailable capability | Future atomic manifest, checksum verification, and isolated restore evidence defined by S002-20 |
| Restore test fails | No implemented restore command before S002-21 | Project Owner | No executable first-response command exists yet | Stop; S002-20/S002-21 must provide the approved command and rollback | Future isolated restore passes integrity, schema, object-count, manifest, and Resource-reference checks |

## Incident procedure

1. Capture the failing structured output and UTC observation time without editing
   logs, artifacts, or the database.
2. Stop automatic continuation when a required check fails.
3. Identify the owner and run only the first read-only command from the matrix.
4. Preserve the run ID, correlation ID, paths, fingerprints, and exit code.
5. Escalate before any retry that writes state, changes authority, or requires a
   migration, retention decision, or external action.
6. Execute only an approved recovery with a known rollback.
7. Close the incident only when the matrix's recovery evidence exists and the
   relevant diagnostic is no longer failed or degraded.

## Tabletop acceptance scenarios

| Scenario | Expected decision |
|---|---|
| Two required database checks fail together | Status is failed, exit is nonzero, both failures remain visible, and no later success masks them. |
| A Service is stale while database checks pass | Status is degraded, the stale timestamp and Service are named, and no automatic rerun occurs. |
| One queue item awaits review | Status is degraded; the operator inspects `gmv queue pending`; no queue mutation is authorized. |
| Historical stdout/stderr paths are absent | Strict doctor fails; the audit names each unavailable reference; no file is fabricated. |
| Backup health is requested before S002-20 | The check remains `UNAVAILABLE`; the system does not claim a fresh backup. |
| A restore fails before S002-21 | Operations stop because no approved restore command exists; manual improvisation is not authorized. |

## Gate exit

Reliability operations pass this gate only when all required checks pass, every
degraded result has an attributed owner and response, unavailable capabilities
remain explicit, and recovery evidence is retained. This policy is incomplete by
design until S002-18 through S002-21 approve recovery objectives and implement
verified backup/restore behavior.
