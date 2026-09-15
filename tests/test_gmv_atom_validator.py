"""Crawler preplan step 7: Atom validator (Correzione 3)."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))
import area35_validator as area35  # noqa: E402
import gmv_atom_validator as av  # noqa: E402

ONTOLOGY_REGISTRY_PATH = ROOT / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_v0.1.json"
EPISTEMIC_RULES_PATH = ROOT / "00_CONFIG" / "EPISTEMIC_INGESTION_RULES_v0.2.json"


def _atom(**overrides: object) -> av.AtomCandidate:
    base = {
        "atom_id": "ATOM-000001",
        "subject": "Federico Garibaldi",
        "predicate": "participated_in",
        "predicate_class": "RELATION",
        "object": "Riyadh 2025",
        "object_type": "EVENT",
        "source": "sha256:" + "a" * 64,
        "status": "VALID",
        "valid_from": "2025-01-01",
        "valid_to": None,
        "asserted_at": "2026-01-01",
        "ingested_at": "2026-01-01",
        "asserted_by": "crawler",
        "confidence": 0.9,
        "visibility": "PUBLIC",
    }
    base.update(overrides)
    return av.AtomCandidate(**base)


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads(ONTOLOGY_REGISTRY_PATH.read_text(encoding="utf-8"))


def test_reuses_area35_validator_issue_and_sev_not_a_parallel_type() -> None:
    """Pins the "extends, does not reinvent" claim: the Issue class and
    the SEV mapping used by this module must be the exact same objects
    area35_validator.py defines, not lookalikes."""
    assert av.Issue is area35.Issue
    assert av.SEV is area35.SEV


def test_compute_atom_fingerprint_reuses_area35_validator_forma() -> None:
    """Pins that fingerprinting reuses area35_validator._forma() by
    import (Correction 3's explicit instruction), not a second
    normalizer -- _forma(), not plain norm(), because norm() alone does
    not reorder tokens (see the name-order test below for the real bug
    this closes)."""
    assert av._forma is area35._forma


def test_fingerprint_is_stable_across_accents_case_and_diacritics() -> None:
    a = _atom(subject="Federico Garibaldi")
    b = _atom(subject="FEDERICO   GARIBALDI")
    assert av.compute_atom_fingerprint(a) == av.compute_atom_fingerprint(b)


def test_fingerprint_is_stable_across_name_order() -> None:
    """Regression guard for a real gap review found: an earlier version
    used norm() alone, which does not reorder tokens, so the same
    subject written "Cognome, Nome" by one extraction pass and "Nome
    Cognome" by another fingerprinted differently -- a dedup false
    negative. area35_validator._forma() already exists to solve exactly
    this (used by r_duplicati/D02 for artista/persona matching);
    compute_atom_fingerprint must reuse it, not just norm()."""
    a = _atom(subject="Federico Garibaldi")
    b = _atom(subject="Garibaldi, Federico")
    assert av.compute_atom_fingerprint(a) == av.compute_atom_fingerprint(b)


def test_fingerprint_ignores_provenance_and_lifecycle_fields() -> None:
    """Two atoms asserting the same claim from different sources, or
    re-derived after a rescan, must fingerprint identically -- provenance
    is not part of claim identity."""
    a = _atom(atom_id="ATOM-1", source="sha256:" + "a" * 64, asserted_at="2026-01-01")
    b = _atom(atom_id="ATOM-2", source="sha256:" + "b" * 64, asserted_at="2026-06-01")
    assert av.compute_atom_fingerprint(a) == av.compute_atom_fingerprint(b)


def test_fingerprint_changes_when_the_claim_itself_changes() -> None:
    a = _atom(object="Riyadh 2025")
    b = _atom(object="Venice 2025")
    assert av.compute_atom_fingerprint(a) != av.compute_atom_fingerprint(b)


def test_fingerprint_collides_on_reordered_non_person_text() -> None:
    """Documents a known, accepted trade-off rather than hiding it
    (flagged by review): area35_validator.py only ever applies _forma()
    to artista/persona entities. Reusing it for every ATOM subject/
    object, regardless of OBJECT_TYPE, closes the person-name-order
    false-negative this fix was written for, but _forma() sorts ALL
    tokens alphabetically -- so two genuinely different multi-word
    values that share words in a different order also collide. This
    test proves the collision is real, not hypothetical, so a future
    reader cannot assume fingerprints are safe for non-person text."""
    a = _atom(object="Venice Biennale", object_type="EVENT")
    b = _atom(object="Biennale Venice", object_type="EVENT")
    assert av.compute_atom_fingerprint(a) == av.compute_atom_fingerprint(b)


def test_fingerprint_is_well_formed_sha256() -> None:
    fp = av.compute_atom_fingerprint(_atom())
    assert fp.startswith("sha256:")
    assert len(fp) == len("sha256:") + 64


def test_fingerprint_default_unchanged_byte_for_byte() -> None:
    """Pinned value, not a self-computed tautology: with neither
    subject_gmv_id nor object_gmv_id provided, the fingerprint of the
    base _atom() must be exactly the SHA-256 of the same _forma-joined
    string this function produced before the optional parameters
    existed. If a future edit changes the default normalization (the
    component separator, _forma()'s role, or the enclosing digest), this
    literal fails -- which is precisely the byte-for-byte stability the
    change was required to preserve for existing single-argument
    callers."""
    assert av.compute_atom_fingerprint(_atom()) == (
        "sha256:dc2216b4f0006f7f5ce9532fb3e76908c63fbdbf26de43bc2a9058b612ff4b63"
    )


def test_fingerprint_explicit_none_matches_default() -> None:
    """None is 'not provided', not an identity value: passing the
    parameters explicitly as None must produce the identical fingerprint
    to the default call, same byte-for-byte guarantee as
    test_fingerprint_default_unchanged_byte_for_byte."""
    a = _atom(subject="Federico Garibaldi", object="Riyadh 2025")
    assert (
        av.compute_atom_fingerprint(a, subject_gmv_id=None, object_gmv_id=None)
        == av.compute_atom_fingerprint(a)
    )


def test_fingerprint_same_gmv_id_collapses_unrelated_spellings() -> None:
    """The bug this change closes, demonstrated on old code: it cannot
    take subject_gmv_id/object_gmv_id at all (TypeError), and even if
    the text-only fingerprint were the only key, these two atoms would
    never match -- "Federico Garibaldi"/"Riyadh 2025" and
    "Garibaldi F."/"Riyadh" do not _forma()-collapse into each
    other. Once both atoms carry the SAME resolved gmv_id for subject
    and object, the resolved identity -- not the normalized text -- is
    what the fingerprint keys on, and they must match."""
    a = _atom(subject="Federico Garibaldi", object="Riyadh 2025", object_type="EVENT")
    b = _atom(subject="Garibaldi F.", object="Riyadh", object_type="EVENT")
    assert av._forma(a.subject) != av._forma(b.subject)
    assert av._forma(a.object) != av._forma(b.object)
    fp_a = av.compute_atom_fingerprint(
        a, subject_gmv_id="GMV-ARTIST-0001", object_gmv_id="GMV-EVENT-0001"
    )
    fp_b = av.compute_atom_fingerprint(
        b, subject_gmv_id="GMV-ARTIST-0001", object_gmv_id="GMV-EVENT-0001"
    )
    assert fp_a == fp_b


def test_fingerprint_same_gmv_id_closes_word_order_collision() -> None:
    """The documented word-order/OBJECT_TYPE weakness, closed for
    resolved entities: "Venice Biennale" and "Biennale Venice" normally
    fingerprint identically under _forma() (see
    test_fingerprint_collides_on_reordered_non_person_text). Bound to
    the SAME event gmv_id they must still fingerprint identically --
    they are the same real-world thing; bound to DIFFERENT gmv_ids (the
    other test below) they must diverge. The id, not the text, decides."""
    a = _atom(object="Venice Biennale", object_type="EVENT")
    b = _atom(object="Biennale Venice", object_type="EVENT")
    assert (
        av.compute_atom_fingerprint(a, object_gmv_id="GMV-EVENT-0001")
        == av.compute_atom_fingerprint(b, object_gmv_id="GMV-EVENT-0001")
    )


def test_fingerprint_different_gmv_id_stays_distinct() -> None:
    """The fix must not collapse everything: two atoms with otherwise
    identical, _forma()-identical SUBJECT/OBJECT text but DIFFERENT
    subject gmv_ids are different real-world facts and must fingerprint
    differently, even though the raw text would normalize the same."""
    a = _atom(subject="Venice Biennale", object="Riyadh 2025")
    b = _atom(subject="Venice Biennale", object="Riyadh 2025")
    assert av._forma(a.subject) == av._forma(b.subject)
    assert (
        av.compute_atom_fingerprint(a, subject_gmv_id="GMV-EVENT-0001")
        != av.compute_atom_fingerprint(b, subject_gmv_id="GMV-EVENT-0002")
    )


def test_eic09_valid_requires_source() -> None:
    assert av.eic09_valid_requires_source(_atom(status="VALID", source="sha256:" + "a" * 64)) == []
    issues = av.eic09_valid_requires_source(_atom(status="VALID", source=""))
    assert len(issues) == 1
    assert issues[0].codice == "A-EIC09"
    assert issues[0].severita == "BLOCKER"


def test_eic09_does_not_fire_for_non_valid_status() -> None:
    assert av.eic09_valid_requires_source(_atom(status="UNVERIFIED", source="")) == []


def test_eic16_invalidated_requires_end_reason() -> None:
    assert av.eic16_invalidated_requires_end_reason(
        _atom(status="INVALIDATED", end_reason="CORRECTED")
    ) == []
    issues = av.eic16_invalidated_requires_end_reason(
        _atom(status="INVALIDATED", end_reason=None)
    )
    assert len(issues) == 1
    assert issues[0].codice == "A-EIC16"


def test_superseded_by_not_required_when_status_superseded() -> None:
    """GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §9: SUPERSEDED_BY is set only when
    directly resolvable -- absence is legitimate. No rule in this module
    should flag it."""
    atom = _atom(status="SUPERSEDED", superseded_by=None)
    issues = av.validate_atom(atom, registry={"predicates": [
        {"predicate_id": "participated_in", "predicate_class": "RELATION", "aliases": []},
    ]})
    assert not any("superseded_by" in (i.campo or "") for i in issues)


def test_predicate_class_is_frozen() -> None:
    assert av.predicate_class_is_frozen(_atom(predicate_class="RELATION")) == []
    issues = av.predicate_class_is_frozen(_atom(predicate_class="INVENTED_CLASS"))
    assert len(issues) == 1
    assert issues[0].codice == "A-SCHEMA01"


def test_confidence_in_bounds() -> None:
    assert av.confidence_in_bounds(_atom(confidence=0.0)) == []
    assert av.confidence_in_bounds(_atom(confidence=1.0)) == []
    assert len(av.confidence_in_bounds(_atom(confidence=1.5))) == 1
    assert len(av.confidence_in_bounds(_atom(confidence=-0.1))) == 1


def test_valid_to_not_before_valid_from() -> None:
    assert av.valid_to_not_before_valid_from(
        _atom(valid_from="2025-01-01", valid_to="2025-06-01")
    ) == []
    assert av.valid_to_not_before_valid_from(_atom(valid_from="2025-01-01", valid_to=None)) == []
    issues = av.valid_to_not_before_valid_from(
        _atom(valid_from="2025-06-01", valid_to="2025-01-01")
    )
    assert len(issues) == 1
    assert issues[0].codice == "A-TIME01"


def test_predicate_is_governed_accepts_real_registered_predicate(registry: dict) -> None:
    atom = _atom(predicate="participated_in", predicate_class="RELATION")
    assert av.predicate_is_governed(atom, registry) == []


def test_predicate_is_governed_accepts_alias(registry: dict) -> None:
    """'evidences' is a registered alias of 'source_for' in the real
    committed registry -- must resolve, not be rejected as unknown."""
    atom = _atom(subject="Doc-1", predicate="evidences", predicate_class="RELATION",
                 object="Claim-1", object_type="DOCUMENT")
    assert av.predicate_is_governed(atom, registry) == []


def test_predicate_is_governed_rejects_unregistered_predicate(registry: dict) -> None:
    atom = _atom(predicate="invented_relationship_never_registered")
    issues = av.predicate_is_governed(atom, registry)
    assert len(issues) == 1
    assert issues[0].codice == "A-EIC07"
    assert issues[0].severita == "BLOCKER"


def test_predicate_is_governed_flags_predicate_class_mismatch(registry: dict) -> None:
    """participated_in is registered as RELATION in the real registry;
    declaring it ATTRIBUTE on the atom is a real mismatch. Codice is
    A-SCHEMA03, not A-EIC07: this is an internal consistency check, not
    an enforcement of EIC-07's actual semantic-equivalence concern --
    an earlier version conflated the two under the same codice."""
    atom = _atom(predicate="participated_in", predicate_class="ATTRIBUTE")
    issues = av.predicate_is_governed(atom, registry)
    assert len(issues) == 1
    assert issues[0].codice == "A-SCHEMA03"
    assert issues[0].severita == "MAJOR"


def test_object_type_matches_predicate_range_accepts_valid_type(registry: dict) -> None:
    # participated_in's real registered range includes EVENT.
    atom = _atom(predicate="participated_in", object_type="EVENT")
    assert av.object_type_matches_predicate_range(atom, registry) == []


def test_object_type_matches_predicate_range_rejects_invalid_type(registry: dict) -> None:
    # participated_in's real registered range does not include DOCUMENT.
    atom = _atom(predicate="participated_in", object_type="DOCUMENT")
    issues = av.object_type_matches_predicate_range(atom, registry)
    assert len(issues) == 1
    assert issues[0].codice == "A-SCHEMA05"
    assert issues[0].severita == "MAJOR"


def test_object_type_matches_predicate_range_skips_any_range(registry: dict) -> None:
    # related_to's real registered range is ["ANY"] -- unconstrained by design.
    atom = _atom(predicate="related_to", predicate_class="RELATION", object_type="anything-at-all")
    assert av.object_type_matches_predicate_range(atom, registry) == []


def test_object_type_matches_predicate_range_skips_unregistered_predicate(registry: dict) -> None:
    """Avoids double-reporting: predicate_is_governed already flags an
    unregistered predicate; this rule must not also fire on it."""
    atom = _atom(predicate="invented_never_registered", object_type="anything")
    assert av.object_type_matches_predicate_range(atom, registry) == []


def test_required_fields_not_empty_accepts_populated_atom() -> None:
    assert av.required_fields_not_empty(_atom()) == []


@pytest.mark.parametrize("field_name", ["atom_id", "subject", "object"])
def test_required_fields_not_empty_rejects_blank_values(field_name: str) -> None:
    """Regression guard: an earlier version of this module had no
    presence check at all -- an atom with empty subject/object/atom_id
    and an otherwise-valid governed predicate passed validate_atom()
    with zero issues."""
    issues = av.required_fields_not_empty(_atom(**{field_name: "   "}))
    assert len(issues) == 1
    assert issues[0].codice == "A-SCHEMA04"
    assert issues[0].campo == field_name


def test_validate_atom_runs_every_rule_and_sorts_by_severity(registry: dict) -> None:
    atom = _atom(status="VALID", source="", predicate="unregistered_predicate", confidence=2.0)
    issues = av.validate_atom(atom, registry)
    codes = {i.codice for i in issues}
    assert "A-EIC09" in codes  # VALID without source
    assert "A-EIC07" in codes  # unregistered predicate
    assert "A-SCHEMA02" in codes  # confidence out of bounds
    assert all(
        av.SEV.get(a.severita, 9) <= av.SEV.get(b.severita, 9)
        for a, b in zip(issues, issues[1:])
    )


def test_validate_atom_clean_atom_produces_no_issues(registry: dict) -> None:
    assert av.validate_atom(_atom(), registry) == []


def _enforced_eic_ids_from_source() -> set[str]:
    """Derives which EIC rule_ids are mechanically enforced by
    introspecting the actual rule functions' source for 'A-EICnn' codice
    literals, instead of a second hand-maintained list -- an earlier
    version hardcoded this set in two different tests, which could not
    have caught a future mismatch between what the module's docstring/
    comments claim and what its code actually emits."""
    import inspect
    import re

    source = "".join(inspect.getsource(rule) for rule in av.ATOM_RULES + av.ONTOLOGY_RULES)
    return {f"EIC-{n}" for n in re.findall(r"A-EIC(\d{2})", source)}


def test_unenforced_rule_ids_are_disjoint_from_enforced_ones() -> None:
    """No rule_id should appear both as mechanically enforced (via an
    A-EICxx code emitted somewhere in this module) and in
    UNENFORCED_RULE_IDS -- that would be a self-contradiction."""
    assert _enforced_eic_ids_from_source().isdisjoint(av.UNENFORCED_RULE_IDS)


def test_unenforced_plus_enforced_covers_all_nineteen_rules() -> None:
    """Cross-checks against the real, committed EPISTEMIC_INGESTION_RULES_v0.2.json
    instead of a second hardcoded count, so a future rule added to that
    file surfaces here as a gap to classify, not silently ignored."""
    rules_doc = json.loads(EPISTEMIC_RULES_PATH.read_text(encoding="utf-8"))
    all_rule_ids = {e["rule_id"] for e in rules_doc["rules"] + rules_doc["v0_2_integrations"]}
    enforced_eic_ids = _enforced_eic_ids_from_source()
    assert enforced_eic_ids <= all_rule_ids
    assert av.UNENFORCED_RULE_IDS <= all_rule_ids
    assert enforced_eic_ids | av.UNENFORCED_RULE_IDS == all_rule_ids, (
        "every rule_id in the real EIC file must be classified as either "
        "mechanically enforced here or explicitly listed as unenforced"
    )
