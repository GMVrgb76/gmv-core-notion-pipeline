# GMV Recovery Policy v1

Status: Approved by Giacomo Marco Valerio on 2026-07-06 (`S002-18`, `ROAD-007`)

## Objectives

| Objective | Approved value |
|---|---|
| Recovery Point Objective | Maximum 15 minutes accepted canonical-data loss |
| Recovery Time Objective | Maximum 60 minutes accepted recovery time |
| Rolling retention | 90 days |
| Permanent retention | Every closed Sprint, tagged release, and schema migration |
| Backup verification | Integrity verification on every backup execution |
| Restore verification | Full isolated restore test monthly |
| Recovery owner | Giacomo Marco Valerio (Human Owner) |

## Authority

- Automatic backup is approved.
- Automatic restore is prohibited.
- Automatic overwrite of canonical state is prohibited.
- Every restore and canonical overwrite requires explicit approval from the Human
  Recovery Owner for the specific recovery operation.
- Recovery commands must default to isolated targets and fail closed when approval,
  evidence, scope, or integrity is missing.

## Protected canonical scope

- canonical SQLite database;
- OID metadata and identity continuity;
- Event Store and Event history;
- Resource metadata and external-reference evidence;
- configuration;
- canonical governance and Sprint documentation;
- approved research documentation;
- Git repository state and history, which remain authoritative for source code.

Repository disaster-recovery copies are permitted. They supplement Git history;
they do not replace its authority.

## Excluded disposable scope

- runtime process state;
- caches;
- temporary outputs;
- generated indexes unless explicitly promoted to canonical state.

Exclusion means rebuildable, not permission to delete active files. A backup may
record runtime metadata needed for diagnosis without treating runtime content as
canonical recovery data.

## Recovery invariants

1. Canonical state is never overwritten automatically.
2. Every backup, verification, restore test, and approved recovery is attributable
   and auditable.
3. Recovery behavior is deterministic and versioned.
4. OID identity and committed allocation semantics are preserved.
5. Event history is preserved; recovery never rewrites canonical Events silently.
6. Recovery never promotes Knowledge automatically.
7. External Resources are verified and reported unless separately included by an
   approved custody contract; they are never mutated implicitly.
8. Failed or partial backup creation cannot appear valid.

## Acceptance evidence

Every backup execution must produce an atomic, versioned manifest containing the
backup identity, creation time, policy version, source repository commit, database
fingerprint, included/excluded scope, file hashes/sizes, Resource-reference status,
and verification result. A backup is valid only after all declared entries verify.

Monthly restore proof must target a new isolated directory and record manifest
verification, SQLite integrity, foreign-key result, schema version, object counts,
OID continuity checks, Event counts/history checks, and Resource-reference status.
No Sprint 002 command may overwrite live state.

Audit evidence must be append-only or tamper-evident within the implemented
operational boundary and must include actor, command/version, timestamps, source
backup, target, outcome, and failure details. Secrets and credentials are never
embedded in manifests or logs.

## Tabletop loss scenarios

| Loss scenario | Recovery source and action | Required evidence | Authority/result |
|---|---|---|---|
| Live SQLite loss/corruption | Select latest verified backup within 15-minute RPO; restore only to isolated target first | Manifest/hash verification, SQLite checks, OID/Event comparison | Human approval required before any canonical replacement; target service within 60 minutes |
| Source/configuration loss | Recover authoritative commit/history from Git; compare backup repository evidence if needed | Commit identity, clean checkout, quality gate | Human approval required before production redeployment |
| Governance/Sprint/research loss | Recover tracked canonical documents from Git and verified backup manifest | Hashes, commit provenance, canonical-document audit | No alias or unapproved research promotion |
| Managed metadata loss | Restore database copy in isolation and verify OID, Event, and Resource metadata | Counts, fingerprints, reference report | Human approval before canonical replacement |
| External Resource unavailable | Report reference unavailable; do not fabricate or mutate external content | OID/path/hash/reference evidence and owner escalation | Outside automatic restore authority |
| Credential loss/compromise | Credentials are excluded from backup payload; rotate through their owning system | Rotation evidence and configuration revalidation | Human/security-owner action only |
| Complete host loss | Rebuild host from Git plus latest verified canonical backup; rebuild disposable paths | Repository commit, backup manifest, isolated restore proof, quality/health checks | Human approves activation after all evidence passes |
| Backup corruption | Reject backup and select an earlier verified set within retention | Failed checksum evidence and next-candidate verification | No restore from failed set |
| Recovery process interrupted | Preserve audit failure; incomplete isolated target remains non-canonical | Nonzero outcome, no valid-completion marker | Restart from verified backup; never resume an unverified overwrite |

## Retention and milestones

Rolling backups expire after 90 days only when retention execution proves that at
least one newer verified recovery set remains. Sprint-close, tagged-release, and
schema-migration backups are permanent and excluded from automatic pruning.
Retention is dry-run/report-only until a separately validated deletion operation
is explicitly approved.

## Change control

Changing the RPO, RTO, scope, retention, verification frequency, authority, or
owner requires a new explicit human approval and a versioned policy update. This
document authorizes backup implementation and isolated restore verification only;
it does not authorize a live restore, live overwrite, database migration,
LaunchAgent modification, or external Resource mutation.
