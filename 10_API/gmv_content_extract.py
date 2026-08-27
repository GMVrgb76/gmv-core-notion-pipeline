#!/usr/bin/env python3
"""Cached deterministic extractor with mandatory pre-extraction hash check."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from gmv_evidence_pipeline import EvidenceError, extract

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("root", type=Path); p.add_argument("--evidence-root", type=Path, required=True); p.add_argument("--max-file-bytes", type=int, default=50_000_000); a = p.parse_args()
    try: print(json.dumps(extract(a.evidence_root, a.root, max_file_bytes=a.max_file_bytes), ensure_ascii=False, indent=2)); return 0
    except EvidenceError as exc: p.error(str(exc))
if __name__ == "__main__": raise SystemExit(main())
