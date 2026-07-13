# ADR: Market Engine Output Rendering Divergence

Status: Accepted
Date: 2026-07-13
Decision owner: Project Owner

## Context

Post-REBASE 001 Task 1 (forensic archaeology) and Task 2 (isolated functional
validation, corrected) established that the Core-governed release of the
Market Engine (`~/.gmv_core/01_RUNTIME/legacy/market_engine_v2.py`,
`SRV-000004`) is a deliberate, single-commit refactor of the Dropbox
historical source
(`~/Library/CloudStorage/Dropbox/GMV_MASTER_SYSTEM/99_SYSTEM/02_SERVICES/RealEstate/market_engine.py`),
introduced in commit `098c00b7` ("refactor: pin reproducible legacy engine
entrypoints").

Isolated, non-production testing across five independent fixture scenarios
confirmed four reproducible output differences between the two
implementations, all traced to a single root cause: the refactor unified two
previously separate, differently-conditioned fallback rules (one for the
market section, one for the comparables section) into one shared rule in
`append_file_summary()`. The four observed effects:

1. Comparables entries with headings, numbers, and keywords gain a
   `Struttura documento` (headings) block in the Core release that the
   Dropbox source never rendered for comparables.
2. Comparables entries with headings only: the Dropbox source falls back to
   `"Comparable presente ma non ancora strutturato."`; the Core release
   renders the headings block instead.
3. Comparables entries with no recognized content: the fallback message text
   differs (`"Comparable presente ma non ancora strutturato."` vs.
   `"Nessun punto operativo rilevato automaticamente."`).
4. Market entries with headings but no recognized numbers/keywords: the
   Dropbox source renders the headings block **and** the fallback message
   together; the Core release renders the headings block only.

No consumer of the affected report sections was found: `real_estate_director.py`
checks only for `MARKET_REPORT.md`'s existence, never its structural content.

## Decision

**INTENTIONAL_IMPROVEMENT.**

The Project Owner has ruled that all four divergences originate from a single
architectural refactoring that intentionally unified two previously
inconsistent fallback implementations into one shared rendering rule. No
evidence indicates accidental corruption of business logic; the generated
reports remain semantically correct; no confirmed downstream consumer depends
on the previous textual rendering.

The Core rendering (`market_engine_v2.py`, as executed through `SRV-000004`)
is accepted as the runtime behaviour going forward. The Dropbox source's
rendering is reclassified from an implicit compatibility contract to
**`HISTORICAL_BEHAVIOUR_ONLY`** — it remains a valid historical reference of
the pre-refactor implementation but is no longer treated as a behavior the
Core release must reproduce.

## Consequences

- No code change is made to either engine as a result of this decision.
- Future changes to `market_engine_v2.py`'s rendering do not need to preserve
  byte-for-byte output compatibility with the Dropbox source's historical
  fallback/heading rendering.
- `00_CONFIG/LEGACY_ENGINE_INVENTORY.md`'s `LEG-MARKET-ENGINE-001` record is
  updated to reference this decision (see that document for the exact
  addition).
- If `SRV-000004` is exercised against live Dropbox data in the future and
  its output is compared to historical Dropbox-rendered reports, the four
  differences documented here are expected and require no further review.

## References

- Post-REBASE 001 Task 1 — Forensic Archaeology of `market_engine.py`
  Divergence.
- Post-REBASE 001 Task 2 (corrected) — Isolated Functional Validation of
  Market Engine Release.
- Commit `098c00b7` — "refactor: pin reproducible legacy engine entrypoints".
