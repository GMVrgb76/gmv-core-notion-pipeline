import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "10_API"))
import gmv_evidence_pipeline as evidence_module
import gmv_run


def _stub_ollama(record, **kwargs):
    return {"file_id": record["file_id"], "entities": [], "claims": [],
            "_runtime": {"done_reason": "stop", "eval_count": 1}}


def test_run_without_notion_rows_skips_resolve_and_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence_module, "ollama_extract", _stub_ollama)
    source = tmp_path / "artist"; source.mkdir()
    (source / "bio.txt").write_text("Federico Garibaldi", encoding="utf-8")
    evidence_root = tmp_path / "state"
    output = gmv_run.run(source, evidence_root, model="test-model")
    assert output["scan"] == "DONE"
    assert output["extract"]["records"] == 1
    assert output["analyze"]["status"] == "DONE"
    assert output["web_retrieval"] == "SKIPPED_NOT_PROVIDED"
    assert output["resolve"] == "SKIPPED_NOT_CONFIGURED"
    assert output["candidate"] == "SKIPPED_NOT_CONFIGURED"


def test_run_with_rows_resolves_but_skips_candidate_without_config(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence_module, "ollama_extract", _stub_ollama)
    source = tmp_path / "artist"; source.mkdir()
    (source / "bio.txt").write_text("Federico Garibaldi", encoding="utf-8")
    evidence_root = tmp_path / "state"
    rows_path = tmp_path / "rows.json"
    rows_path.write_text(json.dumps({"artista": [{"id": "n1", "titolo": "Federico Garibaldi"}]}), encoding="utf-8")
    output = gmv_run.run(source, evidence_root, model="test-model", notion_rows=rows_path)
    assert output["resolve"]["status"] == "DONE"
    assert output["candidate"] == "SKIPPED_NOT_CONFIGURED"
