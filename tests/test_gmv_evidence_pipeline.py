import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("evidence", Path(__file__).parents[1] / "10_API" / "gmv_evidence_pipeline.py")
evidence = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(evidence)
sys.path.insert(0, str(Path(__file__).parents[1] / "10_API"))
import gmv_notion_candidate as candidate

FIXTURES = Path(__file__).parent / "fixtures"

def test_index_move_and_extract_hash_guard(tmp_path):
    source = tmp_path / "dropbox"; source.mkdir(); (source / "a.txt").write_text("Federico Garibaldi", encoding="utf8")
    state = tmp_path / "state"; rows = evidence.scan(source, state); assert rows[0]["paths"] == ["a.txt"]
    (source / "moved.txt").write_text("Federico Garibaldi", encoding="utf8"); (source / "a.txt").unlink()
    assert evidence.scan(source, state)[0]["paths"] == ["moved.txt"]
    extracted = evidence.extract(state, source); assert extracted[0]["extraction_status"] == "SUCCESS"
    (source / "moved.txt").write_text("changed", encoding="utf8")
    # A fresh evidence root avoids a legitimate cache hit and exercises the pre-extraction hash check.
    state2 = tmp_path / "state2"; evidence.scan(source, state2); (source / "moved.txt").write_text("changed twice", encoding="utf8")
    assert evidence.extract(state2, source)[0]["extraction_status"] == "EXTRACTION_ABORTED_STALE_HASH"

def test_post_resolution_consolidation_and_pending():
    raw = [
        {"file_id":"sha256:a", "subject_raw":"Federico Garibaldi", "predicate":"participated_in", "object_raw":"Through", "evidence_excerpt":"a"},
        {"file_id":"sha256:b", "subject_raw":"F. Garibaldi", "predicate":"participated_in", "object_raw":"Through", "evidence_excerpt":"b"},
    ]
    resolved = evidence.resolve_claims(raw, {"artista":[{"id":"n1", "titolo":"Federico Garibaldi"}], "mostra":[{"id":"n2", "titolo":"Through"}]}, {"f garibaldi":"federico garibaldi"})
    claims = evidence.consolidate_claims(resolved)
    assert len(claims) == 1 and claims[0]["source_file_ids"] == ["sha256:a", "sha256:b"]
    payload = evidence.notion_payload("artista", "Federico Garibaldi", claims, "NEW_ENTITY", {"participated_in"})
    assert payload["gate"] == "READY_FOR_NOTION" and payload["dry_run"] is True

def test_consolidate_claims_status_precedence_is_order_independent():
    """A still-pending web claim must never hold back a predicate the archive already
    establishes, regardless of which raw claim consolidate_claims sees first."""
    def raw(file_id, status):
        return {"file_id": file_id, "subject_raw": "Federico Garibaldi", "predicate": "opere", "object_raw": "Through",
                "evidence_excerpt": file_id, "status": status}
    rows = {"artista": [{"id": "n1", "titolo": "Federico Garibaldi"}], "mostra": [{"id": "n2", "titolo": "Through"}]}
    web_then_archive = evidence.consolidate_claims(evidence.resolve_claims(
        [raw("sha256:web", "SUPPORTED_BY_WEB"), raw("sha256:archive", "SUPPORTED_BY_ARCHIVE")], rows))
    archive_then_web = evidence.consolidate_claims(evidence.resolve_claims(
        [raw("sha256:archive", "SUPPORTED_BY_ARCHIVE"), raw("sha256:web", "SUPPORTED_BY_WEB")], rows))
    assert web_then_archive[0]["status"] == "SUPPORTED_BY_ARCHIVE"
    assert archive_then_web[0]["status"] == "SUPPORTED_BY_ARCHIVE"
    assert evidence.gate("NEW_ENTITY", web_then_archive, {"opere"}) == "READY_FOR_NOTION"

def test_known_limitation_supported_status_silently_outranks_disputed_on_merge():
    """Documented trade-off, not a bug to fix here: if two raw claims resolve to the
    EXACT same (subject, predicate, object) but one is flagged DISPUTED and another is
    SUPPORTED_BY_ARCHIVE/VERIFIED/etc., consolidate_claims keeps only the higher-
    precedence "supported" status — the DISPUTED flag on that specific citation is lost
    from the merged claim, not preserved as a side-signal. Raised by gmv-code-reviewer
    as a plausible-risk architectural note (not reproduced against real data); tracked
    here so the behavior is intentional and visible, not an unspecified accident."""
    def raw(file_id, status):
        return {"file_id": file_id, "subject_raw": "Federico Garibaldi", "predicate": "opere", "object_raw": "Through",
                "evidence_excerpt": file_id, "status": status}
    rows = {"artista": [{"id": "n1", "titolo": "Federico Garibaldi"}], "mostra": [{"id": "n2", "titolo": "Through"}]}
    consolidated = evidence.consolidate_claims(evidence.resolve_claims(
        [raw("sha256:disputed", "DISPUTED"), raw("sha256:archive", "SUPPORTED_BY_ARCHIVE")], rows))
    assert consolidated[0]["status"] == "SUPPORTED_BY_ARCHIVE"
    assert set(consolidated[0]["source_file_ids"]) == {"sha256:disputed", "sha256:archive"}

def test_better_status_known_pairs_outside_the_common_archive_web_case():
    # DISPUTED (contradicted) must never lose to UNVERIFIED (merely unconfirmed) regardless of order.
    assert evidence._better_status("UNVERIFIED", "DISPUTED") == "DISPUTED"
    assert evidence._better_status("DISPUTED", "UNVERIFIED") == "DISPUTED"

def test_better_status_unrecognized_status_never_wins_against_a_known_one():
    assert evidence._better_status("SOME_NEW_LLM_STATUS", "SUPPORTED_BY_ARCHIVE") == "SUPPORTED_BY_ARCHIVE"
    assert evidence._better_status("SUPPORTED_BY_ARCHIVE", "SOME_NEW_LLM_STATUS") == "SUPPORTED_BY_ARCHIVE"

def test_resolve_cli_extra_claims_merges_before_resolving(tmp_path, capsys):
    archive = [{"file_id": "sha256:a", "subject_raw": "Federico Garibaldi", "predicate": "opere", "object_raw": "Through", "evidence_excerpt": "a"}]
    web = [{"file_id": "sha256:b", "subject_raw": "Federico Garibaldi", "predicate": "formazione", "object_raw": "Accademia", "evidence_excerpt": "b", "status": "SUPPORTED_BY_WEB"}]
    (tmp_path / "claims.json").write_text(evidence.canonical(archive), encoding="utf-8")
    (tmp_path / "extra.json").write_text(evidence.canonical(web), encoding="utf-8")
    (tmp_path / "rows.json").write_text(evidence.canonical({"artista": [{"id": "n1", "titolo": "Federico Garibaldi"}], "mostra": [{"id": "n2", "titolo": "Through"}]}), encoding="utf-8")
    argv = ["gmv_evidence_pipeline.py", "resolve", str(tmp_path / "claims.json"), "--rows", str(tmp_path / "rows.json"), "--extra-claims", str(tmp_path / "extra.json")]
    original_argv = sys.argv
    sys.argv = argv
    try:
        assert evidence.main() == 0
    finally:
        sys.argv = original_argv
    output = json.loads(capsys.readouterr().out)
    predicates = {c["predicate"] for c in output["claims"]}
    assert predicates == {"opere", "formazione"}

def test_bundle_is_local_and_has_dry_run_payload(tmp_path):
    claims = [{"claim_id":"claim:x", "predicate":"nome", "source_file_ids":["sha256:x"], "source_excerpts":["Federico"]}]
    bundle = evidence.write_evidence_bundle(tmp_path, "Federico Garibaldi", "artista", claims, "NEW_ENTITY", {"nome"}, {"sha256:x":["bio.txt"]})
    assert (bundle / "EVIDENCE.md").exists()
    assert evidence.read_json(bundle / "NOTION_PAYLOAD.json", {})["dry_run"] is True

def test_artist_body_routing_and_semantic_deduplication():
    idx = {"sha256:x": {"paths": ["source.txt"]}}
    body = "La ricerca riguarda memoria, paesaggio, identità e narrazione. Fotografo, filmmaker. Riyadh e Venezia."
    def c(cid, predicate, obj, status="CONFIRMED"):
        return {"claim_id": cid, "subject": "Federico Garibaldi", "predicate": predicate, "object": obj, "status": status, "source_file_ids": ["sha256:x"], "source_excerpts": [str(obj)]}
    claims = [c("q1", "is the source of", "Through"), c("q2", "has themes", "memoria, paesaggio"), c("q3", "has themes", "mare, memoria, paesaggio"), c("q4", "has themes", "storytelling, cinema, fotografia"), c("q5", "has themes", "fotografia, identità, Riyadh, Venezia"), c("q6", "said", "Non congelo immagini, congelo sensazioni."), c("q7", "said", "La fotografia e il cinema sono due modi diversi di raccontare.", "UNVERIFIED")]
    result = candidate.build_artist_body_candidates(claims, body, idx)
    by_id = {x["claim_id"]: x for x in result["candidates"]}
    assert by_id["q1"]["action"] == "KEEP_EVIDENCE"
    assert by_id["q2"]["action"] == "KEEP_SEMANTIC"
    assert by_id["q3"]["action"] == "PARTIAL_ADD" and by_id["q3"]["delta_text"] == "mare"
    assert by_id["q4"]["action"] == "KEEP_SEMANTIC"
    assert by_id["q5"]["action"] == "KEEP_CONTEXT"
    assert by_id["q6"]["action"] == "ADD"
    assert by_id["q7"]["action"] == "HOLD"
    rendered = candidate.render_body_patch_markdown(result)
    assert "Nei materiali esaminati emerge inoltre il mare come elemento ricorrente della ricerca." in rendered
    assert "KEEP_EVIDENCE" not in rendered and "Riyadh" not in rendered

def test_chunker_keeps_small_paragraph_intact():
    record = {"file_id": "f", "text": "Prima frase. Seconda frase."}
    chunks = evidence.deterministic_chunks(record, 8000)
    assert len(chunks) == 1 and chunks[0]["text"] == record["text"]

def test_chunker_splits_long_paragraph_losslessly_and_within_limit():
    text = " ".join(f"Frase {i}." for i in range(1600))
    chunks = evidence.deterministic_chunks({"file_id": "f", "text": text}, 8000)
    assert len(chunks) > 1
    assert all(len(c["text"]) <= 8000 for c in chunks)
    assert "".join(c["text"] for c in chunks) == text
    assert len(set(c["text"] for c in chunks)) == len(chunks)
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))

def test_adaptive_split_recursive_and_provenance(monkeypatch, tmp_path):
    original = evidence.ollama_extract
    def fake(record, **kwargs):
        if len(record["text"]) > 3000:
            raise evidence.OllamaResponseError("OLLAMA_OUTPUT_TRUNCATED", runtime={"done_reason":"length", "eval_count":2048}, raw_output="x")
        return {"file_id": record["file_id"], "entities": [], "claims": [{"subject_raw":"A", "predicate":"p", "object_raw":"o", "evidence_excerpt":"e"}], "_runtime":{"done_reason":"stop","eval_count":2}}
    monkeypatch.setattr(evidence, "ollama_extract", fake)
    record = {"file_id":"sha256:f", "extraction_status":"SUCCESS", "text":"A. " * 2500}
    out = evidence.semantic_extract_batch([record], tmp_path, artist="A", endpoint="x", model="m", max_chunk_chars=8000, min_adaptive_chunk_chars=2000, max_adaptive_depth=4)
    manifest = evidence.read_json(tmp_path / "semantic" / "run_manifest.json", {})
    leaves = [n for n in manifest["nodes"] if n["outcome"] == "SUCCESS"]
    assert len(leaves) > 2 and all(n["input_chars"] <= 8000 for n in leaves)
    assert all(c["leaf_chunk_id"] for c in out["claims"])
    monkeypatch.setattr(evidence, "ollama_extract", original)

SOFFICE_MISSING = not (shutil.which("soffice") or shutil.which("libreoffice"))

@pytest.mark.skipif(SOFFICE_MISSING, reason="soffice not installed")
def test_doc_extraction_via_libreoffice(tmp_path):
    source = tmp_path / "dropbox"; source.mkdir()
    (source / "bio.doc").write_bytes((FIXTURES / "sample.doc").read_bytes())
    state = tmp_path / "state"; evidence.scan(source, state)
    record = evidence.extract(state, source)[0]
    assert record["extraction_status"] == "SUCCESS"
    assert record["extractor"] == "doc_text_libreoffice"
    # exact prefix, not `in`: catches a stray leading BOM (﻿) that
    # LibreOffice's txt:Text filter always writes and that plain .strip() does not remove.
    assert record["text"].startswith("Federico Garibaldi")

@pytest.mark.skipif(SOFFICE_MISSING, reason="soffice not installed")
def test_doc_extraction_of_empty_document_requires_ocr(tmp_path):
    source = tmp_path / "dropbox"; source.mkdir()
    (source / "empty.doc").write_bytes((FIXTURES / "empty.doc").read_bytes())
    state = tmp_path / "state"; evidence.scan(source, state)
    assert evidence.extract(state, source)[0]["extraction_status"] == "OCR_REQUIRED"

def test_doc_extraction_fails_explicitly_without_libreoffice(monkeypatch, tmp_path):
    monkeypatch.setattr(evidence.shutil, "which", lambda _name: None)
    source = tmp_path / "dropbox"; source.mkdir()
    (source / "bio.doc").write_bytes((FIXTURES / "sample.doc").read_bytes())
    state = tmp_path / "state"; evidence.scan(source, state)
    assert evidence.extract(state, source)[0]["extraction_status"] == "EXTRACTION_FAILED"

def test_doc_extractor_version_bump_invalidates_pre_fix_unsupported_cache(tmp_path):
    """A .doc scanned before this fix would have a cached UNSUPPORTED_FORMAT
    record under the old extractor_version — that stale record must not shadow
    the new extractor, or the fix is invisible for already-processed archives."""
    source = tmp_path / "dropbox"; source.mkdir()
    (source / "bio.doc").write_bytes((FIXTURES / "sample.doc").read_bytes())
    state = tmp_path / "state"; rows = evidence.scan(source, state)
    _, cache = evidence.paths(state)
    stale_record_path = cache / "extracted" / f"{rows[0]['sha256']}-0.1.json"
    evidence.write_json(stale_record_path, {"file_id": rows[0]["file_id"], "extraction_status": "UNSUPPORTED_FORMAT"})
    record = evidence.extract(state, source)[0]
    assert record["extraction_status"] != "UNSUPPORTED_FORMAT"

def test_unsupported_format_still_rejected(tmp_path):
    source = tmp_path / "dropbox"; source.mkdir(); (source / "a.zip").write_bytes(b"PK\x03\x04")
    state = tmp_path / "state"; evidence.scan(source, state)
    assert evidence.extract(state, source)[0]["extraction_status"] == "UNSUPPORTED_FORMAT"

def test_scan_excludes_10_md_processed_files_recursively(tmp_path):
    source = tmp_path / "dropbox"; source.mkdir()
    (source / "09_TEMP_IMPORT").mkdir()
    (source / "09_TEMP_IMPORT" / "bio.pdf").write_bytes(b"%PDF-1.4 not real pdf bytes")
    md_dir = source / "10_MD_PROCESSED_FILES"; md_dir.mkdir()
    (md_dir / "09_TEMP_IMPORT__bio.pdf.md").write_text("# AnyDoc Markdown\ncontent", encoding="utf-8")
    state = tmp_path / "state"; rows = evidence.scan(source, state)
    all_paths = [p for r in rows for p in r["paths"]]
    assert "09_TEMP_IMPORT/bio.pdf" in all_paths
    assert not any("10_MD_PROCESSED_FILES" in p for p in all_paths)

def test_anydoc_md_used_when_present_root_is_artist_folder(tmp_path):
    source = tmp_path / "dropbox"; source.mkdir()
    (source / "09_TEMP_IMPORT").mkdir()
    (source / "09_TEMP_IMPORT" / "bio.pdf").write_bytes(b"%PDF-1.4 not real pdf bytes")
    md_dir = source / "10_MD_PROCESSED_FILES"; md_dir.mkdir()
    (md_dir / "09_TEMP_IMPORT__bio.pdf.md").write_text("# AnyDoc Markdown\ncontent", encoding="utf-8")
    state = tmp_path / "state"; rows = evidence.scan(source, state)
    # scan() (not modified here) also indexes the AnyDoc .md file itself as a
    # separate source document, so the target record is looked up by its
    # known source path rather than assumed to be first in the list.
    target_fid = next(r["file_id"] for r in rows if r["paths"] == ["09_TEMP_IMPORT/bio.pdf"])
    records = {r["file_id"]: r for r in evidence.extract(state, source)}
    record = records[target_fid]
    assert record["extraction_status"] == "SUCCESS"
    assert record["extractor"] == "anydoc_md"
    assert record["text"] == "# AnyDoc Markdown\ncontent"

def test_anydoc_md_absent_falls_back_to_legacy_extractor(tmp_path):
    source = tmp_path / "dropbox"; source.mkdir()
    (source / "note.txt").write_text("Federico Garibaldi", encoding="utf-8")
    state = tmp_path / "state"; evidence.scan(source, state)
    record = evidence.extract(state, source)[0]
    assert record["extraction_status"] == "SUCCESS"
    assert record["extractor"] == "text"

def test_anydoc_md_path_root_is_artist_folder(tmp_path):
    root = tmp_path / "artist"
    md_dir = root / "10_MD_PROCESSED_FILES"; md_dir.mkdir(parents=True)
    (md_dir / "09_TEMP_IMPORT__bio.pdf.md").write_text("x", encoding="utf-8")
    found = evidence._anydoc_md_path(root, "09_TEMP_IMPORT/bio.pdf")
    assert found == md_dir / "09_TEMP_IMPORT__bio.pdf.md"

def test_anydoc_md_path_root_is_01_artists_parent(tmp_path):
    root = tmp_path / "01_ARTISTS"
    artist_dir = root / "PATERNO_CASTELLO_Riccardo"
    md_dir = artist_dir / "10_MD_PROCESSED_FILES"; md_dir.mkdir(parents=True)
    (md_dir / "09_TEMP_IMPORT__bio.pdf.md").write_text("x", encoding="utf-8")
    found = evidence._anydoc_md_path(root, "PATERNO_CASTELLO_Riccardo/09_TEMP_IMPORT/bio.pdf")
    assert found == md_dir / "09_TEMP_IMPORT__bio.pdf.md"

def test_adaptive_minimum_exhausted(monkeypatch, tmp_path):
    def truncated(record, **kwargs):
        raise evidence.OllamaResponseError("OLLAMA_OUTPUT_TRUNCATED", runtime={"done_reason":"length", "eval_count":2048}, raw_output="x")
    monkeypatch.setattr(evidence, "ollama_extract", truncated)
    record = {"file_id":"sha256:f", "extraction_status":"SUCCESS", "text":"x" * 600}
    try:
        evidence.semantic_extract_batch([record], tmp_path, artist="A", endpoint="x", model="m", max_chunk_chars=8000, min_adaptive_chunk_chars=500)
    except evidence.EvidenceError as exc:
        assert str(exc) == "ADAPTIVE_CHUNK_MINIMUM_EXHAUSTED"
    else:
        assert False


def _fake_extract_fixed(record, **kwargs):
    return {"file_id": record["file_id"], "entities": [{"name": "A", "evidence_excerpt": "e"}],
            "claims": [{"subject_raw": "A", "predicate": "p", "object_raw": "o", "evidence_excerpt": "e"}],
            "_runtime": {"done_reason": "stop"}}


def test_analyze_writes_semantic_output_and_marks_valid(monkeypatch, tmp_path):
    monkeypatch.setattr(evidence, "ollama_extract", _fake_extract_fixed)
    record = {"file_id": "sha256:abc123", "extraction_status": "SUCCESS", "text": "some text"}
    out = evidence.semantic_extract_batch([record], tmp_path, artist="A", endpoint="x", model="m")
    sem = tmp_path / "semantic" / "abc123-0.2.sem.json"
    assert sem.exists()
    data = evidence.read_json(sem, None)
    # The per-file .sem.json carries exactly the same (enriched) content as the aggregate stdout.
    assert data == out
    assert data["entities"] == [{"name": "A", "evidence_excerpt": "e"}]
    assert data["claims"][0]["subject_raw"] == "A"
    manifest = evidence.load_analyze_manifest(tmp_path)
    assert manifest["sha256:abc123"]["status"] == "valid"


def test_analyze_resume_skips_valid_files_without_ollama(monkeypatch, tmp_path):
    def _raise_if_called(record, **kwargs):
        raise AssertionError("ollama_extract must not be called on resumed file")
    calls = []
    def _spy(*a, **kw):
        calls.append(a)
        return _raise_if_called(*a, **kw)
    evidence.mark_analyzed(tmp_path, "sha256:abc123", "valid", artist="A", model="m", timeout=60)
    sem = tmp_path / "semantic" / "abc123-0.2.sem.json"
    sem.parent.mkdir(parents=True, exist_ok=True)
    sentinel = {"entities": [{"name": "SENTINEL"}], "claims": []}
    sem.write_text(evidence.canonical(sentinel) + "\n", encoding="utf-8")
    monkeypatch.setattr(evidence, "ollama_extract", _spy)
    record = {"file_id": "sha256:abc123", "extraction_status": "SUCCESS", "text": "some text"}
    out = evidence.semantic_extract_batch([record], tmp_path, artist="A", endpoint="x", model="m", resume=True)
    assert calls == []
    assert sem.read_text(encoding="utf-8").strip() == evidence.canonical(sentinel).strip()
    manifest = evidence.load_analyze_manifest(tmp_path)
    assert manifest["sha256:abc123"]["status"] == "valid"
    assert out == {"entities": [], "claims": []}


def test_analyze_retry_limit_then_failed(monkeypatch, tmp_path):
    # (a) transient-timeout twice then success with retry_limit=3 -> success, 3 calls.
    records = []
    def _flaky(record, **kwargs):
        records.append(record)
        n = len(records)
        if n < 3:
            raise evidence.EvidenceError("TIMEOUT")
        return {"file_id": record["file_id"], "entities": [], "claims": [], "_runtime": {"done_reason": "stop"}}
    monkeypatch.setattr(evidence, "ollama_extract", _flaky)
    record = {"file_id": "sha256:abc123", "extraction_status": "SUCCESS", "text": "some text"}
    out = evidence.semantic_extract_batch([record], tmp_path, artist="A", endpoint="x", model="m", retry_limit=3)
    assert len(records) == 3
    manifest = evidence.load_analyze_manifest(tmp_path)
    assert manifest["sha256:abc123"]["status"] == "valid"

    # (b) always TIMEOUT, retry_limit=2 -> batch raises, manifest "failed", exactly 2 calls.
    calls = []
    def _always_timeout(record, **kwargs):
        calls.append(record)
        raise evidence.EvidenceError("TIMEOUT")
    monkeypatch.setattr(evidence, "ollama_extract", _always_timeout)
    record2 = {"file_id": "sha256:def456", "extraction_status": "SUCCESS", "text": "some text"}
    try:
        evidence.semantic_extract_batch([record2], tmp_path, artist="A", endpoint="x", model="m", retry_limit=2)
    except evidence.EvidenceError as exc:
        assert str(exc) == "TIMEOUT"
    else:
        assert False
    assert len(calls) == 2
    manifest2 = evidence.load_analyze_manifest(tmp_path)
    assert manifest2["sha256:def456"]["status"] == "failed"


def test_analyze_manifest_survives_no_trailing_newline(tmp_path):
    path = tmp_path / "semantic" / "analyze_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = '{"sha256:abc123": {"status": "valid", "artist": "A", "model": "m", "timeout": 60}}'
    path.write_text(body, encoding="utf-8")
    manifest = evidence.load_analyze_manifest(tmp_path)
    assert manifest["sha256:abc123"]["status"] == "valid"
