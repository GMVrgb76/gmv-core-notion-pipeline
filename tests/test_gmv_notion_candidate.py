import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "10_API"))
import gmv_evidence_pipeline as evidence
import gmv_notion_candidate as candidate

CONFIG = {"entita": {"artista": {"campi": {
    "nome": {"notion": "Nome", "obbligatorio": True},
    "opere": {"notion": "Opere", "obbligatorio": True},
}, "relazioni": {}}}}


def _rows(entity_name):
    return {"artista": [{"id": "notion-1", "titolo": entity_name,
            "campi": {"nome": entity_name, "opere": None}, "relazioni": {}, "corpo": ""}]}


def test_merged_index_rows_normalizes_web_entries_to_paths_shape(tmp_path):
    (tmp_path / "index").mkdir(parents=True)
    evidence.save_index(tmp_path / "index" / "FILE_INDEX.jsonl", {"sha256:a": {"file_id": "sha256:a", "paths": ["bio.txt"]}})
    evidence.save_index(tmp_path / "index" / "WEB_INDEX.jsonl", {"sha256:b": {"file_id": "sha256:b", "url": "https://x.example/page", "source_url": "//x.example/page"}})
    index = candidate.merged_index_rows(tmp_path)
    assert index["sha256:a"]["paths"] == ["bio.txt"]
    assert index["sha256:b"]["paths"] == ["https://x.example/page"]

def test_merged_index_rows_handles_missing_web_index(tmp_path):
    (tmp_path / "index").mkdir(parents=True)
    evidence.save_index(tmp_path / "index" / "FILE_INDEX.jsonl", {"sha256:a": {"file_id": "sha256:a", "paths": ["bio.txt"]}})
    index = candidate.merged_index_rows(tmp_path)
    assert list(index) == ["sha256:a"]

def test_web_sourced_verified_claim_does_not_conflict_on_missing_locator(tmp_path):
    """The bug this wiring fixes: before merged_index_rows, a claim whose only
    source_file_ids point into WEB_INDEX.jsonl (not FILE_INDEX.jsonl) would resolve
    zero locators and get wrongly marked CONFLICT/UNSUPPORTED_STATUS_OR_MISSING_PROVENANCE
    even though its status (VERIFIED) is otherwise gate-eligible."""
    (tmp_path / "index").mkdir(parents=True)
    evidence.save_index(tmp_path / "index" / "WEB_INDEX.jsonl", {"sha256:web1": {"file_id": "sha256:web1", "url": "https://a.example/page"}})
    index = candidate.merged_index_rows(tmp_path)
    claims = [{"claim_id": "claim:opere", "predicate": "opere", "object": "Studio da Bronzino", "status": "VERIFIED", "source_file_ids": ["sha256:web1"]}]
    patch = candidate.build_incremental_patch("Riccardo Paternò Castello", "artista", claims, _rows("Riccardo Paternò Castello"), CONFIG, index)
    conflicts = [op for op in patch["operations"] if op["action"] == "CONFLICT"]
    assert conflicts == []
    assert any(op["action"] == "ADD" and op["property"] == "Opere" for op in patch["operations"])

def test_main_run_dir_flow_wires_web_index_and_writes_real_verification(tmp_path, capsys):
    """End-to-end through main() itself, exercising the previously-untested
    run_dir.parent/"state" convention for real, with mixed archive+web claims."""
    entity_name = "Riccardo Paternò Castello"
    run_dir = tmp_path / "run"
    state = tmp_path / "state"
    (state / "index").mkdir(parents=True)
    evidence.save_index(state / "index" / "FILE_INDEX.jsonl", {"sha256:bio": {"file_id": "sha256:bio", "paths": ["bio.doc"]}})
    evidence.save_index(state / "index" / "WEB_INDEX.jsonl", {"sha256:web1": {"file_id": "sha256:web1", "url": "https://a.example/page", "source_type": "WEB"}})
    claims = [
        {"claim_id": "claim:nome", "subject": entity_name, "predicate": "nome", "object": entity_name,
         "status": "SUPPORTED_BY_ARCHIVE", "source_file_ids": ["sha256:bio"], "source_excerpts": ["bio"]},
        {"claim_id": "claim:opere", "subject": entity_name, "predicate": "opere", "object": "Studio da Bronzino",
         "status": "VERIFIED", "source_file_ids": ["sha256:web1"], "source_excerpts": ["web"]},
        {"claim_id": "claim:formazione", "subject": entity_name, "predicate": "formazione", "object": "Accademia di Brera",
         "status": "SUPPORTED_BY_WEB", "source_file_ids": ["sha256:web1"], "source_excerpts": ["web"]},
    ]
    (tmp_path / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    (tmp_path / "rows.json").write_text(json.dumps(_rows(entity_name)), encoding="utf-8")
    (tmp_path / "config.json").write_text(json.dumps(CONFIG), encoding="utf-8")

    argv = ["gmv_notion_candidate.py", entity_name, "--entity-type", "artista",
            "--claims", str(tmp_path / "claims.json"), "--rows", str(tmp_path / "rows.json"),
            "--config", str(tmp_path / "config.json"), "--run-dir", str(run_dir)]
    original_argv = sys.argv
    sys.argv = argv
    try:
        assert candidate.main() == 0
    finally:
        sys.argv = original_argv
    capsys.readouterr()

    bundle = run_dir / "entities" / "Riccardo_Patern_Castello"
    sources = evidence.read_json(bundle / "sources.json", None)
    urls = {s["file_id"]: s["paths"] for s in sources}
    assert urls["sha256:web1"] == ["https://a.example/page"]
    assert urls["sha256:bio"] == ["bio.doc"]

    verification = evidence.read_json(bundle / "verification.json", None)
    assert verification["status"] == "EXECUTED"
    assert verification["verified_predicates"] == ["opere"]
    assert verification["pending_predicates"] == ["formazione"]

    patch = evidence.read_json(bundle / "NOTION_PATCH.json", None)
    conflicts = {op["claim_id"] for op in patch["operations"] if op["action"] == "CONFLICT"}
    # "formazione" is correctly blocked: still SUPPORTED_BY_WEB, not yet verified.
    # "opere" must NOT be blocked: VERIFIED status, web-sourced locator resolves fine
    # now that merged_index_rows folds WEB_INDEX.jsonl in — this is the bug this wiring fixes.
    assert conflicts == {"claim:formazione"}
    assert any(op["action"] == "ADD" and op.get("property") == "Opere" for op in patch["operations"])

def test_main_run_dir_flow_archive_only_reports_verification_not_executed(tmp_path, capsys):
    """The common case today (no web retrieval ever run for this artist) must produce
    an honest NOT_EXECUTED, not a false EXECUTED with empty lists — a VERIFIED status
    alone is not proof of web work, since archive claims can legitimately carry it too."""
    entity_name = "Federico Garibaldi"
    run_dir = tmp_path / "run"
    state = tmp_path / "state"
    (state / "index").mkdir(parents=True)
    evidence.save_index(state / "index" / "FILE_INDEX.jsonl", {"sha256:bio": {"file_id": "sha256:bio", "paths": ["bio.txt"]}})
    claims = [
        {"claim_id": "claim:nome", "subject": entity_name, "predicate": "nome", "object": entity_name,
         "status": "SUPPORTED_BY_ARCHIVE", "source_file_ids": ["sha256:bio"], "source_excerpts": ["bio"]},
        {"claim_id": "claim:opere", "subject": entity_name, "predicate": "opere", "object": "Through",
         "status": "VERIFIED", "source_file_ids": ["sha256:bio"], "source_excerpts": ["bio"]},
    ]
    (tmp_path / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    (tmp_path / "rows.json").write_text(json.dumps(_rows(entity_name)), encoding="utf-8")
    (tmp_path / "config.json").write_text(json.dumps(CONFIG), encoding="utf-8")

    argv = ["gmv_notion_candidate.py", entity_name, "--entity-type", "artista",
            "--claims", str(tmp_path / "claims.json"), "--rows", str(tmp_path / "rows.json"),
            "--config", str(tmp_path / "config.json"), "--run-dir", str(run_dir)]
    original_argv = sys.argv
    sys.argv = argv
    try:
        assert candidate.main() == 0
    finally:
        sys.argv = original_argv
    capsys.readouterr()

    bundle = run_dir / "entities" / "Federico_Garibaldi"
    verification = evidence.read_json(bundle / "verification.json", None)
    assert verification == {"status": "NOT_EXECUTED", "reason": "no web-sourced claims present"}
