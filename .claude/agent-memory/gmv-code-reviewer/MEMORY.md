# gmv-code-reviewer memory (index — see topics/ for detail)

- [.doc extraction: BOM + cache blast radius](topics/doc-extraction-bom-and-cache.md) — LibreOffice BOM survives `.strip()`, extractor_version bump invalidates ALL cached formats, `TimeoutExpired.stderr` can be `None`
- [Web-source corroboration must key on URL identity, not content hash](topics/web-source-corroboration.md) — content-hash file_ids are gameable, `normalize_source_url` needed 2 rounds (scheme/www/query), query-string-only-discriminator is an accepted safe-direction residual
- [verification.json / summarize_web_verification wiring gaps](topics/verification-artifact-wiring.md) — unused optional params, unwired module, "EXECUTED" false positive on pure-archive case, undocumented shared path convention between `gmv_artist_web_retrieve.py` and `gmv_notion_candidate.py`
- [STATUS_PRECEDENCE completeness and ordering](topics/status-precedence-table.md) — must cover every status literal in sibling modules (`UNVERIFIED`/`DISPUTED` were missing), DISPUTED-vs-SUPPORTED order is an unreviewed judgment call (tracked as known-limitation test, not fixed)
- [credential_assignment scanner: single-match guard regression](topics/credential-scanner-guard.md) — `search()`-based skip-on-call-shape logic missed real literals later on the same line; fixed with `finditer`
- [Review methodology notes](topics/review-methodology.md) — always re-run a prior BLOCK's repro against the fix, always reproduce test-suite claims independently in a throwaway venv
