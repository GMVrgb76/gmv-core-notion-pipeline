#!/usr/bin/env python3
"""Deterministic entity resolver over a read-only normalized Notion snapshot."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from gmv_evidence_pipeline import consolidate_claims, resolve_claims

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("semantic", type=Path); p.add_argument("--rows", type=Path, required=True); p.add_argument("--aliases", type=Path); a = p.parse_args()
    semantic = json.loads(a.semantic.read_text()); aliases = json.loads(a.aliases.read_text()) if a.aliases else {}
    resolved = resolve_claims(semantic["claims"], json.loads(a.rows.read_text()), aliases)
    print(json.dumps({"resolved": resolved, "claims": consolidate_claims(resolved)}, ensure_ascii=False, indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
