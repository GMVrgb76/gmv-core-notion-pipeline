import importlib.util
import json
import sys
from pathlib import Path

import pytest

API_DIR = Path(__file__).parents[1] / "10_API"
sys.path.insert(0, str(API_DIR))

SPEC = importlib.util.spec_from_file_location("extract_templates", API_DIR / "gmv_property_extract_templates.py")
extract_templates = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(extract_templates)

import gmv_evidence_pipeline as evidence  # noqa: E402

REGISTRY_PATH = Path(__file__).parents[1] / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_REALESTATE_v0.1.json"


@pytest.fixture
def registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_build_fact_template_predicate_enum_matches_registry_exactly(registry):
    """The model can only ever emit a predicate that's in this enum -- an
    ungoverned predicate must be structurally unreachable, not just filtered
    out after the fact."""
    template = extract_templates.build_fact_template(registry)
    fact_shape = template["fatti"][0]
    expected = sorted(p["predicate_id"] for p in registry["predicates"])
    assert fact_shape["predicato"] == expected


def test_build_fact_template_ambito_enum_from_registry(registry):
    template = extract_templates.build_fact_template(registry)
    assert template["fatti"][0]["ambito"] == registry["proposed_vocabulary_v0_1"]["ambito_enum"]


def test_build_fact_template_falls_back_to_default_ambito_enum_when_missing():
    registry = {"predicates": [{"predicate_id": "ha_tipo_documento"}]}
    template = extract_templates.build_fact_template(registry)
    assert template["fatti"][0]["ambito"] == extract_templates.DEFAULT_AMBITO_ENUM


def test_build_fact_template_all_mandatory_envelope_fields_present(registry):
    fact_shape = extract_templates.build_fact_template(registry)["fatti"][0]
    for field in ("soggetto", "predicato", "oggetto", "valuta", "ambito", "pagina",
                  "testo_evidenza", "data_documento", "competenza_da", "competenza_a", "stato_evidenza"):
        assert field in fact_shape


class _FakeHTTPResponse:
    def __init__(self, payload): self._body = json.dumps(payload).encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, *a): return self._body


def _record(file_id="sha256:f"):
    return {"file_id": file_id, "extraction_status": "SUCCESS", "text": "hello"}


def test_extract_facts_keeps_governed_facts_and_rejects_ungoverned(monkeypatch, registry):
    body = {"fatti": [
        {"soggetto": "Comune di Germignaga", "predicato": "ha_tipo_tributo", "oggetto": "TARI", "testo_evidenza": "TARI 2026"},
        {"soggetto": "X", "predicato": "predicato_non_esistente", "oggetto": "Y", "testo_evidenza": "z"},
    ]}
    def fake_urlopen(request, timeout=None):
        return _FakeHTTPResponse({"message": {"role": "assistant", "content": json.dumps(body)}, "done_reason": "stop"})
    monkeypatch.setattr(evidence.urllib.request, "urlopen", fake_urlopen)
    out = extract_templates.extract_facts(_record(), registry, endpoint="http://localhost:11434")
    assert len(out["facts"]) == 1
    assert out["facts"][0]["predicato"] == "ha_tipo_tributo"
    assert len(out["rejected_facts"]) == 1
    assert out["rejected_facts"][0]["predicato"] == "predicato_non_esistente"
    assert out["file_id"] == "sha256:f"


def test_extract_facts_rejects_non_dict_fact_entries(monkeypatch, registry):
    body = {"fatti": ["not a dict", 42, None]}
    def fake_urlopen(request, timeout=None):
        return _FakeHTTPResponse({"message": {"role": "assistant", "content": json.dumps(body)}, "done_reason": "stop"})
    monkeypatch.setattr(evidence.urllib.request, "urlopen", fake_urlopen)
    out = extract_templates.extract_facts(_record(), registry, endpoint="http://localhost:11434")
    assert out["facts"] == []
    assert len(out["rejected_facts"]) == 3


def test_extract_facts_handles_missing_fatti_key(monkeypatch, registry):
    def fake_urlopen(request, timeout=None):
        return _FakeHTTPResponse({"message": {"role": "assistant", "content": json.dumps({})}, "done_reason": "stop"})
    monkeypatch.setattr(evidence.urllib.request, "urlopen", fake_urlopen)
    out = extract_templates.extract_facts(_record(), registry, endpoint="http://localhost:11434")
    assert out["facts"] == [] and out["rejected_facts"] == []


def test_extract_facts_passes_num_predict_and_repeat_penalty_through(monkeypatch, registry):
    captured = {}
    def fake_urlopen(request, timeout=None):
        captured["payload"] = json.loads(request.data)
        return _FakeHTTPResponse({"message": {"role": "assistant", "content": json.dumps({"fatti": []})}, "done_reason": "stop"})
    monkeypatch.setattr(evidence.urllib.request, "urlopen", fake_urlopen)
    extract_templates.extract_facts(_record(), registry, endpoint="http://localhost:11434")
    options = captured["payload"]["options"]
    assert options["num_predict"] == 4096  # extract_facts()'s own higher default, not nuextract_extract()'s 2048
    assert options["repeat_penalty"] == 1.1


def test_fact_to_raw_claim_maps_mandatory_fields():
    fact = {"soggetto": "Comune di Germignaga", "predicato": "ha_importo_dovuto", "oggetto": "222,00€",
            "testo_evidenza": "Totale da pagare 222,00€", "valuta": "EUR", "pagina": 2, "stato_evidenza": "esplicito"}
    claim = extract_templates.fact_to_raw_claim(fact, "sha256:f")
    assert claim == {
        "file_id": "sha256:f",
        "subject_raw": "Comune di Germignaga",
        "predicate": "ha_importo_dovuto",
        "object_raw": "222,00€",
        "evidence_excerpt": "Totale da pagare 222,00€",
        "status": "SUPPORTED_BY_ARCHIVE",
        "qualifiers": {"valuta": "EUR", "pagina": 2},
    }


def test_fact_to_raw_claim_inferito_maps_to_inferred_status():
    fact = {"soggetto": "A", "predicato": "p", "oggetto": "B", "testo_evidenza": "e", "stato_evidenza": "inferito"}
    claim = extract_templates.fact_to_raw_claim(fact, "sha256:f")
    assert claim["status"] == "INFERRED"


@pytest.mark.parametrize("missing", ["soggetto", "predicato", "oggetto", "testo_evidenza"])
def test_fact_to_raw_claim_returns_none_when_mandatory_field_missing(missing):
    fact = {"soggetto": "A", "predicato": "p", "oggetto": "B", "testo_evidenza": "e"}
    fact[missing] = None
    assert extract_templates.fact_to_raw_claim(fact, "sha256:f") is None


def test_fact_to_raw_claim_omits_null_and_empty_qualifier_fields():
    fact = {"soggetto": "A", "predicato": "p", "oggetto": "B", "testo_evidenza": "e",
            "valuta": None, "ambito": "", "pagina": 3}
    claim = extract_templates.fact_to_raw_claim(fact, "sha256:f")
    assert claim["qualifiers"] == {"pagina": 3}


def test_facts_to_raw_claims_drops_none_results():
    facts = [
        {"soggetto": "A", "predicato": "p", "oggetto": "B", "testo_evidenza": "e"},
        {"soggetto": "A", "predicato": "p", "oggetto": None, "testo_evidenza": "e"},
    ]
    claims = extract_templates.facts_to_raw_claims(facts, "sha256:f")
    assert len(claims) == 1
    assert claims[0]["subject_raw"] == "A"
