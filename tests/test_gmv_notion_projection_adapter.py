"""Crawler preplan step 16: Notion ProjectionAdapter (spec v0.2 §33).

Reuses the same real fixtures step 5's own test suite already grounds
against (tests/test_gmv_notion_multi_candidate.py's PAGE_TEMPLATES/ROWS),
not a second hardcoded copy. Cross-checks CRAWLER_ENTITY_TYPE_TO_LEGACY
against the real, already-committed GMV_ONTOLOGY_REGISTRY_v0.1.json and
notion_page_templates.json, and pins the module's disclosed predicate-
vocabulary-mismatch limitation with a real regression test against both
real files, not just a docstring claim.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

from gmv_atom_validator import AtomCandidate  # noqa: E402
from gmv_monad_materializer import MonadDocument  # noqa: E402
from gmv_notion_projection_adapter import (  # noqa: E402
    CRAWLER_ENTITY_TYPE_TO_LEGACY,
    MultiCandidateNotionAdapter,
    _atoms_to_claims,
    _body_gate_to_crawler_gate,
    _entity_gate_to_crawler_gate,
    _write_bundle,
)
from gmv_notion_publish import load_bundle  # noqa: E402
from gmv_projection_adapter_contracts import ProjectionAdapter, TargetPayload  # noqa: E402
from notion_publish import check_staleness, plan_requests  # noqa: E402

from tests.test_gmv_notion_multi_candidate import PAGE_TEMPLATES, ROWS  # noqa: E402


class FakeNotionClient:
    """Minimal fake for check_staleness()'s only real dependency
    (client.call("GET", "/pages/<id>") -> {"properties": {...}}). Uses
    the "number" property type so notion_extract.prop_value() returns
    the raw value unchanged (its fallback branch), avoiding having to
    replicate Notion's richer rich_text/title array shape for a test
    that only cares about value comparison, not property-type fidelity.
    """

    def __init__(self, live_properties: dict) -> None:
        self._live_properties = live_properties

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        return {"properties": {
            name: {"type": "number", "number": value} for name, value in self._live_properties.items()
        }}

CONFIG = {"entita": {
    "artista": {"campi": {"nome": {"notion": "Nome", "obbligatorio": True}}, "relazioni": {}},
}}

ONTOLOGY_REGISTRY_PATH = ROOT / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_v0.1.json"
NOTION_PAGE_TEMPLATES_PATH = ROOT / "00_CONFIG" / "notion_page_templates.json"


def make_atom(**overrides) -> AtomCandidate:
    fields = {
        "atom_id": "GMV-ATOM-001",
        "subject": "Federico Garibaldi",
        "predicate": "nome",
        "predicate_class": "ATTRIBUTE",
        "object": "Federico Garibaldi",
        "object_type": "PERSON",
        "source": "SRC-001",
        "status": "VALID",
        "valid_from": None,
        "valid_to": None,
        "asserted_at": "2026-01-01T00:00:00Z",
        "ingested_at": "2026-01-01T00:00:00Z",
        "asserted_by": "gemma4:12b",
        "confidence": 0.9,
        "visibility": "PUBLIC",
    }
    fields.update(overrides)
    return AtomCandidate(**fields)


def make_monad(**overrides) -> MonadDocument:
    fields = {
        "gmv_id": "GMV-PERSON-001",
        "entity_type": "ARTIST",
        "canonical_name": "Federico Garibaldi",
        "status": "active",
        "public_text": "",
        "atoms": (make_atom(),),
        "sources": (),
    }
    fields.update(overrides)
    return MonadDocument(**fields)


def make_adapter(tmp_path: Path, **overrides) -> MultiCandidateNotionAdapter:
    fields = {
        "rows": ROWS, "config": CONFIG, "config_path": tmp_path / "config.json",
        "page_templates": PAGE_TEMPLATES, "run_dir": tmp_path,
    }
    fields.update(overrides)
    return MultiCandidateNotionAdapter(**fields)


# --- CRAWLER_ENTITY_TYPE_TO_LEGACY cross-checks ---

def test_every_mapped_crawler_class_is_a_real_registry_class_id() -> None:
    registry = json.loads(ONTOLOGY_REGISTRY_PATH.read_text(encoding="utf-8"))
    real_class_ids = {c["class_id"] for c in registry["entity_classes"]}
    assert set(CRAWLER_ENTITY_TYPE_TO_LEGACY) <= real_class_ids


def test_every_mapped_legacy_value_is_a_real_page_templates_entita_key() -> None:
    templates = json.loads(NOTION_PAGE_TEMPLATES_PATH.read_text(encoding="utf-8"))
    real_entita_keys = set(templates.get("entita", {}))
    assert set(CRAWLER_ENTITY_TYPE_TO_LEGACY.values()) <= real_entita_keys


def test_registry_classes_with_no_notion_table_are_not_mapped() -> None:
    """ORGANIZATION/PLACE/EVENT/DOCUMENT/PROJECT/COLLECTION/ARTWORK/CONTRACT
    have no real page_templates entry -- must not silently map to
    something incorrect."""
    for unmapped in ("ORGANIZATION", "PLACE", "EVENT", "DOCUMENT", "PROJECT", "COLLECTION", "ARTWORK", "CONTRACT"):
        assert unmapped not in CRAWLER_ENTITY_TYPE_TO_LEGACY


def test_predicate_vocabulary_mismatch_is_real_not_just_documented(tmp_path: Path) -> None:
    """Pins the module docstring's disclosed limitation with a real
    regression test against the real, committed registry and page
    templates: every registered crawler predicate must be confirmed to
    NOT match any real relation_hint/field_hint phrase. If this test
    ever starts failing, the vocabularies have converged and the
    docstring's disclosure is stale, not just this test."""
    registry = json.loads(ONTOLOGY_REGISTRY_PATH.read_text(encoding="utf-8"))
    crawler_predicates = {p["predicate_id"] for p in registry["predicates"]}
    templates = json.loads(NOTION_PAGE_TEMPLATES_PATH.read_text(encoding="utf-8"))
    hint_phrases = set()
    for spec in templates.get("entita", {}).values():
        for entries in spec.get("relation_hints", {}).values():
            hint_phrases.update(entry["predicate"] for entry in entries)
        hint_phrases.update(spec.get("field_hints", {}))
    assert crawler_predicates.isdisjoint(hint_phrases)


# --- supports() ---

def test_supports_true_for_mapped_class(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    assert adapter.supports("ARTIST") is True


def test_supports_false_for_unmapped_class(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    assert adapter.supports("PLACE") is False


# --- project() ---

def test_project_uses_crawler_entity_type_not_legacy_uppercase_italian(tmp_path: Path) -> None:
    """Regression test for a bug caught during this module's own
    development: an earlier draft used patch["entity_type"]
    ("ARTISTA", build_entity_patch()'s internal display convention)
    instead of the crawler's real vocabulary."""
    adapter = make_adapter(tmp_path)
    payload = adapter.project(make_monad())
    assert payload.entity_type == "ARTIST"


def test_project_field_matched_predicate_routes_to_add_operation(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path, page_templates={
        "generation_priority": ["artista"],
        "entita": {"artista": {"struttura_pagina": [{"titolo": "DOCUMENTAZIONE"}],
                                "field_hints": {"nome": "nome"}, "relation_hints": {}}},
    })
    payload = adapter.project(make_monad())
    assert payload.operation == "CREATE"
    assert payload.operations[0].action == "ADD"
    assert payload.operations[0].field == "Nome"
    assert payload.operations[0].claim_id == "GMV-ATOM-001"
    assert payload.gate == "AUTO_ACCEPT"


def test_project_relation_predicate_always_conflicts_no_relation_writer(tmp_path: Path) -> None:
    """Grounds "no relation-writer exists" against real code, not just
    the docstring's claim. config has no required fields for "artista"
    (an empty "entita" dict), so the only thing that can push the gate
    off READY_FOR_NOTION is the unresolved CONFLICT itself -- isolating
    exactly the behavior this test is about."""
    templates = {
        "generation_priority": ["artista"],
        "entita": {"artista": {"struttura_pagina": [{"titolo": "DOCUMENTAZIONE"}], "field_hints": {},
                                "relation_hints": {"mostre": [{"predicate": "esposto_a", "anchor": "object"}]}}},
    }
    atom = make_atom(predicate="esposto_a", object="Mostra al MAXXI", predicate_class="RELATION")
    monad = make_monad(atoms=(atom,))
    adapter = make_adapter(tmp_path, page_templates=templates, config={"entita": {}})
    payload = adapter.project(monad)
    assert payload.operations[0].action == "CONFLICT"
    assert payload.operations[0].reason is not None
    assert payload.gate == "REVIEW_REQUIRED"  # never AUTO_ACCEPT with an unresolved CONFLICT


def test_project_unsupported_entity_type_raises() -> None:
    adapter = MultiCandidateNotionAdapter(
        rows=ROWS, config=CONFIG, config_path=Path("/nonexistent"),
        page_templates=PAGE_TEMPLATES, run_dir=Path("/nonexistent"),
    )
    with pytest.raises(ValueError, match="no legacy Notion target"):
        adapter.project(make_monad(entity_type="PLACE"))


def test_project_empty_atoms_produces_empty_operations_and_blocked_gate(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    payload = adapter.project(make_monad(atoms=()))
    assert payload.operations == ()
    assert payload.gate == "BLOCKED"


def test_project_adapter_satisfies_projection_adapter_protocol(tmp_path: Path) -> None:
    assert isinstance(make_adapter(tmp_path), ProjectionAdapter)


# --- gate translation ---

def test_entity_gate_ready_no_conflict_is_auto_accept() -> None:
    assert _entity_gate_to_crawler_gate("READY_FOR_NOTION", has_conflict=False) == "AUTO_ACCEPT"


def test_entity_gate_ready_with_conflict_downgrades_to_review_required() -> None:
    """gate() itself never looks at operations, so READY_FOR_NOTION +
    CONFLICT is a real combination the real pipeline can produce --
    passing it through unmodified would violate TargetPayload's own
    AUTO_ACCEPT-forbids-CONFLICT invariant."""
    assert _entity_gate_to_crawler_gate("READY_FOR_NOTION", has_conflict=True) == "REVIEW_REQUIRED"


def test_entity_gate_review_required_maps_through() -> None:
    assert _entity_gate_to_crawler_gate("REVIEW_REQUIRED", has_conflict=False) == "REVIEW_REQUIRED"


def test_entity_gate_insufficient_evidence_maps_to_blocked() -> None:
    assert _entity_gate_to_crawler_gate("INSUFFICIENT_EVIDENCE", has_conflict=False) == "BLOCKED"


def test_entity_gate_unknown_value_raises() -> None:
    with pytest.raises(ValueError, match="unknown entity-level gate"):
        _entity_gate_to_crawler_gate("MADE_UP", has_conflict=False)


def test_body_gate_review_required_maps_through() -> None:
    assert _body_gate_to_crawler_gate("BODY_REVIEW_REQUIRED") == "REVIEW_REQUIRED"


def test_body_gate_ready_maps_to_auto_accept() -> None:
    assert _body_gate_to_crawler_gate("BODY_PATCH_READY") == "AUTO_ACCEPT"


def test_body_gate_unknown_value_raises() -> None:
    with pytest.raises(ValueError, match="unknown body-level gate"):
        _body_gate_to_crawler_gate("MADE_UP")


# --- _atoms_to_claims() ---

def test_atoms_to_claims_maps_atom_id_to_claim_id() -> None:
    claims = _atoms_to_claims((make_atom(atom_id="GMV-ATOM-999"),))
    assert claims[0]["claim_id"] == "GMV-ATOM-999"


def test_atoms_to_claims_empty_source_produces_empty_source_file_ids() -> None:
    claims = _atoms_to_claims((make_atom(source=""),))
    assert claims[0]["source_file_ids"] == []


# --- _write_bundle() / publish() ---

def test_write_bundle_produces_a_directory_load_bundle_can_load(tmp_path: Path) -> None:
    payload = TargetPayload(
        entity_type="ARTIST", name="Federico Garibaldi", operation="CREATE",
        operations=(), gate="AUTO_ACCEPT",
    )
    bundle_dir = _write_bundle(tmp_path, payload)
    bundle = load_bundle(bundle_dir)
    assert bundle.entity_name == "Federico Garibaldi"
    assert bundle.entity_type == "ARTIST"
    assert bundle.payload["gate"] == "READY_FOR_NOTION"
    assert bundle.patch["operation"] == "CREATE"


def test_publish_maps_every_real_publish_bundle_return_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import gmv_notion_projection_adapter as module

    expected = {
        0: "PUBLISHED", 1: "CANCELLED", 2: "FAILED_AUTHENTICATION",
        3: "ALREADY_PUBLISHED", 4: "BLOCKED_GATE_NOT_READY", 5: "BLOCKED_STALE_OR_DUPLICATE",
    }
    payload = TargetPayload(entity_type="ARTIST", name="Federico Garibaldi",
                             operation="CREATE", operations=(), gate="AUTO_ACCEPT")
    adapter = make_adapter(tmp_path)
    def make_fake(code):
        def fake(bundle_dir, **kwargs):
            if code == 0:
                # The real publish_bundle() always writes PUBLISHED.json
                # before returning 0 -- replicated here so this fake is
                # faithful to that real guarantee, not just its return code.
                (bundle_dir / "PUBLISHED.json").write_text(
                    json.dumps({"notion_page_id": "notion-page-x"}), encoding="utf-8",
                )
            return code
        return fake

    for code, outcome in expected.items():
        monkeypatch.setattr(module, "publish_bundle", make_fake(code))
        result = adapter.publish(payload)
        assert result.outcome == outcome


def test_publish_unrecognized_return_code_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import gmv_notion_projection_adapter as module

    monkeypatch.setattr(module, "publish_bundle", lambda *a, **k: 99)
    payload = TargetPayload(entity_type="ARTIST", name="Federico Garibaldi",
                             operation="CREATE", operations=(), gate="AUTO_ACCEPT")
    adapter = make_adapter(tmp_path)
    with pytest.raises(ValueError, match="unrecognized code"):
        adapter.publish(payload)


def test_publish_reads_real_page_id_when_published(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import gmv_notion_projection_adapter as module

    def fake_publish_bundle(bundle_dir, **kwargs):
        (bundle_dir / "PUBLISHED.json").write_text(
            json.dumps({"notion_page_id": "notion-page-123"}), encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(module, "publish_bundle", fake_publish_bundle)
    payload = TargetPayload(entity_type="ARTIST", name="Federico Garibaldi",
                             operation="CREATE", operations=(), gate="AUTO_ACCEPT")
    adapter = make_adapter(tmp_path)
    result = adapter.publish(payload)
    assert result.target_reference == "notion-page-123"


# --- reconcile_correction() ---

def test_reconcile_correction_raises_not_implemented(tmp_path: Path) -> None:
    adapter = make_adapter(tmp_path)
    with pytest.raises(NotImplementedError, match="no real implementation"):
        adapter.reconcile_correction(object())


# --- Regression tests for the review-reported BLOCK: keep_properties/
# body_gate were silently dropped by an earlier draft of _write_bundle(),
# making check_staleness() a permanent no-op and the body-append path
# permanently dead. Both exercise the REAL notion_publish.py functions,
# not a re-derived assertion about what they should do.

def test_keep_properties_propagates_so_check_staleness_detects_a_real_diff(tmp_path: Path) -> None:
    payload = TargetPayload(
        entity_type="ARTIST", name="Federico Garibaldi", operation="UPDATE",
        operations=(), gate="AUTO_ACCEPT", existing_target_reference="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        keep_properties={"Nome": "Old Value"},
    )
    bundle_dir = _write_bundle(tmp_path, payload)
    bundle = load_bundle(bundle_dir)
    client = FakeNotionClient({"Nome": "New Live Value"})
    result = check_staleness(client, bundle.patch)
    assert result["stale"] is True
    assert result["diffs"] == [{"property": "Nome", "bundle_value": "Old Value", "live_value": "New Live Value"}]


def test_keep_properties_matching_live_value_is_not_stale(tmp_path: Path) -> None:
    payload = TargetPayload(
        entity_type="ARTIST", name="Federico Garibaldi", operation="UPDATE",
        operations=(), gate="AUTO_ACCEPT", existing_target_reference="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        keep_properties={"Nome": "Same Value"},
    )
    bundle_dir = _write_bundle(tmp_path, payload)
    bundle = load_bundle(bundle_dir)
    client = FakeNotionClient({"Nome": "Same Value"})
    result = check_staleness(client, bundle.patch)
    assert result["stale"] is False


def test_body_gate_auto_accept_propagates_so_plan_requests_appends_body(tmp_path: Path) -> None:
    payload = TargetPayload(
        entity_type="ARTIST", name="Federico Garibaldi", operation="CREATE",
        operations=(), gate="AUTO_ACCEPT", body_text="## DOCUMENTAZIONE\n- una riga\n",
        body_gate="AUTO_ACCEPT",
    )
    bundle_dir = _write_bundle(tmp_path, payload)
    bundle = load_bundle(bundle_dir)
    requests, _ = plan_requests("db-1", bundle.patch, {}, bundle.body_markdown)
    body_requests = [r for r in requests if r["path"].startswith("/blocks/")]
    assert len(body_requests) == 1


def test_body_gate_review_required_never_appends_body(tmp_path: Path) -> None:
    """build_entity_patch() always sets BODY_REVIEW_REQUIRED today -- this
    is the realistic default path, and must never append body text."""
    payload = TargetPayload(
        entity_type="ARTIST", name="Federico Garibaldi", operation="CREATE",
        operations=(), gate="AUTO_ACCEPT", body_text="## DOCUMENTAZIONE\n- una riga\n",
        body_gate="REVIEW_REQUIRED",
    )
    bundle_dir = _write_bundle(tmp_path, payload)
    bundle = load_bundle(bundle_dir)
    requests, _ = plan_requests("db-1", bundle.patch, {}, bundle.body_markdown)
    body_requests = [r for r in requests if r["path"].startswith("/blocks/")]
    assert body_requests == []


def test_project_filters_out_non_valid_atoms(tmp_path: Path) -> None:
    """Regression test for the review-reported correctness issue: an
    INVALIDATED (tombstoned) atom must never be proposed as Notion
    content, even when its predicate matches a real field hint."""
    templates = {
        "generation_priority": ["artista"],
        "entita": {"artista": {"struttura_pagina": [{"titolo": "DOCUMENTAZIONE"}],
                                "field_hints": {"nome": "nome"}, "relation_hints": {}}},
    }
    valid_atom = make_atom(atom_id="GMV-ATOM-VALID", status="VALID", object="Federico Garibaldi")
    invalidated_atom = make_atom(
        atom_id="GMV-ATOM-INVALIDATED", status="INVALIDATED", object="Wrong Value",
    )
    monad = make_monad(atoms=(valid_atom, invalidated_atom))
    adapter = make_adapter(tmp_path, page_templates=templates)
    payload = adapter.project(monad)
    claim_ids = [op.claim_id for op in payload.operations]
    assert "GMV-ATOM-INVALIDATED" not in claim_ids
    assert "GMV-ATOM-VALID" in claim_ids
    assert "Wrong Value" not in (payload.body_text or "")
