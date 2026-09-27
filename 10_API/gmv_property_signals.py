#!/usr/bin/env python3
"""Property status/deadline signals for real-estate documents, on top of the
existing evidence scan/extract stages. Reads already-extracted records
(gmv_evidence_pipeline.scan/extract, unchanged) and attaches Laya-derived
signals: scadenza_presente (automatic, validated 14/14), dominio (automatic,
metadata only -- known blind spot on informal maintenance reports, see
below), rischio_alto (always paired with an explicit reliability field, never
a bare boolean -- validated recall only 2/4).

Deliberately excluded: `azione` (not needed for a status+deadlines tool) and
`rischio_medio`/`rischio_basso` as standalone outputs (both are still asked
of the model, because the validated numbers were measured with the full
5-question set in one call -- see gmv_mitigated_schema.py's finding that
which questions are asked together shifts the others -- but shown to fire on
content unrelated to any property, so they are computed and discarded here,
not surfaced).

`dominio` is informational, not a filter: this module processes every
successfully extracted record under the given root regardless of `dominio`'s
own classification. The 14-case real-estate validation
(~/GMV/models/laya/results/real_estate_validation_summary.md) found `dominio`
routes informal maintenance/damage reports to "altro" 2 times out of 3 such
cases -- exactly the documents this tool most needs, so a caller must not use
`dominio == "real_estate"` to decide what to scan. The folder root passed to
scan() is the real signal for "this is a property document"; dominio is
recorded for cross-domain sanity (e.g. spotting a stray unrelated file), not
as a gate.

Laya itself runs only inside the isolated venv at ~/GMV/models/laya/.venv
(see that directory's README.md for the full validated setup and every raw
number cited above) via gmv_property_laya_worker.py as a subprocess -- same
isolation pattern this codebase already uses for PaddleOCR
(gmv_evidence_pipeline.PADDLEOCR_VENV_PYTHON / ocr_paddleocr_pdf.py). No new
dependency was added to this project's own venv or requirements-dev.txt.

Output is Runtime output (file-based, content-addressed cache under
`<evidence_root>/property_signals/`), not a Core SQLite object -- "property"
is not yet a valid Core OID type (ADR_DB008_OID_PREFIX_TYPE_CONSISTENCY.md),
and this module makes no attempt to become one. No automation is wired here:
this module only produces the structured artifact; nothing here schedules,
notifies, or escalates on its own (GMV_ENGINE_DECISION_AUTOMATION_FREEZE.md).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gmv_evidence_pipeline import EvidenceError, read_json, write_json  # noqa: E402

# Same isolation pattern and reasoning as gmv_evidence_pipeline.PADDLEOCR_VENV_PYTHON:
# laya-mlx/mlx are heavy, platform-specific (Apple Silicon) dependencies kept out of
# this project's own venv/requirements-dev.txt. Setup and every validated number are
# documented in ~/GMV/models/laya/README.md.
LAYA_VENV_PYTHON = Path.home() / "GMV" / "models" / "laya" / ".venv" / "bin" / "python3"
LAYA_WORKER_SCRIPT = Path(__file__).parent / "gmv_property_laya_worker.py"

# Bumped whenever gmv_property_laya_worker.py's PRODUCTION_QUESTIONS or aggregation
# logic changes, so a cached signal from a stale question set is never silently reused.
PROPERTY_SIGNAL_VERSION = "0.1"

DEFAULT_TIMEOUT_SECONDS = 120


def property_signal_path(fid: str | None, evidence_root: Path) -> Path | None:
    """Mirrors gmv_evidence_pipeline.semantic_output_path's fid-parsing convention."""
    if not fid or ":" not in fid:
        return None
    prefix, sha256 = fid.split(":", 1)
    if prefix != "sha256" or not sha256:
        return None
    return evidence_root / "property_signals" / f"{sha256}-{PROPERTY_SIGNAL_VERSION}.json"


def _run_laya_worker(text: str, *, timeout: int) -> dict:
    if not LAYA_VENV_PYTHON.is_file():
        raise EvidenceError(
            "LAYA_UNAVAILABLE",
            detail=f"Laya venv not found at {LAYA_VENV_PYTHON} — see ~/GMV/models/laya/README.md",
        )
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv from module constants, no shell, text via stdin
            [str(LAYA_VENV_PYTHON), str(LAYA_WORKER_SCRIPT)],
            input=json.dumps({"text": text}),
            capture_output=True, text=True, timeout=timeout, check=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise EvidenceError("LAYA_TIMEOUT", detail=str(exc)[:2000]) from exc
    except subprocess.CalledProcessError as exc:
        raise EvidenceError("LAYA_ERROR", detail=(exc.stderr or "")[:2000]) from exc
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise EvidenceError("LAYA_INVALID_OUTPUT", detail=proc.stdout[:2000]) from exc


def property_signals_batch(records: list[dict], evidence_root: Path, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> list[dict]:
    """Mirrors gmv_evidence_pipeline.semantic_extract_batch's cache-then-compute
    shape: skip records whose cache file already exists, only failed/missing
    entries invoke the (expensive, subprocess) Laya worker."""
    out = []
    for record in records:
        fid = record.get("file_id")
        if record.get("extraction_status") != "SUCCESS":
            out.append({"file_id": fid, "signal_status": "SKIPPED_NOT_EXTRACTED",
                        "extraction_status": record.get("extraction_status")})
            continue
        cache_path = property_signal_path(fid, evidence_root)
        if cache_path is not None and cache_path.exists():
            out.append(read_json(cache_path, {}))
            continue
        try:
            signals = _run_laya_worker(record["text"], timeout=timeout)
            result = {"file_id": fid, "signal_status": "SUCCESS", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **signals}
            # Only a SUCCESS is ever persisted, mirroring gmv_evidence_pipeline's own
            # semantic_extract_batch convention (mark_analyzed only on "valid"). A
            # transient failure (timeout, venv momentarily missing, MLX OOM) must be
            # retried on the next invocation, not permanently poisoned into the cache.
            if cache_path is not None:
                write_json(cache_path, result)
        except EvidenceError as exc:
            result = {"file_id": fid, "signal_status": exc.code}
            if exc.detail:
                result["error_detail"] = exc.detail
        out.append(result)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("record", type=Path, help="A single extract() output record (JSON), extraction_status=SUCCESS")
    p.add_argument("--evidence-root", type=Path, required=True)
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    args = p.parse_args()
    try:
        output = property_signals_batch([read_json(args.record, {})], args.evidence_root, timeout=args.timeout)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except EvidenceError as exc:
        print(f"property-signals: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
