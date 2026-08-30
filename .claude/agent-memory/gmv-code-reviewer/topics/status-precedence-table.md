# STATUS_PRECEDENCE completeness and ordering judgment calls

- **A `STATUS_PRECEDENCE`/"pick the more authoritative status" list must be
  audited against every status literal actually referenced anywhere in the
  same file tree's own gating logic, not just the ones in the demonstrated
  repro.** `gmv_evidence_pipeline.STATUS_PRECEDENCE` (added to fix an
  order-dependent bug in `consolidate_claims` when archive and web claims
  land in the same group) lists 8 statuses but omits `UNVERIFIED` and
  `DISPUTED`, both of which are explicitly recognized elsewhere in the very
  same pipeline (`gmv_notion_candidate.py`'s HOLD-status set) and are legal
  free-text values a claim's `status` field can hold (the LLM extraction
  schema in `ollama_extract`/`SEMANTIC_OUTPUT_SCHEMA` places no enum
  constraint on `status`, only defaults to `SUPPORTED_BY_ARCHIVE` when
  absent). `_better_status("UNVERIFIED", "DISPUTED")` and the swapped-argument
  call return different results (verified empirically 2026-08-29) —
  reproducing, for any status pair outside the precedence list, the exact
  order-dependent bug the function was written to eliminate. The new
  regression test only exercises the `SUPPORTED_BY_WEB`/`SUPPORTED_BY_ARCHIVE`
  pair from the original repro, not the general "any two statuses" case.
  When reviewing a precedence/priority table meant to fix non-determinism,
  grep every literal status/state string referenced anywhere in sibling
  modules' own gating sets before accepting the table as complete.

  **Fixed and verified round 2 (2026-08-29):** `STATUS_PRECEDENCE` now
  includes `UNVERIFIED`/`DISPUTED`, and `_better_status` ranks any status
  absent from the table strictly below every recognized one (so an
  unrecognized LLM status string can only "win" against another unrecognized
  string, never against a real one) — verified this only resolves to
  first-seen-wins in that narrow unrecognized-vs-unrecognized case, which is
  the documented low-stakes residual, not a reopened version of the original
  bug. Full suite re-run independently in a throwaway venv (513 passed, same
  one pre-existing unrelated `adapter_notion.py` credential-scan failure).

- **A completed precedence table can still embed an unreviewed judgment call in
  the *relative* order of statuses that downstream code treats as equals.** In the
  same `STATUS_PRECEDENCE` fix, `DISPUTED` ranks below the whole SUPPORTED/VERIFIED
  tier. No other code in the tree ever ranks `DISPUTED` against `SUPPORTED_BY_ARCHIVE`/
  `SUPPORTED_BY_WEB`/`VERIFIED` — `gmv_notion_candidate.py`'s body-adapter treats
  `UNVERIFIED`/`DISPUTED`/`CONFLICTING`/`MISSING` as identical peers (all -> `HOLD`),
  and `GATE_BLOCKING_STATUS` doesn't even include `UNVERIFIED`/`DISPUTED` at all. So
  today the specific order chosen has zero observable effect except in one narrow,
  untested case: two raw claims about the exact same (subject, predicate, resolved
  object) — one tagged `DISPUTED`, one tagged `SUPPORTED_BY_ARCHIVE` — get merged into
  a single claim by `consolidate_claims`, and the "supported" status silently wins,
  erasing the dispute signal from the consolidated `status` field entirely (it's not
  visible anywhere downstream since only the winning status is kept). Not reproduced
  as an active bug (requires that specific same-fact-both-tags input, not demonstrated
  to occur in real extraction output), but worth naming as a plausible risk and an
  untested combination whenever a precedence table is extended: check not just
  completeness (every literal covered) but whether the *chosen order between two
  specific statuses* is justified by anything other than convenience, especially when
  one of the two encodes "known to conflict" — silently discarding a conflict marker
  during consolidation is the kind of provenance loss this pipeline is designed to
  prevent elsewhere (see [[web-source-corroboration]]). Tracked as an explicit
  known-limitation test by the submitter rather than fixed, since changing the order
  is a product decision about how to treat contested claims.
