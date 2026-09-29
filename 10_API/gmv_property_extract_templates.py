#!/usr/bin/env python3
"""Real-estate fact extraction via NuExtract3, built on top of the generic
gmv_evidence_pipeline.nuextract_extract(). Implements the SOGGETTO/PREDICATO/
OGGETTO fact shape defined in 00_CONFIG/GMV_ONTOLOGY_REGISTRY_REALESTATE_v0.1.json's
`fact_extraction_contract` (user proposal, 2026-09-28): one uniform template
across every document type (no per-document-type template, no separate
classification pass -- `ha_tipo_documento` is just one of the extracted facts),
with the model's own `predicato` field constrained by an enum built FROM the
registry, so an ungoverned predicate cannot even be emitted, let alone silently
governed -- reuse-before-invention enforced mechanically, not just by convention.

Every fact is defensively re-validated against the registry after parsing
(never trust that enum-constrained decoding alone is airtight -- this project's
own history today includes NuExtract3 not respecting a required-field
constraint without explicit `format`). A fact with an ungoverned predicate is
dropped, not silently kept or coerced.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gmv_evidence_pipeline as evidence  # noqa: E402
from gmv_evidence_pipeline import nuextract_extract  # noqa: E402
from gmv_ontology_check import object_matches_range, predicate_is_governed  # noqa: E402

DEFAULT_AMBITO_ENUM = ["immobile", "unita", "quota_individuale", "intero_condominio", "conto_corrente"]
STATO_EVIDENZA_ENUM = ["esplicito", "inferito"]

# qualifiers carried through resolve_claims()/consolidate_claims() unchanged (both
# already copy/forward an unrecognized "qualifiers" key -- no changes needed there).
QUALIFIER_FIELDS = ("valuta", "ambito", "pagina", "data_documento", "competenza_da", "competenza_a")


def build_fact_template(registry: dict) -> dict:
    """Builds the NuExtract3 template from the registry's own governed predicate
    list -- never hardcoded, so a newly-promoted predicate is usable the moment
    it's added to the registry, with no second place to update."""
    predicate_ids = sorted(p["predicate_id"] for p in registry["predicates"])
    ambito_enum = registry.get("proposed_vocabulary_v0_1", {}).get("ambito_enum", DEFAULT_AMBITO_ENUM)
    return {
        "fatti": [{
            "soggetto": "verbatim-string",
            "predicato": predicate_ids,
            "oggetto": "verbatim-string",
            "valuta": "verbatim-string",
            "ambito": ambito_enum,
            "pagina": "integer",
            "testo_evidenza": "verbatim-string",
            "data_documento": "date-time",
            "competenza_da": "date-time",
            "competenza_a": "date-time",
            "stato_evidenza": STATO_EVIDENZA_ENUM,
        }]
    }


def extract_facts(record: dict, registry: dict, *, endpoint: str, model: str = "numind/nuextract3:q4_k_m",
                  timeout: int = 120, num_ctx: int = 8192, num_predict: int = 4096) -> dict:
    """Runs the fact template against one already-extracted document record.
    Returns {"file_id", "facts": [...governed facts...], "rejected_facts": [...],
    "_runtime": {...}}. `rejected_facts` is never silently dropped from the
    return value -- a caller that ignores it is choosing to, not forced to.

    num_predict defaults higher (4096) than nuextract_extract()'s own default
    (2048) -- the fact envelope is verbose (11 fields per fact), and 2048 was
    live-observed to truncate on a real document (see project memory)."""
    template = build_fact_template(registry)
    result = nuextract_extract(record, endpoint=endpoint, model=model, template=template, timeout=timeout, num_ctx=num_ctx, num_predict=num_predict)
    raw_facts = result["extracted"].get("fatti", [])
    facts, rejected = [], []
    for fact in raw_facts if isinstance(raw_facts, list) else []:
        if not isinstance(fact, dict) or not predicate_is_governed(fact.get("predicato"), registry):
            rejected.append(fact)
            continue
        if not object_matches_range(fact.get("predicato"), fact.get("oggetto"), registry):
            rejected.append(fact)
            continue
        facts.append(fact)
    return {"file_id": record["file_id"], "facts": facts, "rejected_facts": rejected,
            "truncated_source": result.get("truncated_source", False), "_runtime": result.get("_runtime", {})}


def fact_to_raw_claim(fact: dict, file_id: str) -> dict | None:
    """Projects one governed fact into the raw-claim shape resolve_claims()/
    consolidate_claims() already expect (both unchanged). Returns None (not a
    claim) if the fact is missing a mandatory field -- never emits a claim
    without a real subject/predicate/object/evidence quadruple, same discipline
    as gmv_property_claims.signal_to_raw_claims()."""
    soggetto, predicato, oggetto, testo = fact.get("soggetto"), fact.get("predicato"), fact.get("oggetto"), fact.get("testo_evidenza")
    if not soggetto or not predicato or not oggetto or not testo:
        return None
    status = "INFERRED" if fact.get("stato_evidenza") == "inferito" else "SUPPORTED_BY_ARCHIVE"
    qualifiers = {k: fact[k] for k in QUALIFIER_FIELDS if fact.get(k) not in (None, "")}
    return {
        "file_id": file_id,
        "subject_raw": soggetto,
        "predicate": predicato,
        "object_raw": oggetto,
        "evidence_excerpt": testo,
        "status": status,
        "qualifiers": qualifiers,
    }


def facts_to_raw_claims(facts: list[dict], file_id: str) -> list[dict]:
    return [claim for fact in facts if (claim := fact_to_raw_claim(fact, file_id)) is not None]


# --- Batch orchestrator ------------------------------------------------------
# Deliberately mirrors gmv_evidence_pipeline.semantic_extract_batch()'s structure
# (same resume-via-manifest convention, same TIMEOUT/OLLAMA_UNAVAILABLE retry
# policy, same recursive adaptive split on OLLAMA_OUTPUT_TRUNCATED, same
# per-file-output + manifest + run_manifest.json + JSONL runtime log shape) so the
# real-estate extraction pipeline has the same production structure as Area35's
# art pipeline, instead of the ad-hoc, uncommitted disposable script used for the
# 2026-09-29 GERMIGNAGA/VIG35 validation batch. Chunking via
# gmv_evidence_pipeline.deterministic_chunks() (reused unchanged) also fixes, as
# a side effect, the large-document OLLAMA_OUTPUT_TRUNCATED failures found in
# that batch (154K/215K/52K-char documents overran num_predict=4096 as a single
# call; each ~8000-char chunk does not).

PROPERTY_FACTS_OUTPUT_VERSION = "0.1"

# Deterministic two-level gate for generic planning-law/zoning reference documents
# (2026-09-29 finding: VIG35's 06_PROGETTI_EDILIZI/.../02_NORMA/ folder holds
# Milan-wide PGT/Norme Tecniche di Attuazione/Regolamento Edilizio documents that
# are NOT specific to that property -- at full-batch scale these produced ~1/4 of
# all consolidated claims, almost entirely noise, e.g. "Le disposizioni di cui
# agli artt. 5, 6, 8... -> ha_anno_imposta -> tutti gli atti PGT"). User's explicit
# call: don't try to have the local model judge applicability, exclude these from
# local extraction entirely -- "se c'e' un file come questo dovrebbe essere
# necessario usare un cloud llm". This gate identifies them; it does NOT call any
# cloud LLM itself (none is configured in this pipeline) -- flagged documents are
# skipped with an explicit, auditable status, not silently dropped, so a future
# cloud-LLM pass has a real worklist to pick up.
#
# Path-level tokens generalize beyond VIG35's own "02_NORMA" folder convention
# (confirmed absent from the other 5 portfolio properties -- gmv-code-architect
# consultation, 2026-09-29) only insofar as other properties may use similar
# Italian planning-law naming; content-level markers are the real generalization,
# since they look at what the document says, not where it lives. Fail-open by
# design: a document matching neither level is treated as property-specific and
# processed normally -- never excluded without an explicit marker.
GENERIC_REFERENCE_PATH_TOKENS = ("norma", "normativ", "pgt", "piano di governo del territorio",
                                  "piano delle regole", "norme tecniche di attuazione", "regolamento edilizio")
GENERIC_REFERENCE_CONTENT_MARKERS = ("piano di governo del territorio", "piano delle regole",
                                      "norme tecniche di attuazione", "tav. r.")
# Content-marker detection alone (no path hint) false-positived live on two real
# GERMIGNAGA documents (2026-09-29): a file-listing PDF whose text happened to
# include another file's name containing "piano delle regole" (first occurrence
# at char 2250 of 2981), and a building-permit declaration form with a passing
# checkbox mention "PGT (documento di piano - piano delle regole...)" (first
# occurrence at char 5762 of 24531) -- both property-specific documents that
# would have lost real facts if gated. A genuine zoning/planning-law reference
# document names itself as such near the top (confirmed on the real GERMIGNAGA
# PGT/Piano delle Regole/Norme di Attuazione document: first occurrence at char
# 29 of 338807 chars, repeated 117 times) -- a passing mention deep in the body
# does not. Position threshold separates the two classes cleanly on every real
# example found so far.
GENERIC_REFERENCE_CONTENT_MARKER_MAX_POSITION = 500


def is_generic_regulatory_reference(record: dict, paths: list[str] | None = None) -> bool:
    """True if `record` looks like a generic planning-law/zoning reference
    document rather than a property-specific one. `paths` are the file's
    known relative paths (from the scan index) -- optional, since a caller
    may not always have them; content-level detection alone still applies,
    but only trusts a marker found near the top of the text (see comment
    above) -- a path-level match needs no such position check, it's already
    a reliable signal on its own (verified 12/12 correct on the real
    2026-09-29 VIG35 batch)."""
    if paths:
        for path in paths:
            lower_path = path.lower()
            if any(token in lower_path for token in GENERIC_REFERENCE_PATH_TOKENS):
                return True
    text = record.get("text", "").lower()
    return any(0 <= text.find(marker) <= GENERIC_REFERENCE_CONTENT_MARKER_MAX_POSITION
               for marker in GENERIC_REFERENCE_CONTENT_MARKERS)


def property_facts_output_path(fid: str | None, evidence_root: Path) -> Path | None:
    """Mirrors gmv_evidence_pipeline.semantic_output_path's fid-parsing convention."""
    if not fid or ":" not in fid:
        return None
    prefix, sha256 = fid.split(":", 1)
    if prefix != "sha256" or not sha256:
        return None
    return evidence_root / "property_facts" / f"{sha256}-{PROPERTY_FACTS_OUTPUT_VERSION}.json"


def load_property_facts_manifest(evidence_root: Path) -> dict:
    """Mirrors gmv_evidence_pipeline.load_analyze_manifest: missing file or parse
    error -> {} (never raise)."""
    path = evidence_root / "property_facts" / "analyze_manifest.json"
    try:
        return evidence.read_json(path, {})
    except (json.JSONDecodeError, OSError):
        return {}


def mark_property_facts_analyzed(evidence_root: Path, fid: str, status: str, *,
                                  property_id: str, model: str, timeout: int,
                                  updated_at: str | None = None) -> None:
    """Mirrors gmv_evidence_pipeline.mark_analyzed, keyed by property_id instead
    of artist."""
    if status not in {"valid", "failed", "skipped"}:
        raise ValueError(f"invalid status: {status}")
    if updated_at is None:
        updated_at = evidence.now()
    manifest = load_property_facts_manifest(evidence_root)
    manifest[fid] = {"status": status, "property_id": property_id, "model": model,
                      "timeout": timeout, "updated_at": updated_at}
    evidence.write_json(evidence_root / "property_facts" / "analyze_manifest.json", manifest)


def property_facts_batch(records: list[dict], registry: dict, evidence_root: Path, *,
                          property_id: str, endpoint: str, model: str = "numind/nuextract3:q4_k_m",
                          timeout: int = 180, max_chunk_chars: int = 8000, num_ctx: int = 8192,
                          num_predict: int = 4096, min_adaptive_chunk_chars: int = 500,
                          max_adaptive_depth: int = 4, log_path: Path | None = None,
                          resume: bool = False, retry_limit: int = 1) -> dict:
    """Sequential, bounded property-fact extraction with optional resume and
    retry -- see module docstring above for why this mirrors
    semantic_extract_batch() field-for-field rather than being a parallel
    design."""
    all_facts, all_rejected = [], []
    log_path = log_path or (evidence_root / "property_facts" / "runtime.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = load_property_facts_manifest(evidence_root)
    index = evidence.load_index(evidence.paths(evidence_root)[0])
    attempts_manifest: list[dict] = []
    nodes_manifest: list[dict] = []
    skipped = 0
    # Per-record tracking, reset for each record; process_node appends here.
    record_facts: list[dict] = []
    record_rejected: list[dict] = []

    def log_node(event: dict) -> None:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(evidence.canonical(event) + "\n")

    def process_node(node: dict, depth: int = 0) -> None:
        nonlocal record_facts, record_rejected
        node_id = str(node.get("chunk_id", node.get("chunk_index", "0")))
        parent_id = node.get("parent_chunk_id")
        input_chars = len(node.get("text", ""))
        try:
            started = time.monotonic()
            result = extract_facts(node, registry, endpoint=endpoint, model=model, timeout=timeout,
                                    num_ctx=num_ctx, num_predict=num_predict)
            record_facts.extend(result["facts"]); record_rejected.extend(result["rejected_facts"])
            all_facts.extend(result["facts"]); all_rejected.extend(result["rejected_facts"])
            nodes_manifest.append({
                "property_id": property_id, "file_id": node.get("file_id"), "chunk_id": node_id,
                "parent_chunk_id": parent_id, "depth": depth, "input_chars": input_chars,
                "estimated_tokens": (input_chars + 3) // 4, "outcome": "SUCCESS", "failure_class": None,
                "facts": len(result["facts"]), "rejected_facts": len(result["rejected_facts"]),
                "elapsed_seconds": round(time.monotonic() - started, 3), "split_performed": False,
            })
            attempts_manifest.append({"file_id": node.get("file_id"), "chunk": node_id, "attempt": 1, "outcome": "SUCCESS"})
            log_node({"property_id": property_id, "file_id": node.get("file_id"), "chunk_id": node_id,
                      "parent_chunk_id": parent_id, "depth": depth, "input_chars": input_chars,
                      "outcome": "SUCCESS", "facts": len(result["facts"]),
                      "rejected_facts": len(result["rejected_facts"]), "split_performed": False,
                      **result.get("_runtime", {})})
        except evidence.OllamaResponseError as exc:
            runtime = exc.runtime; failure = str(exc)
            nodes_manifest.append({
                "property_id": property_id, "file_id": node.get("file_id"), "chunk_id": node_id,
                "parent_chunk_id": parent_id, "depth": depth, "input_chars": input_chars,
                "estimated_tokens": (input_chars + 3) // 4, "outcome": "FAIL", "failure_class": failure,
                "done_reason": runtime.get("done_reason"), "eval_count": runtime.get("eval_count"),
                "elapsed_seconds": None, "split_performed": False,
            })
            if exc.raw_output:
                evidence.write_json(
                    log_path.parent / f"raw_{node.get('file_id', 'unknown').replace(':', '_')}_chunk{node_id.replace('.', '_')}.json",
                    {"raw_output": exc.raw_output, "raw_output_chars": len(exc.raw_output), **runtime})
            log_node({"property_id": property_id, "file_id": node.get("file_id"), "chunk_id": node_id,
                      "parent_chunk_id": parent_id, "depth": depth, "input_chars": input_chars,
                      "outcome": "FAIL", "failure_class": failure, "split_performed": False, **runtime,
                      "raw_output_chars": len(exc.raw_output)})
            if failure != "OLLAMA_OUTPUT_TRUNCATED":
                raise
            if input_chars <= min_adaptive_chunk_chars:
                raise evidence.EvidenceError("ADAPTIVE_CHUNK_MINIMUM_EXHAUSTED")
            if depth >= max_adaptive_depth:
                raise evidence.EvidenceError("ADAPTIVE_CHUNK_MAX_DEPTH")
            children = evidence.adaptive_split_chunk(node)
            nodes_manifest[-1]["split_performed"] = True
            process_node(children[0], depth + 1); process_node(children[1], depth + 1)
        except evidence.EvidenceError:
            raise

    try:
        for record in records:
            fid = record.get("file_id")
            # Resume: skip files already marked valid OR skipped (gated) in the manifest.
            if resume and fid and manifest.get(fid, {}).get("status") in {"valid", "skipped"}:
                skipped += 1
                continue
            # Generic regulatory/zoning reference gate: never runs NuExtract3 on these at
            # all (see module-level GENERIC_REFERENCE_* comment) -- persisted as an
            # explicit "skipped" status, not silently dropped, so a future cloud-LLM pass
            # has a real worklist.
            if is_generic_regulatory_reference(record, paths=index.get(fid, {}).get("paths")):
                out_path = property_facts_output_path(fid, evidence_root)
                if out_path is not None:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    evidence.write_json(out_path, {"facts": [], "rejected_facts": [],
                                                    "gate_status": "SKIPPED_GENERIC_REFERENCE"})
                    mark_property_facts_analyzed(evidence_root, fid, "skipped", property_id=property_id,
                                                  model=model, timeout=timeout)
                log_node({"property_id": property_id, "file_id": fid, "chunk_id": "0", "parent_chunk_id": None,
                          "depth": 0, "input_chars": len(record.get("text", "")), "outcome": "SKIPPED_GENERIC_REFERENCE",
                          "facts": 0, "rejected_facts": 0, "split_performed": False})
                continue
            record_facts = []
            record_rejected = []
            last_error = None
            for attempt in range(max(retry_limit, 1)):
                record_facts = []
                record_rejected = []
                try:
                    for index, chunk in enumerate(evidence.deterministic_chunks(record, max_chunk_chars)):
                        chunk["chunk_id"] = str(record.get("chunk_id", index)); chunk["original_chunk_id"] = str(record.get("original_chunk_id", index))
                        process_node(chunk)
                    # Record succeeded -- persist per-file output, then mark valid.
                    out_path = property_facts_output_path(fid, evidence_root)
                    if out_path is not None:
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        evidence.write_json(out_path, {"facts": record_facts, "rejected_facts": record_rejected})
                        mark_property_facts_analyzed(evidence_root, fid, "valid", property_id=property_id, model=model, timeout=timeout)
                    break
                except evidence.EvidenceError as exc:
                    last_error = exc
                    if exc.code in {"TIMEOUT", "OLLAMA_UNAVAILABLE"} and attempt < retry_limit - 1:
                        continue
                    # Non-retryable or retries exhausted -- mark failed, then re-raise.
                    out_path = property_facts_output_path(fid, evidence_root)
                    if fid and out_path is not None:
                        mark_property_facts_analyzed(evidence_root, fid, "failed", property_id=property_id, model=model, timeout=timeout)
                    raise
            else:
                # Defensive: all retries exhausted without a final raise.
                out_path = property_facts_output_path(fid, evidence_root)
                if fid and out_path is not None:
                    mark_property_facts_analyzed(evidence_root, fid, "failed", property_id=property_id, model=model, timeout=timeout)
                raise last_error
    except evidence.EvidenceError as exc:
        evidence.write_json(evidence_root / "property_facts" / "run_manifest.json", {
            "property_id": property_id, "model": model, "num_ctx": num_ctx, "num_predict": num_predict,
            "timeout": timeout, "max_chunk_chars": max_chunk_chars,
            "min_adaptive_chunk_chars": min_adaptive_chunk_chars, "max_adaptive_depth": max_adaptive_depth,
            "status": "BLOCKED", "failure_class": str(exc),
            "attempts": attempts_manifest, "nodes": nodes_manifest})
        raise
    evidence.write_json(evidence_root / "property_facts" / "run_manifest.json", {
        "property_id": property_id, "model": model, "num_ctx": num_ctx, "num_predict": num_predict,
        "timeout": timeout, "max_chunk_chars": max_chunk_chars,
        "min_adaptive_chunk_chars": min_adaptive_chunk_chars, "max_adaptive_depth": max_adaptive_depth,
        "status": "SUCCESS", "attempts": attempts_manifest, "nodes": nodes_manifest})
    return {"facts": all_facts, "rejected_facts": all_rejected}


def run_property_pipeline(property_id: str, dropbox_root: Path, evidence_root: Path, registry: dict, *,
                          endpoint: str, model: str = "numind/nuextract3:q4_k_m", **kwargs) -> dict:
    """End-to-end chain: scan -> extract -> per-document fact extraction ->
    resolve -> consolidate. Every stage is an existing function, reused as-is:
    scan/extract/resolve_claims/consolidate_claims come from
    gmv_evidence_pipeline, property_facts_batch/facts_to_raw_claims from this
    module. Nothing here re-implements any of them.

    property_facts_batch() is called ONCE PER DOCUMENT rather than once for the
    whole property: it raises EvidenceError and aborts the entire call on the
    first unrecoverable document failure (deliberate, mirroring
    semantic_extract_batch()), which would otherwise throw away every other
    document of the same property. Per-document isolation is the whole point of
    chaining them in a loop here.

    resolve_claims() is called with an empty notion_rows dict on purpose: the
    live Notion real-estate databases are populated by an independent ChatGPT
    pipeline with its own confidence-tier reconciliation contract, and no
    reconciliation contract has been decided here. An empty dict means no
    subject/object can ever match, so every one of them deterministically
    becomes NEW_ENTITY with a synthetic hash id -- no live comparison is
    performed, and none of these ids correspond to a real Notion page.
    """
    evidence.scan(dropbox_root, evidence_root)
    records = [r for r in evidence.extract(evidence_root, dropbox_root)
               if r.get("extraction_status") == "SUCCESS"]
    raw_claims: list[dict] = []
    per_file: list[dict] = []
    for record in records:
        fid = record["file_id"]
        try:
            property_facts_batch([record], registry, evidence_root, property_id=property_id,
                                 endpoint=endpoint, model=model, **kwargs)
        except evidence.EvidenceError as exc:
            per_file.append({"file_id": fid, "error": str(exc)})
            continue
        out_path = property_facts_output_path(fid, evidence_root)
        data = evidence.read_json(out_path, {}) if out_path is not None else {}
        facts, rejected = data.get("facts", []), data.get("rejected_facts", [])
        raw_claims.extend(facts_to_raw_claims(facts, fid))
        per_file.append({"file_id": fid, "facts": len(facts), "rejected": len(rejected)})
    resolved = evidence.resolve_claims(raw_claims, {})
    consolidated = evidence.consolidate_claims(resolved)
    return {"property_id": property_id, "documents_processed": len(per_file),
            "raw_claims": len(raw_claims), "consolidated_claims": len(consolidated),
            "per_file": per_file, "consolidated": consolidated}


DEFAULT_EVIDENCE_ROOT = Path.home() / ".gmv_core" / "area35-qa" / "evidence" / "immobili"

# argparse gives a subparser's --evidence-root the same dest as the top-level
# one, so passing it after the subcommand would silently overwrite the
# top-level value with None (verified, not assumed). Distinct dests keep both
# positions usable; _add_shared_args resolves them, subcommand-level winning.
def _add_shared_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--endpoint", default="http://localhost:11434")
    parser.add_argument("--model", default="numind/nuextract3:q4_k_m")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-chunk-chars", type=int, default=8000)
    parser.add_argument("--ollama-context", type=int, default=8192)
    parser.add_argument("--num-predict", type=int, default=4096)
    parser.add_argument("--min-adaptive-chunk-chars", type=int, default=500)
    parser.add_argument("--max-adaptive-depth", type=int, default=4)
    parser.add_argument("--retry-limit", type=int, default=1,
                        help="Max attempts per file for transient TIMEOUT/OLLAMA_UNAVAILABLE errors")
    parser.add_argument("--resume", action="store_true", default=False,
                        help="Skip files already marked valid/skipped in property_facts/analyze_manifest.json")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence-root", type=Path, dest="legacy_evidence_root", help=argparse.SUPPRESS)
    p.add_argument("--registry", type=Path, dest="legacy_registry", help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="command", required=True)
    analyze_p = sub.add_parser("analyze")
    analyze_p.add_argument("record", type=Path)
    analyze_p.add_argument("--property-id", required=True)
    analyze_p.add_argument("--evidence-root", type=Path, dest="evidence_root")
    analyze_p.add_argument("--registry", type=Path)
    _add_shared_args(analyze_p)
    property_p = sub.add_parser("analyze-property")
    property_p.add_argument("property_id")
    property_p.add_argument("--dropbox-root", type=Path, required=True)
    property_p.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    property_p.add_argument("--registry", type=Path, required=True)
    _add_shared_args(property_p)
    args = p.parse_args()
    evidence_root = getattr(args, "evidence_root", None) or args.legacy_evidence_root
    registry_path = getattr(args, "registry", None) or args.legacy_registry
    if evidence_root is None or registry_path is None:
        p.error("--evidence-root and --registry are required")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    shared = {"endpoint": args.endpoint, "model": args.model, "timeout": args.timeout,
              "max_chunk_chars": args.max_chunk_chars, "num_ctx": args.ollama_context,
              "num_predict": args.num_predict,
              "min_adaptive_chunk_chars": args.min_adaptive_chunk_chars,
              "max_adaptive_depth": args.max_adaptive_depth,
              "resume": args.resume, "retry_limit": args.retry_limit}
    try:
        if args.command == "analyze":
            output = property_facts_batch(
                [evidence.read_json(args.record, {})], registry, evidence_root,
                property_id=args.property_id, **shared)
        else:
            output = run_property_pipeline(
                args.property_id, args.dropbox_root, evidence_root, registry, **shared)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except evidence.EvidenceError as exc:
        print(f"property-facts: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
