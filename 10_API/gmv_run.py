#!/usr/bin/env python3
"""gmv run v1 — orchestrates scan -> extract -> analyze -> resolve -> candidate
by calling the existing gmv_evidence_pipeline functions directly (batch shapes,
no per-file subprocess fan-out) and gmv_notion_candidate.py as a subprocess for
the candidate step (its CLI is already the clean per-entity contract).

No new checkpoint mechanism: relies entirely on the checkpoints scan/extract/
analyze already have (FILE_INDEX.jsonl, cache/extracted/*.json,
analyze_manifest.json). Web retrieval is out of scope for v1 (declared as
SKIPPED_NOT_PROVIDED, never simulated) and resolve/candidate only run when the
Notion inputs needed for them are actually supplied.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from gmv_evidence_pipeline import (
    EvidenceError,
    consolidate_claims,
    extract,
    read_json,
    resolve_claims,
    scan,
    semantic_extract_batch,
)


def run(
    root: Path,
    evidence_root: Path,
    *,
    model: str,
    artist: str = "unknown",
    endpoint: str = "http://localhost:11434",
    resume: bool = False,
    retry_limit: int = 1,
    timeout: int = 180,
    max_chunk_chars: int = 8000,
    ollama_context: int = 8192,
    num_predict: int = 2048,
    min_adaptive_chunk_chars: int = 500,
    max_adaptive_depth: int = 4,
    max_file_bytes: int = 50_000_000,
    notion_rows: Path | None = None,
    aliases: Path | None = None,
    notion_config: Path | None = None,
    entity_name: str | None = None,
    entity_type: str | None = None,
) -> dict:
    result: dict = {}

    scan(root, evidence_root)
    result["scan"] = "DONE"

    extracted = extract(evidence_root, root, max_file_bytes=max_file_bytes)
    result["extract"] = {"status": "DONE", "records": len(extracted)}

    eligible = [r for r in extracted if r.get("extraction_status") == "SUCCESS"]
    analyzed = semantic_extract_batch(
        eligible, evidence_root, artist=artist, endpoint=endpoint, model=model,
        resume=resume, retry_limit=retry_limit, timeout=timeout, max_chunk_chars=max_chunk_chars,
        context=ollama_context, num_predict=num_predict,
        min_adaptive_chunk_chars=min_adaptive_chunk_chars, max_adaptive_depth=max_adaptive_depth,
    )
    result["analyze"] = {"status": "DONE", "claims": len(analyzed.get("claims", []))}

    # Web retrieval (request/ingest/verify) is a separate, human/agent-driven
    # loop today — v1 never performs or simulates it, only declares the gap.
    result["web_retrieval"] = "SKIPPED_NOT_PROVIDED"

    if notion_rows is None:
        result["resolve"] = "SKIPPED_NOT_CONFIGURED"
        result["candidate"] = "SKIPPED_NOT_CONFIGURED"
        return result

    rows = read_json(notion_rows, {})
    alias_map = read_json(aliases, {}) if aliases else {}
    resolved = resolve_claims(analyzed.get("claims", []), rows, alias_map)
    claims = consolidate_claims(resolved)
    result["resolve"] = {"status": "DONE", "claims": len(claims)}

    if not (notion_config and entity_name and entity_type):
        result["candidate"] = "SKIPPED_NOT_CONFIGURED"
        return result

    claims_path = evidence_root / "run" / "resolved_claims.json"
    claims_path.parent.mkdir(parents=True, exist_ok=True)
    claims_path.write_text(
        json.dumps({"claims": claims}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    candidate_script = Path(__file__).parent / "gmv_notion_candidate.py"
    proc = subprocess.run(
        [sys.executable, str(candidate_script), entity_name,
         "--entity-type", entity_type, "--claims", str(claims_path),
         "--rows", str(notion_rows), "--config", str(notion_config)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        result["candidate"] = {"status": "FAILED", "stderr": proc.stderr[-2000:]}
    else:
        result["candidate"] = {"status": "DONE", "payload": json.loads(proc.stdout)}
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="gmv run v1 — scan/extract/analyze/resolve/candidate orchestrator")
    p.add_argument("root", type=Path)
    p.add_argument("--evidence-root", type=Path, required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--artist", default="unknown")
    p.add_argument("--endpoint", default="http://localhost:11434")
    p.add_argument("--resume", action="store_true", default=False)
    p.add_argument("--retry-limit", type=int, default=1)
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--max-chunk-chars", type=int, default=8000)
    p.add_argument("--ollama-context", type=int, default=8192)
    p.add_argument("--num-predict", type=int, default=2048)
    p.add_argument("--min-adaptive-chunk-chars", type=int, default=500)
    p.add_argument("--max-adaptive-depth", type=int, default=4)
    p.add_argument("--max-file-bytes", type=int, default=50_000_000)
    p.add_argument("--notion-rows", type=Path)
    p.add_argument("--aliases", type=Path)
    p.add_argument("--notion-config", type=Path)
    p.add_argument("--entity-name")
    p.add_argument("--entity-type")
    a = p.parse_args()
    try:
        output = run(
            a.root, a.evidence_root, model=a.model, artist=a.artist, endpoint=a.endpoint,
            resume=a.resume, retry_limit=a.retry_limit, timeout=a.timeout,
            max_chunk_chars=a.max_chunk_chars, ollama_context=a.ollama_context,
            num_predict=a.num_predict, min_adaptive_chunk_chars=a.min_adaptive_chunk_chars,
            max_adaptive_depth=a.max_adaptive_depth, max_file_bytes=a.max_file_bytes,
            notion_rows=a.notion_rows, aliases=a.aliases, notion_config=a.notion_config,
            entity_name=a.entity_name, entity_type=a.entity_type,
        )
        print(json.dumps(output, ensure_ascii=False, indent=2)); return 0
    except EvidenceError as exc:
        print(f"run: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
