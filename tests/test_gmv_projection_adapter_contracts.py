"""Crawler preplan step 5: ProjectionAdapter contract."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))
import gmv_notion_candidate as candidate  # noqa: E402
import gmv_notion_multi_candidate as multi  # noqa: E402
import gmv_projection_adapter_contracts as contracts  # noqa: E402

from tests.test_gmv_notion_multi_candidate import CLAIMS, PAGE_TEMPLATES, ROWS  # noqa: E402


def _operation(**overrides: object) -> contracts.FieldOperation:
    base = {"action": "ADD", "field": "biography", "value": "text", "claim_id": "C-1"}
    base.update(overrides)
    return contracts.FieldOperation(**base)


def _payload(**overrides: object) -> contracts.TargetPayload:
    base = {
        "entity_type": "artist",
        "name": "Test Entity",
        "operation": "CREATE",
        "operations": (_operation(),),
        "gate": "REVIEW_REQUIRED",
    }
    base.update(overrides)
    return contracts.TargetPayload(**base)


def test_field_operation_requires_non_empty_field() -> None:
    with pytest.raises(ValueError):
        contracts.FieldOperation(action="ADD", field="", value="x")


def test_field_operation_conflict_requires_reason() -> None:
    with pytest.raises(ValueError):
        contracts.FieldOperation(action="CONFLICT", field="biography", value=None)

    op = contracts.FieldOperation(
        action="CONFLICT", field="biography", value=None, reason="FIELD_VALUE_MISMATCH"
    )
    assert op.reason == "FIELD_VALUE_MISMATCH"


def test_target_payload_requires_non_empty_entity_type() -> None:
    with pytest.raises(ValueError):
        _payload(entity_type="")


def test_target_payload_rejects_auto_accept_with_unresolved_conflict() -> None:
    """This is a NEW invariant this contract introduces, not a mirror of
    today's real behavior: gate() in gmv_evidence_pipeline.py never looks
    at `operations` at all, so build_entity_patch() can and does produce
    READY_FOR_NOTION alongside an unresolved CONFLICT on any non-required
    field/relation right now (every relation is unconditionally CONFLICT,
    "no relation-writer exists," and that alone does not lower the real
    gate -- confirmed in test_target_payload_conflict_reflects_real_
    relation_behavior below). This contract deliberately tightens that
    for AUTO_ACCEPT specifically."""
    conflicted_op = _operation(action="CONFLICT", reason="FIELD_VALUE_MISMATCH")
    with pytest.raises(ValueError):
        _payload(operations=(conflicted_op,), gate="AUTO_ACCEPT")

    # REVIEW_REQUIRED alongside a CONFLICT operation is fine.
    payload = _payload(operations=(conflicted_op,), gate="REVIEW_REQUIRED")
    assert payload.gate == "REVIEW_REQUIRED"


def test_target_payload_conflict_reflects_real_relation_behavior(tmp_path) -> None:
    """Verifies, by running the real code, the claim the previous test's
    docstring makes: gate() does not look at `operations`, so
    build_entity_patch() really does produce a READY_FOR_NOTION-equivalent
    gate alongside an unresolved CONFLICT (every relation-type claim in
    these fixtures resolves to CONFLICT, "no relation-writer exists")."""
    output = multi.run_multi_candidate(
        CLAIMS, ROWS, {"entita": {}}, PAGE_TEMPLATES,
        "Riccardo Paternò Castello", "artista", tmp_path,
    )
    checked = False
    for entity in output["entities"]:
        if "bundle" not in entity:
            continue
        patch = json.loads((Path(entity["bundle"]) / "PATCH.json").read_text(encoding="utf-8"))
        if any(op["action"] == "CONFLICT" for op in patch["operations"]):
            assert patch["gate"] == "READY_FOR_NOTION"
            checked = True
    assert checked, "fixture produced no CONFLICT operation -- test would be vacuous"


def test_target_payload_default_body_gate_is_review_required() -> None:
    payload = _payload()
    assert payload.body_gate == "REVIEW_REQUIRED"


def test_publish_result_published_requires_target_reference() -> None:
    with pytest.raises(ValueError):
        contracts.PublishResult(outcome="PUBLISHED")

    result = contracts.PublishResult(outcome="PUBLISHED", target_reference="page-123")
    assert result.target_reference == "page-123"


@pytest.mark.parametrize(
    "outcome",
    [
        "CANCELLED",
        "ALREADY_PUBLISHED",
        "BLOCKED_GATE_NOT_READY",
        "BLOCKED_STALE_OR_DUPLICATE",
        "FAILED_AUTHENTICATION",
    ],
)
def test_publish_result_non_published_outcomes_do_not_require_target_reference(
    outcome: str,
) -> None:
    result = contracts.PublishResult(outcome=outcome)
    assert result.target_reference is None


def test_publish_outcome_matches_every_return_statement_in_publish_bundle_source() -> None:
    """Inspects the real source of gmv_notion_publish.py::publish_bundle()
    (not a second hardcoded copy in this file) for the literal marker
    strings tied to each of its six real return paths, so a future edit
    to that function that removes/renames a branch fails this test
    instead of silently drifting from PublishOutcome. Also confirms, by
    grep rather than assumption, that publish_bundle can raise outside
    these six paths (this contract's docstring says so -- verified here,
    not just asserted)."""
    source = (ROOT / "10_API" / "gmv_notion_publish.py").read_text(encoding="utf-8")

    markers = {
        "PUBLISHED": "Pubblicato: pagina Notion",
        "CANCELLED": "ANNULLATO",
        "FAILED_AUTHENTICATION": "credentials.TokenError",
        "ALREADY_PUBLISHED": "già pubblicato",
        "BLOCKED_GATE_NOT_READY": "READY_FOR_NOTION",
        "BLOCKED_STALE_OR_DUPLICATE": "obsoleto",
    }
    for outcome, marker in markers.items():
        assert marker in source, f"expected marker for {outcome} not found in publish_bundle source"
        assert outcome in contracts.PublishOutcome.__args__

    assert set(contracts.PublishOutcome.__args__) == set(markers)

    # publish_bundle is not total over these six paths -- load_bundle()
    # can raise FileNotFoundError/ValueError before any of them run.
    assert "def load_bundle" in source
    assert "raise FileNotFoundError" in source or "raise ValueError" in source


def test_proposed_patch_requires_reason_when_authority_check_fails() -> None:
    with pytest.raises(ValueError):
        contracts.ProposedPatch(
            entity_type="artist",
            field="biography",
            observed_target_value="new text on Notion",
            proposed_monad_value="new text on Notion",
            authority_check_passed=False,
        )

    patch = contracts.ProposedPatch(
        entity_type="artist",
        field="biography",
        observed_target_value="new text on Notion",
        proposed_monad_value="new text on Notion",
        authority_check_passed=False,
        reason="NO_CANONICAL_SOURCE_FOR_CORRECTION",
    )
    assert patch.reason == "NO_CANONICAL_SOURCE_FOR_CORRECTION"


def test_proposed_patch_allows_missing_reason_when_authority_check_passes() -> None:
    patch = contracts.ProposedPatch(
        entity_type="artist",
        field="biography",
        observed_target_value="new text on Notion",
        proposed_monad_value="new text on Notion",
        authority_check_passed=True,
    )
    assert patch.reason is None


def test_projection_adapter_protocol_is_runtime_checkable_and_structural() -> None:
    class FakeAdapter:
        def supports(self, entity_type):
            return entity_type == "artist"

        def project(self, monad):
            raise NotImplementedError

        def publish(self, payload):
            raise NotImplementedError

        def reconcile_correction(self, target_change):
            raise NotImplementedError

    assert isinstance(FakeAdapter(), contracts.ProjectionAdapter)

    class IncompleteAdapter:
        def supports(self, entity_type):
            return True

    assert not isinstance(IncompleteAdapter(), contracts.ProjectionAdapter)


def test_multi_adapter_registry_routes_by_supports() -> None:
    class ArtistAdapter:
        def supports(self, entity_type):
            return entity_type == "artist"

        def project(self, monad):
            raise NotImplementedError

        def publish(self, payload):
            raise NotImplementedError

        def reconcile_correction(self, target_change):
            raise NotImplementedError

    class ExhibitionAdapter:
        def supports(self, entity_type):
            return entity_type == "exhibition"

        def project(self, monad):
            raise NotImplementedError

        def publish(self, payload):
            raise NotImplementedError

        def reconcile_correction(self, target_change):
            raise NotImplementedError

    artist_adapter = ArtistAdapter()
    exhibition_adapter = ExhibitionAdapter()
    registry = contracts.MultiAdapterRegistry(adapters=(artist_adapter, exhibition_adapter))

    assert registry.adapters_for("artist") == (artist_adapter,)
    assert registry.adapters_for("exhibition") == (exhibition_adapter,)
    assert registry.adapters_for("sponsor") == ()


def test_operation_action_vocabulary_matches_actions_real_code_actually_emits(
    tmp_path,
) -> None:
    """Executes the real build_entity_patch()/run_multi_candidate() (via
    the sibling test module's own claims/templates/rows fixtures, not a
    second copy) and collects every `action` value really produced,
    asserting it is a non-empty subset of OperationAction -- proof the
    contract's vocabulary is exercised against live code, not just
    compared to a second hardcoded set in this same file (the mistake an
    earlier draft of this test made)."""
    output = multi.run_multi_candidate(
        CLAIMS, ROWS, {"entita": {}}, PAGE_TEMPLATES,
        "Riccardo Paternò Castello", "artista", tmp_path,
    )
    observed_actions: set[str] = set()
    for entity in output["entities"]:
        if "bundle" not in entity:
            continue
        patch = json.loads((Path(entity["bundle"]) / "PATCH.json").read_text(encoding="utf-8"))
        observed_actions.update(op["action"] for op in patch["operations"])

    assert observed_actions, "fixture produced no operations -- test would be vacuous"
    assert observed_actions <= set(contracts.OperationAction.__args__)
    # CONFLICT is guaranteed by the real "no relation-writer exists" path
    # for every relation-type claim in these fixtures.
    assert "CONFLICT" in observed_actions


def test_operation_action_update_value_matches_gmv_notion_candidate_real_output() -> None:
    """build_entity_patch()/run_multi_candidate() above never emit "UPDATE"
    (that code path only ever produces ADD/CONFLICT). "UPDATE" comes from
    the sibling module, gmv_notion_candidate.py::build_incremental_patch --
    exercised here against a real existing-row/differing-value case so
    this vocabulary value is verified by execution too, not only by
    reading that function's source."""
    config = {"entita": {"artista": {"campi": {
        "opere": {"notion": "Opere", "obbligatorio": True},
    }, "relazioni": {}}}}
    rows = {"artista": [{"id": "notion-1", "titolo": "Riccardo Paternò Castello",
            "campi": {"opere": "Old Value"}, "relazioni": {}, "corpo": ""}]}
    index = {"sha256:a": {"file_id": "sha256:a", "paths": ["bio.txt"]}}
    claims = [{"claim_id": "c1", "predicate": "opere", "object": "New Value",
               "status": "VERIFIED", "source_file_ids": ["sha256:a"]}]

    patch = candidate.build_incremental_patch(
        "Riccardo Paternò Castello", "artista", claims, rows, config, index
    )
    actions = {op["action"] for op in patch["operations"]}
    assert "UPDATE" in actions
    assert actions <= set(contracts.OperationAction.__args__)
