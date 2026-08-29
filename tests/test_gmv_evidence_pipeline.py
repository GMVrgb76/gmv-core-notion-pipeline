import importlib.util
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("evidence", Path(__file__).parents[1] / "10_API" / "gmv_evidence_pipeline.py")
evidence = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(evidence)
sys.path.insert(0, str(Path(__file__).parents[1] / "10_API"))
import gmv_notion_candidate as candidate

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
