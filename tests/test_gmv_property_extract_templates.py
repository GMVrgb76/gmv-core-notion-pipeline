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


# --- property_facts_batch() -- mirrors gmv_evidence_pipeline's own
# semantic_extract_batch() test suite (test_adaptive_split_recursive_and_provenance,
# test_adaptive_minimum_exhausted, test_analyze_writes_semantic_output_and_marks_valid,
# test_analyze_resume_skips_valid_files_without_ollama, test_analyze_retry_limit_then_failed)
# field-for-field, since the function itself is a deliberate structural mirror.

def _fake_extract_facts_fixed(record, registry, **kwargs):
    return {"file_id": record["file_id"], "facts": [{"soggetto": "A", "predicato": "p", "oggetto": "o", "testo_evidenza": "e"}],
            "rejected_facts": [], "truncated_source": False, "_runtime": {"done_reason": "stop"}}


def test_property_facts_batch_writes_output_and_marks_valid(monkeypatch, tmp_path, registry):
    monkeypatch.setattr(extract_templates, "extract_facts", _fake_extract_facts_fixed)
    record = {"file_id": "sha256:abc123", "extraction_status": "SUCCESS", "text": "some text"}
    out = extract_templates.property_facts_batch([record], registry, tmp_path, property_id="GERMIGNAGA", endpoint="x", model="m")
    out_path = tmp_path / "property_facts" / "abc123-0.1.json"
    assert out_path.exists()
    data = evidence.read_json(out_path, None)
    assert data["facts"] == out["facts"]
    assert data["facts"][0]["soggetto"] == "A"
    manifest = extract_templates.load_property_facts_manifest(tmp_path)
    assert manifest["sha256:abc123"]["status"] == "valid"
    assert manifest["sha256:abc123"]["property_id"] == "GERMIGNAGA"
    run_manifest = evidence.read_json(tmp_path / "property_facts" / "run_manifest.json", {})
    assert run_manifest["status"] == "SUCCESS"


def test_property_facts_batch_resume_skips_valid_files(monkeypatch, tmp_path, registry):
    def _raise_if_called(record, registry, **kwargs):
        raise AssertionError("extract_facts must not be called on resumed file")
    extract_templates.mark_property_facts_analyzed(tmp_path, "sha256:abc123", "valid", property_id="GERMIGNAGA", model="m", timeout=60)
    out_path = tmp_path / "property_facts" / "abc123-0.1.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sentinel = {"facts": [{"soggetto": "SENTINEL"}], "rejected_facts": []}
    out_path.write_text(evidence.canonical(sentinel) + "\n", encoding="utf-8")
    monkeypatch.setattr(extract_templates, "extract_facts", _raise_if_called)
    record = {"file_id": "sha256:abc123", "extraction_status": "SUCCESS", "text": "some text"}
    out = extract_templates.property_facts_batch([record], registry, tmp_path, property_id="GERMIGNAGA", endpoint="x", model="m", resume=True)
    assert out_path.read_text(encoding="utf-8").strip() == evidence.canonical(sentinel).strip()
    manifest = extract_templates.load_property_facts_manifest(tmp_path)
    assert manifest["sha256:abc123"]["status"] == "valid"
    assert out == {"facts": [], "rejected_facts": []}


def test_property_facts_batch_retry_limit_then_failed(monkeypatch, tmp_path, registry):
    calls = []
    def _flaky(record, registry, **kwargs):
        calls.append(record)
        if len(calls) < 3:
            raise evidence.EvidenceError("TIMEOUT")
        return {"file_id": record["file_id"], "facts": [], "rejected_facts": [], "truncated_source": False, "_runtime": {"done_reason": "stop"}}
    monkeypatch.setattr(extract_templates, "extract_facts", _flaky)
    record = {"file_id": "sha256:abc123", "extraction_status": "SUCCESS", "text": "some text"}
    extract_templates.property_facts_batch([record], registry, tmp_path, property_id="GERMIGNAGA", endpoint="x", model="m", retry_limit=3)
    assert len(calls) == 3
    manifest = extract_templates.load_property_facts_manifest(tmp_path)
    assert manifest["sha256:abc123"]["status"] == "valid"

    calls2 = []
    def _always_timeout(record, registry, **kwargs):
        calls2.append(record)
        raise evidence.EvidenceError("TIMEOUT")
    monkeypatch.setattr(extract_templates, "extract_facts", _always_timeout)
    record2 = {"file_id": "sha256:def456", "extraction_status": "SUCCESS", "text": "some text"}
    with pytest.raises(evidence.EvidenceError) as exc_info:
        extract_templates.property_facts_batch([record2], registry, tmp_path, property_id="GERMIGNAGA", endpoint="x", model="m", retry_limit=2)
    assert str(exc_info.value) == "TIMEOUT"
    assert len(calls2) == 2
    manifest2 = extract_templates.load_property_facts_manifest(tmp_path)
    assert manifest2["sha256:def456"]["status"] == "failed"


def test_property_facts_batch_adaptive_split_on_truncation(monkeypatch, tmp_path, registry):
    def fake(record, registry, **kwargs):
        if len(record["text"]) > 3000:
            raise evidence.OllamaResponseError("OLLAMA_OUTPUT_TRUNCATED", runtime={"done_reason": "length", "eval_count": 2048}, raw_output="x")
        return {"file_id": record["file_id"], "facts": [{"soggetto": "A", "predicato": "p", "oggetto": "o", "testo_evidenza": "e"}],
                "rejected_facts": [], "truncated_source": False, "_runtime": {"done_reason": "stop", "eval_count": 2}}
    monkeypatch.setattr(extract_templates, "extract_facts", fake)
    record = {"file_id": "sha256:f", "extraction_status": "SUCCESS", "text": "A. " * 2500}
    out = extract_templates.property_facts_batch([record], registry, tmp_path, property_id="P", endpoint="x", model="m",
                                                   max_chunk_chars=8000, min_adaptive_chunk_chars=2000, max_adaptive_depth=4)
    manifest = evidence.read_json(tmp_path / "property_facts" / "run_manifest.json", {})
    leaves = [n for n in manifest["nodes"] if n["outcome"] == "SUCCESS"]
    assert len(leaves) > 2 and all(n["input_chars"] <= 8000 for n in leaves)
    assert len(out["facts"]) == len(leaves)


def test_property_facts_batch_adaptive_minimum_exhausted(monkeypatch, tmp_path, registry):
    def truncated(record, registry, **kwargs):
        raise evidence.OllamaResponseError("OLLAMA_OUTPUT_TRUNCATED", runtime={"done_reason": "length", "eval_count": 2048}, raw_output="x")
    monkeypatch.setattr(extract_templates, "extract_facts", truncated)
    record = {"file_id": "sha256:f", "extraction_status": "SUCCESS", "text": "x" * 600}
    with pytest.raises(evidence.EvidenceError) as exc_info:
        extract_templates.property_facts_batch([record], registry, tmp_path, property_id="P", endpoint="x", model="m",
                                                 max_chunk_chars=8000, min_adaptive_chunk_chars=500)
    assert str(exc_info.value) == "ADAPTIVE_CHUNK_MINIMUM_EXHAUSTED"


def test_property_facts_output_path_rejects_malformed_file_id(tmp_path):
    assert extract_templates.property_facts_output_path(None, tmp_path) is None
    assert extract_templates.property_facts_output_path("not-a-sha", tmp_path) is None
    assert extract_templates.property_facts_output_path("md5:abc", tmp_path) is None


# --- is_generic_regulatory_reference() -- real paths/markers from the
# 2020_PROGETTO_CRISTIANO_RINALDI/02_NORMA/ VIG35 documents that motivated this
# gate (2026-09-29): these produced ~1/4 of all consolidated VIG35 claims as
# noise once chunking let them succeed instead of failing outright.

def test_gate_flags_via_path_token_norma_folder():
    record = {"text": "testo qualsiasi senza marcatori"}
    paths = ["06_PROGETTI_EDILIZI/2020_PROGETTO_CRISTIANO RINALDI/02_NORMA/2020_12_25_NTA.pdf"]
    assert extract_templates.is_generic_regulatory_reference(record, paths=paths) is True


def test_gate_flags_via_content_marker_without_path_hint():
    record = {"text": "Estratto dalle Norme Tecniche di Attuazione del Piano delle Regole vigente."}
    assert extract_templates.is_generic_regulatory_reference(record) is True


def test_gate_fails_open_on_property_specific_document():
    record = {"text": "Comune di Germignaga - AVVISO DI PAGAMENTO TARI - ANNO 2026 - Totale da pagare 222,00€"}
    paths = ["03_FISCALE/2026_tari_germignaga.pdf"]
    assert extract_templates.is_generic_regulatory_reference(record, paths=paths) is False


def test_gate_case_insensitive_content_match():
    record = {"text": "PGT Milano. PR_Tavola R03. PIANO DELLE REGOLE - indicazioni morfologiche"}
    assert extract_templates.is_generic_regulatory_reference(record) is True


def test_gate_does_not_flag_a_passing_mention_deep_in_a_real_document():
    """Regression guard for two real GERMIGNAGA false positives found live
    2026-09-29: a file-listing PDF whose text happened to include another
    file's name containing 'piano delle regole', and a building-permit
    declaration form with a passing checkbox mention of the same phrase --
    both property-specific documents, marker only appears deep in the body."""
    filler = "x" * 600
    record = {"text": filler + " ...documento di piano - norme di attuazione piano delle regole.pdf"}
    assert extract_templates.is_generic_regulatory_reference(record) is False


def test_gate_flags_marker_near_document_start():
    record = {"text": "COMUNE di GERMIGNAGA - PGT - PIANO DELLE REGOLE - NORME di ATTUAZIONE" + " x" * 600}
    assert extract_templates.is_generic_regulatory_reference(record) is True


# --- _marker_position() -- whitespace/newline-tolerant matching --------------

def test_marker_position_tolerates_a_newline_inside_the_phrase():
    """Regression guard for a real find 2026-09-29: the GERMIGNAGA construction-
    safety document's own title is extracted as 'PIANO DI SICUREZZA E
    \\nCOORDINAMENTO' -- a line break falls inside the phrase because of the
    source PDF's layout. A plain str.find() on the full lowercase phrase misses
    this near-the-top occurrence entirely and only matches a later, incidental
    repeat deep in the body -- which would silently defeat the position
    threshold this whole gate design depends on."""
    text = "comune di germignaga\npiano di sicurezza e \ncoordinamento\n(allegato xv)"
    assert extract_templates._marker_position(text, "piano di sicurezza e coordinamento") < 30


def test_marker_position_returns_minus_one_when_absent():
    assert extract_templates._marker_position("testo qualsiasi", "piano di sicurezza e coordinamento") == -1


# --- is_construction_safety_document() -- real GERMIGNAGA PSC excerpt --------

def test_construction_safety_gate_flags_real_psc_document():
    """Real excerpt (2026-09-29) from GERMIGNAGA's own construction-safety plan
    -- the document that motivated this whole second detector, after its facts
    ('lavoratori -> ha_ricorrenza -> vaccinazione antitetanica') were found to
    be structurally valid but semantically meaningless."""
    record = {"text": ("Ristrutturazione di un edificio condominiale in c.a. - Pag. 1 \n"
                       "Comune di \nGermignaga\nProvincia di VA\nPIANO DI SICUREZZA E \n"
                       "COORDINAMENTO\n(Allegato XV e art. 100 del D.Lgs. 9 aprile 2008, n. 81 e s.m.i.) ")}
    assert extract_templates.is_construction_safety_document(record) is True


def test_construction_safety_gate_fails_open_on_property_specific_document():
    record = {"text": "Comune di Germignaga - AVVISO DI PAGAMENTO TARI - ANNO 2026 - Totale da pagare 222,00€"}
    assert extract_templates.is_construction_safety_document(record) is False


def test_construction_safety_gate_does_not_flag_a_passing_mention_deep_in_a_document():
    filler = "x" * 2100
    record = {"text": filler + " ...come previsto dal piano di sicurezza e coordinamento del cantiere vicino."}
    assert extract_templates.is_construction_safety_document(record) is False


def test_out_of_domain_detectors_list_is_consulted_in_order():
    names = [reason for reason, _ in extract_templates.OUT_OF_DOMAIN_DETECTORS]
    assert names == ["GENERIC_REGULATORY_REFERENCE", "CONSTRUCTION_SAFETY_DOCUMENT"]


# --- _skip_reason() -- text quality checked before domain relevance ----------

def test_skip_reason_flags_garbled_text_before_checking_domain():
    """Real GERMIGNAGA catasto document (2026-09-29): text_quality_flags()
    already marks this possibly_garbled -- must be caught here without ever
    reaching the out-of-domain detectors."""
    record = {"text": "testo qualsiasi non normativo", "text_quality": {"possibly_garbled": True}}
    assert extract_templates._skip_reason(record, None) == ("SKIPPED_UNRELIABLE_TEXT", "GARBLED_TEXT")


def test_skip_reason_falls_through_to_out_of_domain_detectors():
    record = {"text": "Piano di Sicurezza e Coordinamento D.Lgs. 81/2008", "text_quality": {"possibly_garbled": False}}
    assert extract_templates._skip_reason(record, None) == ("SKIPPED_OUT_OF_DOMAIN", "CONSTRUCTION_SAFETY_DOCUMENT")


def test_skip_reason_none_for_a_clean_in_domain_document():
    record = {"text": "Comune di Germignaga - AVVISO DI PAGAMENTO TARI - ANNO 2026", "text_quality": {"possibly_garbled": False}}
    assert extract_templates._skip_reason(record, None) is None


def test_skip_reason_handles_missing_text_quality_field():
    """A record without text_quality (e.g. an older cache format) must not
    crash -- treated as not garbled, falls through to domain detectors."""
    record = {"text": "Comune di Germignaga - AVVISO DI PAGAMENTO TARI - ANNO 2026"}
    assert extract_templates._skip_reason(record, None) is None


def test_property_facts_batch_skips_garbled_document_with_its_own_status(monkeypatch, tmp_path, registry):
    def _raise_if_called(record, registry, **kwargs):
        raise AssertionError("extract_facts must not be called on garbled text")
    monkeypatch.setattr(extract_templates, "extract_facts", _raise_if_called)
    record = {"file_id": "sha256:garbled1", "extraction_status": "SUCCESS", "text": "x",
              "text_quality": {"possibly_garbled": True}}
    out = extract_templates.property_facts_batch([record], registry, tmp_path, property_id="GERMIGNAGA", endpoint="x", model="m")
    assert out == {"facts": [], "rejected_facts": []}
    data = evidence.read_json(tmp_path / "property_facts" / "garbled1-0.1.json", None)
    assert data["gate_status"] == "SKIPPED_UNRELIABLE_TEXT"
    assert data["gate_reason"] == "GARBLED_TEXT"


def test_property_facts_batch_skips_gated_document_without_calling_extract_facts(monkeypatch, tmp_path, registry):
    def _raise_if_called(record, registry, **kwargs):
        raise AssertionError("extract_facts must not be called on a gated document")
    monkeypatch.setattr(extract_templates, "extract_facts", _raise_if_called)
    record = {"file_id": "sha256:norma1", "extraction_status": "SUCCESS",
              "text": "Norme Tecniche di Attuazione del Piano di Governo del Territorio."}
    out = extract_templates.property_facts_batch([record], registry, tmp_path, property_id="VIG35", endpoint="x", model="m")
    assert out == {"facts": [], "rejected_facts": []}
    out_path = tmp_path / "property_facts" / "norma1-0.1.json"
    data = evidence.read_json(out_path, None)
    assert data["gate_status"] == "SKIPPED_OUT_OF_DOMAIN"
    assert data["gate_reason"] == "GENERIC_REGULATORY_REFERENCE"
    manifest = extract_templates.load_property_facts_manifest(tmp_path)
    assert manifest["sha256:norma1"]["status"] == "skipped"


def test_property_facts_batch_skips_construction_safety_document(monkeypatch, tmp_path, registry):
    def _raise_if_called(record, registry, **kwargs):
        raise AssertionError("extract_facts must not be called on a construction-safety document")
    monkeypatch.setattr(extract_templates, "extract_facts", _raise_if_called)
    record = {"file_id": "sha256:psc1", "extraction_status": "SUCCESS",
              "text": "PIANO DI SICUREZZA E COORDINAMENTO (Allegato XV e art. 100 del D.Lgs. 9 aprile 2008, n. 81)"}
    out = extract_templates.property_facts_batch([record], registry, tmp_path, property_id="GERMIGNAGA", endpoint="x", model="m")
    assert out == {"facts": [], "rejected_facts": []}
    data = evidence.read_json(tmp_path / "property_facts" / "psc1-0.1.json", None)
    assert data["gate_status"] == "SKIPPED_OUT_OF_DOMAIN"
    assert data["gate_reason"] == "CONSTRUCTION_SAFETY_DOCUMENT"


def test_property_facts_batch_resume_skips_previously_gated_document(monkeypatch, tmp_path, registry):
    def _raise_if_called(record, registry, **kwargs):
        raise AssertionError("extract_facts must not be called on a resumed, already-gated document")
    extract_templates.mark_property_facts_analyzed(tmp_path, "sha256:norma1", "skipped", property_id="VIG35", model="m", timeout=60)
    monkeypatch.setattr(extract_templates, "extract_facts", _raise_if_called)
    record = {"file_id": "sha256:norma1", "extraction_status": "SUCCESS", "text": "irrelevant text, resume must short-circuit"}
    out = extract_templates.property_facts_batch([record], registry, tmp_path, property_id="VIG35", endpoint="x", model="m", resume=True)
    assert out == {"facts": [], "rejected_facts": []}


# --- run_property_pipeline() -- the end-to-end chain, with every Ollama-touching
# stage mocked. The real per-document failure isolation is the point of the loop
# in run_property_pipeline, so the isolation itself is what's tested here.

def _fake_records(n):
    return [{"file_id": f"sha256:{i}", "extraction_status": "SUCCESS", "text": f"doc {i}"}
            for i in range(1, n + 1)]


def test_run_property_pipeline_chains_scan_extract_and_consolidates(monkeypatch, tmp_path, registry):
    records = _fake_records(2)
    monkeypatch.setattr(evidence, "scan", lambda root, ev: records)
    monkeypatch.setattr(evidence, "extract", lambda ev, root: records)
    monkeypatch.setattr(extract_templates, "extract_facts", _fake_extract_facts_fixed)
    out = extract_templates.run_property_pipeline(
        "GERMIGNAGA", tmp_path / "dropbox", tmp_path, registry, endpoint="x", model="m")
    assert out["property_id"] == "GERMIGNAGA"
    assert out["documents_processed"] == 2
    # Two documents, same subject/predicate/object -> one consolidated claim.
    assert out["raw_claims"] == 2
    assert out["consolidated_claims"] == 1
    assert out["consolidated"][0]["predicate"] == "p"
    assert sorted(out["consolidated"][0]["source_file_ids"]) == ["sha256:1", "sha256:2"]


def test_run_property_pipeline_skips_non_successful_extraction_records(monkeypatch, tmp_path, registry):
    records = _fake_records(2) + [{"file_id": "sha256:bad", "extraction_status": "OCR_REQUIRED", "text": ""}]
    monkeypatch.setattr(evidence, "scan", lambda root, ev: records)
    monkeypatch.setattr(evidence, "extract", lambda ev, root: records)
    monkeypatch.setattr(extract_templates, "extract_facts", _fake_extract_facts_fixed)
    out = extract_templates.run_property_pipeline("P", tmp_path, tmp_path, registry, endpoint="x", model="m")
    assert out["documents_processed"] == 2
    assert all(entry["file_id"] != "sha256:bad" for entry in out["per_file"])


def test_run_property_pipeline_one_failed_document_does_not_block_the_others(monkeypatch, tmp_path, registry):
    """The reason run_property_pipeline calls property_facts_batch per document:
    one unrecoverable failure must not discard the whole property's work."""
    records = _fake_records(3)
    monkeypatch.setattr(evidence, "scan", lambda root, ev: records)
    monkeypatch.setattr(evidence, "extract", lambda ev, root: records)
    def _only_second_fails(record, registry, **kwargs):
        if record["file_id"] == "sha256:2":
            raise evidence.EvidenceError("OLLAMA_SCHEMA_INVALID")
        return _fake_extract_facts_fixed(record, registry, **kwargs)
    monkeypatch.setattr(extract_templates, "extract_facts", _only_second_fails)
    out = extract_templates.run_property_pipeline("P", tmp_path, tmp_path, registry, endpoint="x", model="m")
    assert out["documents_processed"] == 3
    assert out["per_file"][1] == {"file_id": "sha256:2", "error": "OLLAMA_SCHEMA_INVALID"}
    assert out["consolidated_claims"] == 1
    assert out["consolidated"][0]["source_file_ids"] == ["sha256:1", "sha256:3"]


def test_run_property_pipeline_assigns_no_real_notion_match_to_any_entity(monkeypatch, tmp_path, registry):
    """resolve_claims is called with an empty notion_rows dict, so every
    subject/object must become a synthetic NEW_ENTITY id -- never a real Notion
    page id, because no live comparison was performed."""
    records = [{"file_id": "sha256:1", "extraction_status": "SUCCESS", "text": "doc"}]
    monkeypatch.setattr(evidence, "scan", lambda root, ev: records)
    monkeypatch.setattr(evidence, "extract", lambda ev, root: records)
    monkeypatch.setattr(extract_templates, "extract_facts", _fake_extract_facts_fixed)
    out = extract_templates.run_property_pipeline("P", tmp_path, tmp_path, registry, endpoint="x", model="m")
    resolved = evidence.resolve_claims(
        extract_templates.facts_to_raw_claims(
            evidence.read_json(extract_templates.property_facts_output_path("sha256:1", tmp_path), {})["facts"],
            "sha256:1"), {})
    assert all(item["resolution_status"] == "RESOLVED" for item in resolved)
    assert all(str(item["resolved_subject_id"]).startswith("new:") for item in resolved)
    assert all(str(item["resolved_object_id"]).startswith("new:") for item in resolved)
    assert out["consolidated_claims"] == 1


def test_main_resolves_evidence_root_and_registry_before_and_after_subcommand(monkeypatch, tmp_path):
    """Regression guard for a real bug found live 2026-09-29: argparse gives a
    subparser's --evidence-root/--registry the same dest as the top-level ones
    by default, so passing them after the subcommand silently overwrote the
    top-level value with None. Both positions must resolve to the same value."""
    captured = []

    def fake_batch(records, registry, evidence_root, *, property_id, **kwargs):
        captured.append(evidence_root)
        return {"facts": [], "rejected_facts": []}

    monkeypatch.setattr(extract_templates, "property_facts_batch", fake_batch)
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps({"file_id": "sha256:f", "extraction_status": "SUCCESS", "text": "x"}), encoding="utf-8")
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"predicates": []}), encoding="utf-8")
    evidence_root = tmp_path / "evroot"

    original_argv = sys.argv
    try:
        sys.argv = ["gmv_property_extract_templates.py", "--evidence-root", str(evidence_root),
                    "--registry", str(registry_path), "analyze", str(record_path), "--property-id", "P"]
        assert extract_templates.main() == 0
        sys.argv = ["gmv_property_extract_templates.py", "analyze", str(record_path), "--property-id", "P",
                    "--evidence-root", str(evidence_root), "--registry", str(registry_path)]
        assert extract_templates.main() == 0
    finally:
        sys.argv = original_argv
    assert captured == [evidence_root, evidence_root]
