import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import notion_publish as np
import credentials


class FakeNotion:
    def __init__(self, responses: dict):
        self.calls = []
        self.responses = responses

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        key = (method, path)
        if key not in self.responses:
            raise AssertionError(f"unexpected call: {method} {path} {body}")
        response = self.responses[key]
        return response(body) if callable(response) else response


# --- NOTION_TYPE_BUILDERS / build_property_payload ---------------------------

SCHEMA = {"Nome": "title", "Bio": "rich_text", "Anno": "number", "Stato": "select",
          "Temi": "multi_select", "Data": "date", "Sito": "url", "Attivo": "checkbox",
          "Formula": "formula", "Mostre": "relation"}

@pytest.mark.parametrize(("prop", "value", "expected"), [
    ("Nome", "Federico Garibaldi", {"title": [{"type": "text", "text": {"content": "Federico Garibaldi"}}]}),
    ("Bio", "testo", {"rich_text": [{"type": "text", "text": {"content": "testo"}}]}),
    ("Anno", "2018", {"number": 2018.0}),
    ("Stato", "Confermato", {"select": {"name": "Confermato"}}),
    ("Temi", "memoria, paesaggio", {"multi_select": [{"name": "memoria"}, {"name": "paesaggio"}]}),
    ("Data", "2026-01-01", {"date": {"start": "2026-01-01"}}),
    ("Sito", "https://x.com", {"url": "https://x.com"}),
    ("Attivo", "yes", {"checkbox": True}),
])
def test_build_property_payload_maps_each_supported_notion_type(prop, value, expected):
    operations = [{"action": "ADD", "claim_id": "c1", "property": prop, "value": value}]
    properties, skipped = np.build_property_payload(SCHEMA, operations)
    assert properties == {prop: expected}
    assert skipped == []

def test_build_property_payload_skips_unsupported_type_and_reports_it():
    operations = [{"action": "ADD", "claim_id": "c1", "property": "Formula", "value": "x"}]
    properties, skipped = np.build_property_payload(SCHEMA, operations)
    assert properties == {}
    assert skipped[0]["reason"] == "UNSUPPORTED_NOTION_TYPE:formula"

def test_build_property_payload_never_writes_a_relation():
    operations = [{"action": "ADD", "claim_id": "c1", "property": "Mostre", "value": "x"}]
    properties, skipped = np.build_property_payload(SCHEMA, operations)
    assert properties == {}
    assert skipped[0]["reason"] == "UNSUPPORTED_NOTION_TYPE:relation"

def test_build_property_payload_ignores_conflict_and_keep_actions():
    operations = [
        {"action": "CONFLICT", "claim_id": "c1", "property": "Nome", "reason": "x"},
        {"action": "KEEP", "claim_id": "c2", "property": "Bio", "value": "y"},
    ]
    properties, skipped = np.build_property_payload(SCHEMA, operations)
    assert properties == {} and skipped == []


# --- markdown_to_blocks -------------------------------------------------------

def test_markdown_to_blocks_converts_h2_h3_and_flat_bullets():
    md = "## PROFILO ARTISTICO\n### La ricerca\n- mare come elemento ricorrente\n- fotografia"
    blocks = np.markdown_to_blocks(md)
    assert blocks[0]["type"] == "heading_2" and blocks[0]["heading_2"]["rich_text"][0]["text"]["content"] == "PROFILO ARTISTICO"
    assert blocks[1]["type"] == "heading_3" and blocks[1]["heading_3"]["rich_text"][0]["text"]["content"] == "La ricerca"
    assert blocks[2]["type"] == "bulleted_list_item"
    assert blocks[2]["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "mare come elemento ricorrente"
    assert blocks[3]["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "fotografia"

def test_markdown_to_blocks_ignores_blank_lines():
    blocks = np.markdown_to_blocks("## A\n\n\n- b\n")
    assert len(blocks) == 2

@pytest.mark.parametrize("bad_line", ["**bold**", "[link](url)", "|a|b|", "  - nested bullet"])
def test_markdown_to_blocks_raises_on_construct_outside_h2_h3_bullet(bad_line):
    with pytest.raises(ValueError):
        np.markdown_to_blocks(f"## Title\n{bad_line}")


# --- check_staleness -----------------------------------------------------------

def test_check_staleness_create_operation_is_never_stale():
    patch = {"operation": "CREATE", "existing_notion_id": None, "keep": {"properties": {}}}
    result = np.check_staleness(FakeNotion({}), patch)
    assert result["stale"] is False

def test_check_staleness_reports_no_diff_when_live_matches_keep():
    page_id = "a" * 32
    patch = {"operation": "UPDATE", "existing_notion_id": page_id, "keep": {"properties": {"Nome": "Federico"}}}
    live_page = {"properties": {"Nome": {"type": "title", "title": [{"plain_text": "Federico"}]}}}
    client = FakeNotion({("GET", f"/pages/{page_id}"): live_page})
    result = np.check_staleness(client, patch)
    assert result["stale"] is False

def test_check_staleness_reports_diff_when_live_value_changed():
    page_id = "b" * 32
    patch = {"operation": "UPDATE", "existing_notion_id": page_id, "keep": {"properties": {"Nome": "Federico"}}}
    live_page = {"properties": {"Nome": {"type": "title", "title": [{"plain_text": "Cambiato"}]}}}
    client = FakeNotion({("GET", f"/pages/{page_id}"): live_page})
    result = np.check_staleness(client, patch)
    assert result["stale"] is True
    assert result["diffs"] == [{"property": "Nome", "bundle_value": "Federico", "live_value": "Cambiato"}]


# --- find_existing_page_id -----------------------------------------------------

def test_find_existing_page_id_returns_id_when_a_match_exists():
    client = FakeNotion({("POST", "/databases/db1/query"): {"results": [{"id": "p1"}]}})
    result = np.find_existing_page_id(client, "db1", "Nome", "Federico Garibaldi")
    assert result == "p1"
    assert client.calls == [("POST", "/databases/db1/query",
                              {"filter": {"property": "Nome", "title": {"equals": "Federico Garibaldi"}}})]

def test_find_existing_page_id_returns_none_when_no_match():
    client = FakeNotion({("POST", "/databases/db1/query"): {"results": []}})
    result = np.find_existing_page_id(client, "db1", "Nome", "Federico Garibaldi")
    assert result is None


# --- plan_requests / apply_patch ------------------------------------------------

CREATE_PATCH = {"operation": "CREATE", "existing_notion_id": None,
                "operations": [{"action": "ADD", "claim_id": "c1", "property": "Nome", "value": "Federico"}],
                "body_gate": "BODY_REVIEW_REQUIRED"}

def test_plan_requests_create_emits_single_post_pages():
    requests, skipped = np.plan_requests("db1", CREATE_PATCH, {"Nome": "title"}, None)
    assert len(requests) == 1
    assert requests[0]["method"] == "POST" and requests[0]["path"] == "/pages"
    assert requests[0]["body"]["parent"] == {"database_id": "db1"}

def test_plan_requests_update_omits_patch_when_no_add_update_ops_survive_skip_filtering():
    page_id = "c" * 32
    patch = {"operation": "UPDATE", "existing_notion_id": page_id,
             "operations": [{"action": "ADD", "claim_id": "c1", "property": "Formula", "value": "x"}],
             "body_gate": "BODY_REVIEW_REQUIRED"}
    requests, skipped = np.plan_requests("db1", patch, {"Formula": "formula"}, None)
    assert requests == []
    assert skipped[0]["reason"] == "UNSUPPORTED_NOTION_TYPE:formula"

def test_plan_requests_omits_body_request_when_body_gate_not_ready():
    requests, _ = np.plan_requests("db1", CREATE_PATCH, {"Nome": "title"}, "## Section\n- item")
    assert all("blocks" not in r["path"] for r in requests)

def test_plan_requests_includes_body_request_when_gate_ready():
    patch = {**CREATE_PATCH, "body_gate": "BODY_PATCH_READY"}
    requests, _ = np.plan_requests("db1", patch, {"Nome": "title"}, "## Section\n- item")
    assert any("blocks" in r["path"] for r in requests)

def test_apply_patch_create_returns_new_page_id_and_applies_only_supported_properties():
    created_page = {"id": "d" * 32}
    client = FakeNotion({("POST", "/pages"): created_page})
    result = np.apply_patch(client, "db1", CREATE_PATCH, {"Nome": "title"}, None)
    assert result == {"page_id": "d" * 32, "created": True, "properties_applied": ["Nome"],
                       "properties_skipped": [], "blocks_appended": 0}

def test_apply_patch_update_never_calls_pages_patch_when_properties_empty():
    page_id = "e" * 32
    patch = {"operation": "UPDATE", "existing_notion_id": page_id,
             "operations": [{"action": "CONFLICT", "claim_id": "c1", "property": "Mostre", "reason": "x"}],
             "body_gate": "BODY_REVIEW_REQUIRED"}
    client = FakeNotion({})  # any call at all is an AssertionError
    result = np.apply_patch(client, "db1", patch, {"Mostre": "relation"}, None)
    assert result["properties_applied"] == []
    assert client.calls == []

def test_apply_patch_appends_body_blocks_only_when_gate_ready():
    page_id = "f" * 32
    patch = {"operation": "UPDATE", "existing_notion_id": page_id, "operations": [], "body_gate": "BODY_PATCH_READY"}
    client = FakeNotion({("PATCH", f"/blocks/{page_id}/children"): {}})
    result = np.apply_patch(client, "db1", patch, {}, "## S\n- item")
    assert result["blocks_appended"] == 2
    assert client.calls == [("PATCH", f"/blocks/{page_id}/children", {"children": np.markdown_to_blocks("## S\n- item")})]

def test_apply_patch_never_includes_a_relation_key_in_properties_payload():
    page_id = "1" * 32
    patch = {"operation": "UPDATE", "existing_notion_id": page_id,
             "operations": [{"action": "UPDATE", "claim_id": "c1", "property": "Mostre", "value": "x"}],
             "body_gate": "BODY_REVIEW_REQUIRED"}
    client = FakeNotion({})
    result = np.apply_patch(client, "db1", patch, {"Mostre": "relation"}, None)
    assert "Mostre" not in result["properties_applied"]
    assert client.calls == []


# --- main() / CLI ---------------------------------------------------------------

def test_main_apply_mode_without_confirm_flag_exits_2_and_makes_no_network_call(monkeypatch, tmp_path, capsys):
    def fail_if_called(*a, **k): raise AssertionError("should never resolve a token without --confirm")
    monkeypatch.setattr(credentials, "get_token", fail_if_called)
    notion_patch = tmp_path / "NOTION_PATCH.json"; notion_patch.write_text(json.dumps(CREATE_PATCH), encoding="utf-8")
    config = tmp_path / "config.json"; config.write_text(json.dumps({"entita": {"artista": {"notion_database_id": "db1"}}}), encoding="utf-8")
    rc = np.main(["apply", "--notion-patch", str(notion_patch), "--config", str(config), "--entity-type", "artista"])
    assert rc == 2

def test_main_never_prints_the_token(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(credentials, "get_token", lambda *a, **k: credentials.ResolvedToken(value="secret_abc123", origin="env"))
    monkeypatch.setattr(np, "Notion", lambda token, version: FakeNotion({}))
    notion_patch = tmp_path / "NOTION_PATCH.json"
    notion_patch.write_text(json.dumps({"operation": "CREATE", "existing_notion_id": None, "keep": {"properties": {}}}), encoding="utf-8")
    config = tmp_path / "config.json"; config.write_text(json.dumps({"entita": {"artista": {"notion_database_id": "db1"}}}), encoding="utf-8")
    np.main(["check", "--notion-patch", str(notion_patch), "--config", str(config), "--entity-type", "artista"])
    out = capsys.readouterr()
    assert "secret_abc123" not in out.out and "secret_abc123" not in out.err
