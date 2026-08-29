#!/usr/bin/env python3
"""Local, fail-closed Dropbox-to-Notion evidence pipeline (dry-run only).

The module deliberately has no Dropbox or Notion write code.  Its persistent
index and caches are content-addressed; run artefacts only reference them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUPPORTED = {".md", ".txt", ".pdf", ".docx", ".doc", ".html", ".csv", ".json"}
TERMINAL_EXTRACTION = {"SUCCESS", "OCR_REQUIRED", "UNSUPPORTED_FORMAT", "FILE_TOO_LARGE", "EXTRACTION_ABORTED_STALE_HASH", "EXTRACTION_FAILED"}


class EvidenceError(RuntimeError):
    def __init__(self, code: str, *, detail: str = ""):
        super().__init__(code); self.detail = detail


SEMANTIC_OUTPUT_SCHEMA = {
    "type": "object", "required": ["entities", "claims"],
    "properties": {
        "entities": {"type": "array", "items": {"type": "object", "required": ["name", "evidence_excerpt"],
            "properties": {"name": {"type": "string"}, "evidence_excerpt": {"type": "string"}, "status": {"type": "string"}}}},
        "claims": {"type": "array", "items": {"type": "object", "required": ["subject_raw", "predicate", "object_raw", "evidence_excerpt"],
            "properties": {"subject_raw": {"type": "string"}, "predicate": {"type": "string"}, "object_raw": {"type": "string"},
                          "evidence_excerpt": {"type": "string"}, "status": {"type": "string"}}}}
    }
}


class OllamaResponseError(EvidenceError):
    def __init__(self, code: str, *, runtime: dict | None = None, raw_output: str = ""):
        super().__init__(code); self.runtime = runtime or {}; self.raw_output = raw_output


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def norm(value: str) -> str:
    value = "".join(c for c in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


def paths(root: Path) -> tuple[Path, Path]:
    root = root.expanduser().resolve()
    return root / "index" / "FILE_INDEX.jsonl", root / "cache"


def load_index(index_path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    if index_path.exists():
        for line in index_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows[row["file_id"]] = row
    return rows


def save_index(index_path: Path, rows: dict[str, dict]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(canonical(rows[k]) + "\n" for k in sorted(rows))
    temp = index_path.with_suffix(".jsonl.tmp")
    temp.write_text(body, encoding="utf-8")
    os.replace(temp, index_path)


def scan(dropbox_root: Path, evidence_root: Path) -> list[dict]:
    """Update the global content index without following symlinks."""
    dropbox_root = dropbox_root.expanduser().resolve()
    if not dropbox_root.is_dir(): raise EvidenceError(f"Not a directory: {dropbox_root}")
    index_path, _ = paths(evidence_root)
    old = load_index(index_path)
    discovered: dict[str, set[str]] = {}
    metadata: dict[str, tuple[Path, os.stat_result]] = {}
    for path in sorted(dropbox_root.rglob("*")):
        if path.is_symlink() or not path.is_file(): continue
        try:
            rel = path.relative_to(dropbox_root).as_posix()
            digest = sha256_file(path)
            fid = f"sha256:{digest}"
            discovered.setdefault(fid, set()).add(rel)
            metadata[fid] = (path, path.stat())
        except (OSError, PermissionError):
            continue
    for fid, file_paths in discovered.items():
        path, stat = metadata[fid]
        old[fid] = {"file_id": fid, "sha256": fid.split(":", 1)[1], "paths": sorted(file_paths),
                    "filename": path.name, "extension": path.suffix.lower(), "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
                    "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream", "scan_status": "INDEXED"}
    # Paths absent from the current scope are removed, but identity is retained only if another path remains.
    current_paths = {p for v in discovered.values() for p in v}
    for fid, row in list(old.items()):
        row["paths"] = [p for p in row["paths"] if p in current_paths]
        if not row["paths"]: del old[fid]
    save_index(index_path, old)
    return [old[k] for k in sorted(discovered)]


def _extract(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower()
    if ext in {".txt", ".md", ".html", ".csv", ".json"}:
        return path.read_text(encoding="utf-8", errors="strict"), "text"
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages).strip()
            if not text: raise EvidenceError("OCR_REQUIRED")
            return text, "pdf_text"
        except ImportError as exc: raise EvidenceError("EXTRACTION_FAILED") from exc
    if ext == ".docx":
        try:
            from docx import Document
            return "\n".join(p.text for p in Document(str(path)).paragraphs), "docx_text"
        except ImportError as exc: raise EvidenceError("EXTRACTION_FAILED") from exc
    if ext == ".doc":
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if not soffice: raise EvidenceError("EXTRACTION_FAILED", detail="soffice/libreoffice binary not found on PATH")
        with tempfile.TemporaryDirectory() as tmp:
            try:
                subprocess.run([soffice, "--headless", "--convert-to", "txt:Text", "--outdir", tmp, str(path)],
                               capture_output=True, timeout=60, check=True)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace")
                raise EvidenceError("EXTRACTION_FAILED", detail=stderr[:2000] or type(exc).__name__) from exc
            out_path = Path(tmp) / f"{path.stem}.txt"
            if not out_path.is_file(): raise EvidenceError("EXTRACTION_FAILED", detail="soffice did not produce the expected .txt output")
            # utf-8-sig strips the UTF-8 BOM that "txt:Text" always prepends; without it an
            # empty/non-textual .doc silently passes the `if not text` OCR_REQUIRED gate below.
            text = out_path.read_text(encoding="utf-8-sig", errors="strict").strip()
            if not text: raise EvidenceError("OCR_REQUIRED")
            return text, "doc_text_libreoffice"
    raise EvidenceError("UNSUPPORTED_FORMAT")


def extract(evidence_root: Path, dropbox_root: Path, *, max_file_bytes: int = 50_000_000, extractor_version: str = "0.2") -> list[dict]:
    index_path, cache = paths(evidence_root); index = load_index(index_path); out = []
    root = dropbox_root.expanduser().resolve()
    for fid, row in index.items():
        if not row["paths"]: continue
        path = root / row["paths"][0]
        record_path = cache / "extracted" / f"{row['sha256']}-{extractor_version}.json"
        if record_path.exists(): out.append(read_json(record_path, {})); continue
        if not path.is_file() or sha256_file(path) != row["sha256"]:
            record = {"file_id": fid, "extraction_status": "EXTRACTION_ABORTED_STALE_HASH"}
        elif row["size_bytes"] > max_file_bytes:
            record = {"file_id": fid, "extraction_status": "FILE_TOO_LARGE"}
        else:
            try:
                text, extractor = _extract(path)
                record = {"file_id": fid, "extraction_status": "SUCCESS", "extractor": extractor,
                          "extractor_version": extractor_version, "text_hash": hashlib.sha256(text.encode()).hexdigest(),
                          "text": text, "metadata": {}}
            except EvidenceError as exc:
                record = {"file_id": fid, "extraction_status": str(exc)}
                if exc.detail: record["error_detail"] = exc.detail
            except (OSError, UnicodeError) as exc:
                record = {"file_id": fid, "extraction_status": "EXTRACTION_FAILED", "error": type(exc).__name__}
        write_json(record_path, record); out.append(record)
    return out


def ollama_extract(record: dict, *, endpoint: str, model: str, max_prompt_chars: int = 24000,
                   timeout: int = 60, num_ctx: int = 8192, num_predict: int = 2048,
                   think: bool = False) -> dict:
    if record.get("extraction_status") != "SUCCESS": raise EvidenceError("Extraction is not successful")
    text = record["text"]; truncated = len(text) > max_prompt_chars
    if truncated: text = text[:max_prompt_chars // 2] + "\n[...TRUNCATED...]\n" + text[-max_prompt_chars // 2:]
    prompt = ("Extract entities and factual claims from this archive text. Return ONLY JSON with entities and claims. "
              "entities MUST be an array; every entity must contain name,evidence_excerpt,status. "
              "Every claim must contain subject_raw,predicate,object_raw,evidence_excerpt,status. Do not infer.\nTEXT:\n" + text)
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": SEMANTIC_OUTPUT_SCHEMA,
                          "think": think, "options": {"num_ctx": num_ctx, "num_predict": num_predict}}).encode()
    request = urllib.request.Request(endpoint.rstrip("/") + "/api/generate", data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            envelope = json.load(response)
            raw_output = envelope.get("response", "")
            runtime = {k: envelope.get(k) for k in ("done_reason", "eval_count", "prompt_eval_count", "prompt_eval_duration", "eval_duration")}
            if envelope.get("done_reason") in {"length", "max_tokens"}:
                raise OllamaResponseError("OLLAMA_OUTPUT_TRUNCATED", runtime=runtime, raw_output=raw_output)
            try:
                parsed = json.loads(raw_output)
            except json.JSONDecodeError as exc:
                raise OllamaResponseError("OLLAMA_INVALID_JSON", runtime=runtime, raw_output=raw_output) from exc
    except urllib.error.URLError as exc: raise EvidenceError("OLLAMA_UNAVAILABLE") from exc
    except TimeoutError as exc: raise EvidenceError("TIMEOUT") from exc
    except KeyError as exc: raise OllamaResponseError("OLLAMA_INVALID_JSON") from exc
    claims = parsed.get("claims"); entities = parsed.get("entities")
    # Ollama models occasionally emit an object keyed by entity name although
    # the contract is an array. Normalize that representation without inventing
    # any evidence fields.
    if isinstance(entities, dict):
        entities = [{"name": name, **(value if isinstance(value, dict) else {})} for name, value in entities.items()]
    if not isinstance(claims, list) or not isinstance(entities, list): raise OllamaResponseError("OLLAMA_SCHEMA_INVALID", runtime=runtime, raw_output=raw_output)
    for entity in entities:
        if not entity.get("name") or not entity.get("evidence_excerpt"):
            raise OllamaResponseError("OLLAMA_SCHEMA_INVALID", runtime=runtime, raw_output=raw_output)
        entity.update({"file_id": record["file_id"], "status": str(entity.get("status", "SUPPORTED_BY_ARCHIVE")).upper()})
    for i, claim in enumerate(claims):
        if not all(claim.get(k) for k in ("subject_raw", "predicate", "object_raw", "evidence_excerpt")):
            raise OllamaResponseError("OLLAMA_SCHEMA_INVALID", runtime=runtime, raw_output=raw_output)
        claim.update({"file_id": record["file_id"], "extraction_claim_ref": f"{record['file_id']}#{i}", "truncated_source": truncated, "status": str(claim.get("status", "SUPPORTED_BY_ARCHIVE")).upper()})
    return {"file_id": record["file_id"], "entities": entities, "claims": claims,
            "_runtime": {k: envelope.get(k) for k in ("eval_count", "prompt_eval_count",
                         "prompt_eval_duration", "eval_duration")}}


def cached_ollama_extract(record: dict, evidence_root: Path, *, endpoint: str, model: str,
                          max_prompt_chars: int = 24000, timeout: int = 60, prompt_version: str = "0.1") -> dict:
    """Global semantic cache keyed by content identity, prompt version and model."""
    _, cache = paths(evidence_root)
    identity = hashlib.sha256(f"{record['file_id']}|{prompt_version}|{model}".encode()).hexdigest()
    cache_path = cache / "semantic" / f"{identity}.json"
    if cache_path.exists(): return read_json(cache_path, {})
    result = ollama_extract(record, endpoint=endpoint, model=model, max_prompt_chars=max_prompt_chars, timeout=timeout)
    result["semantic_prompt_version"] = prompt_version
    result["model"] = model
    write_json(cache_path, result)
    return result


def ollama_health(endpoint: str, timeout: int = 5) -> bool:
    try:
        request = urllib.request.Request(endpoint.rstrip("/") + "/api/tags")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def ollama_warmup(endpoint: str, model: str, *, num_ctx: int = 8192,
                  num_predict: int = 2048, timeout: int = 30, think: bool = False) -> dict:
    """Load the model once; this request is never counted as a semantic attempt."""
    request = urllib.request.Request(endpoint.rstrip("/") + "/api/generate",
        data=json.dumps({"model": model, "prompt": "Return {}", "stream": False,
                         "format": "json", "think": think,
                         "options": {"num_ctx": num_ctx, "num_predict": num_predict}}).encode(),
        headers={"Content-Type": "application/json"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
        return {"outcome": "SUCCESS", "elapsed_seconds": round(time.monotonic() - started, 3),
                "eval_count": payload.get("eval_count"), "prompt_eval_duration": payload.get("prompt_eval_duration"),
                "eval_duration": payload.get("eval_duration")}
    except TimeoutError as exc:
        raise EvidenceError("TIMEOUT") from exc
    except urllib.error.URLError as exc:
        raise EvidenceError("OLLAMA_UNAVAILABLE") from exc


def deterministic_chunks(record: dict, max_chars: int = 8000) -> list[dict]:
    """Split losslessly, preferring paragraph then sentence boundaries."""
    text = record.get("text", "")
    if len(text) <= max_chars: return [record]
    boundaries = {m.end() for m in re.finditer(r"\n\n+", text)}
    boundaries.update(m.end() for m in re.finditer(r"[.!?。！？](?:[\"'»”)]*)\s+", text))
    boundaries.add(len(text))
    chunks, start = [], 0
    while start < len(text):
        limit = min(start + max_chars, len(text))
        valid = [b for b in boundaries if start < b <= limit]
        end = max(valid) if valid else limit
        chunks.append(text[start:end]); start = end
    out = []
    for i, chunk in enumerate(chunks):
        item = dict(record); item["text"] = chunk; item["chunk_index"] = i; item["chunk_count"] = len(chunks); out.append(item)
    return out


def adaptive_split_chunk(chunk: dict) -> tuple[dict, dict]:
    """Split one chunk at the nearest safe boundary to its midpoint."""
    text = chunk.get("text", ""); midpoint = len(text) // 2
    boundaries = {m.end() for m in re.finditer(r"\n\n+", text)}
    boundaries.update(m.end() for m in re.finditer(r"[.!?。！？](?:[\"'»”)]*)\s+", text))
    valid = [b for b in boundaries if 0 < b < len(text)]
    split_at = min(valid, key=lambda b: abs(b - midpoint)) if valid else midpoint
    if split_at <= 0 or split_at >= len(text): raise EvidenceError("ADAPTIVE_SPLIT_FAILED")
    parent = str(chunk.get("chunk_id", chunk.get("chunk_index", "0")))
    base = dict(chunk); base.pop("chunk_count", None)
    left, right = dict(base), dict(base)
    left.update(text=text[:split_at], chunk_id=f"{parent}.0", parent_chunk_id=parent)
    right.update(text=text[split_at:], chunk_id=f"{parent}.1", parent_chunk_id=parent)
    return left, right


def semantic_extract_batch(records: list[dict], evidence_root: Path, *, artist: str, endpoint: str,
                           model: str, timeout: int = 180, max_chunk_chars: int = 8000,
                           context: int = 8192, num_predict: int = 2048,
                           think: bool = False, min_adaptive_chunk_chars: int = 500,
                           max_adaptive_depth: int = 4, log_path: Path | None = None) -> dict:
    """Sequential, bounded semantic extraction with one health-checked retry."""
    all_entities, all_claims = [], []
    log_path = log_path or (evidence_root / "semantic" / "runtime.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    attempts_manifest = []; nodes_manifest = []
    def log_node(event: dict) -> None:
        with log_path.open("a", encoding="utf-8") as handle: handle.write(canonical(event) + "\n")
    def process_node(node: dict, depth: int = 0) -> None:
        node_id = str(node.get("chunk_id", node.get("chunk_index", "0")))
        parent_id = node.get("parent_chunk_id")
        input_chars = len(node.get("text", ""))
        try:
            started = time.monotonic(); result = ollama_extract(node, endpoint=endpoint, model=model,
                max_prompt_chars=max_chunk_chars, timeout=timeout, num_ctx=context,
                num_predict=num_predict, think=think)
            for i, claim in enumerate(result.get("claims", [])):
                claim["extraction_claim_ref"] = f"{node['file_id']}#{node_id}:{i}"
                claim["leaf_chunk_id"] = node_id; claim["original_chunk_id"] = str(node.get("original_chunk_id", node_id))
            all_entities.extend(result.get("entities", [])); all_claims.extend(result.get("claims", []))
            nodes_manifest.append({"artist": artist, "file_id": node.get("file_id"), "chunk_id": node_id, "parent_chunk_id": parent_id,
                "depth": depth, "input_chars": input_chars, "estimated_tokens": (input_chars + 3)//4,
                "outcome": "SUCCESS", "failure_class": None, "done_reason": result.get("_runtime", {}).get("done_reason"),
                "eval_count": result.get("_runtime", {}).get("eval_count"), "elapsed_seconds": round(time.monotonic()-started,3), "split_performed": False})
            attempts_manifest.append({"file_id": node.get("file_id"), "chunk": node_id, "attempt": 1, "outcome": "SUCCESS"})
            log_node({"artist": artist, "file_id": node.get("file_id"), "chunk_id": node_id, "parent_chunk_id": parent_id,
                "depth": depth, "input_chars": input_chars, "estimated_tokens": (input_chars + 3)//4,
                "outcome": "SUCCESS", "failure_class": None, "split_performed": False,
                **result.get("_runtime", {})})
        except OllamaResponseError as exc:
            runtime = exc.runtime; failure = str(exc)
            nodes_manifest.append({"artist": artist, "file_id": node.get("file_id"), "chunk_id": node_id, "parent_chunk_id": parent_id,
                "depth": depth, "input_chars": input_chars, "estimated_tokens": (input_chars + 3)//4,
                "outcome": "FAIL", "failure_class": failure, "done_reason": runtime.get("done_reason"),
                "eval_count": runtime.get("eval_count"), "elapsed_seconds": None, "split_performed": False})
            if exc.raw_output:
                write_json(log_path.parent / f"raw_{node.get('file_id','unknown').replace(':','_')}_chunk{node_id.replace('.','_')}.json",
                           {"raw_output": exc.raw_output, "raw_output_chars": len(exc.raw_output), **runtime})
            log_node({"artist": artist, "file_id": node.get("file_id"), "chunk_id": node_id, "parent_chunk_id": parent_id,
                "depth": depth, "input_chars": input_chars, "estimated_tokens": (input_chars + 3)//4,
                "outcome": "FAIL", "failure_class": failure, "split_performed": False, **runtime,
                "raw_output_chars": len(exc.raw_output)})
            if failure != "OLLAMA_OUTPUT_TRUNCATED": raise
            if input_chars <= min_adaptive_chunk_chars: raise EvidenceError("ADAPTIVE_CHUNK_MINIMUM_EXHAUSTED")
            if depth >= max_adaptive_depth: raise EvidenceError("ADAPTIVE_CHUNK_MAX_DEPTH")
            children = adaptive_split_chunk(node)
            nodes_manifest[-1]["split_performed"] = True
            process_node(children[0], depth + 1); process_node(children[1], depth + 1)
        except EvidenceError:
            raise
    try:
        for record in records:
            for index, chunk in enumerate(deterministic_chunks(record, max_chunk_chars)):
                chunk["chunk_id"] = str(record.get("chunk_id", index)); chunk["original_chunk_id"] = str(record.get("original_chunk_id", index))
                process_node(chunk)
    except EvidenceError as exc:
        write_json(evidence_root / "semantic" / "run_manifest.json", {"artist": artist, "model": model, "context": context,
            "num_ctx": context, "num_predict": num_predict, "thinking": think, "timeout": timeout,
            "max_chunk_chars": max_chunk_chars, "min_adaptive_chunk_chars": min_adaptive_chunk_chars,
            "max_adaptive_depth": max_adaptive_depth, "status": "BLOCKED", "failure_class": str(exc),
            "attempts": attempts_manifest, "nodes": nodes_manifest})
        raise
    write_json(evidence_root / "semantic" / "run_manifest.json", {"artist": artist, "model": model, "context": context,
        "num_ctx": context, "num_predict": num_predict, "thinking": think,
        "timeout": timeout, "max_chunk_chars": max_chunk_chars, "min_adaptive_chunk_chars": min_adaptive_chunk_chars,
        "max_adaptive_depth": max_adaptive_depth, "status": "SUCCESS", "attempts": attempts_manifest, "nodes": nodes_manifest})
    return {"entities": all_entities, "claims": all_claims}


def required_fields(config: dict, entity_type: str) -> set[str]:
    spec = config["entita"][entity_type.lower()]
    return {k for k, v in {**spec.get("campi", {}), **spec.get("relazioni", {})}.items() if v.get("obbligatorio")}


def resolve_claims(raw_claims: list[dict], notion_rows: dict[str, list[dict]], aliases: dict[str, str] | None = None) -> list[dict]:
    """Deterministic exact/alias resolution; ambiguous values remain pending."""
    aliases = aliases or {}; candidates: dict[str, list[str]] = {}
    for typ, rows in notion_rows.items():
        for row in rows:
            name = norm(row.get("titolo", "")); candidates.setdefault(name, []).append(row["id"])
    result = []
    for claim in raw_claims:
        item = dict(claim); states = []
        for field in ("subject", "object"):
            raw = str(item.get(f"{field}_raw", "")); key = aliases.get(norm(raw), norm(raw)); found = candidates.get(key, [])
            if len(found) == 1: item[f"resolved_{field}_id"] = found[0]; states.append("MATCH")
            elif not found and key: item[f"resolved_{field}_id"] = "new:" + hashlib.sha256(key.encode()).hexdigest()[:16]; states.append("NEW_ENTITY")
            else: states.append("AMBIGUOUS")
        item["resolution_status"] = "PENDING_RESOLUTION" if "AMBIGUOUS" in states else "RESOLVED"
        result.append(item)
    return result


def consolidate_claims(claims: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for c in claims:
        if c.get("resolution_status") != "RESOLVED": continue
        key = [c["resolved_subject_id"], norm(c["predicate"]), c["resolved_object_id"], c.get("qualifiers", {})]
        cid = "claim:" + hashlib.sha256(canonical(key).encode()).hexdigest()
        target = grouped.setdefault(cid, {"claim_id": cid, "subject": c["subject_raw"], "predicate": c["predicate"], "object": c["object_raw"], "qualifiers": c.get("qualifiers", {}), "source_file_ids": [], "source_excerpts": [], "status": c.get("status", "SUPPORTED_BY_ARCHIVE")})
        if c["file_id"] not in target["source_file_ids"]: target["source_file_ids"].append(c["file_id"])
        if c["evidence_excerpt"] not in target["source_excerpts"]: target["source_excerpts"].append(c["evidence_excerpt"])
    return list(grouped.values())


def gate(notion_status: str, claims: list[dict], mandatory: set[str]) -> str:
    if notion_status == "AMBIGUOUS": return "REVIEW_REQUIRED"
    by_predicate = {norm(c["predicate"]): c for c in claims}
    if any(norm(field) not in by_predicate or by_predicate[norm(field)].get("status") in {"INFERRED", "MISSING", "CONFLICTING"} for field in mandatory):
        return "INSUFFICIENT_EVIDENCE" if notion_status == "NEW_ENTITY" else "REVIEW_REQUIRED"
    return "REVIEW_REQUIRED" if notion_status == "EXISTS_CONFLICTING" else "READY_FOR_NOTION"


def compare_entity(name: str, entity_type: str, notion_rows: dict[str, list[dict]]) -> tuple[str, dict | None]:
    """Read-only deterministic comparison against normalized Notion rows."""
    matches = [r for r in notion_rows.get(entity_type.lower(), []) if norm(r.get("titolo", "")) == norm(name)]
    if len(matches) > 1: return "AMBIGUOUS", None
    if not matches: return "NEW_ENTITY", None
    return "EXISTS_AND_MATCHES", matches[0]


def notion_payload(entity_type: str, name: str, claims: list[dict], notion_status: str, required: set[str]) -> dict:
    final_gate = gate(notion_status, claims, required)
    if any(not c.get("source_file_ids") for c in claims): raise EvidenceError("CLAIM_WITHOUT_EVIDENCE")
    return {"entity_type": entity_type.upper(), "operation": "CREATE" if notion_status == "NEW_ENTITY" else "UPDATE",
            "existing_notion_id": None, "properties": {"name": name}, "relations": [],
            "provenance": [{"claim_id": c["claim_id"], "source_file_id": fid, "source_path": None}
                           for c in claims for fid in c["source_file_ids"]], "gate": final_gate,
            "dry_run": True}


def write_evidence_bundle(run_dir: Path, entity_name: str, entity_type: str, claims: list[dict], notion_status: str,
                          required: set[str], source_paths: dict[str, list[str]] | None = None) -> Path:
    """Write a local, inspectable dry-run bundle; it never calls Notion."""
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", entity_name).strip("_") or "unnamed"
    bundle = run_dir / "entities" / safe_name
    sources = [{"file_id": fid, "paths": (source_paths or {}).get(fid, [])}
               for claim in claims for fid in claim.get("source_file_ids", [])]
    unique_sources = {item["file_id"]: item for item in sources}
    payload = notion_payload(entity_type, entity_name, claims, notion_status, required)
    write_json(bundle / "entity.json", {"entity_type": entity_type.upper(), "name": entity_name})
    write_json(bundle / "claims.json", claims)
    write_json(bundle / "sources.json", list(unique_sources.values()))
    write_json(bundle / "notion_match.json", {"status": notion_status})
    write_json(bundle / "verification.json", {"status": "NOT_EXECUTED", "reason": "local verifier adapter pending"})
    write_json(bundle / "NOTION_PAYLOAD.json", payload)
    lines = [f"# Evidence — {entity_name}", "", f"Gate: `{payload['gate']}`", "", "## Claims", ""]
    lines.extend(f"- `{claim['claim_id']}` — {claim['predicate']} — sources: {', '.join(claim['source_file_ids'])}" for claim in claims)
    (bundle / "EVIDENCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return bundle


def main() -> int:
    p = argparse.ArgumentParser(description="GMV local evidence pipeline (no Dropbox/Notion writes)")
    p.add_argument("--evidence-root", type=Path, default=Path.home()/".gmv_core"/"area35-qa"/"evidence")
    sub = p.add_subparsers(dest="command", required=True)
    scan_p = sub.add_parser("scan"); scan_p.add_argument("root", type=Path)
    ext_p = sub.add_parser("extract"); ext_p.add_argument("root", type=Path); ext_p.add_argument("--max-file-bytes", type=int, default=50_000_000)
    analyze_p = sub.add_parser("analyze"); analyze_p.add_argument("record", type=Path); analyze_p.add_argument("--endpoint", default="http://localhost:11434"); analyze_p.add_argument("--model", required=True); analyze_p.add_argument("--artist", default="unknown"); analyze_p.add_argument("--timeout", type=int, default=180); analyze_p.add_argument("--max-chunk-chars", type=int, default=8000); analyze_p.add_argument("--ollama-context", type=int, default=8192); analyze_p.add_argument("--num-predict", type=int, default=2048); analyze_p.add_argument("--min-adaptive-chunk-chars", type=int, default=500); analyze_p.add_argument("--max-adaptive-depth", type=int, default=4)
    resolve_p = sub.add_parser("resolve"); resolve_p.add_argument("claims", type=Path); resolve_p.add_argument("--rows", type=Path, required=True); resolve_p.add_argument("--aliases", type=Path)
    args = p.parse_args()
    try:
        if args.command == "scan": output = scan(args.root, args.evidence_root)
        elif args.command == "extract": output = extract(args.evidence_root, args.root, max_file_bytes=args.max_file_bytes)
        elif args.command == "analyze": output = semantic_extract_batch([read_json(args.record, {})], args.evidence_root, artist=args.artist, endpoint=args.endpoint, model=args.model, max_chunk_chars=args.max_chunk_chars, timeout=args.timeout, context=args.ollama_context, num_predict=args.num_predict, min_adaptive_chunk_chars=args.min_adaptive_chunk_chars, max_adaptive_depth=args.max_adaptive_depth)
        else:
            claim_document = read_json(args.claims, {})
            raw = claim_document.get("claims", []) if isinstance(claim_document, dict) else claim_document
            output = {"resolved": resolve_claims(raw, read_json(args.rows, {}), read_json(args.aliases, {}) if args.aliases else {}), "claims": []}
            output["claims"] = consolidate_claims(output["resolved"])
        print(json.dumps(output, ensure_ascii=False, indent=2)); return 0
    except EvidenceError as exc:
        print(f"evidence: {exc}", file=sys.stderr); return 2

if __name__ == "__main__": raise SystemExit(main())
