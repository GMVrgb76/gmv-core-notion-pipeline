# Constitution CLI Feature — Freeze Record

## 1. Status

- Feature status: **FROZEN — UNAPPROVED**
- Decision: REBASE 001, Task 8 (archaeology) / Task 9 (CLI restore)
- Date of freeze: 2026-07-12
- No active CLI wiring remains: `11_CLI/gmv` is identical to repository `HEAD`; `gmv constitution` is not exposed.

## 2. Historical implementation

- `10_API/constitution_service.py` exists as preserved, untracked historical/reference code. It is not deleted and not wired into any live entry point.
- `10_API/constitution_service.py.bak_20260709_220335` and `11_CLI/gmv.bak_20260709_220211` remain preserved, untracked, unmoved.
- None of these files has Service authority.
- No Service OID exists for this feature (`GMV.db.service_registry_view` contains only `SRV-000001`–`SRV-000004`).
- No tests or approved specification exist for `status`, `check`, `graph`, or the CLI dispatch itself.

## 3. Reason for freeze

- No documented requirement anywhere in the project for a `gmv constitution` command.
- No Service registration.
- No test coverage.
- Direct Core-to-Dropbox read boundary violation: `constitution_service.py` reads
  `~/Library/CloudStorage/Dropbox/GMV_MASTER_SYSTEM/99_SYSTEM/00_CONSTITUTION` directly from a Core CLI path.
- Confirmed invalid-subcommand exit-code defect: an unrecognized `gmv constitution <sub>` argument printed help text but exited `0` instead of failing non-zero.
- Explicitly excluded from Sprint 002 closure: `GMV_HANDOFF_S002_FINAL.md` lists `10_API/constitution_service.py` twice, as a "Legacy component" and as "Untracked material excluded from Sprint 002 closure."

## 4. Current operational state

- `11_CLI/gmv` is identical to `HEAD` (verified by SHA-256 match).
- `gmv constitution` is not exposed by the live CLI.
- `constitution_service.py` is not reachable through the live CLI or any other Core entry point.
- No data or historical evidence was deleted at any point in this freeze.

## 5. Reactivation conditions

The feature must not be reactivated unless all of the following exist:

- Explicit Project Owner approval.
- A documented architectural role for the feature.
- A resolved Runtime/Repository boundary (i.e., an approved answer to whether/how a Core CLI command may read Dropbox).
- Service registration, or an explicit documented exception from registration.
- Tests covering `status`, `check`, `graph`, and invalid-input handling.
- Explicit non-zero failure semantics for invalid subcommands.
- Review of constitution source authority (what makes a given Dropbox constitution file authoritative).

## 6. Preservation hashes

SHA-256, recorded 2026-07-12:

- `10_API/constitution_service.py`: `5f3de7e158a2518b4d94ee9a5c6b1852f9ca2e4ee079cbce565ef49b9f24a407`
- `10_API/constitution_service.py.bak_20260709_220335`: `db7a47ccc9e82f4c20f826d0463952e33b34f5dbfc002bb298cbc119573e0fb7`
- `11_CLI/gmv.bak_20260709_220211`: `f70fbf28f2be705f5429df8256b84ae9844da11721e889ee2e62213944b5f7a6`

## 7. Rollback / reactivation note

Reactivation is not a simple restore operation. It requires a new, separately approved implementation task that addresses all conditions in Section 5 — including a resolved Runtime/Repository boundary decision, Service registration, and test coverage — before any CLI wiring is reintroduced. This record intentionally does not provide a command to re-add the prior CLI block.
