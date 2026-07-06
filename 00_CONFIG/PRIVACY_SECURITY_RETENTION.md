# GMV Privacy, Security, and Retention Controls

Status: Approved Privacy, Security, and Retention Policy v1 on 2026-07-06
(`S002-15`, `ROAD-006`)

GMV is currently single-user and local-first. Filesystem access is not authority;
the Human Owner is accountable for protected-data access, deletion exceptions,
recovery, and incident decisions. Recovery objectives come from
`RECOVERY_OBJECTIVES.md`; Git rules come from `RUNTIME_DATA_GIT_POLICY.md`.

| Data class | Owner | Location | Access | Retention | Deletion exception | Backup | Incident response |
|---|---|---|---|---|---|---|---|
| Canonical SQLite/OID/Event/Resource metadata | Human Owner / database custodian | `09_DATABASE/` | Runtime Services and approved operators; mode `0600` target | Permanent history subject to approved migrations | Never delete to satisfy retention; migration/restore plan required | 15-minute verified recovery sets; milestone retention | Stop writers, preserve fingerprint, diagnose read-only, human-approved recovery only |
| Source/configuration | Repository maintainer | Git-tracked source and `00_CONFIG/` | Reviewed commits | Git history | No silent history rewrite | Git authoritative plus recovery archive | Revoke compromised access, scan history, rotate exposed credentials |
| Governance/Sprint/research | Human Owner / governance owner | Canonical tracked documents | Reviewed commits | Permanent or archived with provenance | Supersession, never silent erasure | Git plus recovery archive | Freeze authority, identify canonical version, record correction |
| Backup manifests/database copies/repository archives | Recovery Owner | `~/.gmv_backups` | Human Owner and backup process; `0700/0600` | Rolling 90 days; milestones permanent | Never remove sole verified set; dry-run before pruning | Backup set is recovery evidence, not recursively backed up | Disable scheduler, preserve audit, verify all sets, rotate keys if applicable |
| Operational audit records | Service owner / Human Owner | protected audit paths | Append writer and read-only operator | Minimum 90 days; preserve incident evidence permanently | Incident/legal hold overrides expiry | Included as recovery metadata where approved | Freeze writer, verify chain, preserve corrupt copy, investigate gap |
| Runtime/logs/generated outputs/indexes/cache | Producing Service | ignored runtime paths | Service and operator | Disposable unless incident hold or explicit promotion | Incident evidence hold | Excluded by default | Preserve relevant evidence; never promote automatically |
| External Resources | Resource owner | External referenced path | External authority | External policy | GMV cannot delete implicitly | Verify/reference only unless custody contract says otherwise | Mark unavailable, preserve OID/hash/provenance, escalate owner |
| Credentials/secrets/keys | Human/Security Owner | External credential store/environment | Least privilege; never manifests/logs/Git | Rotate by owning system policy | Compromise requires immediate rotation | Excluded from backup payload | Disable affected capability, rotate, audit access, verify configuration |
| Personal/domain data | Human Owner | Canonical metadata and external Resources | Purpose-limited operator access | Business/legal policy; unresolved domain-specific periods are explicit gaps | Legal/contractual hold | According to canonical/external classification | Restrict access, preserve evidence, assess disclosure, document decision |

## Release gates

1. Security quality gate passes with no unexplained exception.
2. Protected runtime paths are untracked and private modes pass diagnostics.
3. Backup and restore evidence satisfies approved RPO/RTO.
4. Logs/manifests contain no credentials or unnecessary private message bodies.
5. Every new data class has an owner and a retention/deletion decision.
6. Behavior-changing documentation is consistent with implementation.

## Gaps and prohibitions

Domain-specific legal retention periods, multi-user authorization, encryption key
custody, and history-rewrite approval are not implemented. They remain explicit
gaps and cannot be inferred. Automatic restore, canonical overwrite, Knowledge
promotion, external Resource mutation, and credential backup are prohibited.

## Incident minimum record

Record UTC time, actor, affected class/OIDs, source evidence, scope, checksums,
actions, approvals, rollback, recovery evidence, and closure owner. Do not include
secrets, hidden reasoning, full transcripts, or unnecessary private content.
