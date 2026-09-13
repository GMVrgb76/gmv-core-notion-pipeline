"""Characterization test for 00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json.

Guards the shape and internal consistency of the vocabulary that will back
the GMV Crawler's RESOLVE ENTITIES / NORMALIZE PREDICATES stages: no
duplicate class/predicate ids, every domain/range/superseded_by/alias
reference resolves to something that actually exists in the file, and the
two documented reuse-before-invention decisions (INSTITUTION -> ORGANIZATION,
evidences -> source_for) stay pinned.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_v0.1.json"
)

VALID_ENTITY_STATUSES = {"CORE", "DOMAIN", "CANDIDATE", "DEPRECATED"}
VALID_PREDICATE_STATUSES = {"CORE", "DOMAIN", "CANDIDATE", "DEPRECATED"}
VALID_PREDICATE_CLASSES = {"IDENTITY", "ATTRIBUTE", "RELATION", "EVENT", "MEASURE", "EPISTEMIC"}


def _load() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_file_is_valid_json_with_expected_top_level_shape() -> None:
    config = _load()
    assert config["version"] == "0.1"
    assert config["authority"] == "REQUIRED"
    assert set(config["predicate_classes"]) == VALID_PREDICATE_CLASSES
    assert "entity_classes" in config
    assert "predicates" in config


def test_entity_class_ids_are_unique() -> None:
    config = _load()
    ids = [entry["class_id"] for entry in config["entity_classes"]]
    assert len(ids) == len(set(ids)), "duplicate class_id found"


def test_predicate_ids_are_unique() -> None:
    config = _load()
    ids = [entry["predicate_id"] for entry in config["predicates"]]
    assert len(ids) == len(set(ids)), "duplicate predicate_id found"


def test_every_entity_class_has_valid_status_and_required_fields() -> None:
    config = _load()
    for entry in config["entity_classes"]:
        assert entry["status"] in VALID_ENTITY_STATUSES, entry["class_id"]
        assert entry["definition"], entry["class_id"]
        assert entry["source_reference"], entry["class_id"]


def test_every_predicate_has_valid_status_class_and_required_fields() -> None:
    config = _load()
    for entry in config["predicates"]:
        assert entry["status"] in VALID_PREDICATE_STATUSES, entry["predicate_id"]
        assert entry["predicate_class"] in VALID_PREDICATE_CLASSES, entry["predicate_id"]
        assert entry["definition"], entry["predicate_id"]
        assert entry["source_reference"], entry["predicate_id"]


def test_deprecated_entity_classes_have_resolvable_superseded_by() -> None:
    config = _load()
    known_ids = {entry["class_id"] for entry in config["entity_classes"]}
    for entry in config["entity_classes"]:
        if entry["status"] == "DEPRECATED":
            assert entry.get("superseded_by"), entry["class_id"]
            for successor in entry["superseded_by"]:
                assert successor in known_ids, (
                    f"{entry['class_id']} superseded_by unknown class {successor}"
                )


def test_predicate_domain_and_range_reference_known_entity_classes_or_any() -> None:
    config = _load()
    known_ids = {entry["class_id"] for entry in config["entity_classes"]}
    known_ids.add("ANY")
    for entry in config["predicates"]:
        for role in ("domain", "range"):
            for class_id in entry[role]:
                if class_id == "integer":
                    continue  # ATTRIBUTE predicates may range over a literal type
                assert class_id in known_ids, (
                    f"{entry['predicate_id']}.{role} references unknown class {class_id}"
                )


def test_predicate_inverse_references_resolve_when_present() -> None:
    config = _load()
    known_predicate_ids = {entry["predicate_id"] for entry in config["predicates"]}
    for entry in config["predicates"]:
        inverse = entry.get("inverse")
        if inverse is not None and inverse not in known_predicate_ids:
            # supersedes/superseded_by is a documented asymmetric pair; the
            # inverse name itself need not be a separately registered
            # predicate as long as it is explicitly noted as such.
            assert entry["predicate_id"] == "supersedes" and inverse == "superseded_by", (
                f"{entry['predicate_id']}.inverse={inverse} does not resolve"
            )


def test_institution_is_its_own_domain_class_not_an_organization_alias() -> None:
    """Regression guard for a reviewed-and-corrected mistake: an earlier
    draft folded INSTITUTION into ORGANIZATION as a bare alias, citing a
    source that actually shows the opposite (INSTITUTION is the concept
    with a real Notion template and a real code mapping; ORGANIZATION was
    never instantiated anywhere in this repo)."""
    config = _load()
    by_id = {entry["class_id"]: entry for entry in config["entity_classes"]}
    assert by_id["INSTITUTION"]["status"] == "DOMAIN"
    assert by_id["ORGANIZATION"]["status"] == "CORE"
    assert by_id["ORGANIZATION"]["aliases"] == []
    assert "INSTITUTION" not in by_id["ORGANIZATION"]["aliases"]


def test_institution_matches_the_real_notion_template_key() -> None:
    """Cross-check against the live schema so this registry cannot drift
    from the entity types the Notion projection adapter actually
    implements -- the exact gap that let the ORGANIZATION/INSTITUTION
    mistake through a first review pass undetected."""
    templates_path = (
        Path(__file__).resolve().parents[2] / "00_CONFIG" / "notion_page_templates.json"
    )
    templates = json.loads(templates_path.read_text(encoding="utf-8"))
    assert "istituzione" in templates["entita"]

    config = _load()
    by_id = {entry["class_id"]: entry for entry in config["entity_classes"]}
    assert "notion_page_templates.json" in by_id["INSTITUTION"]["source_reference"]


def test_no_predicate_is_registered_twice_under_different_ids() -> None:
    """Pin the source_for/evidences reuse-before-invention decision."""
    config = _load()
    source_for = next(
        entry for entry in config["predicates"] if entry["predicate_id"] == "source_for"
    )
    assert "evidences" in source_for["aliases"]
    all_ids = {entry["predicate_id"] for entry in config["predicates"]}
    assert "evidences" not in all_ids, "evidences must stay an alias, not a predicate_id"


def test_work_artwork_instance_split_is_present_and_artwork_is_deprecated() -> None:
    config = _load()
    by_id = {entry["class_id"]: entry for entry in config["entity_classes"]}
    assert by_id["WORK"]["status"] == "DOMAIN"
    assert by_id["ARTWORK_INSTANCE"]["status"] == "DOMAIN"
    assert by_id["ARTWORK"]["status"] == "DEPRECATED"
    assert set(by_id["ARTWORK"]["superseded_by"]) == {"WORK", "ARTWORK_INSTANCE"}


def test_exhibited_at_domain_excludes_work() -> None:
    """Regression guard for a reviewed-and-corrected mistake: exhibited_at
    is a physical-occurrence predicate, but WORK is defined in this same
    file as independent of any physical exemplar. Allowing WORK in the
    domain would silently reintroduce the granularity collapse that
    deprecating flat ARTWORK was meant to resolve."""
    config = _load()
    exhibited_at = next(
        entry for entry in config["predicates"] if entry["predicate_id"] == "exhibited_at"
    )
    assert exhibited_at["domain"] == ["ARTWORK_INSTANCE"]
    assert "WORK" not in exhibited_at["domain"]
