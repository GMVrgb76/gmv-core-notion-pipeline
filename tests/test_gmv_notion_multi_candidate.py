import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))
import gmv_notion_multi_candidate as multi
import gmv_notion_publish as gnp

PAGE_TEMPLATES = {
    "generation_priority": ["artista", "mostra", "persona"],
    "entita": {
        "artista": {
            "struttura_pagina": [{"titolo": "DOCUMENTAZIONE", "formato": "testo"}],
            "field_hints": {},
            "relation_hints": {"mostre": [{"predicate": "is the author of", "anchor": "object"}]},
        },
        "mostra": {
            "struttura_pagina": [{"titolo": "DOCUMENTAZIONE", "formato": "testo"}],
            "field_hints": {},
            "relation_hints": {"artisti": [{"predicate": "is the author of", "anchor": "subject"}]},
        },
        "persona": {
            "struttura_pagina": [{"titolo": "EVIDENZE E FONTI", "formato": "testo"}],
            "field_hints": {}, "relation_hints": {},
        },
    },
    "discovery_hints": {
        "mostra": [{"predicate": "is the author of", "anchor": "object"}],
        "persona": [{"predicate": "is the author of the text for", "anchor": "subject"}],
    },
}

CLAIMS = [
    {"claim_id": "c1", "subject": "Riccardo Paternò Castello", "predicate": "is the author of",
     "object": "De Profundis", "status": "CONFIRMED", "source_file_ids": ["sha256:a"]},
    {"claim_id": "c2", "subject": "Myriam Zerbi", "predicate": "is the author of the text for",
     "object": "the exhibition", "status": "CONFIRMED", "source_file_ids": ["sha256:a"]},
    {"claim_id": "c3", "subject": "Riccardo Paternò Castello", "predicate": "was born in",
     "object": "Catania in 1980", "status": "CONFIRMED", "source_file_ids": ["sha256:b"]},
]

ROWS = {"artista": [], "mostra": [], "persona": [], "istituzione": [], "opera": [], "sponsor": []}


def test_discover_entities_known_vs_hinted_vs_no_signal():
    rows = {**ROWS, "mostra": [{"id": "n1", "titolo": "De Profundis"}]}
    discovered = multi.discover_entities(CLAIMS, rows, PAGE_TEMPLATES, "Riccardo Paternò Castello")
    by_name = {d["name"]: d for d in discovered}
    assert by_name["De Profundis"]["type_source"] == "matched_existing_row"
    assert by_name["De Profundis"]["entity_type"] == "mostra"
    assert by_name["Myriam Zerbi"]["type_source"] == "hinted_not_confirmed"
    assert by_name["Myriam Zerbi"]["entity_type"] == "persona"
    assert by_name["Catania in 1980"]["type_source"] == "no_signal"
    assert by_name["Catania in 1980"]["generate"] is False


def test_hint_is_anchor_aware_not_substring_confused():
    """'is the author of' must not also fire on the longer, distinct predicate
    'is the author of the text for' via substring matching."""
    discovered = multi.discover_entities(CLAIMS, ROWS, PAGE_TEMPLATES, "Riccardo Paternò Castello")
    by_name = {d["name"]: d for d in discovered}
    assert by_name["the exhibition"]["type_source"] == "no_signal"
    assert by_name["De Profundis"]["entity_type"] == "mostra"
    assert by_name["Myriam Zerbi"]["entity_type"] == "persona"


def test_route_claim_relation_uses_declared_anchor():
    artista_route = multi.route_claim(CLAIMS[0], "artista", PAGE_TEMPLATES, ROWS, {})
    assert artista_route["layer"] == "relation" and artista_route["target"]["pending_entity"] == "De Profundis"
    mostra_route = multi.route_claim(CLAIMS[0], "mostra", PAGE_TEMPLATES, ROWS, {})
    assert mostra_route["layer"] == "relation" and mostra_route["target"]["pending_entity"] == "Riccardo Paternò Castello"


def test_route_claim_no_match_falls_through_to_body():
    route = multi.route_claim(CLAIMS[2], "artista", PAGE_TEMPLATES, ROWS, {})
    assert route["layer"] == "body"


def test_run_multi_candidate_generates_mutual_pending_relations(tmp_path):
    output = multi.run_multi_candidate(CLAIMS, ROWS, {"entita": {}}, PAGE_TEMPLATES,
                                       "Riccardo Paternò Castello", "artista", tmp_path)
    by_type = {(e["entity_type"], e["name"]) for e in output["entities"]}
    assert ("artista", "Riccardo Paternò Castello") in by_type
    assert ("mostra", "De Profundis") in by_type
    assert ("persona", "Myriam Zerbi") in by_type
    assert len(output["entities"]) == 3

    import json
    artista_patch = json.loads((tmp_path / "entities" / "artista__Riccardo_Patern_Castello" / "PATCH.json").read_text())
    mostra_patch = json.loads((tmp_path / "entities" / "mostra__De_Profundis" / "PATCH.json").read_text())
    assert artista_patch["operations"][0]["target"]["pending_entity"] == "De Profundis"
    assert artista_patch["operations"][0]["target"]["pending_type"] == "mostra"
    assert mostra_patch["operations"][0]["target"]["pending_entity"] == "Riccardo Paternò Castello"
    assert mostra_patch["operations"][0]["target"]["pending_type"] == "artista"


FIELD_TEMPLATES = {
    "generation_priority": ["mostra"],
    "entita": {
        "mostra": {
            "struttura_pagina": [{"titolo": "DOCUMENTAZIONE", "formato": "testo"}],
            "field_hints": {"is located in": "luogo"},
            "relation_hints": {},
        },
    },
    "discovery_hints": {},
}

FIELD_CLAIM = {"claim_id": "c1", "subject": "De Profundis", "predicate": "is located in",
               "object": "Roma", "status": "CONFIRMED", "source_file_ids": ["sha256:a"]}

FIELD_CONFIG = {"entita": {"mostra": {"campi": {"luogo": {"notion": "Luogo"}}, "relazioni": {}}}}


def test_build_entity_patch_adds_field_when_existing_value_is_empty():
    rows = {"mostra": [{"id": "n1", "titolo": "De Profundis", "campi": {"luogo": ""}}]}
    patch = multi.build_entity_patch("De Profundis", "mostra", [FIELD_CLAIM], rows, FIELD_CONFIG, FIELD_TEMPLATES, {})
    assert patch["operation"] == "UPDATE"
    assert patch["operations"] == [{"action": "ADD", "claim_id": "c1", "property": "Luogo", "value": "Roma"}]


def test_build_entity_patch_keeps_field_silently_when_value_already_matches():
    rows = {"mostra": [{"id": "n1", "titolo": "De Profundis", "campi": {"luogo": "Roma"}}]}
    patch = multi.build_entity_patch("De Profundis", "mostra", [FIELD_CLAIM], rows, FIELD_CONFIG, FIELD_TEMPLATES, {})
    assert patch["operations"] == []


def test_build_entity_patch_flags_conflict_instead_of_silently_overwriting_a_different_value():
    rows = {"mostra": [{"id": "n1", "titolo": "De Profundis", "campi": {"luogo": "Milano"}}]}
    patch = multi.build_entity_patch("De Profundis", "mostra", [FIELD_CLAIM], rows, FIELD_CONFIG, FIELD_TEMPLATES, {})
    assert patch["operations"] == [{"action": "CONFLICT", "claim_id": "c1", "property": "Luogo",
                                    "reason": "FIELD_VALUE_MISMATCH"}]


def test_build_entity_patch_flags_conflict_when_field_not_defined_in_config():
    """config.json is the only source of truth for a real Notion property
    name; if it doesn't define this campo for this entity_type, the claim
    must never be silently dropped nor guessed at -- it becomes an
    inspectable CONFLICT."""
    rows = {"mostra": [{"id": "n1", "titolo": "De Profundis", "campi": {}}]}
    patch = multi.build_entity_patch("De Profundis", "mostra", [FIELD_CLAIM], rows, {"entita": {}}, FIELD_TEMPLATES, {})
    assert patch["operations"] == [{"action": "CONFLICT", "claim_id": "c1",
                                    "reason": "FIELD_NOT_IN_ENTITY_SCHEMA"}]


RELATION_CONFIG = {"entita": {
    "artista": {"campi": {}, "relazioni": {"mostre": {"notion": "Mostre"}}},
    "mostra": {"campi": {}, "relazioni": {}},
}}


def test_build_entity_patch_relation_is_conflict_when_target_unresolved():
    """No relation-writer exists anywhere in this codebase: an unresolved
    relation target must never become anything but CONFLICT."""
    patch = multi.build_entity_patch("Riccardo Paternò Castello", "artista", [CLAIMS[0]],
                                     ROWS, RELATION_CONFIG, PAGE_TEMPLATES, {})
    assert patch["operations"] == [{"action": "CONFLICT", "claim_id": "c1", "property": "Mostre",
                                    "relation": "mostre", "reason": "RELATION_TARGET_ID_NOT_RESOLVED",
                                    "target": {"resolved": False, "pending_entity": "De Profundis",
                                               "pending_type": None}}]


def test_build_entity_patch_relation_stays_conflict_even_when_target_is_resolved():
    """A resolved relation target (a real Notion row already exists) still
    must not become ADD/UPDATE/RELATE -- writing a relation property safely
    requires a merge against the existing list, which nothing implements yet."""
    rows = {**ROWS, "mostra": [{"id": "n1", "titolo": "De Profundis"}]}
    patch = multi.build_entity_patch("Riccardo Paternò Castello", "artista", [CLAIMS[0]],
                                     rows, RELATION_CONFIG, PAGE_TEMPLATES, {})
    assert patch["operations"][0]["action"] == "CONFLICT"
    assert patch["operations"][0]["reason"] == "RELATION_WRITE_NOT_SUPPORTED"
    assert patch["operations"][0]["target"]["resolved"] is True


def test_build_entity_patch_relation_conflict_when_not_defined_in_config():
    patch = multi.build_entity_patch("Riccardo Paternò Castello", "artista", [CLAIMS[0]],
                                     ROWS, {"entita": {}}, PAGE_TEMPLATES, {})
    assert patch["operations"][0]["property"] is None
    assert patch["operations"][0]["reason"] == "RELATION_NOT_IN_ENTITY_SCHEMA"


def test_build_entity_patch_keep_uses_real_property_names_from_existing_row():
    rows = {"mostra": [{"id": "n1", "titolo": "De Profundis", "campi": {"luogo": "Roma"},
                        "relazioni": {}}]}
    patch = multi.build_entity_patch("De Profundis", "mostra", [], rows, FIELD_CONFIG, FIELD_TEMPLATES, {})
    assert patch["keep"] == {"properties": {"Luogo": "Roma"}, "relations": {}}


def test_write_entity_bundle_produces_a_notion_publish_compatible_bundle(tmp_path):
    patch = multi.build_entity_patch("De Profundis", "mostra",
                                     [FIELD_CLAIM], {"mostra": []}, FIELD_CONFIG, FIELD_TEMPLATES, {})
    bundle = multi.write_entity_bundle(tmp_path, patch, "## S\n- item", [FIELD_CLAIM])
    assert (bundle / "NOTION_PATCH.json").is_file()
    assert (bundle / "NOTION_PAYLOAD.json").is_file()
    import json
    notion_patch = json.loads((bundle / "NOTION_PATCH.json").read_text())
    assert notion_patch["operation"] == "CREATE"
    assert notion_patch["body"]["proposed_markdown"] == "## S\n- item"
    payload = json.loads((bundle / "NOTION_PAYLOAD.json").read_text())
    assert payload["gate"] == patch["gate"]


def test_build_entity_patch_decides_create_when_no_existing_row():
    patch = multi.build_entity_patch("De Profundis", "mostra", [], {"mostra": []}, {"entita": {}}, FIELD_TEMPLATES, {})
    assert patch["operation"] == "CREATE"
    assert patch["existing_notion_id"] is None


def test_build_entity_patch_decides_update_when_a_single_existing_row_matches():
    rows = {"mostra": [{"id": "n1", "titolo": "De Profundis", "campi": {}}]}
    patch = multi.build_entity_patch("De Profundis", "mostra", [], rows, {"entita": {}}, FIELD_TEMPLATES, {})
    assert patch["operation"] == "UPDATE"
    assert patch["existing_notion_id"] == "n1"


def test_build_entity_patch_never_decides_create_when_ambiguous():
    """Two existing rows with the same title must never fall through to
    'existing is None -> CREATE', which would risk a duplicate Notion page."""
    rows = {"mostra": [{"id": "n1", "titolo": "De Profundis"}, {"id": "n2", "titolo": "De Profundis"}]}
    patch = multi.build_entity_patch("De Profundis", "mostra", [], rows, {"entita": {}}, FIELD_TEMPLATES, {})
    assert patch["notion_status"] == "AMBIGUOUS"
    assert patch["operation"] is None
    assert patch["gate"] == "REVIEW_REQUIRED"


def test_multi_candidate_bundle_is_loadable_by_the_real_publish_command_unmodified(tmp_path):
    """The actual point of this integration: a bundle produced by
    write_entity_bundle() must be readable by gmv_notion_publish.load_bundle()
    -- the same, untouched function the single-entity path already publishes
    through -- with no special-casing added to gmv_notion_publish.py."""
    patch = multi.build_entity_patch("De Profundis", "mostra", [], {"mostra": []},
                                     FIELD_CONFIG, FIELD_TEMPLATES, {})
    assert patch["gate"] == "READY_FOR_NOTION"
    bundle_dir = multi.write_entity_bundle(tmp_path, patch, "## S\n- item", [])
    bundle = gnp.load_bundle(bundle_dir)
    assert bundle.entity_name == "De Profundis"
    assert bundle.patch["operation"] == "CREATE"
    assert bundle.body_markdown == "## S\n- item"


def test_sponsor_skipped_without_required_link(tmp_path):
    """A sponsor card is meaningless on its own (per the real template: it
    must reference an already-linked persona/istituzione); with no such
    relation resolved this run, generation must be skipped, not attempted."""
    templates = {**PAGE_TEMPLATES, "generation_priority": ["artista", "sponsor"],
                "entita": {**PAGE_TEMPLATES["entita"],
                           "sponsor": {"struttura_pagina": [], "field_hints": {}, "relation_hints": {},
                                      "requires_existing_link": ["persona", "istituzione"]}}}
    rows = {**ROWS, "sponsor": [{"id": "s1", "titolo": "Banca Azimut"}]}
    claims = CLAIMS + [{"claim_id": "c4", "subject": "Riccardo Paternò Castello", "predicate": "sponsored by",
                        "object": "Banca Azimut", "status": "CONFIRMED", "source_file_ids": ["sha256:c"]}]
    output = multi.run_multi_candidate(claims, rows, {"entita": {}}, templates,
                                       "Riccardo Paternò Castello", "artista", tmp_path)
    sponsor_result = next(e for e in output["entities"] if e["entity_type"] == "sponsor")
    assert sponsor_result["skipped"] == "REQUIRES_EXISTING_LINK_NOT_FOUND"
    assert "bundle" not in sponsor_result
