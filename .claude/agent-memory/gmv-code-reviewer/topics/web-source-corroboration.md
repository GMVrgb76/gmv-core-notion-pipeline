# Web-evidence corroboration: source identity, not content hash

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
