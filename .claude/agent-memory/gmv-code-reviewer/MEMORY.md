# gmv-code-reviewer memory

- **LibreOffice `soffice --convert-to txt:Text` always writes a UTF-8 BOM** at
  the start of the output file, on every input including empty documents.
  `str.strip()` does NOT remove `﻿`. Any code that reads this output and
  gates on `if not text: raise ...` (e.g. OCR_REQUIRED) must decode with
  `encoding="utf-8-sig"`, not `"utf-8"`, or an empty/non-textual source
  document will silently produce `SUCCESS` with a BOM-only string. Verified
  empirically on 2026-08-29 in `10_API/gmv_evidence_pipeline.py::_extract`
  (`.doc` branch): raw bytes were `b'\xef\xbb\xbf\n'`.

- **Content-addressed extraction caches keyed by `{sha256}-{extractor_version}.json`
  invalidate globally on version bump**, not just for the format that motivated
  the bump. Bumping `extract()`'s default `extractor_version` (e.g. "0.1" ->
  "0.2") to invalidate a stale cached status for one new format (`.doc`) also
  forces re-extraction of every already-cached file across all formats on the
  next run. Not a correctness bug (idempotent recompute), but a real
  performance/blast-radius cost worth flagging as a warning, not silently
  assuming the fix is scoped to the new code path.

- **`subprocess.TimeoutExpired.stderr` can be `None`** even when the call used
  `capture_output=True`, if the timeout fires before any output is captured.
  Code that does `exc.stderr.decode(...)` unconditionally will crash on this
  path; must guard with `(exc.stderr or b"")` before decoding. Verified by
  forcing a real `timeout=0.001` against `soffice` and observing
  `exc.stderr is None`.

- When a review previously issued BLOCK with an empirically demonstrated
  repro (not just a theoretical concern), on re-review always re-run the same
  repro against the fixed code rather than trusting the diff/description —
  in this case both blockers (BOM survival through `.strip()`, and stale
  `-0.1.json` cache shadowing the new `.doc` extractor) were independently
  reproduced and confirmed fixed, not just asserted by the submitter's test
  suite.

- Test fixtures that are real generated binaries (e.g. `tests/fixtures/*.doc`
  produced by `soffice`) are meaningfully more probative than synthetic/mocked
  fixtures for pipeline steps that shell out to external converters — confirm
  by decoding the fixture's actual bytes at least once, don't just trust that
  a test named `..._requires_ocr` passing means the gate logic is exercised
  (it could pass vacuously if the fixture were empty in a different way, e.g.
  zero-byte file that fails earlier in the pipeline).

- **"Corroborated by N distinct sources" implemented as "N distinct content-hash
  file_ids" is not the same guarantee**, and the gap is trivially triggered
  without adversarial intent. In `10_API/gmv_artist_web_retrieve.py`
  (`ingest_web_findings`/`verify_local`), a web finding's `file_id` is
  `sha256(evidence_excerpt)`; the claim itself carries no `url`/domain field,
  and `verify_local` counts `len(source_file_ids)` only. Two quotes pulled
  from the *same* URL (different paragraphs, or a re-fetch after a page edit)
  produce two distinct file_ids and satisfy `min_corroborating_sources=2`,
  promoting the claim to `VERIFIED` and passing `gate()` from a single real
  source — reproduced empirically 2026-08-29. Any "N independent sources"
  corroboration check must be verified to actually key on the source
  identity (URL/domain), not on a hash of the extracted text, before trusting
  the safety claim in its docstring.

- **Content-addressing keyed on excerpt/body text (not on a stable source
  identifier) silently overwrites sibling metadata when two different real
  sources happen to share exact text.** In the same module, two findings
  with identical `evidence_excerpt` but different `url` collapse to the same
  `sha256` file_id; the second `ingest_web_findings` call's `url` silently
  replaces the first in both the in-memory index dict and the on-disk
  `cache/web/{sha}.json` snapshot, with no warning — reproduced empirically.
  This is a provenance-preservation violation (auditing a claim by its
  file_id can return the wrong URL) even though its net effect on the gate
  is a safe-direction false negative (undercounts corroboration) rather than
  a false positive.

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

- Before judging a claimed test-suite result (e.g. "497 passed, 1 pre-existing
  unrelated failure"), actually create a throwaway venv and run the suite
  yourself if `pytest` isn't already on PATH — in this repo it usually isn't
  (`requirements-dev.txt` pins it, but the base interpreter doesn't have it
  installed). Do not accept the submitter's reported numbers without
  independent reproduction when it's cheap to do (`python3 -m venv /tmp/x &&
  /tmp/x/bin/pip install -q pytest ... && /tmp/x/bin/python -m pytest`).

- **A "source identity" normalizer fixed only against the literal repro that
  was demonstrated, not against the general class of the bug, still leaves
  the same exploit open.** `gmv_artist_web_retrieve.normalize_source_url`
  was added specifically to stop the same URL, quoted twice with different
  excerpts, from counting as two independent corroborating sources
  (lowercases scheme/netloc, strips trailing `/` from path, drops fragment).
  It does NOT unify `http://` vs `https://` on the same host, does NOT unify
  `www.` vs non-`www.`, and does NOT strip tracking query params — so two
  citations of the literal same real-world page reached via
  `http://example.com/x` and `https://example.com/x` (or `www.example.com`
  vs `example.com`, or `?utm_source=a` vs `?utm_source=b`) still produce two
  distinct `source_url` values and satisfy `min_corroborating_sources=2`,
  falsely promoting a single-source claim to `VERIFIED` and passing `gate()`
  — reproduced empirically 2026-08-29 end-to-end (`ingest_web_findings` ->
  `resolve_claims` -> `consolidate_claims` -> `verify_local` -> `gate`).
  These are not adversarial edge cases: an ordinary human pasting two links
  copied from a browser routinely differs by exactly these axes. When
  reviewing a fix for a "counted as N independent sources but was really
  one" bug, always test the normalizer against scheme/subdomain/tracking-param
  variants of the *same* real source, not just the identical-URL-string case
  that was in the original repro — a fix that closes only the literal repro
  and not the general normalization problem will pass the submitter's own
  new regression test while leaving the safety property it claims
  ("independent sources") false in the docstring.

- A constant like `GATE_BLOCKING_STATUS` moved into the shared module
  (`gmv_evidence_pipeline.py`) and imported by a new module
  (`gmv_artist_web_retrieve.py`) rather than duplicated as a literal set in
  both places is the right pattern here — check `git diff origin/main` on
  the shared file too when a submitter says a dependency-module change was
  "just a revert"/no-op; in this case the diff also added a real new
  gate-blocking status (`SUPPORTED_BY_WEB`) that did not exist in `main` at
  all, contradicting the submitter's claim that gate() "already correctly"
  blocked on it — the end state was correct, but the description of what
  changed was not, and would have gone unverified without reading the diff.

- **A URL-identity fix that discards the query string entirely closes the
  "http vs https vs www vs tracking-param" blocker but opens a narrower one:
  sites that use the query string as the ONLY page discriminator (e.g.
  `article.php?id=123` vs `?id=456`, common on PHP/CMS/forum sites) now
  collapse two genuinely different pages into one `source_url`.** In
  `gmv_artist_web_retrieve.normalize_source_url`, verified empirically
  2026-08-29: this failure is in the safe direction (under-counts distinct
  sources -> claim stays `SUPPORTED_BY_WEB`/`INSUFFICIENT_EVIDENCE` instead
  of being falsely promoted to `VERIFIED`), so it does not reopen the
  original blocker, but it is a real, non-rare limitation worth flagging as
  a warning rather than ignoring just because the net direction is safe.
  When reviewing any URL/source-identity normalizer, explicitly test the
  "un-collapse" direction too (does the fix now conflate things that should
  stay distinct?), not just the "does it collapse the demonstrated
  duplicates" direction.

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

- **Round-2 verification of the two `STATUS_PRECEDENCE`/`summarize_web_verification`
  blockers above (2026-08-29): both genuinely fixed, confirmed by re-reading the diff,
  re-running the full suite in a throwaway venv (513 passed, same one pre-existing
  unrelated `adapter_notion.py` credential-scan failure), and reading the new tests'
  actual assertions rather than trusting their names.** `summarize_web_verification`
  now takes `web_file_ids` and only counts a claim as web-touched if a `source_file_id`
  is actually in `WEB_INDEX.jsonl`; the pure-archive negative case is now covered by
  an end-to-end `main()` test. `STATUS_PRECEDENCE` now includes `UNVERIFIED`/`DISPUTED`,
  and `_better_status` ranks any status absent from the table strictly below every
  recognized one (so an unrecognized LLM status string can only "win" against another
  unrecognized string, never against a real one) — verified this only resolves to
  first-seen-wins in that narrow unrecognized-vs-unrecognized case, which is the
  documented low-stakes residual, not a reopened version of the original bug.

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
  prevent elsewhere (see the URL-identity and content-hash provenance entries above).

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
