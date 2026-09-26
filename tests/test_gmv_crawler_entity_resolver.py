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

import ast
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
    EntityIdentityProposal,
    EntityTypeProposal,
    classify_entity_types,
    confirm_entity_alias,
    confirm_new_entity,
    next_sequential_gmv_id,
    propose_entity_identity,
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
# G7: the loader reads the real file fresh on every call and normalizes
#   nothing in it (unlike the two rosters above, which _forma() every
#   name) -> test_load_entity_registry_reads_the_real_file_fresh_and_unnormalized

REAL_REGISTRY_PATH = ROOT / "00_CONFIG" / "gmv_entity_registry.json"


def _registry(*entities: dict) -> dict:
    return {"note": "test fixture", "entities": list(entities)}


GARIBALDI = {
    "gmv_id": "GMV-000001",
    "entity_type": "ARTIST",
    "canonical_name": "Federico Garibaldi",
    "aliases": ["Garibaldi"],
    "status": "active",
}


def test_load_entity_registry_reads_the_real_file_fresh_and_unnormalized() -> None:
    """G7, same style as test_load_known_artists_is_forma_normalized_frozenset
    above: assert the contract that matters for correctness, on the real
    committed file, not on a fixture.

    The loader's one job is to hand the parser what a human actually
    wrote. Two things could silently break that and neither would show up
    in any other test in this file: a module-level cache (the nightly
    pipeline calls this once per document, and a cached copy would keep
    proposing a name the human has just confirmed for the rest of the
    process), and a normalization borrowed from the two roster loaders --
    `_forma()` collapses token order, so a canonical_name like "Venice
    Biennale" would be stored as "Biennale Venice" and become a
    different string from the one the resolver is asked about.

    Freshness is proved without writing anything: two calls returning two
    distinct objects cannot have come from a cache of the parsed file. The
    committed registry is never modified here, or anywhere in this file
    outside tmp_path (that is guarantee A7's whole subject)."""
    assert resolver.ENTITY_REGISTRY_PATH == REAL_REGISTRY_PATH
    committed = json.loads(REAL_REGISTRY_PATH.read_text(encoding="utf-8"))
    first = resolver._load_entity_registry()
    second = resolver._load_entity_registry()
    assert first is not second, "the registry must be re-read per call, never memoized"
    assert first == second == committed
    assert first["entities"], "committed entity registry is empty"
    # Byte-for-byte, including the name: no _forma(), no lowercasing, no
    # stripping -- resolve_entity_gmv_id() does its own comparison and the
    # loader must not do it twice, differently.
    assert first["entities"] == committed["entities"]
    # ...and the loaded content still resolves through the real resolver,
    # so a loader returning the right keys with the wrong content would
    # not pass this either.
    for entity in first["entities"]:
        assert resolve_entity_gmv_id(entity["canonical_name"], first) == entity["gmv_id"]


def test_gmv_id_resolves_canonical_name_case_and_whitespace_insensitively() -> None:
    registry = _registry(GARIBALDI)
    for name in ("Federico Garibaldi", "federico garibaldi", "FEDERICO GARIBALDI",
                 "  Federico Garibaldi  ", "\nFederico Garibaldi\t"):
        assert resolve_entity_gmv_id(name, registry) == "GMV-000001"


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
    assert resolve_entity_gmv_id("Garibaldi", registry) == "GMV-000001"
    assert resolve_entity_gmv_id(" garibaldi ", registry) == "GMV-000001"
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
            "GMV-000001"
        )
    for first, second in ((GARIBALDI, aliased), (aliased, GARIBALDI)):
        registry = _registry(first, second)
        assert resolve_entity_gmv_id("Federico Garibaldi", registry) is None
        assert resolve_entity_gmv_id("Garibaldi", registry) == (
            "GMV-000001"
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
        "GMV-000001"
    )


def test_gmv_id_entry_with_empty_gmv_id_is_skipped_not_returned_as_empty_string() -> None:
    registry = _registry(
        {"gmv_id": "", "entity_type": "ARTIST", "canonical_name": "Federico Garibaldi",
         "aliases": [], "status": "active"},
        GARIBALDI,
    )
    resolved = resolve_entity_gmv_id("Federico Garibaldi", registry)
    assert resolved == "GMV-000001"
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
        "GMV-000001"
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
        # ...and, since 2026-09-26, every id in the committed file must be
        # in the sequential format the registry's own note now claims --
        # a hand-pasted legacy id back into this file would be silently
        # ignored by next_sequential_gmv_id()'s max, which is a documented
        # behaviour but not one anyone should discover by accident.
        assert re.fullmatch(r"GMV-\d{6,}", gmv_id), gmv_id
    # ...and the ids really are the sequential ones, with none reused: the
    # whole file hands out exactly the next one.
    assert len({e["gmv_id"] for e in data["entities"]}) == len(data["entities"])
    assert next_sequential_gmv_id(data) not in {e["gmv_id"] for e in data["entities"]}


# =========================================================================
# Task 13 (2026-09-26): the "stop and ask" mechanism.
#
# propose_entity_identity() -- a name the resolver could not resolve becomes a
# real, reviewable proposal; next_sequential_gmv_id() /
# confirm_new_entity() / confirm_entity_alias() -- the ONLY code in the repo
# that writes 00_CONFIG/gmv_entity_registry.json, reachable only by an
# explicit human action.
#
# The guarantees these tests try to BREAK, deliberately, one each:
#   P1 "None if the name already resolves, proposal otherwise"
#       -> test_identity_proposal_is_none_for_any_name_that_already_resolves
#   P2 "a real proposal carrying all 4 fields verbatim"
#       -> test_identity_proposal_carries_all_four_fields_verbatim_unnormalized
#   P3 the accepted homonym hazard (proposed even when 2 entities claim the
#      name) -- pinned so it can never be "fixed" by accident
#       -> test_identity_proposal_is_also_produced_for_an_ambiguous_name
#   P4 "a blank name yields legible garbage, not a silent drop"
#       -> test_identity_proposal_for_a_blank_name_is_legible_not_dropped
#   P5 no network, no writes, no registry mutation
#       -> test_identity_proposal_never_touches_network_or_mutates_registry
#   P6 "suggested_entity_type is passed in, never computed here"
#       -> test_identity_proposal_never_derives_the_type_itself
#   N1 "max existing numeric id + 1, GMV-000001 when none"
#       -> test_next_gmv_id_is_max_plus_one_and_starts_at_one
#   N2 "computed from the ids present, never from a stored counter" -- the
#      direct attack is a registry carrying BOTH a gap and a "next_sequence"
#       -> test_next_gmv_id_ignores_a_stored_counter_field_and_uses_the_gap
#   N3 "a non-numeric legacy id is ignored, not an error"
#       -> test_next_gmv_id_ignores_non_numeric_legacy_ids_entirely
#   N4 "only the exact shape counts" -- near-miss shapes must not be parsed
#       -> test_next_gmv_id_never_partially_parses_a_near_miss_id
#   N5 "an over-long id is respected, never clamped"
#       -> test_next_gmv_id_does_not_clamp_an_over_long_id
#   N6 "a malformed entry raises, it is never skipped"
#       -> test_next_gmv_id_raises_on_a_malformed_entry_instead_of_skipping
#   C1 "appends one resolvable entry, returns its real id"
#       -> test_confirm_new_entity_writes_one_entry_that_resolves_back
#   C2 "the sequence advances across repeated confirms; no id is ever reused"
#       -> test_confirm_new_entity_never_reuses_an_id_and_advances_the_sequence
#   C3 "a name that already resolves RAISES, and writes nothing"
#       -> test_confirm_new_entity_refuses_a_name_that_already_resolves
#   C4 "an ambiguous name raises too, and writes nothing"
#       -> test_confirm_new_entity_refuses_an_ambiguous_name
#   C5/C6 "bad entity_type / blank name raise, and write nothing"
#       -> test_confirm_new_entity_rejects_bad_type_and_blank_name_without_writing
#   C7 "touches nothing else in the file"
#       -> test_confirm_new_entity_leaves_every_other_field_untouched
#   C8 "the written id satisfies migration 010's own CHECK; status is never
#       a merge status"   -> test_confirm_new_entity_written_id_satisfies_the_sql_check
#   A1 "adds the alias, and a FRESH resolve finds it"
#       -> test_confirm_entity_alias_writes_and_fresh_resolve_finds_it
#   A2 "unknown gmv_id RAISES (no auto-create), writes nothing"
#       -> test_confirm_entity_alias_raises_on_unknown_id_without_writing
#   A3 "already-present alias is a no-op, byte-identical file"
#       -> test_confirm_entity_alias_is_a_noop_for_an_alias_already_present
#   A4 "blank alias / blank id raise"
#       -> test_confirm_entity_alias_rejects_blank_alias_and_blank_id
#   A5 "never moves or retypes the entity"
#       -> test_confirm_entity_alias_never_changes_the_entity_itself
#   A6 alias membership is exact-string, case-SENSITIVE (SQL-aligned), and
#      a case-variant creates no ambiguity
#       -> test_confirm_entity_alias_membership_is_exact_and_case_sensitive
#   A7 the committed registry is never touched by any of this
#       -> test_no_new_function_ever_writes_the_committed_registry_file

BUCCHI = "Danilo Bucchi"  # real, verified member of area35_known_artists.json


def _write_registry(tmp_path: Path, *entities: dict, **extra) -> Path:
    """A real on-disk registry file, for the WRITE functions only -- every
    other test in this file passes a plain dict, so no test can ever
    touch the committed governance file by accident."""
    path = tmp_path / "gmv_entity_registry.json"
    payload = {"note": "test fixture", "entities": [dict(e) for e in entities], **extra}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _fresh(path: Path) -> dict:
    """Re-read from disk. Deliberately not reused across a write: a
    stale in-memory dict is exactly what would make a write look like it
    took effect when it did not."""
    return json.loads(path.read_text(encoding="utf-8"))


# --- propose_entity_identity() -- the READ half of the loop ---

def test_identity_proposal_is_none_for_any_name_that_already_resolves() -> None:
    """P1, both spellings: an already-known CANONICAL name and an already-
    known ALIAS are both "nothing to propose" -- proposing for either would
    put a duplicate of a known entity in front of a human."""
    registry = _registry(GARIBALDI)
    for known in ("Federico Garibaldi", "federico garibaldi", "  Federico Garibaldi  ", "Garibaldi"):
        assert propose_entity_identity(
            known, registry, source_id="SRC-1", evidence_excerpt="cited"
        ) is None, known
    # ...while an unknown name in the SAME registry is proposed, so the None
    # above is a real resolution and not a function that always returns None.
    assert propose_entity_identity(
        BUCCHI, registry, source_id="SRC-1", evidence_excerpt="cited"
    ) is not None


def test_identity_proposal_carries_all_four_fields_verbatim_unnormalized() -> None:
    """P2: `raw_name` is recorded exactly as received -- not stripped, not
    lower-cased, not _forma()'d. The queue is a record of what was actually
    seen; a "tidied" name would point at a string the resolver could never
    be handed again."""
    registry = _registry(GARIBALDI)
    raw = "  DANILO  Bucchi\t"
    proposal = propose_entity_identity(
        raw, registry, source_id="/A B/c d.pdf.md", evidence_excerpt=' quote "inside" ',
        suggested_entity_type="ARTIST",
    )
    assert proposal == EntityIdentityProposal(
        raw_name=raw,
        suggested_entity_type="ARTIST",
        source_id="/A B/c d.pdf.md",
        evidence_excerpt=' quote "inside" ',
    )


def test_identity_proposal_is_also_produced_for_an_ambiguous_name() -> None:
    """P3, the ACCEPTED limitation, pinned so it cannot be quietly changed:
    `resolve_entity_gmv_id()` returns None both for "unknown" and for
    "claimed by two entities", and `propose_entity_identity()` cannot tell
    them apart. So a homonym DOES get a "consider a new entity" proposal
    here. The alternative -- hiding those cases -- was rejected (see the
    function's docstring, point 1); this test exists so the cost is a
    decision on record, not an accident."""
    registry = _registry(
        GARIBALDI,
        {"gmv_id": "GMV-000002", "entity_type": "PERSON", "canonical_name": "Garibaldi",
         "aliases": [], "status": "ACTIVE"},
    )
    assert resolve_entity_gmv_id("Garibaldi", registry) is None
    assert propose_entity_identity(
        "Garibaldi", registry, source_id="SRC-1", evidence_excerpt="cited"
    ) == EntityIdentityProposal(
        raw_name="Garibaldi", suggested_entity_type="", source_id="SRC-1",
        evidence_excerpt="cited",
    )


def test_identity_proposal_for_a_blank_name_is_legible_not_dropped() -> None:
    """P4: a blank name resolves to None, so a caller filtering on "the
    resolver said None" could not distinguish "unknown name" from "you
    passed nothing" -- and would have to drop blank names silently. A
    proposal carrying the empty name is visible garbage a human can see
    in the queue; a dropped one is an invisible extraction bug."""
    registry = _registry(GARIBALDI)
    for blank in ("", "   ", "\t\n"):
        proposal = propose_entity_identity(
            blank, registry, source_id="SRC-1", evidence_excerpt="cited"
        )
        assert proposal is not None, repr(blank)
        assert proposal.raw_name == blank


def test_identity_proposal_never_touches_network_or_mutates_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P5: the whole point of the read half is that looking up a name --
    succeeding OR failing -- has no effect and costs nothing. `urlopen`
    and `_classify_via_ollama` are both patched to FAIL, so an accidental
    network call surfaces as a test failure instead of a silent Ollama hit."""
    monkeypatch.setattr(resolver, "_classify_via_ollama", fail_if_called)
    monkeypatch.setattr(urllib.request, "urlopen", fail_if_called)
    registry = _registry(GARIBALDI)
    before = json.dumps(registry, sort_keys=True)
    assert propose_entity_identity(
        BUCCHI, registry, source_id="SRC-1", evidence_excerpt="cited"
    ) is not None
    assert propose_entity_identity(
        "Federico Garibaldi", registry, source_id="SRC-1", evidence_excerpt="cited"
    ) is None
    assert json.dumps(registry, sort_keys=True) == before


def test_identity_proposal_never_derives_the_type_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P6: the default is the empty string, and a caller-supplied type is
    passed through untouched -- this function never calls the model. If it
    ever did, one name would get two independent, unreconcilable type
    answers and generating an identity proposal would cost a network call
    on a code path whose contract is "cheap, mechanical, no network"."""
    monkeypatch.setattr(resolver, "_classify_via_ollama", fail_if_called)
    monkeypatch.setattr(urllib.request, "urlopen", fail_if_called)
    registry = _registry(GARIBALDI)
    default = propose_entity_identity(
        BUCCHI, registry, source_id="SRC-1", evidence_excerpt="cited"
    )
    assert default is not None and default.suggested_entity_type == ""
    # Passed through verbatim -- NOT validated here. An empty type is a real
    # state (the caller had none); an ungoverned one is confirm_new_entity()'s
    # problem to reject, at the write boundary, not this function's.
    supplied = propose_entity_identity(
        BUCCHI, registry, source_id="SRC-1", evidence_excerpt="cited",
        suggested_entity_type="NOT_A_GOVERNED_TYPE",
    )
    assert supplied is not None
    assert supplied.suggested_entity_type == "NOT_A_GOVERNED_TYPE"


# --- next_sequential_gmv_id() -- arithmetic over the ids present ---

def test_next_gmv_id_is_max_plus_one_and_starts_at_one() -> None:
    """N1: the two ends. An empty registry starts at GMV-000001, and
    otherwise the answer is the HIGHEST id + 1 -- not the number of
    entries + 1 (pinned by the gap case in the next test)."""
    assert next_sequential_gmv_id(_registry()) == "GMV-000001"
    assert next_sequential_gmv_id({"entities": []}) == "GMV-000001"
    assert next_sequential_gmv_id(_registry(GARIBALDI)) == "GMV-000002"
    assert next_sequential_gmv_id(_registry(
        GARIBALDI,
        {"gmv_id": "GMV-000009", "entity_type": "ARTIST", "canonical_name": "X",
         "aliases": [], "status": "ACTIVE"},
    )) == "GMV-000010"
    # Order-independent: the same registry shuffled gives the same answer.
    assert next_sequential_gmv_id(_registry(
        {"gmv_id": "GMV-000009", "entity_type": "ARTIST", "canonical_name": "X",
         "aliases": [], "status": "ACTIVE"},
        GARIBALDI,
    )) == "GMV-000010"


def test_next_gmv_id_ignores_a_stored_counter_field_and_uses_the_gap() -> None:
    """N2, the direct attack on the "no stored counter" rule. The registry
    carries BOTH a deliberate gap in its ids AND a `next_sequence` field
    left behind by hand -- exactly the second-source-of-truth the audit
    rejected. The gap must win: GMV-000009 present means the next id is
    GMV-000010, and the counter claiming 99 (or 3) must be ignored. A
    count-based implementation returns GMV-000003 here and a
    counter-reading one returns GMV-000099."""
    registry = _registry(
        GARIBALDI,  # GMV-000001
        {"gmv_id": "GMV-000009", "entity_type": "ARTIST", "canonical_name": "X",
         "aliases": [], "status": "ACTIVE"},
    )
    registry["next_sequence"] = 99
    registry["next_gmv_id"] = "GMV-000099"
    assert next_sequential_gmv_id(registry) == "GMV-000010"
    # And the function must not have invented the field either.
    assert "next_sequence" in registry and registry["next_sequence"] == 99


def test_next_gmv_id_ignores_non_numeric_legacy_ids_entirely() -> None:
    """N3: the pre-retrofit content-derived id is IGNORED, not an error and
    not parsed leniently. This is the state the registry was actually in
    before Step 1 of this task, and it must produce a usable id rather
    than crash or -- worse -- derive a number from "ARTIST"."""
    legacy = {"gmv_id": "GMV-ARTIST-FEDERICO-GARIBALDI", "entity_type": "ARTIST",
              "canonical_name": "Federico Garibaldi", "aliases": [], "status": "ACTIVE"}
    assert next_sequential_gmv_id(_registry(legacy)) == "GMV-000001"
    # Mixed: the legacy id must not stop the numeric ones being counted.
    assert next_sequential_gmv_id(_registry(
        legacy, GARIBALDI, {"gmv_id": "GMV-000002", "entity_type": "ARTIST",
                            "canonical_name": "X", "aliases": [], "status": "ACTIVE"},
    )) == "GMV-000003"
    # A blank id is skipped, exactly as resolve_entity_gmv_id() skips it.
    assert next_sequential_gmv_id(_registry(
        {**GARIBALDI, "gmv_id": ""}
    )) == "GMV-000001"


def test_next_gmv_id_never_partially_parses_a_near_miss_id() -> None:
    """N4: an id that is NOT exactly GMV-<6-or-more digits> contributes
    NOTHING, even when a lenient parser would find digits inside it. The
    attack case is "GMV-000001-extra": a `search`/substring
    implementation would read 000001 and hand back a number in the middle
    of the real sequence, colliding with an id that already exists. The
    lowercase and space-padded variants are the same attack in different
    clothes."""
    assert next_sequential_gmv_id(_registry(
        {"gmv_id": "GMV-000001-extra", "entity_type": "ARTIST", "canonical_name": "X",
         "aliases": [], "status": "ACTIVE"},
    )) == "GMV-000001"
    for near_miss in ("GMV-000001-extra", "gmv-000005", " GMV-000005", "GMV-000005 ",
                      "XGMV-000005", "GMV-", "GMV-00000A", "GMV-0000012x",
                      "GMV-00000", "GMV-0000", "GMV-ARTIST-000005", "GMV-+005"):
        registry = _registry(
            GARIBALDI,
            {"gmv_id": near_miss, "entity_type": "ARTIST", "canonical_name": "X",
             "aliases": [], "status": "ACTIVE"},
        )
        assert next_sequential_gmv_id(registry) == "GMV-000002", near_miss


def test_next_gmv_id_does_not_clamp_an_over_long_id() -> None:
    """N5: 6 digits is a MINIMUM width for what is COUNTED, but the value
    handed back is always re-padded to that minimum -- clamping the COUNT
    to 6 digits instead would re-issue an id that already exists, the
    exact collision this function exists to prevent. So `GMV-1234567`
    yields `GMV-1234568` (still 7 digits, nothing truncated), while
    `GMV-0000017` yields `GMV-000018` -- number 18, re-padded, which is
    still strictly greater than every id in the file and therefore still
    cannot collide. The invariant is pinned directly below."""
    assert next_sequential_gmv_id(_registry(
        {"gmv_id": "GMV-1234567", "entity_type": "ARTIST", "canonical_name": "X",
         "aliases": [], "status": "ACTIVE"},
    )) == "GMV-1234568"
    assert next_sequential_gmv_id(_registry(
        {"gmv_id": "GMV-0000017", "entity_type": "ARTIST", "canonical_name": "X",
         "aliases": [], "status": "ACTIVE"},
    )) == "GMV-000018"
    assert len("GMV-1234568") > len("GMV-000001")
    # The real guarantee, over a deliberately adversarial id set: the
    # returned id is never one of the ids already in the registry.
    ids = ["GMV-000001", "GMV-0000017", "GMV-1234567", "GMV-999999", "GMV-000010"]
    registry = _registry(*[
        {"gmv_id": i, "entity_type": "ARTIST", "canonical_name": i, "aliases": [],
         "status": "ACTIVE"}
        for i in ids
    ])
    assert next_sequential_gmv_id(registry) == "GMV-1234568"
    assert next_sequential_gmv_id(registry) not in ids


def test_next_gmv_id_raises_on_a_malformed_entry_instead_of_skipping() -> None:
    """N6: same rule as resolve_entity_gmv_id()'s point 5 -- a broken
    hand-curated governance file is a caller bug, and quietly ignoring the
    entry that does not parse is how a real entity stops resolving with
    nobody told."""
    with pytest.raises(KeyError):
        next_sequential_gmv_id({"entities": [{"entity_type": "ARTIST",
                                              "canonical_name": "X"}]})
    with pytest.raises(TypeError):
        next_sequential_gmv_id({"entities": ["not-a-dict"]})
    with pytest.raises(TypeError) as excinfo:
        next_sequential_gmv_id({"entities": [{"gmv_id": 7, "entity_type": "ARTIST",
                                              "canonical_name": "X", "aliases": []}]})
    assert "must be a string" in str(excinfo.value)


# --- confirm_new_entity() -- the ONLY new-entity write, human-triggered ---

def test_confirm_new_entity_writes_one_entry_that_resolves_back(tmp_path: Path) -> None:
    """C1: the whole point, on a real file. Returns GMV-000002 (NOT
    GMV-000001, which Garibaldi already holds -- re-issuing it would put
    two entities behind one id), the file on disk gains exactly one entry,
    and a FRESH read resolves the new name to the returned id."""
    path = _write_registry(tmp_path, GARIBALDI)
    new_id = confirm_new_entity(BUCCHI, "ARTIST", path)
    assert new_id == "GMV-000002"
    data = _fresh(path)
    assert len(data["entities"]) == 2
    assert resolve_entity_gmv_id(BUCCHI, data) == "GMV-000002"
    assert resolve_entity_gmv_id("Federico Garibaldi", data) == "GMV-000001"  # untouched
    assert data["entities"][1] == {
        "gmv_id": "GMV-000002", "entity_type": "ARTIST",
        "canonical_name": BUCCHI, "aliases": [], "status": "ACTIVE",
    }
    # The canonical name resolves EXACTLY, and a name variant does not:
    # a new entity starts with no aliases, it does not invent them.
    assert resolve_entity_gmv_id("  danilo bucchi ", data) == "GMV-000002"
    assert resolve_entity_gmv_id("D. Bucchi", data) is None


def test_confirm_new_entity_never_reuses_an_id_and_advances_the_sequence(
    tmp_path: Path,
) -> None:
    """C2: three confirms in a row produce three DISTINCT, increasing ids
    and the file really holds all three. A function that computed the id
    from an in-memory count, or that cached anything, would re-issue
    GMV-000002 here."""
    path = _write_registry(tmp_path, GARIBALDI)
    ids = [confirm_new_entity(name, "ARTIST", path) for name in ("A Uno", "B Due", "C Tre")]
    assert ids == ["GMV-000002", "GMV-000003", "GMV-000004"]
    data = _fresh(path)
    assert [e["gmv_id"] for e in data["entities"]] == ["GMV-000001", *ids]
    assert len({e["gmv_id"] for e in data["entities"]}) == 4
    for gmv_id, name in zip(ids, ("A Uno", "B Due", "C Tre"), strict=True):
        assert resolve_entity_gmv_id(name, data) == gmv_id


def test_confirm_new_entity_refuses_a_name_that_already_resolves(tmp_path: Path) -> None:
    """C3: the realistic human error -- confirming a name that is already
    registered, canonical OR alias. It must RAISE and leave the file
    byte-identical: a silent second entry would split one real entity in
    two (the eager-splitting risk the audit accepts) while LOOKING like a
    successful confirmation to whoever called it. `confirm_institution()`
    returns an "already there" string instead, but this function's return
    value IS the new id, and there is no honest id to return."""
    path = _write_registry(tmp_path, GARIBALDI)
    before = path.read_bytes()
    for known in ("Federico Garibaldi", "federico  garibaldi".replace("  ", " "),
                  "Garibaldi", "  GARIBALDI "):
        with pytest.raises(ValueError) as excinfo:
            confirm_new_entity(known, "ARTIST", path)
        assert "confirm_entity_alias" in str(excinfo.value), known
    assert path.read_bytes() == before
    assert len(_fresh(path)["entities"]) == 1


def test_confirm_new_entity_refuses_an_ambiguous_name(tmp_path: Path) -> None:
    """C4: the homonym case. Two entities already claim "Garibaldi", so the
    resolver answers None -- and None must NOT read as "unknown, safe to
    create". Confirming here would add a THIRD record for a name two
    entities own. The check reuses the resolver's own ambiguity rule, so
    this is caught without a second matching implementation."""
    homonym = {"gmv_id": "GMV-000002", "entity_type": "PERSON",
               "canonical_name": "Garibaldi", "aliases": [], "status": "ACTIVE"}
    path = _write_registry(tmp_path, GARIBALDI, homonym)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        confirm_new_entity("Garibaldi", "PERSON", path)
    assert path.read_bytes() == before
    assert len(_fresh(path)["entities"]) == 2


def test_confirm_new_entity_rejects_bad_type_and_blank_name_without_writing(
    tmp_path: Path,
) -> None:
    """C5/C6: every rejection happens BEFORE the file is touched. A
    not-governed entity_type (a typo, or a CANDIDATE/DEPRECATED class_id
    migration 010 deliberately excludes) would otherwise be written into a
    governance file and only surface much later; a blank canonical_name
    would create an entry the resolver skips forever -- written, counted in
    the sequence, and resolving nothing, i.e. looking like success."""
    path = _write_registry(tmp_path, GARIBALDI)
    before = path.read_bytes()
    for bad_type in ("SUPERHERO", "ARTWORK", "SPONSOR", "CONTRACT", "artist", ""):
        with pytest.raises(ValueError) as excinfo:
            confirm_new_entity("A Uno", bad_type, path)
        assert "not a governed entity_type" in str(excinfo.value), bad_type
    for blank in ("", "   ", "\t\n"):
        with pytest.raises(ValueError) as excinfo:
            confirm_new_entity(blank, "ARTIST", path)
        assert "blank" in str(excinfo.value), repr(blank)
    assert path.read_bytes() == before
    # A valid pair right after all those failures still works, and gets the
    # id the rejected calls did not consume.
    assert confirm_new_entity("A Uno", "ARTIST", path) == "GMV-000002"


def test_confirm_new_entity_leaves_every_other_field_untouched(tmp_path: Path) -> None:
    """C7: only one entity is appended. The note fields, the existing
    entry's gmv_id/entity_type/canonical_name/aliases/status -- including
    a non-default status someone set by hand -- must all survive
    unchanged. A whole-file rebuild that dropped unknown top-level keys
    (the "note"/"note_on_maintenance" governance text) is the specific
    failure this pins."""
    legacy_status = {**GARIBALDI, "status": "MERGE_CANDIDATE", "aliases": ["Garibaldi", "Il Generale"]}
    path = _write_registry(
        tmp_path, legacy_status,
        note="hand-written governance note", note_on_maintenance="do not auto-populate",
    )
    before = _fresh(path)
    assert confirm_new_entity(BUCCHI, "ARTIST", path) == "GMV-000002"
    after = _fresh(path)
    assert after["note"] == before["note"]
    assert after["note_on_maintenance"] == before["note_on_maintenance"]
    assert after["entities"][0] == before["entities"][0]
    assert after["entities"][0]["status"] == "MERGE_CANDIDATE"  # not normalised to ACTIVE
    assert after["entities"][0]["aliases"] == ["Garibaldi", "Il Generale"]
    assert len(after["entities"]) == 2


def test_confirm_new_entity_written_id_satisfies_the_sql_check(tmp_path: Path) -> None:
    """C8: the id really written must satisfy migration 010's own CHECK
    (`GLOB 'GMV-*' AND length > length('GMV-')`) and re-expressed by
    gmv_monad_materializer.gmv_id_is_well_formed() -- a BLOCKER waiting
    far downstream if it does not. And the new entry must never carry a
    merge status or a merged_into key: status=MERGE_CANDIDATE/MERGED is
    the human merge-repair vocabulary of the deliberately-unbuilt Layer 2,
    and a write that could set it could assert a merge nobody made."""
    path = _write_registry(tmp_path, GARIBALDI)
    new_id = confirm_new_entity(BUCCHI, "ARTIST", path)
    assert new_id.startswith("GMV-") and len(new_id) > len("GMV-")
    entry = _fresh(path)["entities"][-1]
    assert entry["status"] == "ACTIVE"
    assert "merged_into" not in entry
    assert set(entry) == {"gmv_id", "entity_type", "canonical_name", "aliases", "status"}


# --- confirm_entity_alias() -- the only alias write, human-triggered ---

def test_confirm_entity_alias_writes_and_fresh_resolve_finds_it(tmp_path: Path) -> None:
    """A1: the real loop-closing move for a name VARIANT -- a fresh read of
    the file resolves the variant to the same id, which is exactly what
    `resolve_entity_gmv_id()`'s point 2 defers to a human ("a real
    'Garibaldi, Federico' variant failing to match is reportable evidence
    for a human to add the alias")."""
    path = _write_registry(tmp_path, GARIBALDI)
    assert resolve_entity_gmv_id("Il Generale", _fresh(path)) is None
    message = confirm_entity_alias("GMV-000001", "Il Generale", path)
    assert "Il Generale" in message and "GMV-000001" in message
    data = _fresh(path)
    assert data["entities"][0]["aliases"] == ["Garibaldi", "Il Generale"]
    assert resolve_entity_gmv_id("il generale", data) == "GMV-000001"
    assert resolve_entity_gmv_id("Federico Garibaldi", data) == "GMV-000001"
    # The write was a read-modify-write of one list, not a rebuild.
    assert len(data["entities"]) == 1


def test_confirm_entity_alias_raises_on_unknown_id_without_writing(
    tmp_path: Path,
) -> None:
    """A2: the id must EXIST. The realistic failure is a human typing
    GMV-00001 for GMV-000001, so that near-miss is the pinned case -- it
    must raise and write nothing, never fall through to "no entity, create
    one", which is the auto-registration this whole human-confirmed half
    exists to prevent. The message lists the ids that DO exist."""
    path = _write_registry(tmp_path, GARIBALDI)
    before = path.read_bytes()
    for wrong in ("GMV-00001", "GMV-999999", "gmv-000001", " GMV-000001", "GARIBALDI"):
        with pytest.raises(ValueError) as excinfo:
            confirm_entity_alias(wrong, "Il Generale", path)
        assert "GMV-000001" in str(excinfo.value), wrong
        assert "confirm_new_entity" in str(excinfo.value), wrong
    assert path.read_bytes() == before
    assert len(_fresh(path)["entities"]) == 1


def test_confirm_entity_alias_is_a_noop_for_an_alias_already_present(
    tmp_path: Path,
) -> None:
    """A3: mirroring confirm_institution()'s "era gia' nell'elenco" case --
    a no-op with a clear message and a BYTE-IDENTICAL file, never a second
    copy of the same alias."""
    path = _write_registry(tmp_path, GARIBALDI)
    before = path.read_bytes()
    message = confirm_entity_alias("GMV-000001", "Garibaldi", path)
    assert "already" in message
    assert path.read_bytes() == before
    assert _fresh(path)["entities"][0]["aliases"] == ["Garibaldi"]


def test_confirm_entity_alias_rejects_blank_alias_and_blank_id(tmp_path: Path) -> None:
    """A4: a blank alias resolves to nothing (the resolver skips empty
    strings), so storing one is data that can never be used; a blank id
    has no entity to attach to. Both raise before any write."""
    path = _write_registry(tmp_path, GARIBALDI)
    before = path.read_bytes()
    for blank in ("", "   ", "\t\n"):
        with pytest.raises(ValueError) as excinfo:
            confirm_entity_alias("GMV-000001", blank, path)
        assert "blank" in str(excinfo.value), repr(blank)
        with pytest.raises(ValueError):
            confirm_entity_alias(blank, "Il Generale", path)
    assert path.read_bytes() == before


def test_confirm_entity_alias_never_changes_the_entity_itself(tmp_path: Path) -> None:
    """A4/A5, the guarantee the spec calls out: an alias must not be able
    to MOVE or RETYPE an entity. gmv_id must stay "indipendente dal nome
    corrente" -- the audit's Q1 rejection of content-derived ids rests on
    exactly that -- and entity_type/status/canonical_name are not this
    function's to touch. A second entity must stay untouched too."""
    path = _write_registry(
        tmp_path, GARIBALDI,
        {"gmv_id": "GMV-000002", "entity_type": "PERSON", "canonical_name": "Other",
         "aliases": ["Someone"], "status": "ACTIVE"},
    )
    before = _fresh(path)
    confirm_entity_alias("GMV-000001", "Il Generale", path)
    after = _fresh(path)
    assert after["entities"][1] == before["entities"][1]  # other entity untouched
    changed = {k: v for k, v in after["entities"][0].items() if v != before["entities"][0][k]}
    assert changed == {"aliases": ["Garibaldi", "Il Generale"]}


def test_confirm_entity_alias_membership_is_exact_and_case_sensitive(
    tmp_path: Path,
) -> None:
    """A6: exact-string membership, no case folding -- the same rule
    migration 010's own comment states for UNIQUE(entity_gmv_id, alias)
    ("'F. Garibaldi' and 'f. garibaldi' are distinct rows"). And the
    resulting pair is harmless, not ambiguous: both spellings belong to
    the SAME entity, so resolve_entity_gmv_id() still returns one id and
    the homonym rule does not fire."""
    path = _write_registry(tmp_path, GARIBALDI)
    confirm_entity_alias("GMV-000001", "F. Garibaldi", path)
    confirm_entity_alias("GMV-000001", "f. garibaldi", path)
    data = _fresh(path)
    assert data["entities"][0]["aliases"] == ["Garibaldi", "F. Garibaldi", "f. garibaldi"]
    assert resolve_entity_gmv_id("F. Garibaldi", data) == "GMV-000001"
    assert resolve_entity_gmv_id("f. garibaldi", data) == "GMV-000001"
    # A THIRD spelling is also accepted, because membership is exact and
    # case-sensitive: this is the SQL's documented behaviour, not an
    # oversight. It creates no ambiguity -- all three belong to the SAME
    # entity, so the resolver still returns one id.
    confirm_entity_alias("GMV-000001", "F. GARIBALDI", path)
    data = _fresh(path)
    assert data["entities"][0]["aliases"] == [
        "Garibaldi", "F. Garibaldi", "f. garibaldi", "F. GARIBALDI",
    ]
    assert resolve_entity_gmv_id("F. GARIBALDI", data) == "GMV-000001"
    assert len({e["gmv_id"] for e in data["entities"]}) == 1
    # Re-adding an EXISTING spelling is still a no-op (exact match), and
    # writes nothing.
    before = path.read_bytes()
    assert "already" in confirm_entity_alias("GMV-000001", "f. garibaldi", path)
    assert path.read_bytes() == before


def test_confirm_entity_alias_tolerates_a_hand_typed_entry_with_no_aliases_key(
    tmp_path: Path,
) -> None:
    """The one shape of registry file this repo actually contains, attacked
    directly: `aliases` is OPTIONAL (a human adding an entity by hand may
    leave the key out entirely), and `resolve_entity_gmv_id()` already reads
    it with `.get("aliases", ())`. The write half must not be stricter than
    the read half of the same module -- a bare `KeyError: 'aliases'` at the
    moment a human asked to add the one alias they wanted would be the worst
    possible failure. The alias is added, the key is materialized as the
    list the schema implies, and the entry is still resolvable afterwards."""
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"note": "hand-typed", "entities": [
        {"gmv_id": "GMV-000001", "entity_type": "ARTIST",
         "canonical_name": "Federico Garibaldi", "status": "ACTIVE"},
    ]}), encoding="utf-8")
    # Precondition: the read half already tolerates the missing key.
    assert resolve_entity_gmv_id("Federico Garibaldi", _fresh(path)) == "GMV-000001"
    assert "aliases" not in _fresh(path)["entities"][0]

    assert "Confirmed" in confirm_entity_alias("GMV-000001", "Garibaldi", path)
    data = _fresh(path)
    assert data["entities"][0]["aliases"] == ["Garibaldi"]
    assert isinstance(data["entities"][0]["aliases"], list)
    assert resolve_entity_gmv_id("Garibaldi", data) == "GMV-000001"
    # And the no-op path on such an entry is a no-op, not a crash.
    before = path.read_bytes()
    assert "already" in confirm_entity_alias("GMV-000001", "Garibaldi", path)
    assert path.read_bytes() == before


def test_no_new_function_ever_writes_the_committed_registry_file(tmp_path: Path) -> None:
    """A7, the cross-cutting boundary. `confirm_institution()` writes
    00_CONFIG/area35_known_institutions.json from a chat tool; these
    functions take a caller-supplied path and are wired to nothing, so the
    committed governance file can only change by a human editing it. A full
    propose->confirm->alias cycle runs against a tmp copy here, and the
    committed file must be byte-identical afterwards."""
    before = REAL_REGISTRY_PATH.read_bytes()
    copy_path = tmp_path / "registry-copy.json"
    copy_path.write_bytes(before)
    registry = _fresh(copy_path)
    assert propose_entity_identity(
        BUCCHI, registry, source_id="SRC-1", evidence_excerpt="cited"
    ) is not None
    assert confirm_new_entity(BUCCHI, "ARTIST", copy_path) == "GMV-000002"
    confirm_entity_alias("GMV-000002", "D. Bucchi", copy_path)
    assert len(_fresh(copy_path)["entities"]) == 2
    assert REAL_REGISTRY_PATH.read_bytes() == before


_HUMAN_GATED_CALLER = "automation/gmv_crawler_review_tool.py"


@pytest.mark.parametrize("callee", ["confirm_new_entity", "confirm_entity_alias"])
def test_no_production_module_calls_a_registry_write_function(callee: str) -> None:
    """A7, the other half, UPDATED 2026-09-26: the invariant this test
    protects was never "zero callers ever" -- it is "no UNATTENDED write is
    possible". Until the Open WebUI wiring existed, those were the same
    thing, so the original assertion (`callers == []`) was correct for the
    right reason by coincidence. Now that
    `automation/gmv_crawler_review_tool.py::confirm_new_entity`/
    `confirm_entity_alias` exist as the human-gated entry point (the same
    role `confirm_institution()` already plays for institutions), a real
    caller exists on purpose, and the test must tell that ONE allowed
    caller apart from a real regression (the crawler pipeline itself --
    orchestrator, nightly_run, an atom builder -- calling a write function
    directly, bypassing the human gate), not just count callers.

    Resolves `from gmv_crawler_entity_resolver import X [as Y]` aliases via
    `ast.ImportFrom` in each module BEFORE matching calls, rather than
    guessing a naming convention (e.g. a leading underscore) for the local
    name -- the tool file happens to alias these as `_confirm_new_entity`/
    `_confirm_entity_alias` today (avoiding a same-name shadow with its own
    method of the same name), but a convention-based string match would
    silently stop working the moment that alias spelling changed, which is
    exactly the kind of blind spot this test exists to not have. Checked
    with `ast`, not a substring search, for the original module docstring's
    own reason: the two docstrings in `gmv_crawler_entity_resolver.py`, in
    the identity queue module, and in the registry's own `note` all NAME
    these functions on purpose, and a naive `in source` scan would flag
    that documentation as a caller."""
    callers: list[str] = []
    for relative in ("01_RUNTIME", "10_API", "automation", "gmv_core"):
        for module in sorted((ROOT / relative).rglob("*.py")):
            if module.name == "gmv_crawler_entity_resolver.py":
                continue  # the definitions themselves
            tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
            local_names = {callee}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "gmv_crawler_entity_resolver":
                    for alias in node.names:
                        if alias.name == callee:
                            local_names.add(alias.asname or alias.name)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = (
                    func.id if isinstance(func, ast.Name)
                    else func.attr if isinstance(func, ast.Attribute)
                    else None
                )
                if name in local_names:
                    callers.append(f"{module.relative_to(ROOT)}:{node.lineno}")
    unattended = [c for c in callers if not c.startswith(_HUMAN_GATED_CALLER)]
    assert unattended == [], (
        f"{callee} is called from unattended production code (never the human-gated "
        f"tool): {unattended}"
    )
    assert callers, (
        f"{callee} is called from nowhere in production, not even the human-gated tool -- "
        "if automation/gmv_crawler_review_tool.py's wiring was removed, that is a real "
        "regression this test should catch, not silently pass on zero callers."
    )
