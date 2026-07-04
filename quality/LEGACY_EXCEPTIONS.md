# S001-06 Legacy Quality Exceptions

These exceptions quarantine findings that predate the Sprint 001 quality gate. They do not mark the findings as resolved and must not be expanded without a separate reviewed task.

## Ruff exceptions

Owner: Sprint 002 Reliability workstream.

Expiry: before Sprint 002 closeout.

- `01_RUNTIME/knowledge_engine.py`: `E401`; legacy combined imports.
- `01_RUNTIME/legacy_inventory.py`: `E401`, `F401`; legacy combined and unused imports.
- `10_API/gmv_compatibility.py`: `E401`, `F401`, `S602`; legacy imports and the tracked `shell=True` finding owned by `SEC-001`.
- `10_API/import_service.py`: `S608`; reviewed constant-column SQL construction, to be re-evaluated with persistence-boundary work.
- `10_API/plugin_manager.py`: `E401`; legacy combined imports.
- `10_API/queue_service.py`: `S608`; reviewed constant-column SQL construction, to be re-evaluated with persistence-boundary work.

The `S101` and `S603` exceptions under `tests/` cover pytest assertions and fixed-argument subprocess characterization. They apply only to tests and are not production-code debt.

## Secret baseline

Owner: Sprint 002 security and runtime-data cleanup (`SEC-004`).

Expiry: before Sprint 002 closeout.

The baseline contains two existing findings: a high-entropy extension list in `legacy_inventory.py` and a hash value in the tracked legacy SQLite snapshot. New findings are rejected. Baseline entries may be removed after their owning files are corrected or removed through an approved task; they must never be refreshed merely to make CI pass.
