# verification.json / summarize_web_verification wiring gaps

- **A newly added optional parameter is not evidence that a gap is closed
  until you grep every call site.** `write_evidence_bundle(..., verification:
  dict | None = None)` was added specifically to receive `verify_local()`'s
  output, but neither `gmv_artist_web_retrieve.py` nor the sole existing
  caller (`gmv_notion_candidate.py`) actually passes it — confirmed by
  `grep -rn "write_evidence_bundle("`. The persisted `verification.json`
  audit artifact stays on the stale `NOT_EXECUTED` placeholder forever in
  practice, even though local verification did run and did affect the gate
  via claim `status`. Always check callers, not just the function signature,
  before crediting a diff with "wiring X into Y".

- **`gmv_artist_web_retrieve.py` remains fully unwired from the real
  candidate pipeline as of 2026-08-29**: `gmv_notion_candidate.py` has zero
  references to `verify_local`, `ingest_web_findings`, or
  `gmv_artist_web_retrieve` (confirmed by grep), and
  `write_evidence_bundle`'s `verification` parameter is still never passed
  by its only caller. The module's internal corroboration-safety logic can
  be correct in isolation while having zero live exposure in production —
  don't let a clean module-level fix imply the feature is deployed end to
  end; always grep the actual caller chain into `gmv_notion_candidate.py`
  before crediting a fix with closing out the feature, not just the bug.

- **A "reflects the real outcome instead of a static placeholder" fold function
  can still be an unconditional static placeholder in the one case that
  matters most.** `gmv_evidence_pipeline.summarize_web_verification(claims)`
  (wired into `gmv_notion_candidate.py::main()`'s `--run-dir` branch, called
  unconditionally on every invocation) always returns `{"status": "EXECUTED",
  ...}`, even when the claims list contains zero web-sourced claims (i.e. a
  100%-archive artist that never went through `gmv_artist_web_retrieve.py` at
  all — currently the only real-world case, since web retrieval requires an
  interactive session per its own docstring). Verified empirically 2026-08-29:
  `summarize_web_verification([{"predicate": "born", "status":
  "SUPPORTED_BY_ARCHIVE"}])` returns `{"status": "EXECUTED",
  "verified_predicates": [], "pending_predicates": []}`. This directly
  contradicts the function's own docstring ("only once a caller has actually
  run web retrieval") and is a regression vs. the prior static
  `"NOT_EXECUTED"` placeholder: the old value was truthfully uninformative,
  the new one is confidently wrong for the common case, in an audit artifact
  (`verification.json`) whose whole purpose is to be trustworthy provenance.
  Not caught by any of the 4 new tests because every new test constructs a
  claims list with at least one web-sourced claim — none test the pure-archive
  case through `--run-dir`. When reviewing any "now reports the real outcome"
  fold/summary function, always construct the *negative* case (the input
  where the thing being summarized never happened at all) and check the
  function doesn't default to claiming it happened anyway.

  **Fixed and verified round 2 (2026-08-29):** `summarize_web_verification`
  now takes `web_file_ids` and only counts a claim as web-touched if a
  `source_file_id` is actually in `WEB_INDEX.jsonl`; the pure-archive negative
  case is now covered by an end-to-end `main()` test.

- **A "bridge" PR that links two CLI tools only through a shared on-disk index-file
  convention (`run_dir.parent / "state" / index / *.jsonl`) has no test or doc proving
  the two tools are actually ever invoked with matching paths in a real run.**
  `gmv_artist_web_retrieve.py` takes an operator-supplied `--evidence-root` with no
  default tying it to `run_dir.parent/"state"`; `gmv_notion_candidate.py` assumes that
  exact convention. Grepped the whole tree: no orchestrator script or README documents
  or enforces this pairing. The new tests hand-construct both index files under a
  matching `state/` directory, which proves the merge logic is correct but not that
  operators/automation will ever actually produce that alignment. When reviewing a
  feature that "wires" two independently-invoked CLI entry points via a shared file
  path convention rather than an explicit shared argument, flag the missing
  integration glue/doc as a gap even if the merge function itself is well tested.
