"""GMV Crawler — BUILD ATOMS v0 (task brief opencode_task_6.md): the
narrow ATTRIBUTE-only slice of gmv_crawler_atom_builder.py.

Cross-checks the module's hardcoded ATTRIBUTE predicate set against the
real, already-committed GMV_ONTOLOGY_REGISTRY_v0.1.json (the import-time
guard and a direct registry read here, not a duplicated hardcoded list),
and reserves one alias-resolution case (evidences -> source_for) to make
sure a governed alias is not treated as an unrelated raw string.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

from gmv_atom_validator import validate_atom  # noqa: E402
from gmv_crawler_atom_builder import (  # noqa: E402
    RejectedCandidate,
    build_atom,
    build_atoms,
)
from gmv_crawler_candidate_extractor import CandidateProposition  # noqa: E402

ONTOLOGY_REGISTRY_PATH = ROOT / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_v0.1.json"

NOW = "2026-09-16T00:00:00Z"


def make_proposition(**overrides) -> CandidateProposition:
    fields = {
        "subject_raw": "Federico Garibaldi",
        "predicate": "edition_size",
        "object_raw": "3",
        "evidence_excerpt": "l'edition è di 3 esemplari",
        "status": "DOCUMENTATO",
        "source_id": "SRC-EVID-42",
        "evidence_id": ("EV-1",),
        "truncated_source": False,
        "extraction_claim_ref": "CLAIM-007",
    }
    fields.update(overrides)
    return CandidateProposition(**fields)


# --- registry grounding ---

def test_module_attribute_literal_predicate_object_types_matches_real_registry() -> None:
    """Renamed 2026-09-27 (opencode_task_16.md) because the shape it asserts
    changed: this module no longer builds "the ATTRIBUTE/integer" set, it
    builds every ATTRIBUTE predicate with a single LITERAL range and
    derives each one's object_type from the registry entry. A set of ids
    can no longer express the thing that matters, which is the id ->
    object_type pairing, so this asserts the mapping.

    Still an independent `json.loads()` of the real, already-committed
    registry file here -- not a duplicated hardcoded list and not a trust
    of the module's own computation. The module's own import-time guard
    would already have raised before this body ran if the file and the
    module's pinned expectation disagreed, which is why the expectations
    below are also checked against the file directly rather than against
    the module's own constant."""
    import json

    import gmv_crawler_atom_builder as module

    registry = json.loads(ONTOLOGY_REGISTRY_PATH.read_text(encoding="utf-8"))
    real = {
        e["predicate_id"]: e["range"][0]
        for e in registry["predicates"]
        if e["predicate_class"] == "ATTRIBUTE" and e.get("range") in (["integer"], ["string"])
    }
    assert real == {
        "edition_size": "integer",
        "edition_number": "integer",
        "creation_year": "integer",
        "dimensions": "string",
        "medium": "string",
    }
    # The module's derived mapping, computed at import from that same file:
    assert module._ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES == real
    # And the fail-loud guard's own pinned expectation, so the literal the
    # module refuses to run without cannot quietly drift from the file:
    assert module._EXPECTED_ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES == real

    # The scope filter's exclusion half, which the assertions above cannot
    # see: every predicate the module must NOT build is excluded because
    # its range is entity-typed or ['ANY'], and all of them are RELATION
    # today. Pinned so that adding a RELATION predicate later does not
    # look like a scope change, and so that a future entity-ranged
    # ATTRIBUTE predicate is visibly a decision rather than a silent
    # widening.
    excluded = {
        e["predicate_id"] for e in registry["predicates"]
        if e["predicate_class"] == "ATTRIBUTE" and e.get("range") not in (["integer"], ["string"])
    }
    assert excluded == set(), f"new non-literal ATTRIBUTE predicate(s) appeared: {sorted(excluded)}"
    non_attribute_in_map = {
        pid for pid in module._ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES
        if pid not in real
    }
    assert non_attribute_in_map == set()
    for entry in registry["predicates"]:
        if entry["predicate_class"] != "ATTRIBUTE":
            assert entry["predicate_id"] not in module._ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES


# --- edition_size valid -> every field exact ---

def test_build_atom_edition_size_valid_all_fields_exact() -> None:
    atom = build_atom(
        make_proposition(object_raw=" 3 "), now=NOW,
    )
    assert isinstance(atom, RejectedCandidate) is False
    assert atom.predicate == "edition_size"
    assert atom.subject == "Federico Garibaldi"  # verbatim, no normalization
    assert atom.predicate_class == "ATTRIBUTE"
    assert atom.object == "3"  # stripped of surrounding whitespace
    assert atom.object_type == "integer"
    assert atom.source == "SRC-EVID-42"
    assert atom.status == "UNVERIFIED"
    assert atom.valid_from is None
    assert atom.valid_to is None
    assert atom.asserted_at == NOW
    assert atom.ingested_at == NOW
    assert atom.asserted_by == "crawler_llm_extraction"
    assert atom.confidence == 0.5
    assert atom.visibility == "INTERNAL"
    assert atom.end_reason is None
    assert atom.supersedes is None
    assert atom.superseded_by is None
    assert len(atom.atom_id) == 5 + 16  # "ATOM-" prefix + 16 hex chars


def test_build_atom_edition_number_valid_all_fields_exact() -> None:
    atom = build_atom(
        make_proposition(predicate="edition_number", object_raw="1", extraction_claim_ref="CLAIM-008"),
        now=NOW,
    )
    assert isinstance(atom, RejectedCandidate) is False
    assert atom.predicate == "edition_number"
    assert atom.subject == "Federico Garibaldi"
    assert atom.predicate_class == "ATTRIBUTE"
    assert atom.object == "1"
    assert atom.object_type == "integer"
    assert atom.source == "SRC-EVID-42"
    assert atom.status == "UNVERIFIED"
    assert atom.valid_from is None
    assert atom.valid_to is None
    assert atom.asserted_at == NOW
    assert atom.ingested_at == NOW
    assert atom.asserted_by == "crawler_llm_extraction"
    assert atom.confidence == 0.5
    assert atom.visibility == "INTERNAL"
    assert atom.end_reason is None
    assert atom.supersedes is None
    assert atom.superseded_by is None


# --- creation_year / dimensions / medium: the three predicates the
# --- 2026-09-27 registry widening added (opencode_task_16.md) ---

def test_build_atom_creation_year_valid_all_fields_exact() -> None:
    """Same style and same fixed literals as the two integer tests above,
    unchanged: the point is that a THIRD integer-range predicate produces
    byte-identical field behaviour, not a new code path."""
    atom = build_atom(
        make_proposition(predicate="creation_year", object_raw="2013",
                         extraction_claim_ref="CLAIM-016"),
        now=NOW,
    )
    assert isinstance(atom, RejectedCandidate) is False
    assert atom.predicate == "creation_year"
    assert atom.subject == "Federico Garibaldi"
    assert atom.predicate_class == "ATTRIBUTE"
    assert atom.object == "2013"
    assert atom.object_type == "integer"
    assert atom.source == "SRC-EVID-42"
    assert atom.status == "UNVERIFIED"
    assert atom.valid_from is None
    assert atom.valid_to is None
    assert atom.asserted_at == NOW
    assert atom.ingested_at == NOW
    assert atom.asserted_by == "crawler_llm_extraction"
    assert atom.confidence == 0.5
    assert atom.visibility == "INTERNAL"
    assert atom.end_reason is None
    assert atom.supersedes is None
    assert atom.superseded_by is None
    assert len(atom.atom_id) == 5 + 16
    # Independent re-validation, same pattern as
    # test_built_atom_passes_validate_atom_with_zero_blockers: this test
    # must not be relying on build_atom()'s own internal check having run.
    assert [i for i in validate_atom(atom) if i.severita == "BLOCKER"] == []


def test_build_atom_dimensions_valid_all_fields_exact() -> None:
    """First string-range predicate this module has ever built. The
    assertion that matters most is object_type == "string": it must come
    from the registry entry's declared range, not from a default, or a
    dimensions atom would fail A-SCHEMA05 the moment it reached
    validation."""
    atom = build_atom(
        make_proposition(predicate="dimensions", object_raw="  150 x 100 cm  ",
                         extraction_claim_ref="CLAIM-017"),
        now=NOW,
    )
    assert isinstance(atom, RejectedCandidate) is False
    assert atom.predicate == "dimensions"
    assert atom.predicate_class == "ATTRIBUTE"
    # Stripped like the integer path's object, and otherwise verbatim:
    # a dimensions string is recorded free-text, so no normalization,
    # casing change or unit parsing may be applied to it here.
    assert atom.object == "150 x 100 cm"
    assert atom.object_type == "string"
    assert atom.status == "UNVERIFIED"
    assert atom.asserted_by == "crawler_llm_extraction"
    assert atom.confidence == 0.5
    assert atom.visibility == "INTERNAL"
    assert atom.valid_from is None and atom.valid_to is None
    assert atom.end_reason is None
    assert atom.supersedes is None and atom.superseded_by is None
    assert len(atom.atom_id) == 5 + 16
    assert [i for i in validate_atom(atom) if i.severita == "BLOCKER"] == []


def test_build_atom_medium_valid_all_fields_exact() -> None:
    atom = build_atom(
        make_proposition(predicate="medium", object_raw="olio su tela",
                         subject_raw="Senza Titolo (prova)", extraction_claim_ref="CLAIM-018"),
        now=NOW,
    )
    assert isinstance(atom, RejectedCandidate) is False
    assert atom.predicate == "medium"
    assert atom.subject == "Senza Titolo (prova)"  # verbatim
    assert atom.object == "olio su tela"
    assert atom.object_type == "string"
    assert atom.status == "UNVERIFIED"
    assert atom.visibility == "INTERNAL"
    assert atom.confidence == 0.5
    assert len(atom.atom_id) == 5 + 16
    assert [i for i in validate_atom(atom) if i.severita == "BLOCKER"] == []


def test_two_attribute_atoms_sharing_subject_raw_share_the_same_atom_subject() -> None:
    """The property the whole 2026-09-27 widening exists to enable, made
    explicit: two propositions about the SAME work produce two atoms with
    the same `subject`, so a future query can find them by subject alone.

    This is NOT new identity machinery and must not be mistaken for any:
    `build_atom()` has always passed `proposition.subject_raw` through
    verbatim, with no normalization and no entity resolution (the module
    docstring's reason for existing). The widening only makes more
    predicates available to exercise it -- before it, the only two
    buildable predicates were edition-level facts whose subjects are
    effectively never the same string.

    What is asserted is therefore both the property and its exact
    limitation: same subject string in, same subject string out, and
    `atom_id` still differs per extraction (so the three facts remain
    three separate atoms rather than collapsing into one row)."""
    year = make_proposition(
        predicate="creation_year", object_raw="2013",
        subject_raw="Senza Titolo (prova)", extraction_claim_ref="CLAIM-020",
    )
    dims = make_proposition(
        predicate="dimensions", object_raw="150 x 100 cm",
        subject_raw="Senza Titolo (prova)", extraction_claim_ref="CLAIM-021",
    )
    medium = make_proposition(
        predicate="medium", object_raw="olio su tela",
        subject_raw="Senza Titolo (prova)", extraction_claim_ref="CLAIM-022",
    )
    atoms, rejected = build_atoms((year, dims, medium), now=NOW)
    assert rejected == ()
    assert len(atoms) == 3
    assert {a.subject for a in atoms} == {"Senza Titolo (prova)"}
    # Same subject, three genuinely different facts:
    assert {a.predicate for a in atoms} == {"creation_year", "dimensions", "medium"}
    assert {a.object_type for a in atoms} == {"integer", "string"}
    # Same subject does NOT mean same atom: still one id per extraction.
    assert len({a.atom_id for a in atoms}) == 3

    # ...and the exact limitation, asserted so it cannot be quietly
    # forgotten: a different subject string is a different subject value.
    # Linking a recurring work across documents is a separate, unbuilt
    # decision, not something this module does by accident.
    other = build_atom(
        make_proposition(predicate="dimensions", object_raw="80 x 60 cm",
                         subject_raw="Senza titolo (PROVA)", extraction_claim_ref="CLAIM-023"),
        now=NOW,
    )
    assert isinstance(other, RejectedCandidate) is False
    assert other.subject == "Senza titolo (PROVA)"
    assert other.subject != "Senza Titolo (prova)"


# --- built atoms must be independently clean under validate_atom() ---

def test_built_atom_passes_validate_atom_with_zero_blockers() -> None:
    """Independent proof, not a trust of build_atom()'s own check: the
    atom it returns, re-validated here directly, produces zero BLOCKER
    issues."""
    atom = build_atom(make_proposition(), now=NOW)
    blockers = [i for i in validate_atom(atom) if i.severita == "BLOCKER"]
    assert blockers == []


# --- UNKNOWN_PREDICATE ---

def test_build_atom_unknown_predicate_rejects() -> None:
    result = build_atom(make_proposition(predicate="foo_bar_predicate"), now=NOW)
    assert isinstance(result, RejectedCandidate)
    assert result.reason_code == "UNKNOWN_PREDICATE"
    assert result.source_id == "SRC-EVID-42"
    assert result.extraction_claim_ref == "CLAIM-007"
    assert result.raw_predicate == "foo_bar_predicate"
    assert result.detail


def test_build_atom_rejection_carries_subject_object_evidence_for_later_review() -> None:
    """2026-09-21: a RejectedCandidate must carry the real subject/object/
    evidence_excerpt, not just the predicate text -- otherwise a human
    reviewing PREDICATE_TEXT_NOT_MAPPED entries later has no way to verify
    the predicate's real domain/range against an actual case, exactly what
    crawler_predicate_text_mapping.json's own governance note requires."""
    result = build_atom(make_proposition(
        predicate="foo_bar_predicate", subject_raw="Federico Garibaldi",
        object_raw="Area35 Art Gallery", evidence_excerpt="Federico Garibaldi foo_bar_predicate Area35 Art Gallery",
    ), now=NOW)
    assert isinstance(result, RejectedCandidate)
    assert result.subject_raw == "Federico Garibaldi"
    assert result.object_raw == "Area35 Art Gallery"
    assert result.evidence_excerpt == "Federico Garibaldi foo_bar_predicate Area35 Art Gallery"


# --- PREDICATE_NOT_YET_SUPPORTED (real RELATION + real alias) ---

def test_build_atom_relation_predicate_rejects_not_yet_supported() -> None:
    result = build_atom(make_proposition(predicate="represented_by"), now=NOW)
    assert isinstance(result, RejectedCandidate)
    assert result.reason_code == "PREDICATE_NOT_YET_SUPPORTED"


def test_build_atom_relation_predicate_alias_resolves_to_canonical_and_rejects() -> None:
    """'evidences' is a real registered alias of RELATION predicate
    'source_for' (GMV_ONTOLOGY_REGISTRY_v0.1.json) -- it must resolve
    through the registry like the canonical form, never be treated as an
    unrelated raw string, and reject as not-yet-supported exactly like
    the canonical id."""
    via_alias = build_atom(make_proposition(predicate="evidences"), now=NOW)
    via_canonical = build_atom(make_proposition(predicate="source_for"), now=NOW)
    assert isinstance(via_alias, RejectedCandidate) and isinstance(via_canonical, RejectedCandidate)
    assert via_alias.reason_code == "PREDICATE_NOT_YET_SUPPORTED"
    assert via_canonical.reason_code == "PREDICATE_NOT_YET_SUPPORTED"
    assert "source_for" in via_alias.detail  # canonical id named, not the alias spelling


# --- OBJECT_NOT_INTEGER: >= 3 distinct non-numeric variants ---

def test_build_atom_non_integer_object_rejects() -> None:
    for bad_object in ("tre", "3/10"):
        result = build_atom(make_proposition(object_raw=bad_object), now=NOW)
        assert isinstance(result, RejectedCandidate), bad_object
        assert result.reason_code == "OBJECT_NOT_INTEGER", bad_object


def test_build_atom_whitespace_only_object_rejects_as_not_integer() -> None:
    """The empty-after-strip case (the brief's `""` variant, which cannot
    reach this function through the CandidateProposition constructor --
    its __post_init__ rejects empty object_raw): a whitespace-only string
    is constructible and strips to empty, which is not decimal digits."""
    result = build_atom(make_proposition(object_raw="   "), now=NOW)
    assert isinstance(result, RejectedCandidate)
    assert result.reason_code == "OBJECT_NOT_INTEGER"


def test_build_atom_creation_year_non_integer_object_rejects() -> None:
    """The integer check is unchanged for the new integer predicate, and
    still conservative in exactly the old way: `circa 2013` and `3/10` are
    rejected rather than guessed at. The brief's own warning applies --
    this is a year, and the real corpus writes 'circa 2013' and
    'realizzate tra il 2012 e il 2018' (see the registry's own
    source_reference for creation_year), so this rejection rate is
    expected and is a raw-text-mapping problem, not a validation bug."""
    for bad_object in ("circa 2013", "3/10", "2013 circa", "due"):
        result = build_atom(
            make_proposition(predicate="creation_year", object_raw=bad_object), now=NOW,
        )
        assert isinstance(result, RejectedCandidate), bad_object
        assert result.reason_code == "OBJECT_NOT_INTEGER", bad_object
        assert "creation_year" in result.detail  # canonical id named


# --- string-range specifics: the one edge case, and the no-fifth-code proof ---

def test_build_atom_blank_object_rejects_for_a_string_range_predicate() -> None:
    """Constraint 5 of the brief asked to be told about any edge case a
    string-range predicate would need a new reason_code for, rather than
    inventing one. This is that edge case, and it needs NO new code.

    `CandidateProposition.__post_init__` guarantees `object_raw` is
    non-empty but NOT non-blank, so `object_raw="   "` is constructible.
    It strips to `""` here, and the string path has no content check to
    catch it (deliberately -- any non-empty string is a valid literal).
    It is caught instead by `validate_atom()`'s own A-SCHEMA04
    mandatory-field check, which is a BLOCKER, which the module's
    pre-existing VALIDATION_FAILED path already handles. Verified
    empirically before this test was written, not assumed: the whole point
    of checking was to find out which of those two things was true."""
    result = build_atom(make_proposition(predicate="dimensions", object_raw="   "), now=NOW)
    assert isinstance(result, RejectedCandidate)
    assert result.reason_code == "VALIDATION_FAILED"
    assert "A-SCHEMA04" in result.detail
    # Identical outcome for the other string predicate, and for an object
    # that is blank-but-not-spaces-to-empty, so the guarantee is not
    # specific to one predicate or one shape of blankness.
    for predicate in ("medium",):
        other = build_atom(
            make_proposition(predicate=predicate, object_raw=" \t \n "), now=NOW,
        )
        assert isinstance(other, RejectedCandidate)
        assert other.reason_code == "VALIDATION_FAILED"
        assert "A-SCHEMA04" in other.detail


def test_registered_attribute_predicate_outside_the_literal_map_rejects() -> None:
    """The step-3 branch added by the widening, exercised. Today every
    ATTRIBUTE predicate in the real registry is a key of the literal map
    (pinned by the import-time guard), so this is the branch's only
    reachable test -- and the branch must exist, because an ATTRIBUTE
    predicate this module cannot type has no other home and would
    otherwise be forced through with some default type.

    A caller-supplied registry carrying an extra ATTRIBUTE predicate with
    a perfectly literal range is the honest way to reach it: the predicate
    IS registered and IS ATTRIBUTE, so steps 1-2 both pass, and only the
    mapping membership check can refuse it."""
    custom = {
        "predicates": [
            {"predicate_id": "edition_size", "predicate_class": "ATTRIBUTE",
             "range": ["integer"], "aliases": [], "status": "DOMAIN"},
            {"predicate_id": "future_literal_attribute", "predicate_class": "ATTRIBUTE",
             "range": ["string"], "aliases": [], "status": "CANDIDATE"},
        ],
    }
    result = build_atom(
        make_proposition(predicate="future_literal_attribute", object_raw="qualsiasi testo"),
        now=NOW, registry=custom,
    )
    assert isinstance(result, RejectedCandidate)
    # Same code as the RELATION case, because the judgement is the same:
    # "this predicate needs a decision this slice does not make".
    assert result.reason_code == "PREDICATE_NOT_YET_SUPPORTED"
    assert "future_literal_attribute" in result.detail
    # And the already-known predicate in that same custom registry still
    # builds, so the new check is a membership test and not a blanket
    # "reject anything not in the real registry".
    still_builds = build_atom(make_proposition(), now=NOW, registry=custom)
    assert isinstance(still_builds, RejectedCandidate) is False
    assert still_builds.object_type == "integer"


def test_entity_ranged_attribute_predicate_is_excluded_from_this_module() -> None:
    """The allow-list's exclusion half, as behaviour rather than as a set
    comparison: an ATTRIBUTE predicate whose range is an entity type (or
    ['ANY']) must be refused by this module, because it is exactly the
    case that needs RESOLVE ENTITIES. This is the boundary constraint 3 of
    the brief protects -- widening the set to string-range predicates must
    not have widened it to entity-ranged ones."""
    for entity_range in (["PLACE"], ["ANY"], ["WORK", "PLACE"]):
        custom = {
            "predicates": [
                {"predicate_id": "entity_ranged_attribute", "predicate_class": "ATTRIBUTE",
                 "range": entity_range, "aliases": [], "status": "CANDIDATE"},
            ],
        }
        result = build_atom(
            make_proposition(predicate="entity_ranged_attribute", object_raw="value"),
            now=NOW, registry=custom,
        )
        assert isinstance(result, RejectedCandidate), entity_range
        assert result.reason_code == "PREDICATE_NOT_YET_SUPPORTED", entity_range


def test_registry_disagreeing_with_the_import_time_map_surfaces_a_major_issue() -> None:
    """Pins the one coupling the widening introduced, and states it
    accurately -- including the part that is NOT as safe as one might
    assume. Predicate resolution and validation read the CALLER's
    `registry`, while object_type comes from the module-level map computed
    at import, so a caller passing a registry that contradicts the
    import-time one (here: real `dimensions` re-declared with an entity
    range) produces an atom whose object_type contradicts that registry's
    declared range.

    The first draft of this test asserted the atom was rejected as
    VALIDATION_FAILED. That was wrong, and running it is how the mistake
    was found: `object_type_matches_predicate_range()` emits A-SCHEMA05
    with severita "MAJOR", and this module blocks only on "BLOCKER"
    (pre-existing step-6 behaviour, deliberately not changed here). So the
    atom IS returned, carrying a visible non-blocking issue. That is the
    documented truth of the coupling, pinned here so a future change to
    the severita or to the blocking rule has to be a deliberate edit of
    this test rather than a silent behaviour change.

    Unreachable in this repository: no call site, production or test,
    passes a non-None `registry`."""
    custom = {
        "predicates": [
            {"predicate_id": "dimensions", "predicate_class": "ATTRIBUTE",
             "range": ["PLACE"], "aliases": [], "status": "CANDIDATE"},
        ],
    }
    result = build_atom(
        make_proposition(predicate="dimensions", object_raw="150 x 100 cm"),
        now=NOW, registry=custom,
    )
    assert isinstance(result, RejectedCandidate) is False
    assert result.object_type == "string"  # from the import-time map, not custom
    # Reported, not swallowed -- as a MAJOR, which does not block.
    issues = validate_atom(result, custom)
    assert [i.codice for i in issues] == ["A-SCHEMA05"]
    assert {i.severita for i in issues} == {"MAJOR"}
    assert [i for i in validate_atom(result, custom) if i.severita == "BLOCKER"] == []
    # Against the REAL registry -- the one every caller actually uses --
    # the same atom is completely clean, zero issues of any severity.
    assert validate_atom(result) == []


def test_the_literal_range_filter_excludes_entity_ranged_and_relation_predicates(
    tmp_path: Path,
) -> None:
    """Pins the DERIVATION RULE, not just its outcome on today's registry.

    Added 2026-09-27 after mutation testing found a real hole: widening the
    module's allow-list from `range == ["integer"]` to
    `range in (["integer"], ["string"])`, or dropping the
    `predicate_class == "ATTRIBUTE"` half of the filter, are both NO-OPS on
    the real registry -- it happens to contain no entity-ranged ATTRIBUTE
    predicate and no literal-ranged RELATION predicate, so both mutations
    produced an identical mapping and every test in this file still passed.
    The module docstring nonetheless claims the filter excludes
    entity-ranged predicates, and that claim was untested.

    The real registry cannot expose this on its own, so a synthetic one is
    used and the module's own import-time expression is re-executed against
    it, with the fail-loud guard as the observation channel: the guard's
    RuntimeError message embeds the mapping the module actually derived, so
    asserting on that message asserts the real code's output rather than a
    transcription of it.

    The real registry is never written (guarantee A7 applies here too), the
    probe script goes to tmp_path, and the synthetic registry exists only
    inside the subprocess -- this process's module is never reloaded, so no
    shared state is disturbed.
    """
    import subprocess
    import sys

    import gmv_crawler_atom_builder as module

    def _entry(pid: str, pclass: str, rng) -> str:
        return repr({"predicate_id": pid, "predicate_class": pclass,
                     "range": rng, "aliases": [], "status": "CANDIDATE"})

    synthetic = [
        # the two shapes that MUST be included
        _entry("int_attribute", "ATTRIBUTE", ["integer"]),
        _entry("str_attribute", "ATTRIBUTE", ["string"]),
        # every shape that must be EXCLUDED, one per exclusion clause
        _entry("place_ranged_attribute", "ATTRIBUTE", ["PLACE"]),
        _entry("any_ranged_attribute", "ATTRIBUTE", ["ANY"]),
        _entry("multi_literal_attribute", "ATTRIBUTE", ["integer", "string"]),
        _entry("no_range_attribute", "ATTRIBUTE", None),
        _entry("int_ranged_relation", "RELATION", ["integer"]),
        _entry("str_ranged_relation", "RELATION", ["string"]),
    ]
    # Run in a SUBPROCESS, not via importlib.reload: the derivation only
    # runs at import time, and reloading this module in-process would
    # rebind gmv_crawler_atom_builder.RejectedCandidate to a new class
    # object, silently breaking every `isinstance(..., RejectedCandidate)`
    # assertion held elsewhere in this file (found by running it). A
    # subprocess isolates the synthetic registry completely, and the
    # fail-loud guard's RuntimeError message is the observation channel: it
    # embeds the mapping the module's own expression actually derived, so
    # this asserts the real code's output, not a transcription of it.
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT / '10_API')!r})\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "import gmv_atom_validator as v\n"
        f"v._load_ontology_registry = lambda: {{'predicates': [{', '.join(synthetic)}]}}\n"
        "try:\n"
        "    import gmv_crawler_atom_builder\n"
        "except RuntimeError as exc:\n"
        "    print('GUARD_FIRED:', exc)\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(probe)], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "GUARD_FIRED:" in result.stdout, result.stdout
    message = result.stdout.split("GUARD_FIRED:", 1)[1].strip()
    assert "is stale" in message
    for included, object_type in (("int_attribute", "integer"), ("str_attribute", "string")):
        assert f"'{included}': '{object_type}'" in message, message
    for excluded in ("place_ranged_attribute", "any_ranged_attribute",
                     "multi_literal_attribute", "no_range_attribute",
                     "int_ranged_relation", "str_ranged_relation"):
        assert f"'{excluded}'" not in message, f"{excluded} was wrongly derived: {message}"
    # And the real registry still derives the real mapping: the in-process
    # module was never reloaded, so this is the same object every other test
    # in this file uses.
    assert module._ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES == {
        "edition_size": "integer", "edition_number": "integer",
        "creation_year": "integer", "dimensions": "string", "medium": "string",
    }


def test_reason_code_set_is_still_exactly_the_four_documented() -> None:
    """Constraint 5: no fifth reason_code, ever. Asserted by EXERCISING
    every rejection path this module has -- including the two that only
    exist because of the string-range widening -- and requiring the union
    of what came out to be exactly the four documented codes. A test that
    merely listed four constants would keep passing if a fifth were
    introduced tomorrow; this one fails."""
    custom = {
        "predicates": [
            {"predicate_id": "future_literal_attribute", "predicate_class": "ATTRIBUTE",
             "range": ["string"], "aliases": [], "status": "CANDIDATE"},
        ],
    }
    rejected = [
        build_atom(make_proposition(predicate="foo_bar_predicate"), now=NOW),  # UNKNOWN
        build_atom(make_proposition(predicate="represented_by"), now=NOW),  # PREDICATE_...
        build_atom(  # PREDICATE_... via the new mapping-membership branch
            make_proposition(predicate="future_literal_attribute"),
            now=NOW, registry=custom,
        ),
        build_atom(make_proposition(predicate="creation_year", object_raw="circa 2013"), now=NOW),
        build_atom(make_proposition(object_raw="tre"), now=NOW),
        build_atom(make_proposition(predicate="medium", object_raw="  "), now=NOW),  # VALIDATION_
    ]
    for result in rejected:
        assert isinstance(result, RejectedCandidate)
    assert {r.reason_code for r in rejected} == {
        "UNKNOWN_PREDICATE",
        "PREDICATE_NOT_YET_SUPPORTED",
        "OBJECT_NOT_INTEGER",
        "VALIDATION_FAILED",
    }


# --- determinism / uniqueness of atom_id ---

def test_build_atom_atom_id_is_deterministic_byte_for_byte() -> None:
    p = make_proposition()
    first = build_atom(p, now=NOW)
    second = build_atom(p, now=NOW)
    assert first.atom_id == second.atom_id


def test_build_atom_atom_id_differs_for_different_extraction_claim_ref() -> None:
    a = build_atom(make_proposition(extraction_claim_ref="CLAIM-007"), now=NOW)
    b = build_atom(make_proposition(extraction_claim_ref="CLAIM-008"), now=NOW)
    assert a.atom_id != b.atom_id


def test_build_atom_atom_id_binds_to_source_id_not_semantic_fact() -> None:
    """The same semantic fact extracted from two different sources must
    get two different ids, never collapse onto one (reconcile()'s
    SUPPORTING outcome premise)."""
    a = build_atom(make_proposition(source_id="SRC-EVID-42"), now=NOW)
    b = build_atom(make_proposition(source_id="SRC-EVID-99"), now=NOW)
    assert a.atom_id != b.atom_id
    assert a.predicate == b.predicate
    assert a.object == b.object  # same fact, different provenance


# --- batch: no propagation, no loss, no duplication ---

def test_build_atoms_mixed_batch_isolates_rejections() -> None:
    propositions = (
        make_proposition(extraction_claim_ref="OK-1"),                       # valid edition_size
        make_proposition(predicate="edition_number", object_raw="1",
                         extraction_claim_ref="OK-2"),                        # valid edition_number
        make_proposition(predicate="foo_bar_predicate", extraction_claim_ref="BAD-1"),  # UNKNOWN_PREDICATE
        make_proposition(object_raw="tre", extraction_claim_ref="BAD-2"),    # OBJECT_NOT_INTEGER
    )
    atoms, rejected = build_atoms(propositions, now=NOW)
    assert len(atoms) == 2 and len(rejected) == 2
    # exactly the two valid propositions built, nothing lost or duplicated
    assert {a.predicate for a in atoms} == {"edition_size", "edition_number"}
    assert {a.source for a in atoms} == {"SRC-EVID-42"}
    # exactly the two invalid propositions rejected, one reason each
    assert {r.reason_code for r in rejected} == {"UNKNOWN_PREDICATE", "OBJECT_NOT_INTEGER"}
    assert {r.extraction_claim_ref for r in rejected} == {"BAD-1", "BAD-2"}


# --- INTERNAL / UNVERIFIED pinned on every constructible atom ---

def test_every_built_atom_is_internal_and_unverified() -> None:
    """Pinned explicitly, not left to drift: no atom this module builds
    may ever carry status != UNVERIFIED or visibility == PUBLIC (step 15
    publishes only PUBLIC atoms; nothing here has passed epistemic
    verification)."""
    atoms, _ = build_atoms(
        (
            make_proposition(),
            make_proposition(predicate="edition_number", object_raw="2",
                             extraction_claim_ref="X-2"),
        ),
        now=NOW,
    )
    assert atoms
    for atom in atoms:
        assert atom.status == "UNVERIFIED"
        assert atom.visibility == "INTERNAL"