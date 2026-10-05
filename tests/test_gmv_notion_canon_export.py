"""GMV Notion canon export -- per-page canon files under `03_STATE/area35_canon/`.

Pins the guarantees `10_API/gmv_notion_canon_export.py`'s own docstrings
claim, each attacked directly rather than re-read:

  Q1  a canon file is written ONLY for a name that resolves to exactly one
      registry `gmv_id`
      -> test_known_registry_entity_writes_the_expected_file
  Q2  frontmatter field names, field ORDER and the two section headers are
      exactly as decided, and `schema` is NOT the Monad's
      -> test_written_frontmatter_is_exact_and_not_the_monad_schema
  Q3  the file name comes from the REGISTRY's `gmv_id`, and the frontmatter's
      canonical_name/entity_type come from the registry entry, never from
      Notion's strings (real case: GMV-000004, Notion "Florencia S.M. Brück"
      vs registry "Florencia Bruck")
      -> test_registry_wins_over_the_notion_strings
  Q4  an unrecognized name produces a real `EntityIdentityProposal` and NO
      file -- proposed, never minted, never auto-registered
      -> test_unrecognized_entity_is_proposed_and_never_written
  Q5  the caller-side wiring: the returned proposal lands in the SAME queue
      file the crawler nightly run and review tool use, and the canon
      directory is still empty
      -> test_unresolved_page_lands_in_the_shared_identity_queue
  Q6  a page with no title names nothing: no file, and no blank name pushed
      into the human review queue
      -> test_empty_title_writes_nothing_and_queues_nothing
  Q7  a page whose name matches a registry `aliases` entry resolves to that
      entity's canonical `gmv_id` (the real Florencia case, not a
      hypothetical one)
      -> test_alias_match_resolves_to_the_registry_gmv_id
  Q8  a HOMONYM (one name claimed by two registry entities) writes no file and
      resolves nothing -- the resolver's own "None, never the first match"
      rule, not re-decided here
      -> test_ambiguous_name_writes_nothing
  Q9  a broken registry entry (two rows with one `gmv_id`; empty
      `canonical_name`) refuses the write instead of picking a winner
      -> test_registry_defects_refuse_the_write
  Q10 nothing in this module imports or calls the Monad/atom pipeline
      -> test_module_never_imports_the_monad_or_atom_modules
  Q11 no file path can be influenced by Notion-controlled text, and nothing is
      ever written outside the caller's `target_dir`
      -> test_only_registry_gmv_ids_become_file_names
  Q12 the write is atomic and private (secure_storage's 0700 dir / 0600 file),
      and re-exporting the same page is idempotent
      -> test_write_is_private_atomic_and_idempotent
  Q13 the hard wall on `03_STATE/ombra/`: the CLI's default destination is the
      canon folder and no other
      -> test_cli_default_destination_is_the_canon_folder
  Q14 `main()` never writes the entity registry and never mints a `gmv_id`
      -> test_export_run_never_writes_the_entity_registry
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

import gmv_notion_canon_export as canon  # noqa: E402
from gmv_crawler_entity_identity_proposal_queue import (  # noqa: E402
    append_entity_identity_proposals,
)
from gmv_crawler_entity_resolver import (  # noqa: E402
    _load_entity_registry,
    resolve_entity_gmv_id,
)

NOW = "2026-10-05T09:00:00Z"
GARIBALDI_PAGE = "3af5a429-a028-81e9-807c-dd2d4c071bfd"
BRUCK_PAGE = "3cf5a429-a028-8112-85a1-e1e1b2567c43"

#: Modules this task's hard wall forbids (constraint 4 / EIC-10). Checked with
#: `ast` over the real imports, not a substring search, because the module's
#: own docstring names all of them on purpose.
FORBIDDEN_MODULES = frozenset({
    "gmv_monad_materializer",
    "gmv_monad_backup",
    "gmv_crawler_atom_builder",
    "gmv_crawler_relation_atom_builder",
    "gmv_atom_validator",
    "gmv_crawler_public_projector",
    "gmv_notion_projection_adapter",
    "gmv_crawler_orchestrator",
    "gmv_run_ledger",
    "area35_validator",
})


@pytest.fixture
def target_dir(tmp_path: Path) -> Path:
    """A fresh, test-owned destination directory.

    Deliberately NOT `tmp_path` itself: `tests/conftest.py`'s autouse
    `isolated_gmv` fixture has already created `.gmv_core/` under it, so
    "this directory contains exactly the one canon file" is only a meaningful
    assertion against a directory the test owns."""
    return tmp_path / "area35_canon"


def make_record(**overrides) -> dict:
    """One record in the exact shape `adapter_notion._record()` produces with
    `--with-bodies`, confirmed live on 2026-10-05 against the real `artista`
    data source (keys: id, titolo, campi, relazioni, servizio, corpo)."""
    record = {
        "id": GARIBALDI_PAGE,
        "titolo": "Federico Garibaldi",
        "campi": {
            "nome": "Federico Garibaldi",
            "anno_nascita": 1968,
            "luogo_nascita": "Chiavari",
            "nazionalita": "Italiana",
        },
        "relazioni": {"mostre": ["3af5a429-a028-81ae-8d78-f2ef7594594a"], "opere": []},
        "servizio": {"stato": "Parziale", "pubblicabile": "__NO__"},
        "corpo": "IDENTITÀ\nNome completo: Federico Garibaldi",
    }
    record.update(overrides)
    return record


def make_registry(entities: list[dict]) -> dict:
    return {"note": "test fixture", "entities": entities}


GARIBALDI_ENTRY = {
    "gmv_id": "GMV-000001", "entity_type": "ARTIST",
    "canonical_name": "Federico Garibaldi", "aliases": ["Garibaldi"], "status": "ACTIVE",
}
BRUCK_ENTRY = {
    "gmv_id": "GMV-000004", "entity_type": "ARTIST",
    "canonical_name": "Florencia Bruck", "aliases": ["Florencia S.M. Brück"], "status": "ACTIVE",
}


def frontmatter_of(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    block = text.split("---\n", 2)[1]
    return yaml.safe_load(block)


# --- Q1/Q2: a known entity produces exactly the decided file ---

def test_known_registry_entity_writes_the_expected_file(target_dir: Path) -> None:
    """Q1/Q2: one file, at `<gmv_id>.md`, under the caller's directory, with
    the page's real body text and nothing invented around it."""
    registry = make_registry([GARIBALDI_ENTRY])
    result = canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir, now=NOW, registry=registry,
    )
    assert result.outcome == canon.OUTCOME_WRITTEN
    assert result.gmv_id == "GMV-000001"
    assert result.target_path == target_dir / "GMV-000001.md"
    assert result.target_path.is_file()
    assert list(target_dir.iterdir()) == [result.target_path]

    text = result.target_path.read_text(encoding="utf-8")
    assert frontmatter_of(result.target_path) == {
        "schema": "GMV_NOTION_CANON_SNAPSHOT_V1",
        "gmv_id": "GMV-000001",
        "entity_type": "ARTIST",
        "canonical_name": "Federico Garibaldi",
        "status": "canon_unaudited",
        "source_notion_page_id": GARIBALDI_PAGE,
        "exported_at": NOW,
    }
    assert text == (
        "---\n"
        "schema: GMV_NOTION_CANON_SNAPSHOT_V1\n"
        "gmv_id: GMV-000001\n"
        "entity_type: ARTIST\n"
        "canonical_name: Federico Garibaldi\n"
        "status: canon_unaudited\n"
        f"source_notion_page_id: {GARIBALDI_PAGE}\n"
        f"exported_at: '{NOW}'\n"
        "---\n"
        "\n"
        "# NOTION TITLE\n"
        "Federico Garibaldi\n"
        "\n"
        "# NOTION PAGE\n"
        "IDENTITÀ\n"
        "Nome completo: Federico Garibaldi\n"
    )


def test_written_frontmatter_is_exact_and_not_the_monad_schema(target_dir: Path) -> None:
    """Q2: field order is the REAL Monad's (schema, gmv_id, entity_type,
    canonical_name, status, then the two Notion-specific ones), read off
    `03_STATE/ombra/GMV-000001.md`, and `schema` is never the Monad's id --
    a canon file has no ATOMS section, so a consumer keying on the Monad
    schema would read Notion prose as verified atoms."""
    real_monad = (ROOT / "03_STATE" / "ombra" / "GMV-000001.md").read_text(encoding="utf-8")
    monad_keys = [
        line.split(":", 1)[0]
        for line in real_monad.splitlines()[1:6]
    ]
    registry = make_registry([GARIBALDI_ENTRY])
    result = canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir, now=NOW, registry=registry,
    )
    canon_lines = result.target_path.read_text(encoding="utf-8").splitlines()
    canon_keys = [line.split(":", 1)[0] for line in canon_lines[1:8]]

    assert monad_keys == ["schema", "gmv_id", "entity_type", "canonical_name", "status"]
    assert canon_keys[:5] == monad_keys
    assert canon_keys[5:] == ["source_notion_page_id", "exported_at"]
    assert frontmatter_of(result.target_path)["schema"] != "GMV_KNOWLEDGE_MONAD_V1"
    assert "# ATOMS" not in result.target_path.read_text(encoding="utf-8")


# --- Q3/Q7: the registry governs identity; Notion's strings are recorded, not trusted ---

def test_registry_wins_over_the_notion_strings(target_dir: Path) -> None:
    """Q3: the live GMV-000004 case. Notion titles the page "Florencia S.M.
    Brück"; the registry's `canonical_name` is "Florencia Bruck". The
    frontmatter states the registry's, and Notion's own string is preserved
    verbatim in `# NOTION TITLE` rather than being silently replaced."""
    registry = make_registry([BRUCK_ENTRY])
    record = make_record(id=BRUCK_PAGE, titolo="Florencia S.M. Brück", corpo="IDENTITÀ\nNome completo: Florencia S.M. Brück")
    result = canon.export_notion_page_to_canon(
        record, "Florencia S.M. Brück", target_dir, now=NOW, registry=registry,
    )
    front = frontmatter_of(result.target_path)
    assert result.gmv_id == "GMV-000004"
    assert front["canonical_name"] == "Florencia Bruck"
    assert front["gmv_id"] == "GMV-000004"
    text = result.target_path.read_text(encoding="utf-8")
    assert "# NOTION TITLE\nFlorencia S.M. Brück\n" in text
    assert "# NOTION PAGE\nIDENTITÀ\nNome completo: Florencia S.M. Brück\n" in text


def test_alias_match_resolves_to_the_registry_gmv_id(target_dir: Path) -> None:
    """Q7: an alias match is the resolver's job, reused. This module does not
    re-derive it: it asks `resolve_entity_gmv_id()`, which the test also
    cross-checks against the real registry so the two can never disagree
    about what resolves."""
    real_registry = _load_entity_registry()
    assert resolve_entity_gmv_id("Florencia S.M. Brück", real_registry) == "GMV-000004"

    registry = make_registry([BRUCK_ENTRY])
    result = canon.export_notion_page_to_canon(
        make_record(id=BRUCK_PAGE, titolo="Florencia S.M. Brück"),
        "Florencia S.M. Brück", target_dir, now=NOW, registry=registry,
    )
    assert result.outcome == canon.OUTCOME_WRITTEN
    assert result.gmv_id == "GMV-000004"


# --- Q4/Q5: the unresolved path proposes, and never writes ---

def test_unrecognized_entity_is_proposed_and_never_written(target_dir: Path) -> None:
    """Q4: an unknown name produces a real `EntityIdentityProposal` carrying
    the page as its source, and leaves the directory completely empty. No
    `gmv_id` is invented -- `result.gmv_id` stays `None`, which is what makes
    "never auto-minted" observable from outside."""
    registry = make_registry([GARIBALDI_ENTRY])
    record = make_record(id="deadbeef-0000-0000-0000-000000000001", titolo="Tizio Quarkus")
    result = canon.export_notion_page_to_canon(
        record, "Tizio Quarkus", target_dir, now=NOW, registry=registry,
    )
    assert result.outcome == canon.OUTCOME_PROPOSED
    assert result.gmv_id is None
    assert not target_dir.exists(), "an unresolved name created the canon directory"
    proposal = result.proposal
    assert proposal is not None
    assert proposal.raw_name == "Tizio Quarkus"
    assert proposal.source_id == "notion:page/deadbeef-0000-0000-0000-000000000001"
    assert proposal.evidence_excerpt == "Tizio Quarkus"
    assert proposal.suggested_entity_type == ""


def test_unresolved_page_lands_in_the_shared_identity_queue(tmp_path: Path) -> None:
    """Q5: the caller-side wiring, with the REAL queue writer. The export
    function itself does not queue (mirroring `propose_entity_identity()`'s
    own contract), so this test composes the two exactly as `main()` does and
    pins the consequences: one JSONL line, the registry untouched, the canon
    directory still empty."""
    registry_path = tmp_path / "gmv_entity_registry.json"
    registry_path.write_text(json.dumps(make_registry([GARIBALDI_ENTRY])), encoding="utf-8")
    before = registry_path.read_bytes()

    canon_dir = tmp_path / "canon_out"
    queue_path = tmp_path / "runtime" / "entity_identity_proposal_queue.jsonl"
    result = canon.export_notion_page_to_canon(
        make_record(id="deadbeef-0000-0000-0000-000000000002", titolo="Caio Sempronio"),
        "Caio Sempronio", canon_dir, now=NOW, registry=make_registry([GARIBALDI_ENTRY]),
    )
    written = append_entity_identity_proposals((result.proposal,), queue_path, now=NOW)

    assert written == 1
    record = json.loads(queue_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["raw_name"] == "Caio Sempronio"
    assert record["queued_at"] == NOW
    assert not canon_dir.exists(), "an unresolved name created the canon directory"
    assert registry_path.read_bytes() == before


# --- Q6: an unnamed page names nothing ---

def test_empty_title_writes_nothing_and_queues_nothing(target_dir: Path, tmp_path: Path) -> None:
    """Q6, attacked from both directions. `adapter_notion._record()` replaces
    a missing title with the literal "(senza titolo) <id>", so a caller that
    passed `record["titolo"]` blindly would hand a placeholder to entity
    resolution; the CLI passes the raw property instead (see
    `_export_one_data_source`), which arrives here as `""`. Neither `""` nor
    whitespace may produce a file, and neither may be pushed into the human
    review queue as a name nobody can confirm."""
    registry = make_registry([GARIBALDI_ENTRY])
    for blank in ("", "   ", "\t\n"):
        result = canon.export_notion_page_to_canon(
            make_record(titolo="(senza titolo) " + GARIBALDI_PAGE), blank, target_dir,
            now=NOW, registry=registry,
        )
        assert result.outcome == canon.OUTCOME_NO_NAME
        assert result.gmv_id is None and result.target_path is None and result.proposal is None
        assert result.page_id == GARIBALDI_PAGE
    assert not target_dir.exists()

    queue_path = tmp_path / "queue.jsonl"
    assert append_entity_identity_proposals((), queue_path, now=NOW) == 0
    assert not queue_path.exists()


# --- Q8/Q9: the resolver's ambiguity and a broken registry ---

def test_ambiguous_name_writes_nothing(target_dir: Path) -> None:
    """Q8: a name claimed by two registry entities. The resolver answers
    `None` (never the first match); this module proposes instead of writing,
    which is the documented, deliberately-misleading-but-visible consequence
    `propose_entity_identity()` records for the homonym case. What matters
    here is only that no file is written and no `gmv_id` is chosen."""
    registry = make_registry([
        {**GARIBALDI_ENTRY, "canonical_name": "Studio Omonimo"},
        {"gmv_id": "GMV-000009", "entity_type": "INSTITUTION",
         "canonical_name": "Studio Omonimo", "aliases": [], "status": "ACTIVE"},
    ])
    result = canon.export_notion_page_to_canon(
        make_record(id="deadbeef-0000-0000-0000-000000000003", titolo="Studio Omonimo"),
        "Studio Omonimo", target_dir, now=NOW, registry=registry,
    )
    assert result.outcome == canon.OUTCOME_PROPOSED
    assert result.gmv_id is None
    assert not target_dir.exists()


@pytest.mark.parametrize(
    ("entities", "query_name", "expected_message"),
    [
        pytest.param(
            [GARIBALDI_ENTRY, {**GARIBALDI_ENTRY, "canonical_name": "Federico G."}],
            "Federico Garibaldi",
            "matches 2 entries",
            id="duplicate_gmv_id",
        ),
        pytest.param(
            [{**GARIBALDI_ENTRY, "canonical_name": "   "}],
            "Garibaldi",
            "empty canonical_name",
            id="blank_canonical_name_matched_through_an_alias",
        ),
        pytest.param(
            [{**GARIBALDI_ENTRY, "entity_type": ""}],
            "Federico Garibaldi",
            "empty entity_type",
            id="empty_entity_type",
        ),
    ],
)
def test_registry_defects_refuse_the_write(
    target_dir: Path, entities: list[dict], query_name: str, expected_message: str,
) -> None:
    """Q9: a registry that cannot state a canonical name or a type for a
    resolved `gmv_id` must not yield a canon file with an empty frontmatter
    field, and two rows sharing one `gmv_id` must not be silently arbitrated.
    Raising keeps the same BLOCKER-stops-the-write convention
    `gmv_monad_materializer`'s M-SCHEMA05 uses, re-expressed here because that
    module is inside this task's hard wall.

    The second case is deliberately reached through the entity's `alias`, not
    its `canonical_name`: a blank `canonical_name` makes the name UNMATCHABLE
    in the first place (the resolver skips blank names), so it never reaches
    the frontmatter gate on that route."""
    with pytest.raises(canon.CanonExportError) as excinfo:
        canon.export_notion_page_to_canon(
            make_record(), query_name, target_dir,
            now=NOW, registry=make_registry(entities),
        )
    assert expected_message in str(excinfo.value)
    assert not target_dir.exists()


def test_blank_canonical_name_leaves_the_name_unresolvable(target_dir: Path) -> None:
    """Q9, the neighbouring real behaviour, pinned because it is easy to
    mistake for the case above: a registry entry whose `canonical_name` is
    blank is skipped by `resolve_entity_gmv_id()` (point 4 of its docstring),
    so a page titled with that name is PROPOSED, not written and not refused.
    The two states are different facts for a human fixing the registry."""
    registry = make_registry([{**GARIBALDI_ENTRY, "canonical_name": "   "}])
    result = canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir, now=NOW, registry=registry,
    )
    assert result.outcome == canon.OUTCOME_PROPOSED
    assert not target_dir.exists()


# --- Q10: the hard wall ---

def test_module_never_imports_the_monad_or_atom_modules() -> None:
    """Q10, the constraint-4c non-interference check. `ast` over the module's
    real imports rather than a substring search: the module's docstring names
    every forbidden module on purpose (to record the wall), so a naive `in
    source` scan would flag that documentation as a dependency."""
    source = (ROOT / "10_API" / "gmv_notion_canon_export.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported & FORBIDDEN_MODULES == set()
    # And the ones it must reuse, so the "reused, not reinvented" claim in the
    # docstring is checked by the same test rather than left to review.
    assert {"adapter_notion", "credentials", "secure_storage"} <= imported
    assert "gmv_crawler_entity_resolver" in imported
    assert "gmv_crawler_entity_identity_proposal_queue" in imported

    # No module-level name in this file is atom- or Monad-shaped either, so
    # the EIC-10 wall is not re-entered through a re-exported helper: there is
    # no public surface here a later caller could use to reach an atom STATUS.
    defined = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }
    assert not any("atom" in name.lower() or "monad" in name.lower() for name in defined)


def test_module_never_writes_outside_the_caller_target_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Q10/Q11 at runtime, not just in the import graph: every write this
    module performs goes through the one recorded primitive, and every path
    it receives is inside the caller's `target_dir` -- so no code path can
    reach `03_STATE/ombra/` or anywhere else on the user's disk."""
    seen: list[Path] = []
    real_atomic_write_text = canon.atomic_write_text

    def _recording(path: Path, text: str) -> None:
        seen.append(Path(path))
        real_atomic_write_text(path, text)

    monkeypatch.setattr(canon, "atomic_write_text", _recording)
    registry = make_registry([GARIBALDI_ENTRY])
    target_dir = tmp_path / "area35_canon"
    canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir, now=NOW, registry=registry,
    )
    canon.export_notion_page_to_canon(
        make_record(id="deadbeef-0000-0000-0000-000000000004", titolo="Ignoto Uno"),
        "Ignoto Uno", target_dir, now=NOW, registry=registry,
    )
    assert seen == [target_dir / "GMV-000001.md"]
    assert all(path.parent == target_dir for path in seen)


# --- Q11: file names can only ever be a registry `gmv_id` ---

def test_only_registry_gmv_ids_become_file_names(target_dir: Path) -> None:
    """Q11, adversarial. Notion-controlled text (`titolo`, `corpo`) gets
    strange enough to try a path escape -- `../../etc/passwd`, an absolute
    path -- and must reach neither the file name nor anything outside the two
    Notion sections it is legitimately rendered into."""
    hostile = "../../../../etc/passwd"
    registry = make_registry([GARIBALDI_ENTRY])
    result = canon.export_notion_page_to_canon(
        make_record(titolo=hostile, corpo=f"body line\n{hostile}\nsecond line"),
        "Federico Garibaldi", target_dir, now=NOW, registry=registry,
    )
    assert result.target_path == target_dir / "GMV-000001.md"
    assert result.target_path.parent == target_dir
    assert sorted(p.name for p in target_dir.iterdir()) == ["GMV-000001.md"]

    text = result.target_path.read_text(encoding="utf-8")
    generated, _, notional = text.partition("# NOTION PAGE")
    assert f"# NOTION TITLE\n{hostile}\n" in generated
    assert notional == f"\nbody line\n{hostile}\nsecond line\n"
    # Nothing Notion said appears in the frontmatter: every generated field is
    # the registry's or a module constant's.
    front = frontmatter_of(result.target_path)
    assert front["canonical_name"] == "Federico Garibaldi"
    assert set(front) == {
        "schema", "gmv_id", "entity_type", "canonical_name", "status",
        "source_notion_page_id", "exported_at",
    }


# --- Q12: write properties ---

def test_write_is_private_atomic_and_idempotent(target_dir: Path) -> None:
    """Q12: `secure_storage.atomic_write_text` gives 0700 directory / 0600 file
    (no partial file, no world-readable canon text) and a byte-identical
    second export for the same page and `now`."""
    import stat

    registry = make_registry([GARIBALDI_ENTRY])
    first = canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir, now=NOW, registry=registry,
    )
    assert stat.S_IMODE(target_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(first.target_path.stat().st_mode) == 0o600
    assert [p.name for p in target_dir.iterdir()] == ["GMV-000001.md"], "a temp file was left behind"

    second = canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir, now=NOW, registry=registry,
    )
    assert first.target_path.read_bytes() == second.target_path.read_bytes()

    third = canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir, now="2026-10-06T00:00:00Z", registry=registry,
    )
    assert frontmatter_of(third.target_path)["exported_at"] == "2026-10-06T00:00:00Z"


# --- Q13/Q14: the CLI caller ---

def test_cli_default_destination_is_the_canon_folder() -> None:
    """Q13: the wall against `03_STATE/ombra/` also holds at the CLI default.
    `CANON_DIR` is a sibling of `03_STATE/`, never the Monad folder, and it is
    inherited into the "never Git" class by `03_STATE/`'s existing
    governance row rather than needing an entry of its own."""
    assert canon.CANON_DIR == ROOT / "03_STATE" / "area35_canon"
    assert canon.CANON_DIR != ROOT / "03_STATE" / "ombra"
    assert canon.CANON_DIR.parent == ROOT / "03_STATE"
    assert "/03_STATE/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert canon.IDENTITY_PROPOSAL_QUEUE_PATH == (
        ROOT / "01_RUNTIME" / "gmv_crawler" / "entity_identity_proposal_queue.jsonl"
    )


def test_export_run_never_writes_the_entity_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Q14: `main()`'s whole path, with the live Notion read replaced by the
    real `adapter_notion` functions returning a canned `artista` result (one
    resolvable page, one unknown, one with no title). Pinned: the canon
    directory gets exactly the one resolvable file, the identity queue gets
    exactly the one unknown name, and `00_CONFIG/gmv_entity_registry.json` is
    byte-identical before and after -- the run proposes, it never mints."""
    real_registry_path = ROOT / "00_CONFIG" / "gmv_entity_registry.json"
    before = real_registry_path.read_bytes()

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "entita": {"artista": {
            "notion_database_id": "db-1",
            "biografia_in_corpo": True,
            "campi": {"nome": {"notion": "Nome"}, "anno_nascita": {"notion": "Anno"}},
            "relazioni": {}, "servizio": {},
        }},
    }), encoding="utf-8")
    token_path = tmp_path / "notion_token"
    token_path.write_text("ntn_fake_for_test_only\n", encoding="utf-8")

    pages = [
        {"id": GARIBALDI_PAGE, "properties": {"Nome": {"type": "title", "title": [{"plain_text": "Federico Garibaldi"}]}}},
        {"id": "deadbeef-0000-0000-0000-00000000000a", "properties": {"Nome": {"type": "title", "title": [{"plain_text": "Ignota Novanta"}]}}},
        {"id": "deadbeef-0000-0000-0000-00000000000b", "properties": {}},
    ]
    bodies = {GARIBALDI_PAGE: "IDENTITÀ\nFederico Garibaldi"}
    monkeypatch.setattr(canon.adapter_notion, "_query_pagine", lambda db_id, tok: pages)
    monkeypatch.setattr(canon.adapter_notion, "_corpo", lambda page_id, tok: bodies.get(page_id, ""))

    canon_dir = tmp_path / "area35_canon"
    queue_path = tmp_path / "entity_identity_proposal_queue.jsonl"
    exit_code = canon.main([
        "--config", str(config_path), "--token-file", str(token_path),
        "--out-dir", str(canon_dir), "--proposal-queue", str(queue_path),
        "--now", NOW,
    ])

    assert exit_code == 0
    assert sorted(p.name for p in canon_dir.iterdir()) == ["GMV-000001.md"]
    lines = queue_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["raw_name"] == "Ignota Novanta"
    assert real_registry_path.read_bytes() == before, "the run minted or edited a gmv_id"


def test_cli_reports_a_data_source_it_could_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Q14, the failure half. One unreadable data source does not abandon the
    other one (the continue-and-report shape `adapter_notion.main()` already
    uses), but the run must not exit 0 either -- a scheduled caller reading
    the exit code would otherwise read a silent success over a run that
    exported nothing."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "entita": {
            "artista": {
                "notion_database_id": "db-1", "biografia_in_corpo": True,
                "campi": {"nome": {"notion": "Nome"}},
            },
            "mostra": {"notion_database_id": "", "campi": {"titolo": {"notion": "Titolo"}}},
        },
    }), encoding="utf-8")
    token_path = tmp_path / "notion_token"
    token_path.write_text("ntn_fake_for_test_only\n", encoding="utf-8")

    pages = [{"id": GARIBALDI_PAGE, "properties": {
        "Nome": {"type": "title", "title": [{"plain_text": "Federico Garibaldi"}]},
    }}]
    monkeypatch.setattr(canon.adapter_notion, "_query_pagine", lambda db_id, tok: pages)
    monkeypatch.setattr(canon.adapter_notion, "_corpo", lambda page_id, tok: "corpo")

    exit_code = canon.main([
        "--config", str(config_path), "--token-file", str(token_path),
        "--out-dir", str(tmp_path / "canon_out"),
        "--proposal-queue", str(tmp_path / "queue.jsonl"), "--now", NOW,
    ])
    stderr = capsys.readouterr().err
    assert exit_code == 1
    assert "mostra" in stderr and "notion_database_id" in stderr
    assert [p.name for p in (tmp_path / "canon_out").iterdir()] == ["GMV-000001.md"]


def test_cli_rejects_unknown_entity_keys(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A typo in `--entities` is a 2, not a silent run that read nothing."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"entita": {"artista": {"campi": {"nome": {}}}}}), encoding="utf-8")
    token_path = tmp_path / "notion_token"
    token_path.write_text("ntn_fake_for_test_only\n", encoding="utf-8")
    exit_code = canon.main([
        "--config", str(config_path), "--token-file", str(token_path),
        "--out-dir", str(tmp_path / "canon_out"), "--entities", "artistai",
        "--proposal-queue", str(tmp_path / "queue.jsonl"), "--now", NOW,
    ])
    assert exit_code == 2
    assert "artistai" in capsys.readouterr().err
    assert not (tmp_path / "canon_out").exists()
