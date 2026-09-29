import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "10_API"))
import gmv_ontology_check as ontology  # noqa: E402
import gmv_property_claims as claims  # noqa: E402

REGISTRY_PATH = Path(__file__).parents[1] / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_REALESTATE_v0.1.json"


@pytest.fixture
def registry():
    return ontology.load_registry(REGISTRY_PATH)


# ---- gmv_ontology_check ----

def test_registry_loads_and_has_mentions_deadline(registry):
    assert ontology.predicate_is_governed("mentions_deadline", registry)
    assert not ontology.predicate_is_governed("not_a_real_predicate", registry)


def test_subject_type_matches_domain(registry):
    assert ontology.subject_type_matches_domain("PROPERTY", "mentions_deadline", registry)
    assert ontology.subject_type_matches_domain("CONTRACT", "mentions_deadline", registry)
    assert not ontology.subject_type_matches_domain("ARTIST", "mentions_deadline", registry)


def test_validate_claim_raises_on_ungoverned_predicate(registry):
    with pytest.raises(ontology.UngovernedPredicateError):
        ontology.validate_claim("PROPERTY", "invented_predicate", registry)


def test_validate_claim_raises_on_domain_mismatch(registry):
    with pytest.raises(ontology.DomainMismatchError):
        ontology.validate_claim("ARTIST", "mentions_deadline", registry)


def test_validate_claim_passes_for_governed_predicate_and_domain(registry):
    ontology.validate_claim("PROPERTY", "mentions_deadline", registry)  # must not raise


def test_registry_has_no_risk_predicate_yet(registry):
    """Regression guard for the explicit v1 scope decision: rischio_alto must
    NOT be registered as a governed claim predicate until a reliability
    qualifier design is agreed (see registry note_on_scope_v1)."""
    predicate_ids = {p["predicate_id"] for p in registry["predicates"]}
    assert "reports_risk" not in predicate_ids
    assert "rischio_alto" not in predicate_ids


def test_object_matches_range_rejects_ungoverned_predicate(registry):
    assert ontology.object_matches_range("invented_predicate", "2026", registry) is False


def test_object_matches_range_rejects_tax_type_label_for_integer_year(registry):
    """Regression guard for a real bug found live 2026-09-29: ha_anno_imposta
    (range: ["integer"]) held 'TARI' and 'TASSA SMALTIMENTO RIFIUTI (TARI)' --
    a tax-type label with zero digits, not a year -- on real GERMIGNAGA/VIG35
    documents after the zoning-noise gate was already applied, so this is a
    distinct extraction defect, not the same bug."""
    assert ontology.object_matches_range("ha_anno_imposta", "TARI", registry) is False
    assert ontology.object_matches_range("ha_anno_imposta", "TASSA SMALTIMENTO RIFIUTI (TARI)", registry) is False


def test_object_matches_range_accepts_real_year_value(registry):
    assert ontology.object_matches_range("ha_anno_imposta", "2026", registry) is True


def test_object_matches_range_accepts_number_embedded_in_label_text(registry):
    """A real, already-validated live example: the model copies the whole
    matched span verbatim, not just the bare number -- must not regress."""
    assert ontology.object_matches_range("ha_maggior_tributo", "(a) TOTALE MAGGIOR TRIBUTO (IMPOSTA) 1.276,00", registry) is True


def test_object_matches_range_rejects_number_with_no_digits(registry):
    assert ontology.object_matches_range("ha_importo_dovuto", "importo non specificato", registry) is False


def test_object_matches_range_does_not_check_date_range(registry):
    """Deliberately permissive: a real deadline is sometimes only expressible as
    relative text, not a parseable date -- same reasoning as mentions_deadline's
    own range:[string] choice. Must not reject this."""
    assert ontology.object_matches_range("ha_scadenza", "entro sessanta giorni dalla notifica", registry) is True


def test_object_matches_range_always_true_for_string_and_entity_ranges(registry):
    assert ontology.object_matches_range("ha_tipo_tributo", "TARI", registry) is True
    assert ontology.object_matches_range("ha_debitore", "VALERIO GIACOMO MARCO", registry) is True


# ---- gmv_property_claims.load_property_rows ----

def test_load_property_rows_reads_real_object_yaml(tmp_path):
    portfolio = tmp_path / "portfolio"
    prop_dir = portfolio / "GERMIGNAGA"
    prop_dir.mkdir(parents=True)
    (prop_dir / "OBJECT.yaml").write_text(
        "schema: GMV_OBJECT_V1\ngmv_id: GMV-REA-000001\nname: Villa Liberty Germignaga\n"
        "aliases:\n  - germignaga\n  - villa liberty\nstatus: active\n",
        encoding="utf-8",
    )
    rows, aliases = claims.load_property_rows(portfolio)
    assert rows["property"] == [{"id": "GMV-REA-000001", "titolo": "Villa Liberty Germignaga"}]
    assert aliases["villa liberty"] == "villa liberty germignaga"


def test_load_property_rows_falls_back_to_folder_name_without_object_yaml(tmp_path):
    portfolio = tmp_path / "portfolio"
    (portfolio / "COURMA").mkdir(parents=True)
    rows, aliases = claims.load_property_rows(portfolio)
    assert rows["property"] == [{"id": "COURMA", "titolo": "COURMA"}]
    assert aliases == {}


def test_load_property_rows_isolates_malformed_object_yaml(tmp_path):
    """Regression guard: a malformed OBJECT.yaml for one property must not drop
    every other property from resolution -- found as a real gap by
    gmv-code-reviewer (yaml.safe_load had no per-folder error isolation)."""
    portfolio = tmp_path / "portfolio"
    good = portfolio / "GERMIGNAGA"
    good.mkdir(parents=True)
    (good / "OBJECT.yaml").write_text("gmv_id: GMV-REA-000001\nname: Villa Liberty Germignaga\naliases: []\n", encoding="utf-8")
    broken = portfolio / "COURMA"
    broken.mkdir()
    (broken / "OBJECT.yaml").write_text("gmv_id: [unclosed\n  bad: yaml: : :\n", encoding="utf-8")

    rows, _ = claims.load_property_rows(portfolio)
    ids = {r["id"] for r in rows["property"]}
    assert ids == {"GMV-REA-000001", "COURMA"}  # COURMA falls back to folder name, GERMIGNAGA still resolves


def test_load_property_rows_handles_missing_portfolio_root(tmp_path):
    rows, aliases = claims.load_property_rows(tmp_path / "does_not_exist")
    assert rows == {"property": []}
    assert aliases == {}


def test_load_property_rows_mixed_real_portfolio_shape(tmp_path):
    """Mirrors the real 2026-09-28 finding: only 1 of 6 property folders has a
    real OBJECT.yaml, the rest must still resolve via folder-name fallback."""
    portfolio = tmp_path / "portfolio"
    for name in ("C2", "COURMA", "VIG35", "VM8", "WITT12"):
        (portfolio / name).mkdir(parents=True)
    germ = portfolio / "GERMIGNAGA"
    germ.mkdir()
    (germ / "OBJECT.yaml").write_text("gmv_id: GMV-REA-000001\nname: Villa Liberty Germignaga\naliases: []\n", encoding="utf-8")
    rows, _ = claims.load_property_rows(portfolio)
    assert len(rows["property"]) == 6
    ids = {r["id"] for r in rows["property"]}
    assert ids == {"GMV-REA-000001", "C2", "COURMA", "VIG35", "VM8", "WITT12"}


# ---- gmv_property_claims.signal_to_raw_claims ----

def test_signal_to_raw_claims_emits_claim_on_positive_deadline(registry):
    signal = {
        "signal_status": "SUCCESS",
        "scadenza_presente": {"value": True, "evidence_excerpt": "entro il 20 novembre"},
    }
    out = claims.signal_to_raw_claims("sha256:abc", "Villa Liberty Germignaga", signal, registry)
    assert len(out) == 1
    claim = out[0]
    assert claim["predicate"] == "mentions_deadline"
    assert claim["subject_raw"] == "Villa Liberty Germignaga"
    assert claim["object_raw"] == "entro il 20 novembre"
    assert claim["evidence_excerpt"] == "entro il 20 novembre"
    assert claim["file_id"] == "sha256:abc"
    assert claim["status"] == "SUPPORTED_BY_ARCHIVE"


def test_signal_to_raw_claims_empty_when_no_deadline(registry):
    signal = {"signal_status": "SUCCESS", "scadenza_presente": {"value": False, "evidence_excerpt": None}}
    assert claims.signal_to_raw_claims("sha256:abc", "Some Property", signal, registry) == []


def test_signal_to_raw_claims_empty_when_signal_not_success(registry):
    signal = {"signal_status": "LAYA_TIMEOUT"}
    assert claims.signal_to_raw_claims("sha256:abc", "Some Property", signal, registry) == []


def test_signal_to_raw_claims_empty_when_deadline_true_but_no_excerpt(registry):
    """Defensive: never emit a claim without real evidence, even if value=True
    somehow arrives without an excerpt (should not happen given the worker's
    own aggregate() logic, but the projection must not assume it)."""
    signal = {"signal_status": "SUCCESS", "scadenza_presente": {"value": True, "evidence_excerpt": None}}
    assert claims.signal_to_raw_claims("sha256:abc", "Some Property", signal, registry) == []


# ---- end-to-end through the real resolve_claims/consolidate_claims ----

def test_projected_claim_resolves_and_consolidates_through_existing_pipeline(registry):
    sys.path.insert(0, str(Path(__file__).parents[1] / "10_API"))
    from gmv_evidence_pipeline import consolidate_claims, resolve_claims

    notion_rows = {"property": [{"id": "GMV-REA-000001", "titolo": "Villa Liberty Germignaga"}]}
    signal = {
        "signal_status": "SUCCESS",
        "scadenza_presente": {"value": True, "evidence_excerpt": "entro il 20 novembre"},
    }
    raw = claims.signal_to_raw_claims("sha256:abc", "Villa Liberty Germignaga", signal, registry)
    resolved = resolve_claims(raw, notion_rows)
    assert resolved[0]["resolution_status"] == "RESOLVED"
    assert resolved[0]["resolved_subject_id"] == "GMV-REA-000001"

    consolidated = consolidate_claims(resolved)
    assert len(consolidated) == 1
    assert consolidated[0]["predicate"] == "mentions_deadline"
    assert consolidated[0]["source_file_ids"] == ["sha256:abc"]
