#!/usr/bin/env python3
"""Run-scoped manifest helper for the evidence pipeline.

It does not create a second ledger: callers pass the existing ledger run
directory, and this helper writes only a pipeline manifest inside that run.
"""
from __future__ import annotations
from pathlib import Path
from gmv_evidence_pipeline import now, write_json

def write_manifest(run_dir: Path, file_ids: list[str], index_path: Path) -> Path:
    path = run_dir / "evidence" / "run_manifest.json"
    write_json(path, {"schema": "gmv.evidence.run-manifest.v0.1", "created_at": now(),
                      "index_path": str(index_path.resolve()), "file_ids": sorted(set(file_ids)),
                      "mode": "DRY_RUN_ONLY"})
    return path
