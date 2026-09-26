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
    resolve_entity_gmv_id,
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

# --- resolve_entity_gmv_id(): the identity half (added 2026-09-26) ---
#
# The guarantees this section tries to BREAK, deliberately, one test each:
#   G1 "exact, case-insensitive, whitespace-normalized match"  -> test_gmv_id_resolves_canonical_name_case_and_whitespace_insensitively
#   G2 "returns the matching entity's gmv_id, or None if no entry
#       matches" (never an error, never an invented id)        -> test_gmv_id_unknown_and_blank_names_return_none
#   G3 "never silently picks a winner" (ambiguity -> None)    -> test_gmv_id_ambiguous_name_across_two_entities_is_never_a_silent_pick
#   G4 no gmv_id is ever generated                            -> test_gmv_id_never_creates_or_mutates_registry_state
# G5 (extra, not in the docstring's list but implied by it): a
#   registry entry with an empty gmv_id must not leak "" to a
#   caller testing `is None`                               -> test_gmv_id_entry_with_empty_gmv_id_is_skipped_not_returned_as_empty_string
# G6: no LLM/network is ever contacted, in any case           -> test_gmv_id_never_touches_network_even_for_unmatched_names

REAL_REGISTRY_PATH = ROOT / "00_CONFIG" / "gmv_entity_registry.json"


def _registry(*entities: dict) -> dict:
    return {"note": "test fixture", "entities": list(entities)}


GARIBALDI = {
    "gmv_id": "GMV-ARTIST-FEDERICO-GARIBALDI",
    "entity_type": "ARTIST",
    "canonical_name": "Federico Garibaldi",
    "aliases": ["Garibaldi"],
    "status": "active",
}


def test_gmv_id_resolves_canonical_name_case_and_whitespace_insensitively() -> None:
    registry = _registry(GARIBALDI)
    for name in ("Federico Garibaldi", "federico garibaldi", "FEDERICO GARIBALDI",
                 "  Federico Garibaldi  ", "\nFederico Garibaldi\t"):
        assert resolve_entity_gmv_id(name, registry) == "GMV-ARTIST-FEDERICO-GARIBALDI"


def test_gmv_id_does_not_normalize_whitespace_inside_the_name() -> None:
    """Pinned limitation, not an oversight: the specified normalization is
    exactly `.strip().lower()` on both sides, which strips only LEADING and
    TRAILING whitespace. A name differing INSIDE itself -- a tab, a
    newline, a double space, a non-breaking space (which LLM output does
    produce) -- is a different string and does not match. Deliberately
    left as-is rather than "fixed" with a broader normalization: any
    internal-whitespace collapsing belongs to the human-curated `aliases`
    list, and this test exists so a future edit that DOES broaden the
    matching has to change this test deliberately rather than silently."""
    registry = _registry(GARIBALDI)
    for name in ("Federico  Garibaldi", "Federico\tGaribaldi", "Federico\xa0Garibaldi"):
        assert resolve_entity_gmv_id(name, registry) is None, repr(name)


def test_gmv_id_resolves_an_alias_exactly_but_never_fuzzily() -> None:
    registry = _registry(GARIBALDI)
    assert resolve_entity_gmv_id("Garibaldi", registry) == "GMV-ARTIST-FEDERICO-GARIBALDI"
    assert resolve_entity_gmv_id(" garibaldi ", registry) == "GMV-ARTIST-FEDERICO-GARIBALDI"
    # Every near-miss below is a DIFFERENT string: no fuzzy matching, no
    # substring matching, no token-order normalization (no _forma()), and
    # "Garibaldi, Federico" is deliberately NOT accepted -- an inverted
    # name is an alias a human adds to the registry, not something the
    # matcher decides (see the function's own docstring, point 2).
    for name in ("Federico", "Garibaldi, Federico", "F. Garibaldi",
                 "Federico Garibaldi Jr", "Garibaldi Federico", "Garibald"):
        assert resolve_entity_gmv_id(name, registry) is None, name


def test_gmv_id_unknown_and_blank_names_return_none_never_an_error() -> None:
    registry = _registry(GARIBALDI)
    for name in (UNKNOWN_NAME, "", "   ", "\t\n", "  Federico  "):
        result = resolve_entity_gmv_id(name, registry)
        assert result is None, name


def test_gmv_id_ambiguous_name_across_two_entities_is_never_a_silent_pick() -> None:
    """The exact attack on the guarantee, in all three forms it can take:
    canonical-vs-canonical (as alias-vs-alias of the same two entities),
    canonical-vs-alias, in BOTH entity orderings -- because a
    "first match wins" implementation passes the name that only the first
    entity carries, and the orderings are what expose it. The
    non-ambiguous sibling name in the same registry must still resolve:
    ambiguity is scoped to one name, it does not poison the file."""
    homonym = {
        "gmv_id": "GMV-PERSON-OTHER-GARIBALDI",
        "entity_type": "PERSON",
        "canonical_name": "Garibaldi",
        "aliases": [],
        "status": "active",
    }
    aliased = {
        "gmv_id": "GMV-PERSON-X",
        "entity_type": "PERSON",
        "canonical_name": "Someone Else",
        "aliases": ["Federico Garibaldi"],
        "status": "active",
    }
    for first, second in ((GARIBALDI, homonym), (homonym, GARIBALDI)):
        registry = _registry(first, second)
        assert resolve_entity_gmv_id("Garibaldi", registry) is None
        assert resolve_entity_gmv_id("Federico Garibaldi", registry) == (
            "GMV-ARTIST-FEDERICO-GARIBALDI"
        )
    for first, second in ((GARIBALDI, aliased), (aliased, GARIBALDI)):
        registry = _registry(first, second)
        assert resolve_entity_gmv_id("Federico Garibaldi", registry) is None
        assert resolve_entity_gmv_id("Garibaldi", registry) == (
            "GMV-ARTIST-FEDERICO-GARIBALDI"
        )
    # A third entity claiming an already-ambiguous name must not
    # re-resolve it back to one of the two.
    three_way = _registry(GARIBALDI, homonym, aliased)
    assert resolve_entity_gmv_id("Garibaldi", three_way) is None
    assert resolve_entity_gmv_id("Federico Garibaldi", three_way) is None
    # ...while an unrelated name in the same ambiguous registry still
    # resolves.
    assert resolve_entity_gmv_id("Someone Else", three_way) == "GMV-PERSON-X"


def test_gmv_id_same_entity_repeating_its_own_name_is_not_ambiguity() -> None:
    """An entity listing its own canonical_name as one of its own aliases
    is one entity, not two -- otherwise a harmless redundancy in a
    hand-curated file would silently un-resolve a real name."""
    registry = _registry({**GARIBALDI, "aliases": ["Garibaldi", "Federico Garibaldi"]})
    assert resolve_entity_gmv_id("Federico Garibaldi", registry) == (
        "GMV-ARTIST-FEDERICO-GARIBALDI"
    )


def test_gmv_id_entry_with_empty_gmv_id_is_skipped_not_returned_as_empty_string() -> None:
    registry = _registry(
        {"gmv_id": "", "entity_type": "ARTIST", "canonical_name": "Federico Garibaldi",
         "aliases": [], "status": "active"},
        GARIBALDI,
    )
    resolved = resolve_entity_gmv_id("Federico Garibaldi", registry)
    assert resolved == "GMV-ARTIST-FEDERICO-GARIBALDI"
    # With no real id behind it at all, the result is None -- never "",
    # which is falsy-but-not-None and would slip past a caller's
    # `if gmv_id is None` check and only fail much later, in
    # gmv_monad_materializer.gmv_id_is_well_formed().
    assert resolve_entity_gmv_id("Federico Garibaldi", _registry(
        {"gmv_id": "", "entity_type": "ARTIST", "canonical_name": "Federico Garibaldi",
         "aliases": [], "status": "active"}
    )) is None


def test_gmv_id_never_touches_network_even_for_unmatched_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resolver, "_classify_via_ollama", fail_if_called)
    monkeypatch.setattr(urllib.request, "urlopen", fail_if_called)
    registry = _registry(GARIBALDI)
    assert resolve_entity_gmv_id("Federico Garibaldi", registry) == (
        "GMV-ARTIST-FEDERICO-GARIBALDI"
    )
    assert resolve_entity_gmv_id(UNKNOWN_NAME, registry) is None


def test_gmv_id_never_creates_or_mutates_registry_state() -> None:
    """An unmatched name must leave the registry exactly as it was, and
    a matched one must not have been back-filled: a lookup that invents
    an id is exactly the auto-registration this function must not do."""
    registry = _registry(GARIBALDI)
    before = json.dumps(registry, sort_keys=True)
    assert resolve_entity_gmv_id(UNKNOWN_NAME, registry) is None
    assert resolve_entity_gmv_id("Federico Garibaldi", registry) is not None
    assert json.dumps(registry, sort_keys=True) == before


def test_committed_entity_registry_file_resolves_its_own_entity() -> None:
    """The real committed file, not a fixture: guards the proof-of-concept
    registry against being renamed/reformatted into something this
    function can no longer read (it is the only entity-registry file
    that exists anywhere in the repository)."""
    data = json.loads(REAL_REGISTRY_PATH.read_text(encoding="utf-8"))
    assert data["entities"], "committed entity registry is empty"
    for entity in data["entities"]:
        gmv_id = resolve_entity_gmv_id(entity["canonical_name"], data)
        assert gmv_id == entity["gmv_id"]
        for alias in entity.get("aliases", []):
            assert resolve_entity_gmv_id(alias, data) == entity["gmv_id"]
        # The gmv_id must also satisfy the format migration 010's own
        # CHECK enforces and gmv_monad_materializer re-expresses in
        # Python (GLOB 'GMV-*' AND length > length('GMV-')).
        assert gmv_id.startswith("GMV-") and len(gmv_id) > len("GMV-")
