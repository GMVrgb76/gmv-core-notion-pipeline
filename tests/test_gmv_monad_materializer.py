"""Crawler preplan step 8: Monad materializer v1.0.

Cross-checks gmv_id/entity_type governance against the real, committed
migration 010 SQL and GMV_ONTOLOGY_REGISTRY_v0.1.json (read, not
duplicated) -- same discipline steps 4/6/7 already used for content_hash/
entity_type/predicate governance.
"""

from __future__ import annotations

import json
import sqlite3
import stat
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

import gmv_core.migrations as migrations  # noqa: E402
from tests.helpers import connect_fixture_database  # noqa: E402

import gmv_monad_materializer as mm  # noqa: E402
from gmv_atom_validator import AtomCandidate  # noqa: E402

ONTOLOGY_REGISTRY_PATH = ROOT / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_v0.1.json"


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads(ONTOLOGY_REGISTRY_PATH.read_text(encoding="utf-8"))


def _entity_registry_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("monad-db") / "entities.db"
    migrations.migrate(database, target_version=migrations.ENTITY_REGISTRY_VERSION)
    return database


def _atom(**overrides: object) -> AtomCandidate:
    base = {
        "atom_id": "ATOM-000001",
        "subject": "Federico Garibaldi",
        "predicate": "participated_in",
        "predicate_class": "RELATION",
        "object": "Riyadh 2025",
        "object_type": "EVENT",
        "source": "SRC-1",
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
    return AtomCandidate(**base)


def _source(**overrides: object) -> mm.SourceManifestEntry:
    base = {
        "source_id": "SRC-1",
        "path": "/GMV_MASTER_SYSTEM/.../file.pdf",
        "source_type": "PDF",
        "size": 1024,
        "modified": "2026-01-01",
        "hash_value": "sha256:" + "a" * 64,
        "epistemic_level": "PRIMARY",
        "extraction_status": "SUCCESS",
    }
    base.update(overrides)
    return mm.SourceManifestEntry(**base)


def _document(**overrides: object) -> mm.MonadDocument:
    base = {
        "gmv_id": "GMV-000001",
        "entity_type": "ARTIST",
        "canonical_name": "Federico Garibaldi",
        "status": "active",
        "public_text": "Federico Garibaldi e' un artista.",
        "atoms": (_atom(),),
        "sources": (_source(),),
    }
    base.update(overrides)
    return mm.MonadDocument(**base)


# --- gmv_id / entity_type cross-checked against the real migration 010 SQL ---


def test_gmv_id_well_formed_matches_real_entities_check(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    database = _entity_registry_database(tmp_path_factory)
    candidates = ["", "GMV-", "GMV-000001", "gmv-lowercase", "not-a-gmv-id", "GMV-x", "GMV-A-B"]

    with connect_fixture_database(database) as connection:
        for candidate in candidates:
            accepted_by_sql = True
            try:
                connection.execute(
                    "INSERT INTO entities (gmv_id, entity_type, canonical_name, created_at) "
                    "VALUES (?, 'PERSON', 'fixture', 't')",
                    (candidate,),
                )
            except sqlite3.IntegrityError:
                accepted_by_sql = False
            finally:
                connection.execute("DELETE FROM entities")

            document = _document(gmv_id=candidate)
            accepted_by_python = mm.gmv_id_is_well_formed(document) == []
            assert accepted_by_python == accepted_by_sql, candidate


def test_entity_type_governed_matches_real_entities_check(
    tmp_path_factory: pytest.TempPathFactory, registry: dict,
) -> None:
    database = _entity_registry_database(tmp_path_factory)
    candidates = [
        "PERSON", "ARTIST", "INSTITUTION", "WORK", "ARTWORK_INSTANCE",
        "ARTWORK", "SPONSOR", "CONTRACT", "NOT_A_REAL_TYPE",
    ]

    with connect_fixture_database(database) as connection:
        for candidate in candidates:
            accepted_by_sql = True
            try:
                connection.execute(
                    "INSERT INTO entities (gmv_id, entity_type, canonical_name, created_at) "
                    "VALUES ('GMV-x', ?, 'fixture', 't')",
                    (candidate,),
                )
            except sqlite3.IntegrityError:
                accepted_by_sql = False
            finally:
                connection.execute("DELETE FROM entities")

            document = _document(entity_type=candidate)
            accepted_by_python = mm.entity_type_is_governed(document, registry) == []
            assert accepted_by_python == accepted_by_sql, candidate


# --- document-level structural rules ---


@pytest.mark.parametrize("field_name", ["canonical_name", "status"])
def test_required_document_fields_not_empty_rejects_blank_values(field_name: str) -> None:
    """Regression guard: canonical_name/status feed the YAML frontmatter
    with no other gate anywhere in this module -- an earlier version had
    no check for this at all, the same class of gap
    gmv_atom_validator.required_fields_not_empty's own docstring records
    as caught by review in step 7."""
    document = _document(**{field_name: "   "})
    issues = mm.required_document_fields_not_empty(document)
    assert len(issues) == 1
    assert issues[0].codice == "M-SCHEMA05"
    assert issues[0].campo == field_name


def test_required_document_fields_not_empty_accepts_populated_document() -> None:
    assert mm.required_document_fields_not_empty(_document()) == []


def test_source_manifest_entry_rejects_negative_size() -> None:
    with pytest.raises(ValueError, match="size"):
        _source(size=-1)


def test_no_duplicate_atom_ids() -> None:
    document = _document(atoms=(_atom(atom_id="A-1"), _atom(atom_id="A-1")))
    issues = mm.no_duplicate_atom_ids(document)
    assert len(issues) == 1
    assert issues[0].codice == "M-SCHEMA03"


def test_no_duplicate_source_ids() -> None:
    document = _document(sources=(_source(source_id="S-1"), _source(source_id="S-1")))
    issues = mm.no_duplicate_source_ids(document)
    assert len(issues) == 1
    assert issues[0].codice == "M-SCHEMA04"


def test_atom_sources_are_resolvable_accepts_matching_source() -> None:
    document = _document(atoms=(_atom(source="SRC-1"),), sources=(_source(source_id="SRC-1"),))
    assert mm.atom_sources_are_resolvable(document) == []


def test_atom_sources_are_resolvable_rejects_dangling_reference() -> None:
    document = _document(atoms=(_atom(source="SRC-MISSING"),), sources=(_source(source_id="SRC-1"),))
    issues = mm.atom_sources_are_resolvable(document)
    assert len(issues) == 1
    assert issues[0].codice == "M-PROV01"
    assert issues[0].severita == "BLOCKER"


def test_atom_sources_are_resolvable_allows_empty_source_string() -> None:
    """An atom with no SOURCE at all is a separate concern (EIC-09/A-EIC09,
    enforced via validate_atom for VALID atoms) -- this rule only catches a
    *non-empty* SOURCE that fails to resolve, not emptiness itself."""
    document = _document(
        atoms=(_atom(status="UNVERIFIED", source=""),), sources=(_source(source_id="SRC-1"),),
    )
    assert mm.atom_sources_are_resolvable(document) == []


# --- BLOCKER-only gating, reusing gmv_atom_validator.validate_atom ---


def test_atoms_have_no_blocking_issues_clean_atom(registry: dict) -> None:
    document = _document()
    assert mm.atoms_have_no_blocking_issues(document, registry) == []


def test_atoms_have_no_blocking_issues_catches_blocker(registry: dict) -> None:
    document = _document(atoms=(_atom(status="VALID", source=""),))
    issues = mm.atoms_have_no_blocking_issues(document, registry)
    assert any(i.codice == "A-EIC09" for i in issues)


def test_atoms_have_no_blocking_issues_ignores_major(registry: dict) -> None:
    """predicate_class mismatch (A-SCHEMA03) is MAJOR, not BLOCKER --
    verified against the real registry (participated_in is RELATION
    there) -- must not gate materialization."""
    document = _document(atoms=(_atom(predicate="participated_in", predicate_class="ATTRIBUTE"),))
    assert mm.atoms_have_no_blocking_issues(document, registry) == []


def test_find_materialization_blockers_empty_for_clean_document(registry: dict) -> None:
    assert mm.find_materialization_blockers(_document(), registry) == []


def test_find_materialization_blockers_major_atom_issue_is_not_a_blocker(registry: dict) -> None:
    """A document whose only defect is a MAJOR-severity atom issue must
    still pass the materialization gate -- MAJOR is a flagged defect, not
    a reason to refuse a write, matching area35_validator.py's own
    BLOCKER-stops-export convention."""
    document = _document(atoms=(_atom(predicate="participated_in", object_type="DOCUMENT"),))
    assert mm.find_materialization_blockers(document, registry) == []


# --- rendering ---


def test_render_matches_canonical_skeleton_structure() -> None:
    document = _document(atoms=(), sources=())
    text = mm.render_monad_markdown(document)
    lines = text.split("\n")
    assert lines[0] == "---"
    end_of_frontmatter = lines[1:].index("---") + 1
    frontmatter = yaml.safe_load("\n".join(lines[1:end_of_frontmatter]))
    assert frontmatter == {
        "schema": "GMV_KNOWLEDGE_MONAD_V1",
        "gmv_id": "GMV-000001",
        "entity_type": "ARTIST",
        "canonical_name": "Federico Garibaldi",
        "status": "active",
    }
    assert "# PUBLIC" in text
    assert "# ATOMS" in text
    assert "# SOURCES" in text
    assert text.index("# PUBLIC") < text.index("# ATOMS") < text.index("# SOURCES")


def test_render_atom_table_header_matches_frozen_18_field_schema() -> None:
    text = mm.render_monad_markdown(_document(atoms=(), sources=()))
    header = next(line for line in text.split("\n") if line.startswith("| ATOM_ID"))
    columns = [c.strip() for c in header.strip("|").split("|")]
    assert columns == [
        "ATOM_ID", "SUBJECT", "PREDICATE", "PREDICATE_CLASS", "OBJECT", "OBJECT_TYPE",
        "SOURCE", "STATUS", "VALID_FROM", "VALID_TO", "ASSERTED_AT", "INGESTED_AT",
        "ASSERTED_BY", "CONFIDENCE", "VISIBILITY", "END_REASON", "SUPERSEDES", "SUPERSEDED_BY",
    ]


def test_render_source_table_header_matches_v19_skeleton() -> None:
    text = mm.render_monad_markdown(_document(atoms=(), sources=()))
    header = next(line for line in text.split("\n") if line.startswith("| SOURCE_ID"))
    columns = [c.strip() for c in header.strip("|").split("|")]
    assert columns == [
        "SOURCE_ID", "PATH", "TYPE", "SIZE", "MODIFIED", "HASH",
        "EPISTEMIC_LEVEL", "EXTRACTION_STATUS", "NOTES",
    ]


def test_render_is_independent_of_input_order() -> None:
    atom_a, atom_b = _atom(atom_id="A-1", source="S-1"), _atom(atom_id="A-2", source="S-2")
    source_a, source_b = _source(source_id="S-1"), _source(source_id="S-2")
    forward = _document(atoms=(atom_a, atom_b), sources=(source_a, source_b))
    reversed_ = _document(atoms=(atom_b, atom_a), sources=(source_b, source_a))
    assert mm.render_monad_markdown(forward) == mm.render_monad_markdown(reversed_)


def test_render_escapes_pipe_characters_in_cells() -> None:
    document = _document(atoms=(_atom(subject="A | B"),))
    text = mm.render_monad_markdown(document)
    assert "A \\| B" in text
    # Every non-separator row must still parse to exactly 18 cells.
    row = next(line for line in text.split("\n") if line.startswith("| ATOM-"))
    assert len(row.strip("|").split(" | ")) == 18


def test_render_none_valued_optional_atom_fields_render_as_empty_cell() -> None:
    document = _document(atoms=(_atom(valid_to=None, end_reason=None, supersedes=None,
                                       superseded_by=None),))
    text = mm.render_monad_markdown(document)
    row = next(line for line in text.split("\n") if line.startswith("| ATOM-"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[9] == ""  # VALID_TO


# --- materialize_monad: validation gate + atomic write ---


def test_materialize_monad_writes_file(tmp_path: Path, registry: dict) -> None:
    target = tmp_path / "monads" / "GMV-000001.md"
    result = mm.materialize_monad(_document(), target, registry)
    assert result == target
    assert target.read_text(encoding="utf-8") == mm.render_monad_markdown(_document())


def test_materialize_monad_uses_secure_atomic_write_permissions(
    tmp_path: Path, registry: dict,
) -> None:
    target = tmp_path / "monads" / "GMV-000001.md"
    mm.materialize_monad(_document(), target, registry)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700


def test_materialize_monad_is_idempotent(tmp_path: Path, registry: dict) -> None:
    target = tmp_path / "monads" / "GMV-000001.md"
    mm.materialize_monad(_document(), target, registry)
    first = target.read_text(encoding="utf-8")
    mm.materialize_monad(_document(), target, registry)
    second = target.read_text(encoding="utf-8")
    assert first == second


def test_materialize_monad_refuses_on_blocker(tmp_path: Path, registry: dict) -> None:
    document = _document(gmv_id="not-well-formed")
    target = tmp_path / "monads" / "bad.md"
    with pytest.raises(mm.MonadMaterializationError) as excinfo:
        mm.materialize_monad(document, target, registry)
    assert any(i.codice == "M-SCHEMA01" for i in excinfo.value.issues)
    assert not target.exists()


def test_materialize_monad_refuses_on_dangling_source_reference(
    tmp_path: Path, registry: dict,
) -> None:
    document = _document(atoms=(_atom(source="SRC-MISSING"),), sources=(_source(source_id="SRC-1"),))
    target = tmp_path / "monads" / "bad.md"
    with pytest.raises(mm.MonadMaterializationError) as excinfo:
        mm.materialize_monad(document, target, registry)
    assert any(i.codice == "M-PROV01" for i in excinfo.value.issues)
    assert not target.exists()


def test_materialize_monad_loads_registry_itself_when_not_given(tmp_path: Path) -> None:
    """registry is optional -- callers that only materialize one document
    should not be forced to load GMV_ONTOLOGY_REGISTRY_v0.1.json themselves."""
    target = tmp_path / "monads" / "GMV-000001.md"
    mm.materialize_monad(_document(), target)
    assert target.exists()


# --- reuse, not reinvention ---


def test_reuses_area35_validator_issue_type() -> None:
    import area35_validator as area35

    assert mm.Issue is area35.Issue


def test_reuses_secure_storage_atomic_write() -> None:
    import secure_storage

    assert mm.atomic_write_text is secure_storage.atomic_write_text


def test_reuses_gmv_atom_validator_validate_atom() -> None:
    import gmv_atom_validator as av

    assert mm.validate_atom is av.validate_atom
