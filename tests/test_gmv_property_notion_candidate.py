import json
import sys
from pathlib import Path

import pytest

API_DIR = Path(__file__).parents[1] / "10_API"
CORE_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(API_DIR))
sys.path.insert(0, str(CORE_ROOT))

import gmv_property_notion_candidate as candidate  # noqa: E402


def _claims():
    return [{"claim_id": "claim:abc", "subject": "Immobile", "predicate": "ha_tipo_tributo",
             "object": "TARI", "qualifiers": {}, "source_file_ids": ["sha256:1"],
             "source_excerpts": ["TARI 2026"], "status": "SUPPORTED_BY_ARCHIVE"}]


def test_build_property_bundle_always_forces_the_publish_blocked_gate(tmp_path):
    bundle = candidate.build_property_bundle("GERMIGNAGA", _claims(), tmp_path)
    payload = json.loads((bundle / "NOTION_PAYLOAD.json").read_text(encoding="utf-8"))
    assert payload["gate"] == "RECONCILIATION_CONTRACT_PENDING"
    assert payload["gate"] != "READY_FOR_NOTION"
    assert "reconciliation contract" in payload["publish_blocked_reason"].lower()


def test_build_property_bundle_gate_stays_closed_for_empty_claim_list(tmp_path):
    """Zero consolidated claims is the degenerate case where gate() would
    otherwise trivially return READY_FOR_NOTION for an empty mandatory set --
    the override must hold there too, not only on a populated bundle."""
    bundle = candidate.build_property_bundle("VIG35", [], tmp_path)
    payload = json.loads((bundle / "NOTION_PAYLOAD.json").read_text(encoding="utf-8"))
    assert payload["gate"] == "RECONCILIATION_CONTRACT_PENDING"


def test_build_property_bundle_writes_the_full_inspectable_bundle_shape(tmp_path):
    bundle = candidate.build_property_bundle("GERMIGNAGA", _claims(), tmp_path)
    assert bundle == tmp_path / "entities" / "GERMIGNAGA"
    for name in ("entity.json", "claims.json", "sources.json", "notion_match.json",
                 "verification.json", "NOTION_PAYLOAD.json", "EVIDENCE.md"):
        assert (bundle / name).is_file(), name
    entity = json.loads((bundle / "entity.json").read_text(encoding="utf-8"))
    assert entity == {"entity_type": "IMMOBILE", "name": "GERMIGNAGA"}


def test_build_property_bundle_records_no_notion_match_for_a_new_entity(tmp_path):
    """notion_match.json must say NEW_ENTITY, i.e. no live comparison was made."""
    bundle = candidate.build_property_bundle("GERMIGNAGA", _claims(), tmp_path)
    match = json.loads((bundle / "notion_match.json").read_text(encoding="utf-8"))
    assert match == {"status": "NEW_ENTITY"}


def test_build_property_bundle_never_writes_a_notion_patch(tmp_path):
    """NOTION_PATCH.json is what gmv_notion_publish.load_bundle requires before it
    even looks at the gate -- a second, independent code-level block."""
    bundle = candidate.build_property_bundle("GERMIGNAGA", _claims(), tmp_path)
    assert not (bundle / "NOTION_PATCH.json").exists()
    assert not (bundle / "PATCH.json").exists()


def test_publish_bundle_refuses_a_property_bundle_before_touching_credentials(tmp_path, monkeypatch):
    """The safety guarantee, proven against the real publisher: a bundle built by
    build_property_bundle can never be published, and no Notion token is even
    looked for on the way to that refusal."""
    import gmv_notion_publish as notion_publish

    def _fail_if_credential_is_read(*a, **k):
        raise AssertionError("credentials must never be read for a blocked bundle")

    monkeypatch.setattr(notion_publish.credentials, "get_token", _fail_if_credential_is_read)
    bundle = candidate.build_property_bundle("GERMIGNAGA", _claims(), tmp_path)
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")
    # load_bundle() rejects first (no NOTION_PATCH.json); if a patch were ever
    # added, the gate check below is what rejects it, with return code 4.
    with pytest.raises(FileNotFoundError):
        notion_publish.publish_bundle(bundle, config_path=config)

    (bundle / "NOTION_PATCH.json").write_text(
        json.dumps({"operation": "CREATE", "operations": [], "existing_notion_id": None}),
        encoding="utf-8")
    assert notion_publish.publish_bundle(bundle, config_path=config) == 4


def test_candidate_cli_writes_bundle_and_reports_the_blocked_gate(tmp_path, capsys):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"property_id": "GERMIGNAGA", "consolidated": _claims()},
                                 ensure_ascii=False), encoding="utf-8")
    run_dir = tmp_path / "run"
    assert candidate.main(["candidate", str(result), "--run-dir", str(run_dir)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["property_id"] == "GERMIGNAGA"
    assert out["gate"] == "RECONCILIATION_CONTRACT_PENDING"
    assert out["consolidated_claims"] == 1
    payload = json.loads((run_dir / "entities" / "GERMIGNAGA" / "NOTION_PAYLOAD.json").read_text(encoding="utf-8"))
    assert payload["gate"] == "RECONCILIATION_CONTRACT_PENDING"


def test_build_property_bundle_evidence_markdown_does_not_advertise_a_ready_gate(tmp_path):
    """write_evidence_bundle renders EVIDENCE.md from the gate IT computed, before
    any override -- so without an explicit correction the human-readable summary
    says READY_FOR_NOTION while NOTION_PAYLOAD.json one directory over says the
    bundle is blocked. Found by inspecting a real GERMIGNAGA bundle."""
    bundle = candidate.build_property_bundle("GERMIGNAGA", _claims(), tmp_path)
    markdown = (bundle / "EVIDENCE.md").read_text(encoding="utf-8")
    assert "READY_FOR_NOTION" not in markdown
    assert "Gate: `RECONCILIATION_CONTRACT_PENDING`" in markdown


def test_evidence_markdown_gate_is_corrected_for_an_empty_claim_list_too(tmp_path):
    bundle = candidate.build_property_bundle("VIG35", [], tmp_path)
    assert "Gate: `RECONCILIATION_CONTRACT_PENDING`" in (bundle / "EVIDENCE.md").read_text(encoding="utf-8")


def test_rewrite_markdown_gate_raises_instead_of_silently_leaving_a_stale_gate(tmp_path):
    """A missing gate line must never be a silent no-op -- that is precisely the
    case that would leave the bundle advertising a publishable state."""
    markdown = tmp_path / "EVIDENCE.md"
    markdown.write_text("# Evidence — X\n\n## Claims\n", encoding="utf-8")
    with pytest.raises(ValueError):
        candidate._rewrite_markdown_gate(markdown, "RECONCILIATION_CONTRACT_PENDING")


# --- render_property_page_markdown() ----------------------------------------

def _claim(predicate, subject="S", obj="O", pagina=None):
    qualifiers = {"pagina": pagina} if pagina else {}
    return {"claim_id": f"claim:{predicate}", "subject": subject, "predicate": predicate,
            "object": obj, "qualifiers": qualifiers, "source_file_ids": ["sha256:1"],
            "source_excerpts": ["e"], "status": "SUPPORTED_BY_ARCHIVE"}


def test_render_places_fiscal_predicate_in_obblighi_fiscali_section():
    markdown = candidate.render_property_page_markdown("GERMIGNAGA", [_claim("ha_tipo_tributo", obj="TARI")])
    sections = markdown.split("## ")
    fiscal = next(s for s in sections if s.startswith("Obblighi fiscali"))
    assert "TARI" in fiscal
    lease = next(s for s in sections if s.startswith("Contratti e locazioni"))
    assert "Nessun fatto governato" in lease


def test_render_places_lease_predicate_in_contratti_section():
    markdown = candidate.render_property_page_markdown("VIG35", [_claim("ha_decorrenza", obj="2021-09-01")])
    sections = markdown.split("## ")
    lease = next(s for s in sections if s.startswith("Contratti e locazioni"))
    assert "2021-09-01" in lease


def test_render_utenze_section_is_always_present_and_always_empty():
    markdown = candidate.render_property_page_markdown("GERMIGNAGA", [_claim("ha_tipo_tributo")])
    assert "## Utenze e bollette" in markdown
    assert "strutturalmente vuota" in markdown


def test_render_unmapped_predicate_falls_into_altri_fatti_not_dropped():
    markdown = candidate.render_property_page_markdown("GERMIGNAGA", [_claim("un_predicato_futuro", obj="X")])
    assert "Altri fatti" in markdown
    assert "un_predicato_futuro" in markdown
    assert "X" in markdown


def test_render_empty_claims_still_produces_all_sections_marked_empty():
    markdown = candidate.render_property_page_markdown("GERMIGNAGA", [])
    for title, _ in candidate.PAGE_SECTIONS:
        assert f"## {title}" in markdown
    assert markdown.count("Nessun fatto governato") == len(candidate.PAGE_SECTIONS)


def test_render_returns_a_plain_string_no_side_effects():
    markdown = candidate.render_property_page_markdown("GERMIGNAGA", [_claim("ha_tipo_tributo")])
    assert isinstance(markdown, str) and markdown.startswith("# GERMIGNAGA")


def test_render_cli_writes_to_output_file(tmp_path, capsys):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"property_id": "GERMIGNAGA", "consolidated": [_claim("ha_tipo_tributo", obj="TARI")]}),
                      encoding="utf-8")
    out_path = tmp_path / "page.md"
    assert candidate.main(["render", str(result), "-o", str(out_path)]) == 0
    assert "TARI" in out_path.read_text(encoding="utf-8")
    assert capsys.readouterr().out == ""


def test_render_cli_prints_to_stdout_by_default(tmp_path, capsys):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"property_id": "GERMIGNAGA", "consolidated": [_claim("ha_tipo_tributo", obj="TARI")]}),
                      encoding="utf-8")
    assert candidate.main(["render", str(result)]) == 0
    assert "TARI" in capsys.readouterr().out
