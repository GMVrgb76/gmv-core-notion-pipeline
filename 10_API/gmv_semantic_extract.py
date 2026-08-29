#!/usr/bin/env python3
"""Ollama-local structured semantic extraction program."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from gmv_evidence_pipeline import EvidenceError, semantic_extract_batch

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("record", type=Path); p.add_argument("--model", required=True); p.add_argument("--endpoint", default="http://localhost:11434"); p.add_argument("--evidence-root", type=Path, required=True); p.add_argument("--max-chunk-chars", type=int, default=8000); p.add_argument("--timeout", type=int, default=180); p.add_argument("--ollama-context", type=int, default=8192); p.add_argument("--num-predict", type=int, default=2048); p.add_argument("--min-adaptive-chunk-chars", type=int, default=500); p.add_argument("--max-adaptive-depth", type=int, default=4); p.add_argument("--artist", default="unknown"); a = p.parse_args()
    try: print(json.dumps(semantic_extract_batch([json.loads(a.record.read_text())], a.evidence_root, artist=a.artist, endpoint=a.endpoint, model=a.model, max_chunk_chars=a.max_chunk_chars, timeout=a.timeout, context=a.ollama_context, num_predict=a.num_predict, min_adaptive_chunk_chars=a.min_adaptive_chunk_chars, max_adaptive_depth=a.max_adaptive_depth), ensure_ascii=False, indent=2)); return 0
    except EvidenceError as exc: p.error(str(exc))
if __name__ == "__main__": raise SystemExit(main())
