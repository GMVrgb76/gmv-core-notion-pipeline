import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))
import gmv_notion_publish as gnp
import audit_integrity

CLOCK = lambda: datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def _write_bundle(tmp_path, *, gate="READY_FOR_NOTION", operation="CREATE",
                   existing_notion_id=None, body_gate="BODY_REVIEW_REQUIRED",
                   operations=None, multi_entity=False) -> Path:
    bundle = tmp_path / "entities" / "Federico_Garibaldi"
    bundle.mkdir(parents=True)
    (bundle / "entity.json").write_text(json.dumps({"entity_type": "ARTISTA", "name": "Federico Garibaldi"}), encoding="utf-8")
    (bundle / "NOTION_PAYLOAD.json").write_text(json.dumps({"gate": gate}), encoding="utf-8")
    if multi_entity:
        (bundle / "PATCH.json").write_text("{}", encoding="utf-8")
        return bundle
    patch = {
        "operation": operation, "existing_notion_id": existing_notion_id,
        "keep": {"properties": {}}, "operations": operations or [],
        "body_gate": body_gate, "body": {"proposed_markdown": "## S\n- item"},
    }
    (bundle / "NOTION_PATCH.json").write_text(json.dumps(patch), encoding="utf-8")
    return bundle


def _config(tmp_path) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"entita": {"artista": {"notion_database_id": "db1"}}}), encoding="utf-8")
    return path


def _patch_notion_plumbing(monkeypatch, *, staleness=None, requests=None, skipped=None, apply_result=None):
    import credentials as credentials_module
    monkeypatch.setattr(credentials_module, "get_token",
                         lambda *a, **k: credentials_module.ResolvedToken(value="tok", origin="env"))
    monkeypatch.setattr(gnp, "Notion", lambda token, version: object())
    monkeypatch.setattr(gnp, "fetch_database_schema", lambda client, db: {})
    monkeypatch.setattr(gnp, "check_staleness", lambda client, patch: staleness or {"stale": False, "diffs": []})
    monkeypatch.setattr(gnp, "plan_requests", lambda db, patch, schema, body: (requests or [], skipped or []))
    monkeypatch.setattr(gnp, "apply_patch", lambda client, db, patch, schema, body:
                         apply_result or {"page_id": "p1", "created": True, "properties_applied": [],
                                           "properties_skipped": [], "blocks_appended": 0})


def test_load_bundle_missing_notion_patch_json_names_the_multi_entity_format_explicitly(tmp_path):
    bundle = _write_bundle(tmp_path, multi_entity=True)
    with pytest.raises(ValueError, match="multi-entity"):
        gnp.load_bundle(bundle)


def test_publish_bundle_refuses_when_published_json_already_present_no_bypass(tmp_path, monkeypatch):
    bundle = _write_bundle(tmp_path)
    (bundle / "PUBLISHED.json").write_text(json.dumps({"notion_page_id": "p1", "published_at": "x", "audit_sequence": 1}), encoding="utf-8")
    def fail_if_called(*a, **k): raise AssertionError("must not proceed past the PUBLISHED.json check")
    monkeypatch.setattr(gnp, "check_staleness", fail_if_called)
    rc = gnp.publish_bundle(bundle, config_path=_config(tmp_path))
    assert rc == 3


def test_publish_bundle_refuses_when_gate_is_not_ready_for_notion(tmp_path, monkeypatch):
    bundle = _write_bundle(tmp_path, gate="REVIEW_REQUIRED")
    def fail_if_called(*a, **k): raise AssertionError("must not proceed past the gate check")
    monkeypatch.setattr(gnp, "check_staleness", fail_if_called)
    rc = gnp.publish_bundle(bundle, config_path=_config(tmp_path))
    assert rc == 4


def test_publish_bundle_aborts_when_duplicate_title_found_on_create_and_never_calls_apply(tmp_path, monkeypatch):
    bundle = _write_bundle(tmp_path, operation="CREATE", existing_notion_id=None)
    _patch_notion_plumbing(monkeypatch)
    monkeypatch.setattr(gnp, "fetch_database_schema", lambda client, db: {"Nome": "title"})
    monkeypatch.setattr(gnp, "find_existing_page_id", lambda client, db, prop, name: "existing-page-id")
    def fail_if_called(*a, **k): raise AssertionError("must not call apply_patch when a duplicate title is found")
    monkeypatch.setattr(gnp, "apply_patch", fail_if_called)
    rc = gnp.publish_bundle(bundle, config_path=_config(tmp_path))
    assert rc == 5


def test_publish_bundle_proceeds_when_no_duplicate_title_found_on_create(tmp_path, monkeypatch):
    bundle = _write_bundle(tmp_path, operation="CREATE", existing_notion_id=None)
    _patch_notion_plumbing(monkeypatch)
    monkeypatch.setattr(gnp, "fetch_database_schema", lambda client, db: {"Nome": "title"})
    monkeypatch.setattr(gnp, "find_existing_page_id", lambda client, db, prop, name: None)
    rc = gnp.publish_bundle(bundle, config_path=_config(tmp_path), input_fn=lambda p: "y", clock=CLOCK,
                             audit_path=tmp_path / "audit.jsonl")
    assert rc == 0


def test_publish_bundle_skip_staleness_check_also_bypasses_duplicate_title_guard(tmp_path, monkeypatch):
    bundle = _write_bundle(tmp_path, operation="CREATE", existing_notion_id=None)
    _patch_notion_plumbing(monkeypatch)
    monkeypatch.setattr(gnp, "fetch_database_schema", lambda client, db: {"Nome": "title"})
    def fail_if_called(*a, **k): raise AssertionError("must not query for a duplicate when --skip-staleness-check is passed")
    monkeypatch.setattr(gnp, "find_existing_page_id", fail_if_called)
    rc = gnp.publish_bundle(bundle, config_path=_config(tmp_path), skip_staleness_check=True,
                             input_fn=lambda p: "y", clock=CLOCK, audit_path=tmp_path / "audit.jsonl")
    assert rc == 0


def test_publish_bundle_aborts_on_staleness_and_never_calls_apply(tmp_path, monkeypatch):
    bundle = _write_bundle(tmp_path)
    _patch_notion_plumbing(monkeypatch, staleness={"stale": True, "diffs": [{"property": "Nome", "bundle_value": "a", "live_value": "b"}]})
    def fail_if_called(*a, **k): raise AssertionError("must not call apply_patch when stale")
    monkeypatch.setattr(gnp, "apply_patch", fail_if_called)
    rc = gnp.publish_bundle(bundle, config_path=_config(tmp_path))
    assert rc == 5


def test_publish_bundle_proceeds_past_staleness_when_flag_explicitly_passed(tmp_path, monkeypatch):
    bundle = _write_bundle(tmp_path)
    _patch_notion_plumbing(monkeypatch, staleness={"stale": True, "diffs": []})
    rc = gnp.publish_bundle(bundle, config_path=_config(tmp_path), skip_staleness_check=True,
                             input_fn=lambda p: "y", clock=CLOCK,
                             audit_path=tmp_path / "audit.jsonl")
    assert rc == 0


def test_publish_bundle_aborts_when_human_declines_and_never_calls_apply(tmp_path, monkeypatch):
    bundle = _write_bundle(tmp_path)
    _patch_notion_plumbing(monkeypatch)
    def fail_if_called(*a, **k): raise AssertionError("must not call apply_patch when human declines")
    monkeypatch.setattr(gnp, "apply_patch", fail_if_called)
    rc = gnp.publish_bundle(bundle, config_path=_config(tmp_path), input_fn=lambda p: "n")
    assert rc == 1
    assert not (bundle / "PUBLISHED.json").exists()


def test_publish_bundle_calls_apply_only_after_yes_confirmation(tmp_path, monkeypatch):
    bundle = _write_bundle(tmp_path)
    calls = []
    _patch_notion_plumbing(monkeypatch)
    def tracking_apply(client, db, patch, schema, body):
        calls.append((db, patch["operation"]))
        return {"page_id": "p1", "created": True, "properties_applied": ["Nome"], "properties_skipped": [], "blocks_appended": 0}
    monkeypatch.setattr(gnp, "apply_patch", tracking_apply)
    rc = gnp.publish_bundle(bundle, config_path=_config(tmp_path), input_fn=lambda p: "yes",
                             clock=CLOCK, audit_path=tmp_path / "audit.jsonl")
    assert rc == 0
    assert calls == [("db1", "CREATE")]


def test_publish_bundle_writes_published_json_with_matching_audit_sequence(tmp_path, monkeypatch):
    bundle = _write_bundle(tmp_path)
    audit_path = tmp_path / "audit.jsonl"
    _patch_notion_plumbing(monkeypatch, apply_result={"page_id": "p1", "created": True,
                                                        "properties_applied": ["Nome"], "properties_skipped": [], "blocks_appended": 0})
    rc = gnp.publish_bundle(bundle, config_path=_config(tmp_path), input_fn=lambda p: "y",
                             clock=CLOCK, audit_path=audit_path)
    assert rc == 0
    published = json.loads((bundle / "PUBLISHED.json").read_text())
    assert published["notion_page_id"] == "p1"
    assert published["audit_sequence"] == 1
    records = audit_integrity.validate(audit_path)
    assert records[0]["record_hash"] == published["audit_record_hash"]
    assert records[0]["notion_page_id"] == "p1"


def test_render_review_screen_lists_every_conflict_as_not_applied(tmp_path):
    operations = [
        {"action": "CONFLICT", "claim_id": "c1", "property": "Mostre", "reason": "RELATION_TARGET_ID_NOT_RESOLVED"},
        {"action": "ADD", "claim_id": "c2", "property": "Nome", "value": "Federico"},
    ]
    bundle_dir = _write_bundle(tmp_path, operations=operations)
    bundle = gnp.load_bundle(bundle_dir)
    screen = gnp.render_review_screen(bundle, requests=[], skipped_ops=[{"claim_id": "c3", "property": "Formula", "reason": "UNSUPPORTED_NOTION_TYPE:formula"}], staleness={"stale": False})
    assert "Mostre" in screen and "RELATION_TARGET_ID_NOT_RESOLVED" in screen
    assert "Formula" in screen and "UNSUPPORTED_NOTION_TYPE:formula" in screen
    assert "Nome" in screen


def test_render_review_screen_shows_body_review_required_banner_when_gate_not_ready(tmp_path):
    bundle_dir = _write_bundle(tmp_path, body_gate="BODY_REVIEW_REQUIRED")
    bundle = gnp.load_bundle(bundle_dir)
    screen = gnp.render_review_screen(bundle, requests=[], skipped_ops=[], staleness={"stale": False})
    assert "REVIEW REQUIRED" in screen
    assert "## S" not in screen
