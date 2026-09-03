#!/usr/bin/env python3
"""OCR a scanned PDF to plain text via PaddleOCR. Prints text to stdout, nothing else.

Runs only under the isolated venv described in GMV_OCR_PADDLEOCR.md — paddleocr/
paddlepaddle are not installed in the project's main .venv (Python version
incompatibility). Never imported by gmv_evidence_pipeline.py; invoked as a
subprocess so the two dependency sets stay isolated.
"""

from __future__ import annotations

import argparse
import contextlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PAGE_NUM_RE = re.compile(r"-(\d+)\.png$")


def _render_pages(pdf_path: Path, tmp_dir: Path, dpi: int) -> list[Path]:
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise RuntimeError("pdftoppm binary not found on PATH (poppler not installed)")
    prefix = tmp_dir / "page"
    proc = subprocess.run(
        [pdftoppm, "-png", "-r", str(dpi), str(pdf_path), str(prefix)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {proc.stderr.strip()}")
    pages = list(tmp_dir.glob("page-*.png"))
    if not pages:
        raise RuntimeError("pdftoppm produced no page images")
    # Numeric sort: pdftoppm does not zero-pad past 9 pages, so lexicographic
    # sort would put page-10.png before page-2.png.
    pages.sort(key=lambda p: int(PAGE_NUM_RE.search(p.name).group(1)))
    return pages


def _ocr_pages(pages: list[Path], lang: str) -> str:
    # PaddlePaddle/PaddleOCR can print framework banners and model-download
    # progress to stdout on some versions; stdout must stay a pure text
    # contract for the caller, so redirect it to stderr for the duration.
    with contextlib.redirect_stdout(sys.stderr):
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(lang=lang)
        page_texts = []
        for page_path in pages:
            result = ocr.predict(str(page_path))
            res = result[0] if isinstance(result, list) else result
            page_texts.append("\n".join(res.get("rec_texts", [])))
    return "\n".join(page_texts).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path")
    parser.add_argument("--lang", default="it")
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.is_file():
        print(f"not a file: {pdf_path}", file=sys.stderr)
        return 1

    try:
        with tempfile.TemporaryDirectory() as tmp:
            pages = _render_pages(pdf_path, Path(tmp), args.dpi)
            text = _ocr_pages(pages, args.lang)
    except Exception as exc:  # noqa: BLE001 - any failure here must surface as a clear non-zero exit
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
