# .doc extraction: BOM and cache-invalidation blast radius

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

- Test fixtures that are real generated binaries (e.g. `tests/fixtures/*.doc`
  produced by `soffice`) are meaningfully more probative than synthetic/mocked
  fixtures for pipeline steps that shell out to external converters — confirm
  by decoding the fixture's actual bytes at least once, don't just trust that
  a test named `..._requires_ocr` passing means the gate logic is exercised
  (it could pass vacuously if the fixture were empty in a different way, e.g.
  zero-byte file that fails earlier in the pipeline).
