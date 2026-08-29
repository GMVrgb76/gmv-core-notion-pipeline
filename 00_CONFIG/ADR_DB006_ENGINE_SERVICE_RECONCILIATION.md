# ADR: DB-006 Engine/Service Run Reconciliation

- **Status:** Accepted
- **Date:** 2026-07-19
- **Decision owner:** Project Owner
- **Backlog:** `DB-006`, `ARC-006`, `MAIN-014`

## Context

GMV Core records execution history in both `engine_runs` and `service_runs`.
At the decision gate, the live database contains 31 Engine rows and five
Service rows. Five Engine rows are exact duplicates of Service rows, 25
additional Engine rows belong to already registered Services, and one row
(`engine="gmv_core"`, command `./11_CLI/gmv constitution check`, run at
`2026-07-11T14:13:49`) belongs to the frozen, unapproved Constitution CLI
feature and has no Service authority.

The roadmap requires one Service-run history and stable Service OIDs. It also
requires reviewed reconciliation rules before a production migration.

## Decision

`service_runs` is the canonical target for execution history. Existing Engine
identities map to registered Services as follows:

| Engine identity | Service OID | Service name |
|---|---|---|
| `ENG-000001` / `knowledge_engine` | `SRV-000001` | Knowledge Engine |
| `ENG-000002` / `morning_brief` | `SRV-000002` | Morning Brief |
| `ENG-000003` / `daily_log` | `SRV-000003` | Daily Log |
| `ENG-000004` / `market_engine` | `SRV-000004` | Market Engine |

Reconciliation is deterministic and loss-averse:

1. An Engine row is an existing Service-row duplicate only when the mapped
   Service OID and every run payload field are equal using null-safe equality.
   The existing Service row is retained and no second row is inserted.
2. A mapped Engine row without such a match is copied once to `service_runs`
   with its canonical Service OID and name and otherwise identical payload.
3. The single `gmv_core` Constitution row is preserved as an explicitly
   excluded historical anomaly in migration evidence. It is not inserted into
   `service_runs`, assigned a Service OID, or treated as authority to reactivate
   the frozen feature.
4. New writers move to `service_runs` before historical production migration
   or retirement of the legacy table. Read-side heuristic merging is removed
   only after reconciliation is complete.

## Consequences

- Authorized execution history converges on stable Service OIDs without
  legitimizing the frozen Constitution CLI feature.
- Production reconciliation must prove five exact duplicates, 25 mapped
  missing rows, and exactly one approved exclusion at the recorded gate, or
  fail closed if the live state has diverged.
- Migration of live rows, backup creation, and retirement or replacement of
  `engine_runs` remain separately authorized operational steps.
- This first implementation slice moves only the native Knowledge Engine
  writer. Compatibility writers remain explicit follow-up work.

## References

- `GMV_V2_EXECUTION_ROADMAP.md`, Sprint 003 step 5 and exit criteria
- `GMV_V2_BACKLOG.md`, `DB-006`, `ARC-006`, and `MAIN-014`
- `00_CONFIG/SERVICE_SPECIFICATION.md`, registered Service contracts
- `00_CONFIG/CONSTITUTION_CLI_FEATURE_FREEZE.md`
