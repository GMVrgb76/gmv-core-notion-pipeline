# Real Estate Legacy Orchestration — Freeze Record

## 1. Status

- Component status: **FROZEN — LEGACY**
- Date: 2026-07-12
- REBASE 001 decision: `FREEZE_AS_LEGACY`, decided by evidence-based forensic archaeology (REBASE 001, Task 12). Full reasoning, timeline, and evidence index are recorded in that task's report; this file states only the operative facts.

## 2. Components covered

- `99_SYSTEM/03_DIRECTORS/realestate_runner.py`
- `99_SYSTEM/03_DIRECTORS/real_estate_director.py`
- `99_SYSTEM/03_DIRECTORS/real_estate_recursion_check.py`

## 3. Historical role

- Original purpose: a working implementation of the Engine → Director layer
  documented in `GMV_OS_CONSTITUTION.md`, coordinating the Real Estate domain's
  Market and Property Engines without performing analysis of its own —
  `real_estate_director.py`'s own generated text states: *"Il Director non
  produce analisi proprie. Coordina gli Engine disponibili."*
- Orchestration model: `realestate_runner.py` runs `real_estate_director.py`,
  hashes the Director/Market/Property reports to detect change, and
  increments a `change_cycles` counter in `~/.gmv_runtime/realestate_state.json`
  on each detected change.
- Recursion protocol: when `change_cycles` reaches 5, `realestate_runner.py`
  invokes `real_estate_recursion_check.py`, which applies the GMV Recursion
  Method (Question/Delete/Simplify/Accelerate/Automate) to the Real Estate
  domain and writes `REAL_ESTATE_RECURSION_PROPOSAL.md`; the counter then
  resets to 0.
- Relationship with Market Engine: `real_estate_director.py` only checks for
  the existence of `MARKET_REPORT.md` — it does not invoke `market_engine.py`
  directly. The Dropbox copy of `market_engine.py` is not called by any of
  the three frozen components.
- Relationship with Property Engine: identical pattern — `real_estate_director.py`
  checks for the existence of `PROPERTY_REPORT.md` only; `property_engine.py`
  is not invoked by any of the three frozen components.

## 4. Reason for freeze

- Dormant: no execution recorded for any of the three components since
  2026-06-29 23:40:28 (13 days as of this record).
- No confirmed consumer: no downstream reader of
  `REAL_ESTATE_DIRECTOR_REPORT.md` or `REAL_ESTATE_RECURSION_PROPOSAL.md` was
  found anywhere in Core, `.gmv_scripts`, or Dropbox.
- Unregistered: none of the three components appears in
  `GMV.db.service_registry_view`.
- No Service OID: confirmed absent from `SERVICE_SPECIFICATION.md`.
- Runtime located in Dropbox: all three components are executable Python
  scripts residing in the Dropbox Repository tree
  (`99_SYSTEM/03_DIRECTORS/`), not in Core.
- Runtime/Repository boundary violation: `realestate_runner.py` writes
  operational state (`~/.gmv_runtime/realestate_state.json`) from a
  Dropbox-resident script — the same class of violation already established
  for the Constitution CLI feature.
- Market Engine already evolved independently: `market_engine.py` is
  separately registered in Core as `SRV-000004` ("Market Engine",
  `compatibility_mode: 1`), executed via
  `~/.gmv_core/12_SCHEDULER/run_market_engine_compatibility.sh` against a
  distinct, hash-pinned Core copy
  (`01_RUNTIME/legacy/market_engine_v2.py`) that is byte-different from the
  Dropbox copy the frozen components' Director layer was built alongside.
  This Core-governed path runs entirely independently of
  `realestate_runner.py`.

## 5. Current operational state

- Preserved unchanged: all three files remain exactly as found during Task 12.
- Not removed.
- Not migrated.
- Not authoritative: none of the three components has Service authority,
  registration, or a defined owner.
- Historical value retained: the change-cycle/recursion-trigger logic and
  the Director's coordination pattern remain intact and readable as
  reference material.

## 6. Reactivation conditions

Reactivation requires at minimum:

- Project Owner approval.
- Runtime relocation into Core.
- Service registration.
- Runtime governance (logging to `GMV.db`'s `engine_runs`/`timeline`, per
  current operative rules).
- Runtime/Repository boundary compliance.
- Test coverage.
- Review of Market Engine integration, given the confirmed divergence
  between the Dropbox `market_engine.py` copy and the Core-governed,
  hash-pinned `SRV-000004` copy.

## 7. Preservation

No code was deleted. No report was deleted. No historical evidence was
removed. `realestate_runner.py`, `real_estate_director.py`,
`real_estate_recursion_check.py`, `realestate_state.json`, and all
associated report files (`MARKET_REPORT.md`, `PROPERTY_REPORT.md`,
`REAL_ESTATE_DIRECTOR_REPORT.md`, `REAL_ESTATE_RECURSION_PROPOSAL.md`)
remain exactly as found.
