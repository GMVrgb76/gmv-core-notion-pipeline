#!/usr/bin/env python3
"""Read-only aggregation of the evidence/Notion pipeline state, for gmv status.

Discovers per-artist evidence roots under a parent directory and summarizes
what gmv_evidence_pipeline.py has already written to disk (scan index,
extraction cache, analyze manifest). Never writes anything.
"""

from __future__ import annotations

import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parent
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from gmv_evidence_pipeline import load_analyze_manifest, load_index, paths, read_json
from health_service import HealthResult

# extraction_status values that mean "this file needs a human/a re-run", as opposed
# to expected terminal skips (UNSUPPORTED_FORMAT, FILE_TOO_LARGE) that are not
# actionable pipeline problems.
NEEDS_ATTENTION = {"EXTRACTION_FAILED", "OCR_REQUIRED", "EXTRACTION_ABORTED_STALE_HASH"}


def discover_evidence_roots(evidence_roots_dir: Path) -> list[Path]:
    """Each immediate subdirectory of evidence_roots_dir with an index/FILE_INDEX.jsonl
    is treated as one artist's evidence_root."""
    if not evidence_roots_dir.is_dir():
        return []
    roots = []
    for candidate in sorted(evidence_roots_dir.iterdir()):
        if not candidate.is_dir():
            continue
        index_path, _ = paths(candidate)
        if index_path.is_file():
            roots.append(candidate)
    return roots


def _artist_summary(evidence_root: Path) -> dict:
    index_path, cache = paths(evidence_root)
    index = load_index(index_path)
    extraction_status_counts: dict[str, int] = {}
    for record_path in sorted((cache / "extracted").glob("*.json")):
        record = read_json(record_path, {})
        status = record.get("extraction_status", "UNKNOWN")
        extraction_status_counts[status] = extraction_status_counts.get(status, 0) + 1
    manifest = load_analyze_manifest(evidence_root)
    analyze_counts = {"valid": 0, "failed": 0}
    for entry in manifest.values():
        status = entry.get("status")
        if status in analyze_counts:
            analyze_counts[status] += 1
    needs_attention = sum(n for status, n in extraction_status_counts.items() if status in NEEDS_ATTENTION)
    return {
        "artist": evidence_root.name,
        "files_scanned": len(index),
        "extraction_status_counts": extraction_status_counts,
        "analyze_counts": analyze_counts,
        "needs_attention": needs_attention,
    }


def pipeline_results(evidence_roots_dir: Path) -> list[HealthResult]:
    roots = discover_evidence_roots(evidence_roots_dir)
    if not roots:
        return [
            HealthResult(
                "pipeline.evidence",
                "PASS",
                "informational",
                f"no evidence roots found under {evidence_roots_dir} — gmv run has not been executed yet",
            )
        ]
    summaries = [_artist_summary(root) for root in roots]
    total_files = sum(s["files_scanned"] for s in summaries)
    total_needs_attention = sum(s["needs_attention"] for s in summaries)
    total_analyzed = sum(s["analyze_counts"]["valid"] + s["analyze_counts"]["failed"] for s in summaries)
    message = (
        f"{len(summaries)} artist(s), {total_files} file(s) scanned, "
        f"{total_analyzed} analyzed, {total_needs_attention} needing attention"
    )
    status = "DEGRADED" if total_needs_attention else "PASS"
    results = [HealthResult("pipeline.evidence", status, "informational", message)]
    for summary in summaries:
        if summary["needs_attention"]:
            breakdown = ", ".join(
                f"{status}={count}"
                for status, count in sorted(summary["extraction_status_counts"].items())
                if status in NEEDS_ATTENTION
            )
            results.append(
                HealthResult(
                    f"pipeline.evidence.{summary['artist']}",
                    "DEGRADED",
                    "informational",
                    f"{summary['needs_attention']} file(s) need attention ({breakdown})",
                )
            )
    return results
