#!/usr/bin/env python3
"""Deterministic, read-only evidence index program."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from gmv_evidence_pipeline import EvidenceError, scan

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("root", type=Path); p.add_argument("--evidence-root", type=Path, required=True); a = p.parse_args()
    try: print(json.dumps(scan(a.root, a.evidence_root), ensure_ascii=False, indent=2)); return 0
    except EvidenceError as exc: p.error(str(exc))
if __name__ == "__main__": raise SystemExit(main())
