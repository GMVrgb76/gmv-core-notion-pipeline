#!/usr/bin/env python3
"""Local, interactive-mode web evidence retrieval (no network calls in this process).

This module never fetches a URL itself: WebSearch/WebFetch belong to the interactive
Claude Code session driving it, never to a subprocess (no external search API, no
recurring cost, consistent with the rest of this pipeline being local-first and
fail-closed). The flow is deterministic on both ends of that interactive step:

  build_retrieval_requests()  -- decides WHAT is missing, no network access
  ... interactive session runs WebSearch/WebFetch itself, fills in findings ...
  ingest_web_findings()       -- records already-fetched findings as claims, no network access
  verify_local()              -- promotes corroborated claims so they can pass gate()

A single web source is never enough on its own: gate() (gmv_evidence_pipeline.py)
treats status SUPPORTED_BY_WEB as gate-blocking (see GATE_BLOCKING_STATUS) until
verify_local promotes a claim to VERIFIED, which happens only once at least
`min_corroborating_sources` independent web sources agree on the same object.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
from pathlib import Path

from gmv_evidence_pipeline import (
    EvidenceError, GATE_BLOCKING_STATUS, load_index, now, paths, required_fields, save_index, write_json, norm,
)

REQUIRED_FINDING_FIELDS = ("predicate", "object_raw", "evidence_excerpt", "url")


def normalize_source_url(url: str) -> str:
    """Same page fetched/quoted twice must count as ONE source, not two: this is the
    identity corroboration counts against, independent of which excerpt was pulled from it.
    Deliberately collapses distinctions that don't imply a different publisher/page:
    scheme (http/https redirects are the same page), a leading "www." host prefix, and
    the query string (mostly tracking parameters in practice). Favors under-counting
    distinct sources over over-counting them, since a single source must never verify
    a claim alone — merging two truly different pages that coincidentally share a path
    is the safer failure direction than treating one page as two independent sources."""
    parsed = urllib.parse.urlsplit(url.strip())
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."): netloc = netloc[4:]
    return urllib.parse.urlunsplit(("", netloc, parsed.path.rstrip("/"), "", ""))


def build_retrieval_requests(entity_name: str, entity_type: str, claims: list[dict], required: set[str]) -> list[dict]:
    """Deterministic gap detection, no network access. Reuses gate()'s own bad-status
    vocabulary so a predicate stuck on SUPPORTED_BY_WEB (retrieved but not yet
    corroborated) is requested again, not silently treated as already satisfied."""
    by_predicate = {norm(c["predicate"]): c for c in claims}
    requests = []
    for field in sorted(required):
        claim = by_predicate.get(norm(field))
        if claim is None or claim.get("status") in GATE_BLOCKING_STATUS:
            requests.append({"entity_name": entity_name, "entity_type": entity_type, "predicate": field,
                              "query": f"{entity_name} {field.replace('_', ' ')}"})
    return requests


def ingest_web_findings(entity_name: str, findings: list[dict], evidence_root: Path) -> list[dict]:
    """Records findings the interactive session already fetched (text, not a URL to
    fetch) as content-addressed web snapshots plus raw claims in the same shape
    ollama_extract() produces, so they flow through the existing
    resolve_claims/consolidate_claims/gate machinery unchanged.

    All findings are validated before any file is written, so a bad finding later in
    the batch never leaves orphaned snapshots from earlier ones. The snapshot's
    file_id is keyed on (url, excerpt) together, not the excerpt alone: two different
    pages that happen to quote identical text must not overwrite each other's
    provenance, and the same page cited twice for different excerpts must not be
    treated as two independent sources by verify_local (see normalize_source_url)."""
    for finding in findings:
        missing = [key for key in REQUIRED_FINDING_FIELDS if not finding.get(key)]
        if missing: raise EvidenceError(f"WEB_FINDING_MISSING_FIELD:{','.join(missing)}")
    evidence_root = evidence_root.expanduser().resolve()
    index_path = evidence_root / "index" / "WEB_INDEX.jsonl"
    _, cache = paths(evidence_root)
    rows = load_index(index_path)
    claims = []
    for finding in findings:
        source_url = normalize_source_url(finding["url"])
        digest = hashlib.sha256(f"{source_url}|{finding['evidence_excerpt']}".encode()).hexdigest()
        fid = f"sha256:{digest}"
        fetched_at = finding.get("fetched_at") or now()
        rows[fid] = {"file_id": fid, "url": finding["url"], "source_url": source_url, "fetched_at": fetched_at, "source_type": "WEB"}
        write_json(cache / "web" / f"{digest}.json", {"file_id": fid, "url": finding["url"],
                   "fetched_at": fetched_at, "text": finding["evidence_excerpt"]})
        claims.append({"subject_raw": entity_name, "predicate": finding["predicate"], "object_raw": finding["object_raw"],
                        "evidence_excerpt": finding["evidence_excerpt"], "file_id": fid,
                        "source_type": "WEB", "status": "SUPPORTED_BY_WEB"})
    save_index(index_path, rows)
    return claims


def verify_local(claims: list[dict], evidence_root: Path, *, min_corroborating_sources: int = 2) -> list[dict]:
    """The 'local verifier adapter' write_evidence_bundle's placeholder anticipated.
    Deliberately conservative: a claim stays SUPPORTED_BY_WEB (gate-blocking) unless
    corroborated by at least `min_corroborating_sources` DISTINCT source URLs (looked
    up in WEB_INDEX.jsonl by file_id, normalized so the same page counts once) —
    not by raw source_file_ids count. Re-fetching or re-quoting the same page twice
    produces two file_ids (two excerpts) but only one source_url, and must not count
    as corroboration on its own."""
    index_path = evidence_root.expanduser().resolve() / "index" / "WEB_INDEX.jsonl"
    web_index = load_index(index_path)
    out = []
    for claim in claims:
        item = dict(claim)
        if item.get("status") == "SUPPORTED_BY_WEB":
            source_urls = {web_index[fid]["source_url"] for fid in item.get("source_file_ids", []) if fid in web_index}
            if len(source_urls) >= min_corroborating_sources: item["status"] = "VERIFIED"
        out.append(item)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Local web evidence retrieval (request/ingest/verify; no network calls here)")
    sub = p.add_subparsers(dest="command", required=True)
    req_p = sub.add_parser("request"); req_p.add_argument("entity_name"); req_p.add_argument("--entity-type", required=True)
    req_p.add_argument("--claims", type=Path, required=True); req_p.add_argument("--config", type=Path, required=True)
    ing_p = sub.add_parser("ingest"); ing_p.add_argument("entity_name"); ing_p.add_argument("--findings", type=Path, required=True)
    ing_p.add_argument("--evidence-root", type=Path, required=True)
    ver_p = sub.add_parser("verify"); ver_p.add_argument("--claims", type=Path, required=True)
    ver_p.add_argument("--evidence-root", type=Path, required=True); ver_p.add_argument("--min-sources", type=int, default=2)
    a = p.parse_args()
    try:
        if a.command == "request":
            doc = json.loads(a.claims.read_text()); claims = doc.get("claims", doc) if isinstance(doc, dict) else doc
            cfg = json.loads(a.config.read_text()); required = required_fields(cfg, a.entity_type)
            output = build_retrieval_requests(a.entity_name, a.entity_type, claims, required)
        elif a.command == "ingest":
            doc = json.loads(a.findings.read_text()); findings = doc.get("findings", doc) if isinstance(doc, dict) else doc
            output = ingest_web_findings(a.entity_name, findings, a.evidence_root)
        else:
            doc = json.loads(a.claims.read_text()); claims = doc.get("claims", doc) if isinstance(doc, dict) else doc
            output = verify_local(claims, a.evidence_root, min_corroborating_sources=a.min_sources)
        print(json.dumps(output, ensure_ascii=False, indent=2)); return 0
    except EvidenceError as exc:
        print(f"web_retrieve: {exc}", file=sys.stderr); return 2

if __name__ == "__main__": raise SystemExit(main())
