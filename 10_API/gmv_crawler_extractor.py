#!/usr/bin/env python3
"""GMV Crawler — Extractors (crawler preplan step 10 / spec v0.2 §7).

Content extraction stage (§3's EXTRACT stage): raw file bytes on disk ->
`ExtractionDocument`. Scope for this step, per §7 verbatim: "Prima fase:
PDF, DOCX, TXT, MD." (XLSX/CSV/PPTX/EML/scanned-image OCR are declared
"seconda fase" there -- explicitly out of scope for this module.)

Grounding, read in full before writing this module (per this session's own
established discipline -- read the real code the step depends on before
designing, do not trust spec prose alone):

- `gmv_evidence_pipeline.py::_extract()` already implements this step's
  declared "prima fase" scope (PDF/DOCX/TXT/MD) *and more* (.doc via a
  LibreOffice subprocess, HTML/CSV/JSON as plain text, a PaddleOCR
  subprocess fallback for scanned PDFs with no text layer) -- a working,
  tested extraction dispatcher already exists for this step's entire
  scope. §7's own coherence note ("se PaddleOCR e' confermata, il
  secondo-fase OCR extractor deve riusarla") is itself already satisfied
  by code that predates this step. This module wraps `_extract()` by
  import rather than reimplementing any format-specific extraction logic
  -- the same reuse discipline steps 3/6/7/8 already applied to
  `area35_validator.py`/`secure_storage.py`.

- Deliberately wraps `_extract()` (the pure per-path format dispatcher: one
  path in, `(text, extractor_name)` out or an `EvidenceError`), not the
  higher-level `extract()` in the same module. `extract()` layers a
  `FILE_INDEX.jsonl` content-addressed cache and its own staleness check
  (`sha256_file(path) != row["sha256"]`) on top of `_extract()` -- but the
  crawler already has its own change-detection/identity layer
  (`crawler_source_registry`, steps 3/6; `SourceConnector.content_hash()`,
  step 4). Reusing `extract()`'s own index would introduce a second,
  competing notion of "already seen this file" rather than close a gap --
  the same distinction Correction 6 of the spec draws between preserving
  the *content-hash-first identity model* (reuse) and the *silent-deletion
  behavior* of `scan()`'s index bookkeeping specifically (do not inherit).

- `ExtractionDocument`'s field set is §7's own worked shape, taken
  verbatim (`SOURCE_ID, source_hash, extractor, extractor_version,
  language, text, structural_units[], warnings[], status`), field names
  lowercased to this repository's own dataclass convention
  (`gmv_crawler_contracts.py`/`gmv_atom_validator.py`/
  `gmv_monad_materializer.py` all use snake_case fields for
  spec-originated dataclasses, never the spec's own SCREAMING_CASE
  pseudocode literally).

- `source_hash` (not `content_hash`, despite meaning the same
  sha256:<hex> identity `gmv_crawler_contracts.validate_content_hash()`
  already enforces for `SourceMetadata`/`EvidenceUnit`): kept as the
  spec's own literal field name for this specific dataclass since there
  is no real precedent yet forcing renaming it to `content_hash` here,
  while still validating it against the one real sha256:<hex> format
  definition already committed (imported, not redefined a third time).

- `status` reuses a subset of `gmv_evidence_pipeline.TERMINAL_EXTRACTION`'s
  own vocabulary (SUCCESS/OCR_REQUIRED/UNSUPPORTED_FORMAT/
  EXTRACTION_FAILED -- the four `_extract()` itself can actually produce)
  plus one status this module adds itself, `EXTRACTION_ABORTED_STALE_HASH`
  -- reusing the literal name `extract()` already uses for the same concept
  (source_hash mismatch), not inventing a synonym. `FILE_TOO_LARGE` is not
  reused here: it is `extract()`'s own index-layer concern (a `max_file_bytes`
  policy applied before extraction is attempted at all), out of scope for a
  function that receives one already-selected path.

- `extract_document()` re-derives the real file's hash and compares it to
  the caller-supplied `source_hash` *before* calling `_extract()`, mirroring
  `extract()`'s own stale-hash gate (`sha256_file(path) != row["sha256"]`)
  rather than skipping it. This directly narrows the ordering risk
  Correction 6 (item 3) flags for the crawler generally ("EXTRACT non
  parta se il suo DETECT CHANGE a monte... non ha gia' aggiornato i
  percorsi"): it does not replace a Run Ledger-level ordering guarantee
  (no Run Ledger integration exists yet for the crawler -- out of scope,
  consistent with steps 1-7's "no premature engine" discipline), but it
  does make this one function safe to call even if that ordering is
  violated, instead of silently extracting stale bytes under a caller's
  now-wrong content_hash claim.

- `language` and `structural_units` are honest gaps in this module, not
  silently-approximated values: no language detection is implemented (v1
  always leaves it `None`), and `structural_units` is always `()` because
  segmentation is §3's next pipeline stage (SEGMENT), not this one --
  §33's implementation order has no separately numbered SEGMENT step, so
  building it here would be exactly the "premature engine" this session's
  working method warns against for a stage this step was not asked to
  cover. Both are left for whichever future step actually consumes them,
  the same pattern already used for `EvidenceUnit.text_hash`'s undecided
  format (step 4) and PUBLIC-text computation (step 8).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_crawler_contracts import validate_content_hash  # noqa: E402 -- reused, not reimplemented

from gmv_evidence_pipeline import (  # noqa: E402 -- reused, not reimplemented
    EvidenceError,
    _extract,
    sha256_file,
)

EXTRACTOR_VERSION = "1.0"

# The subset of gmv_evidence_pipeline.TERMINAL_EXTRACTION that _extract()
# itself can actually raise (grepped from _extract(), not guessed -- see
# tests/test_gmv_crawler_extractor.py's cross-check against the real
# function), plus EXTRACTION_ABORTED_STALE_HASH, which this module adds.
STATUS_VALUES = frozenset({
    "SUCCESS",
    "OCR_REQUIRED",
    "UNSUPPORTED_FORMAT",
    "EXTRACTION_FAILED",
    "EXTRACTION_ABORTED_STALE_HASH",
})


@dataclass(frozen=True, slots=True)
class ExtractionDocument:
    """Crawler spec v0.2 §7's ExtractionDocument, field names lowercased to
    this repository's dataclass convention. `source_id` is the same
    identity `crawler_source_registry`/`EvidenceUnit.source_id` (step
    3/4) use for the source this extraction ran against -- not
    reintroducing a separate id scheme.
    """

    source_id: str
    source_hash: str
    status: str
    extractor: str = ""
    extractor_version: str = EXTRACTOR_VERSION
    text: str = ""
    language: str | None = None
    structural_units: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error_detail: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("source_id must not be empty")
        validate_content_hash(self.source_hash)
        if self.status not in STATUS_VALUES:
            raise ValueError(
                f"status must be one of {sorted(STATUS_VALUES)}, got {self.status!r}"
            )
        if self.status == "SUCCESS":
            if not self.text:
                raise ValueError("text must not be empty when status is SUCCESS")
            if not self.extractor:
                raise ValueError("extractor must not be empty when status is SUCCESS")
        else:
            if self.text:
                raise ValueError(f"text must be empty when status is {self.status!r}")
            if self.extractor:
                raise ValueError(f"extractor must be empty when status is {self.status!r}")


def extract_document(path: Path, *, source_id: str, source_hash: str,
                      extractor_version: str = EXTRACTOR_VERSION) -> ExtractionDocument:
    """Extract `path`'s text content, gated on `source_hash` matching the
    file's real current content hash (see module docstring on why this
    check exists here, not only upstream). Never raises for an
    extraction-format failure -- that is reported via `status`/
    `error_detail`, exactly like `gmv_evidence_pipeline.extract()`'s own
    per-file record shape, so a caller processing many sources can iterate
    without a per-file try/except. Still raises `ValueError` for a
    malformed `source_hash` (not the sha256:<hex> format
    `validate_content_hash` enforces) -- a caller bug, not an extraction
    outcome.

    Catches `(EvidenceError, OSError, UnicodeError)`, not only
    `EvidenceError`: `_extract()`'s plain-text branch (.txt/.md/.html/
    .csv/.json) reads with `errors="strict"` and no try/except of its
    own -- a non-UTF-8 file raises a bare `UnicodeDecodeError` straight
    out of `_extract()`, uncaught. `gmv_evidence_pipeline.extract()`
    already guards against exactly this
    (`except (OSError, UnicodeError) as exc:`); `extract_document()`
    reuses the identical exception set for the identical reason, rather
    than silently re-narrowing the safety net `_extract()` itself
    depends on its caller providing."""
    validate_content_hash(source_hash)
    if not path.is_file() or f"sha256:{sha256_file(path)}" != source_hash:
        return ExtractionDocument(
            source_id=source_id, source_hash=source_hash,
            status="EXTRACTION_ABORTED_STALE_HASH", extractor_version=extractor_version,
        )
    try:
        text, extractor = _extract(path)
    except EvidenceError as exc:
        status = str(exc) if str(exc) in STATUS_VALUES else "EXTRACTION_FAILED"
        return ExtractionDocument(
            source_id=source_id, source_hash=source_hash, status=status,
            extractor_version=extractor_version, error_detail=exc.detail or None,
        )
    except (OSError, UnicodeError) as exc:
        return ExtractionDocument(
            source_id=source_id, source_hash=source_hash, status="EXTRACTION_FAILED",
            extractor_version=extractor_version, error_detail=type(exc).__name__,
        )
    return ExtractionDocument(
        source_id=source_id, source_hash=source_hash, status="SUCCESS",
        extractor=extractor, extractor_version=extractor_version, text=text,
    )
