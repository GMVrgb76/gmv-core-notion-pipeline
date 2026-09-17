"""GMV Crawler — Task 8: entity type classification (RESOLVE ENTITIES slice).

Pins the categorical two-source principle: a roster match is a verified
fact (MATCHED_KNOWN_ARTIST_ROSTER, needs_verification=False, no model
call), a model inference is ALWAYS needs_verification=True whatever
confidence the model declares (the central guarantee of this task) --
plus the exact HTTP envelope/error mapping mirrored from
gmv_evidence_pipeline.ollama_extract(). Real Ollama is never contacted:
`urllib.request.urlopen` is patched for every call (mirroring the
repo's monkeypatch-based Ollama fakes) and the roster-only cases also
patch `resolver._classify_via_ollama` to fail, so even an accidental
network call would surface, not just be unchecked.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

import gmv_crawler_entity_resolver as resolver  # noqa: E402
from area35_validator import _forma  # noqa: E402
from gmv_crawler_candidate_extractor import CandidateEntity  # noqa: E402
from gmv_crawler_entity_resolver import (  # noqa: E402
    CLASSIFICATION_SCHEMA,
    EntityTypeProposal,
    classify_entity_types,
)
from gmv_evidence_pipeline import EvidenceError, OllamaResponseError  # noqa: E402

ENTITY_REGISTRY_SQL = ROOT / "gmv_core" / "migration_sql" / "010_entity_registry.sql"

KNOWN_NAME = "Federico Garibaldi"  # literal row in 00_CONFIG/area35_known_artists.json
UNKNOWN_NAME = "Ugo Dossi"  # invented: guaranteed not in the 47-name roster


def fail_if_called(*_args, **_kwargs):
    pytest.fail("network/Ollama must not be called for roster-matched entities")


class FakeUrlResponse:
    """Minimal urllib response: context-managed, JSON-serializable read()."""

    def __init__(self, envelope: dict):
        self._envelope = envelope

    def __enter__(self) -> FakeUrlResponse:
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def read(self) -> bytes:
        return json.dumps(self._envelope).encode()


def classification_envelope(items: list[dict]) -> dict:
    return {
        "model": "gemma4:12b",
        "response": json.dumps({"classifications": items}),
        "done_reason": "stop",
    }


def make_urlopen(envelope: dict | None = None, *, raise_exc: Exception | None = None,
                 captured: list | None = None):
    def _fake(request, timeout=None):
        if captured is not None:
            captured.append(request)
        if raise_exc is not None:
            raise raise_exc
        return FakeUrlResponse(envelope or classification_envelope([]))

    return _fake


def make_entity(name: str, *, excerpt: str = "evidence excerpt about this entity") -> CandidateEntity:
    return CandidateEntity(
        name=name,
        evidence_excerpt=excerpt,
        status="DOCUMENTATO",
        source_id="SRC-EVID-42",
        evidence_id=("EV-1",),
    )


# --- the verified-fact source: roster match, no model call ---

def test_roster_exact_match_is_verified_fact_and_never_touches_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resolver, "_classify_via_ollama", fail_if_called)
    monkeypatch.setattr(urllib.request, "urlopen", fail_if_called)
    proposals = classify_entity_types((make_entity(KNOWN_NAME),))
    assert proposals == (
        EntityTypeProposal(
            entity_name=KNOWN_NAME, entity_type="ARTIST",
            confidence="HIGH", source="MATCHED_KNOWN_ARTIST_ROSTER",
            needs_verification=False,
        ),
    )


def test_institution_list_match_is_verified_fact_and_never_touches_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-09-17: mirrors the artist-roster test exactly, for the
    institution list (00_CONFIG/area35_known_institutions.json), added
    after a live finding that the same institution name was classified
    INSTITUTION in one Ollama run and EXHIBITION in another -- a
    human-confirmed institution list closes that gap the same way the
    artist roster already does. `known_institutions` is passed explicitly
    here rather than relying on the real file's current content: that
    file grows over time through the OpenWebUI review chat, and this test
    must stay correct regardless of what it happens to contain."""
    monkeypatch.setattr(resolver, "_classify_via_ollama", fail_if_called)
    monkeypatch.setattr(urllib.request, "urlopen", fail_if_called)
    name = "Le Stanze della Fotografia"
    proposals = classify_entity_types(
        (make_entity(name),),
        known_artists=frozenset(),
        known_institutions=frozenset({_forma(name)}),
    )
    assert proposals == (
        EntityTypeProposal(
            entity_name=name, entity_type="INSTITUTION",
            confidence="HIGH", source="MATCHED_KNOWN_INSTITUTION_LIST",
            needs_verification=False,
        ),
    )


def test_artist_roster_checked_before_institution_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A name present in BOTH lists resolves as ARTIST (roster checked
    first) -- not a real case this project has seen, but the order is
    fixed and tested, not left to chance."""
    monkeypatch.setattr(resolver, "_classify_via_ollama", fail_if_called)
    monkeypatch.setattr(urllib.request, "urlopen", fail_if_called)
    name = "Ambiguous Name"
    proposals = classify_entity_types(
        (make_entity(name),),
        known_artists=frozenset({_forma(name)}),
        known_institutions=frozenset({_forma(name)}),
    )
    assert proposals[0].entity_type == "ARTIST"
    assert proposals[0].source == "MATCHED_KNOWN_ARTIST_ROSTER"


def test_roster_match_after_forma_normalization_inverted_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'Garibaldi, Federico' is NOT in the roster byte-for-byte; it matches
    only because _forma() collapses surname,firstname, proving the lookup
    really goes through _forma(), not exact string comparison."""
    monkeypatch.setattr(resolver, "_classify_via_ollama", fail_if_called)
    monkeypatch.setattr(urllib.request, "urlopen", fail_if_called)
    proposals = classify_entity_types((make_entity("Garibaldi, Federico"),))
    assert proposals == (
        EntityTypeProposal(
            entity_name="Garibaldi, Federico", entity_type="ARTIST",
            confidence="HIGH", source="MATCHED_KNOWN_ARTIST_ROSTER",
            needs_verification=False,
        ),
    )


def test_load_known_artists_is_forma_normalized_frozenset() -> None:
    data = json.loads(resolver.KNOWN_ARTISTS_PATH.read_text(encoding="utf-8"))
    raw_names = data["artists"]
    roster = resolver._load_known_artists()
    assert isinstance(roster, frozenset)
    # NOTE: the file's own "source" note and the task brief both say "47
    # real folder names", but the actual artists list in the file has 46
    # entries -- reported in the commit, not silently "fixed". The contract
    # pinned here is the one that matters for correctness: no two DISTINCT
    # roster names may collide under _forma(), or one key would attest two
    # different real artists as a single known entity.
    assert len(roster) == len(raw_names) == len({_forma(n) for n in raw_names})
    assert "federico garibaldi" in roster
    assert all(name == resolver._forma(name) for name in roster)
    assert "not an artist" not in roster


# --- the inference source: one batch call, needs_verification always True ---

def test_mixed_batch_makes_single_ollama_call_only_for_unmatched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list = []
    monkeypatch.setattr(
        urllib.request, "urlopen",
        make_urlopen(
            classification_envelope(
                [{"name": "Ugo Dossi", "entity_type": "PERSON", "confidence": "LOW"},
                 {"name": "Vanda Bianchi", "entity_type": "ARTIST", "confidence": "MEDIUM"}]
            ),
            captured=captured,
        ),
    )
    entities = (
        make_entity(KNOWN_NAME),
        make_entity("Luo Qi"),  # also in the roster
        make_entity("Ugo Dossi"),
        make_entity("Vanda Bianchi"),
    )
    proposals = classify_entity_types(entities)
    assert len(captured) == 1  # ONE call for the whole unmatched sub-batch
    payload = json.loads(captured[0].data)
    assert payload["prompt"].count("- ") >= 2
    assert "- Ugo Dossi" in payload["prompt"] and "- Vanda Bianchi" in payload["prompt"]
    assert [p.entity_name for p in proposals] == [e.name for e in entities]
    assert proposals[0].source == "MATCHED_KNOWN_ARTIST_ROSTER"
    assert proposals[1].source == "MATCHED_KNOWN_ARTIST_ROSTER"
    assert all(p.source == "MODEL_INFERENCE" and p.needs_verification for p in proposals[2:])


@pytest.mark.parametrize("model_confidence", ["HIGH", "MEDIUM", "LOW"])
def test_model_inference_needs_verification_true_whatever_confidence(
    monkeypatch: pytest.MonkeyPatch, model_confidence: str,
) -> None:
    """THE central pin: a model's declared confidence is a category of its
    own, never a surrogate for verification -- HIGH included."""
    monkeypatch.setattr(
        urllib.request, "urlopen",
        make_urlopen(classification_envelope(
            [{"name": UNKNOWN_NAME, "entity_type": "ARTIST", "confidence": model_confidence}]
        )),
    )
    proposals = classify_entity_types((make_entity(UNKNOWN_NAME),))
    assert proposals == (
        EntityTypeProposal(
            entity_name=UNKNOWN_NAME, entity_type="ARTIST",
            confidence=model_confidence, source="MODEL_INFERENCE",
            needs_verification=True,
        ),
    )


def test_model_response_matched_by_exact_name_not_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model may REORDER names -- matching is keyed on the exact name
    string, never on position."""
    monkeypatch.setattr(
        urllib.request, "urlopen",
        make_urlopen(classification_envelope(
            [{"name": "Vanda Bianchi", "entity_type": "PERSON", "confidence": "LOW"},
             {"name": "Ugo Dossi", "entity_type": "PLACE", "confidence": "MEDIUM"}]
        )),
    )
    proposals = classify_entity_types(
        (make_entity("Ugo Dossi"), make_entity("Vanda Bianchi"))
    )
    assert [p.entity_name for p in proposals] == ["Ugo Dossi", "Vanda Bianchi"]  # input order kept
    assert [p.entity_type for p in proposals] == ["PLACE", "PERSON"]


def test_model_invented_extra_entity_is_ignored_not_leaked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        urllib.request, "urlopen",
        make_urlopen(classification_envelope(
            [{"name": "Ugo Dossi", "entity_type": "PERSON", "confidence": "LOW"},
             {"name": "Made Up Person", "entity_type": "ARTIST", "confidence": "HIGH"}]
        )),
    )
    proposals = classify_entity_types((make_entity("Ugo Dossi"),))
    assert len(proposals) == 1
    assert proposals[0].entity_name == "Ugo Dossi"


# --- HTTP envelope, mirroring ollama_extract() ---

def test_payload_has_explicit_think_false_and_schema_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list = []
    monkeypatch.setattr(
        urllib.request, "urlopen",
        make_urlopen(classification_envelope(
            [{"name": UNKNOWN_NAME, "entity_type": "ARTIST", "confidence": "HIGH"}]
        ), captured=captured),
    )
    classify_entity_types((make_entity(UNKNOWN_NAME),))
    payload = json.loads(captured[0].data)
    assert payload["think"] is False
    assert payload["stream"] is False
    assert payload["format"] == CLASSIFICATION_SCHEMA
    assert payload["model"] == resolver.DEFAULT_MODEL
    assert captured[0].full_url.endswith("/api/generate")


@pytest.mark.parametrize(
    "error, expected_code",
    [
        (urllib.error.URLError("connection refused"), "OLLAMA_UNAVAILABLE"),
        (TimeoutError("timed out"), "TIMEOUT"),
    ],
)
def test_network_failure_propagates_never_suppressed(
    monkeypatch: pytest.MonkeyPatch, error: Exception, expected_code: str,
) -> None:
    """A call-level failure is evidence to surface, never a fake proposal."""
    monkeypatch.setattr(urllib.request, "urlopen", make_urlopen(raise_exc=error))
    with pytest.raises(EvidenceError) as excinfo:
        classify_entity_types((make_entity(UNKNOWN_NAME),))
    assert str(excinfo.value) == expected_code


def test_truncated_done_reason_raises_exactly_like_ollama_extract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        urllib.request, "urlopen",
        make_urlopen({"model": "gemma4:12b", "response": "{\"classifications\": [", "done_reason": "length"}),
    )
    with pytest.raises(OllamaResponseError) as excinfo:
        classify_entity_types((make_entity(UNKNOWN_NAME),))
    assert str(excinfo.value) == "OLLAMA_OUTPUT_TRUNCATED"
    assert excinfo.value.raw_output == "{\"classifications\": ["


def test_malformed_model_output_raises_like_ollama_extract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # raw output is not JSON
    monkeypatch.setattr(
        urllib.request, "urlopen",
        make_urlopen({"model": "gemma4:12b", "response": "not-json", "done_reason": "stop"}),
    )
    with pytest.raises(OllamaResponseError, match="OLLAMA_INVALID_JSON"):
        classify_entity_types((make_entity(UNKNOWN_NAME),))
    # envelope without the classifications array
    monkeypatch.setattr(
        urllib.request, "urlopen",
        make_urlopen({"model": "gemma4:12b", "response": "{}", "done_reason": "stop"}),
    )
    with pytest.raises(OllamaResponseError, match="OLLAMA_SCHEMA_INVALID"):
        classify_entity_types((make_entity(UNKNOWN_NAME),))
    # item with out-of-vocabulary entity_type
    monkeypatch.setattr(
        urllib.request, "urlopen",
        make_urlopen(classification_envelope(
            [{"name": UNKNOWN_NAME, "entity_type": "SUPERHERO", "confidence": "HIGH"}]
        )),
    )
    with pytest.raises(OllamaResponseError, match="OLLAMA_SCHEMA_INVALID"):
        classify_entity_types((make_entity(UNKNOWN_NAME),))


# --- the open point (brief point 5): entity missing from model response ---

def test_requested_entity_absent_from_model_response_raises_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decision documented in the commit: a silent drop or an invented
    proposal are both forbidden; this raises CLASSIFICATION_MISSING_ENTITY
    with the offending names in the detail."""
    monkeypatch.setattr(
        urllib.request, "urlopen",
        make_urlopen(classification_envelope([])),  # classified nothing we asked for
    )
    with pytest.raises(EvidenceError) as excinfo:
        classify_entity_types((make_entity(UNKNOWN_NAME),))
    assert str(excinfo.value) == "CLASSIFICATION_MISSING_ENTITY"
    assert UNKNOWN_NAME in excinfo.value.detail


# --- schema grounding: the 12 types must be the real 010 registry CHECK ---

def test_valid_entity_types_match_entity_registry_sql() -> None:
    sql = ENTITY_REGISTRY_SQL.read_text(encoding="utf-8")
    match = re.search(r"CHECK\(entity_type IN \(([^)]*)\)\)", sql)
    assert match is not None
    schema_types = re.findall(r"'([A-Z_]+)'", match.group(1))
    assert set(schema_types) == set(resolver.VALID_ENTITY_TYPES)


# --- degenerate batch ---

def test_empty_batch_returns_empty_tuple_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resolver, "_classify_via_ollama", fail_if_called)
    assert classify_entity_types(()) == ()