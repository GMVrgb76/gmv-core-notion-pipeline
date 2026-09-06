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
import re
import sys
import urllib.parse
from pathlib import Path

from gmv_evidence_pipeline import (
    EvidenceError, GATE_BLOCKING_STATUS, all_fields, load_index, now, paths, save_index, write_json, norm,
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


def build_retrieval_requests(entity_name: str, entity_type: str, claims: list[dict], fields: set[str]) -> list[dict]:
    """Deterministic gap detection, no network access. Reuses gate()'s own bad-status
    vocabulary so a predicate stuck on SUPPORTED_BY_WEB (retrieved but not yet
    corroborated) is requested again, not silently treated as already satisfied.

    One combined request per entity, not one per missing field: a single good
    source (a biography page, a gallery bio) typically covers several fields at
    once, so the interactive session should search broadly and extract as much
    as a source actually offers, rather than run one narrow query per field."""
    by_predicate = {norm(c["predicate"]): c for c in claims}
    missing = sorted(
        field for field in fields
        if by_predicate.get(norm(field)) is None or by_predicate[norm(field)].get("status") in GATE_BLOCKING_STATUS
    )
    if not missing:
        return []
    return [{"entity_name": entity_name, "entity_type": entity_type, "missing_fields": missing, "query": entity_name}]


def normalize_web_object_value(tipo: str, object_raw: str) -> str:
    """Best-effort canonicalization so two sources phrasing the same fact
    differently corroborate instead of silently creating two separate,
    never-merging claims. Only 'anno' fields are touched -- deliberately
    conservative, not a general fuzzy-text matcher.

    tipo == 'anno': extracts the first 4-digit year found (1000-2099) and
    normalizes to that alone -- a range like "between 1910 and 1922"
    normalizes to "1910", favoring under-precision over fabricating false
    certainty. The original wording always survives untouched in
    evidence_excerpt, so a human reviewing the bundle still sees the real
    uncertainty; only the machine-comparable object_raw is canonicalized.

    Uses digit lookaround, not \\b: a plain word-boundary regex fails right
    after a letter prefix like "c1910" (letter and digit are both \\w, so
    there is no boundary between them) and would silently skip ahead to the
    WRONG year in a range like "c1910-2006" (matching the death year instead
    of the birth year) -- verified against this exact real case."""
    if tipo == "anno":
        match = re.search(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)", object_raw)
        if match:
            return match.group(1)
    return object_raw


def ingest_web_findings(entity_name: str, findings: list[dict], evidence_root: Path, *,
                        field_types: dict[str, str] | None = None) -> list[dict]:
    """Records findings the interactive session already fetched (text, not a URL to
    fetch) as content-addressed web snapshots plus raw claims in the same shape
    ollama_extract() produces, so they flow through the existing
    resolve_claims/consolidate_claims/gate machinery unchanged.

    All findings are validated before any file is written, so a bad finding later in
    the batch never leaves orphaned snapshots from earlier ones. The snapshot's
    file_id is keyed on (url, excerpt) together, not the excerpt alone: two different
    pages that happen to quote identical text must not overwrite each other's
    provenance, and the same page cited twice for different excerpts must not be
    treated as two independent sources by verify_local (see normalize_source_url).

    field_types (predicate -> config.json 'tipo', e.g. {"anno_nascita": "anno"}) is
    optional and defaults to no normalization, preserving prior behavior exactly for
    any caller that doesn't pass it. When given, normalize_web_object_value()
    canonicalizes object_raw for known field types (currently just 'anno') before
    the claim is built, so differently-worded sources for the same fact land on the
    same resolved_object_id in resolve_claims() and get merged by consolidate_claims()
    instead of silently never corroborating each other."""
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
        tipo = (field_types or {}).get(finding["predicate"])
        object_raw = normalize_web_object_value(tipo, finding["object_raw"]) if tipo else finding["object_raw"]
        claims.append({"subject_raw": entity_name, "predicate": finding["predicate"], "object_raw": object_raw,
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
    ing_p.add_argument("--config", type=Path); ing_p.add_argument("--entity-type")
    ver_p = sub.add_parser("verify"); ver_p.add_argument("--claims", type=Path, required=True)
    ver_p.add_argument("--evidence-root", type=Path, required=True); ver_p.add_argument("--min-sources", type=int, default=2)
    a = p.parse_args()
    try:
        if a.command == "request":
            doc = json.loads(a.claims.read_text()); claims = doc.get("claims", doc) if isinstance(doc, dict) else doc
            cfg = json.loads(a.config.read_text()); fields = all_fields(cfg, a.entity_type)
            output = build_retrieval_requests(a.entity_name, a.entity_type, claims, fields)
        elif a.command == "ingest":
            doc = json.loads(a.findings.read_text()); findings = doc.get("findings", doc) if isinstance(doc, dict) else doc
            field_types = None
            if a.config and a.entity_type:
                cfg = json.loads(a.config.read_text())
                field_types = {k: v.get("tipo") for k, v in cfg["entita"][a.entity_type.lower()].get("campi", {}).items()}
            output = ingest_web_findings(a.entity_name, findings, a.evidence_root, field_types=field_types)
        else:
            doc = json.loads(a.claims.read_text()); claims = doc.get("claims", doc) if isinstance(doc, dict) else doc
            output = verify_local(claims, a.evidence_root, min_corroborating_sources=a.min_sources)
        print(json.dumps(output, ensure_ascii=False, indent=2)); return 0
    except EvidenceError as exc:
        print(f"web_retrieve: {exc}", file=sys.stderr); return 2

if __name__ == "__main__": raise SystemExit(main())
