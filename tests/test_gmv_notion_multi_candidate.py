import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "10_API"))
import gmv_notion_multi_candidate as multi

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
