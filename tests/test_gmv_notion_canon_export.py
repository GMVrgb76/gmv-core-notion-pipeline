"""GMV Notion canon export -- per-page canon files under `03_STATE/area35_canon/`.

Pins the guarantees `10_API/gmv_notion_canon_export.py`'s own docstrings
claim, each attacked directly rather than re-read:

  Q1  EVERY real page gets a file. A name that resolves to a registry `gmv_id`
      gets the file WITH `gmv_id`/`entity_type`/`canonical_name`
      -> test_known_registry_entity_writes_the_expected_file
  Q2  frontmatter field names, field ORDER and the two section headers are
      exactly as decided, and `schema` is NOT the Monad's
      -> test_written_frontmatter_is_exact_and_not_the_monad_schema
  Q3  the frontmatter's canonical_name/entity_type come from the registry
      entry, never from Notion's strings (real case: GMV-000004, Notion
      "Florencia S.M. Brück" vs registry "Florencia Bruck")
      -> test_registry_wins_over_the_notion_strings
  Q4  an UNRESOLVED name still gets a file -- with those three keys ABSENT, not
      empty -- AND still gets a real proposal. Not one-or-the-other.
      -> test_unresolved_name_is_still_filed_and_still_proposed
  Q5  the caller-side wiring: the returned proposal lands in the SAME queue
      file the crawler nightly run and review tool use, in the same run that
      wrote the file
      -> test_unresolved_page_is_filed_and_lands_in_the_shared_identity_queue
  Q6  a page Notion left untitled is still filed, with `notion_title: ''` and
      never the "(senza titolo) <id>" placeholder, and is NOT proposed
      -> test_untitled_page_is_filed_empty_and_never_proposed
  Q7  a page whose name matches a registry `aliases` entry resolves to that
      entity's canonical `gmv_id` (the real Florencia case, not a
      hypothetical one)
      -> test_alias_match_resolves_to_the_registry_gmv_id
  Q8  a HOMONYM (one name claimed by two registry entities) picks no winner --
      the resolver's own "None, never the first match" rule, not re-decided
      here -- and is still filed and still proposed
      -> test_ambiguous_name_files_without_choosing_a_winner
  Q9  a broken registry entry (two rows with one `gmv_id`; empty
      `canonical_name`/`entity_type`) refuses the write instead of picking a
      winner, but only for the page that reached it
      -> test_registry_defects_refuse_the_write
  Q10 nothing in this module imports or calls the Monad/atom pipeline
      -> test_module_never_imports_the_monad_or_atom_modules
  Q11 no Notion-controlled text can influence a path -- neither the page's
      title/body nor its own id -- and nothing is ever written outside the
      caller's `target_dir`
      -> test_hostile_notion_text_and_page_ids_cannot_escape_the_target_dir
  Q12 the write is atomic and private (secure_storage's 0700 dir / 0600 file),
      and re-exporting the same page is idempotent
      -> test_write_is_private_atomic_and_idempotent
  Q13 the hard wall on `03_STATE/ombra/`: the CLI's default destination is the
      canon folder, and the CLI's default identity queue is the SHARED one
      -> test_cli_default_destination_is_the_canon_folder
  Q14 `main()` never writes the entity registry, files every page it read, and
      queues exactly the unresolved names
      -> test_export_run_files_every_page_and_never_writes_the_entity_registry
  Q15 queueing is a side effect, not a precondition: an unwritable queue does
      not cost a single canon file, and does not exit 0 either
      -> test_an_unwritable_queue_costs_no_canon_file
  Q16 `notion_kind` is Notion's own raw label and is NEVER mapped onto the
      governed `entity_type` vocabulary (Group B, not decided)
      -> test_notion_kind_is_the_raw_notion_label_and_is_never_mapped
  Q17 the renderer refuses a partial identity rather than writing a file that
      claims to know an entity
      -> test_renderer_refuses_a_partial_identity
  Q18 one unreadable data source does not abandon the rest, and does not exit 0
      -> test_cli_reports_a_data_source_it_could_not_read
  Q19 a typo in `--entities` is a 2, not a silent run that read nothing
      -> test_cli_rejects_unknown_entity_keys
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

#: Modules this task's hard wall forbids (EIC-10). Checked with `ast` over the
#: real imports, not a substring search, because the module's own docstring
#: names all of them on purpose.
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


def frontmatter_keys(path: Path) -> list[str]:
    """Frontmatter key ORDER as written on disk, not as a dict would compare
    equal -- a `yaml.safe_dump(sort_keys=True)` regression would still load
    into an equal dict, so the order has to be read back off the file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---"
    closing = lines.index("---", 1)
    return [line.split(":", 1)[0] for line in lines[1:closing]]


# --- Q1/Q2: a known entity produces exactly the decided file ---

def test_known_registry_entity_writes_the_expected_file(target_dir: Path) -> None:
    """Q1/Q2: one file, at `<page_id>.md`, under the caller's directory, with
    the page's real body text and nothing invented around it."""
    registry = make_registry([GARIBALDI_ENTRY])
    result = canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir,
        now=NOW, notion_kind="artista", registry=registry,
    )
    assert result.outcome == canon.OUTCOME_WRITTEN
    assert result.gmv_id == "GMV-000001"
    assert result.notion_kind == "artista"
    assert result.proposal is None
    assert result.target_path == target_dir / f"{GARIBALDI_PAGE}.md"
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
        "notion_kind": "artista",
        "notion_title": "Federico Garibaldi",
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
        "notion_kind: artista\n"
        "notion_title: Federico Garibaldi\n"
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
    canonical_name, status, then the four Notion-specific ones), read off
    `03_STATE/ombra/GMV-000001.md`, and `schema` is never the Monad's id --
    a canon file has no ATOMS section, so a consumer keying on the Monad
    schema would read Notion prose as verified atoms."""
    real_monad = (ROOT / "03_STATE" / "ombra" / "GMV-000001.md").read_text(encoding="utf-8")
    monad_keys = [line.split(":", 1)[0] for line in real_monad.splitlines()[1:6]]
    registry = make_registry([GARIBALDI_ENTRY])
    result = canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir,
        now=NOW, notion_kind="artista", registry=registry,
    )
    canon_keys = frontmatter_keys(result.target_path)

    assert monad_keys == ["schema", "gmv_id", "entity_type", "canonical_name", "status"]
    assert canon_keys[:5] == monad_keys
    assert canon_keys[5:] == ["source_notion_page_id", "notion_kind", "notion_title", "exported_at"]
    assert frontmatter_of(result.target_path)["schema"] != "GMV_KNOWLEDGE_MONAD_V1"
    assert "# ATOMS" not in result.target_path.read_text(encoding="utf-8")

    # And the unresolved shape: the SAME order with the three optional keys
    # removed from the middle, not moved to the end.
    unresolved = canon.export_notion_page_to_canon(
        make_record(id=BRUCK_PAGE, titolo="Tizio Quarkus"), "Tizio Quarkus", target_dir,
        now=NOW, notion_kind="artista", registry=registry,
    )
    assert frontmatter_keys(unresolved.target_path) == [
        "schema", "status", "source_notion_page_id", "notion_kind", "notion_title", "exported_at",
    ]


# --- Q3/Q7: the registry governs identity; Notion's strings are recorded, not trusted ---

def test_registry_wins_over_the_notion_strings(target_dir: Path) -> None:
    """Q3: the live GMV-000004 case. Notion titles the page "Florencia S.M.
    Brück"; the registry's `canonical_name` is "Florencia Bruck". The
    frontmatter states the registry's, and Notion's own string is preserved
    verbatim -- in `notion_title` and in `# NOTION TITLE` -- rather than being
    silently replaced."""
    registry = make_registry([BRUCK_ENTRY])
    record = make_record(id=BRUCK_PAGE, titolo="Florencia S.M. Brück", corpo="IDENTITÀ\nNome completo: Florencia S.M. Brück")
    result = canon.export_notion_page_to_canon(
        record, "Florencia S.M. Brück", target_dir, now=NOW, notion_kind="artista", registry=registry,
    )
    front = frontmatter_of(result.target_path)
    assert result.gmv_id == "GMV-000004"
    assert front["canonical_name"] == "Florencia Bruck"
    assert front["gmv_id"] == "GMV-000004"
    assert front["notion_title"] == "Florencia S.M. Brück"
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
        "Florencia S.M. Brück", target_dir, now=NOW, notion_kind="artista", registry=registry,
    )
    assert result.outcome == canon.OUTCOME_WRITTEN
    assert result.gmv_id == "GMV-000004"


# --- Q4/Q5: the unresolved path is filed AND proposed ---

def test_unresolved_name_is_still_filed_and_still_proposed(target_dir: Path) -> None:
    """Q4, the redesign's central guarantee, attacked on both halves at once.
    An unknown name produces a file AND a real `EntityIdentityProposal`; the
    three registry-only keys are ABSENT from the file (not `None`, not `''`),
    and `result.gmv_id` stays `None`, which is what makes "never auto-minted"
    observable from outside. Task 37's version returned here with no file at
    all -- that gate is gone, and this test is what says so."""
    registry = make_registry([GARIBALDI_ENTRY])
    record = make_record(id="deadbeef-0000-0000-0000-000000000001", titolo="Tizio Quarkus")
    result = canon.export_notion_page_to_canon(
        record, "Tizio Quarkus", target_dir, now=NOW, notion_kind="mostra", registry=registry,
    )
    assert result.outcome == canon.OUTCOME_WRITTEN
    assert result.gmv_id is None
    assert result.target_path == target_dir / "deadbeef-0000-0000-0000-000000000001.md"
    assert result.target_path.is_file()
    assert sorted(p.name for p in target_dir.iterdir()) == [result.target_path.name]

    front = frontmatter_of(result.target_path)
    for absent in ("gmv_id", "entity_type", "canonical_name"):
        assert absent not in front, f"{absent} must be absent, not rendered empty"
    assert front == {
        "schema": "GMV_NOTION_CANON_SNAPSHOT_V1",
        "status": "canon_unaudited",
        "source_notion_page_id": "deadbeef-0000-0000-0000-000000000001",
        "notion_kind": "mostra",
        "notion_title": "Tizio Quarkus",
        "exported_at": NOW,
    }

    proposal = result.proposal
    assert proposal is not None
    assert proposal.raw_name == "Tizio Quarkus"
    assert proposal.source_id == "notion:page/deadbeef-0000-0000-0000-000000000001"
    assert proposal.evidence_excerpt == "Tizio Quarkus"
    assert proposal.suggested_entity_type == ""

    # Adversarial: an EMPTY registry must not restore the old gate. This is
    # the 436-page case -- no `gmv_id` anywhere -- and it still files.
    empty = canon.export_notion_page_to_canon(
        make_record(id="deadbeef-0000-0000-0000-000000000002", titolo="Vuoto Registro"),
        "Vuoto Registro", target_dir, now=NOW, notion_kind="opera", registry=make_registry([]),
    )
    assert empty.gmv_id is None and empty.proposal is not None
    assert empty.target_path.is_file()
    assert len(list(target_dir.iterdir())) == 2


def test_unresolved_page_is_filed_and_lands_in_the_shared_identity_queue(tmp_path: Path) -> None:
    """Q5: the caller-side wiring, with the REAL queue writer. The export
    function itself does not queue (mirroring `propose_entity_identity()`'s
    own contract), so this test composes the two exactly as `main()` does and
    pins the consequences: the file IS on disk and the proposal is in the ONE
    JSONL line the nightly crawler and the review tool read."""
    canon_dir = tmp_path / "canon_out"
    queue_path = tmp_path / "runtime" / "entity_identity_proposal_queue.jsonl"
    result = canon.export_notion_page_to_canon(
        make_record(id="deadbeef-0000-0000-0000-000000000003", titolo="Caio Sempronio"),
        "Caio Sempronio", canon_dir, now=NOW, notion_kind="persona",
        registry=make_registry([GARIBALDI_ENTRY]),
    )
    assert result.target_path.is_file()
    queued = append_entity_identity_proposals((result.proposal,), queue_path, now=NOW)

    assert queued == 1
    record = json.loads(queue_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["raw_name"] == "Caio Sempronio"
    assert record["source_id"] == "notion:page/deadbeef-0000-0000-0000-000000000003"
    assert record["queued_at"] == NOW


# --- Q6: an untitled page is filed, empty, and never proposed ---

def test_untitled_page_is_filed_empty_and_never_proposed(target_dir: Path, tmp_path: Path) -> None:
    """Q6, attacked from both directions. `adapter_notion._record()` replaces
    a missing title with the literal "(senza titolo) <id>", so a caller that
    passed `record["titolo"]` blindly would put that placeholder into a
    required frontmatter field AND into the human review queue; the CLI passes
    the raw property instead (see `_export_one_data_source`), which arrives
    here as `""`. Such a page must still be FILED -- the redesign removed the
    skip branch -- with `notion_title: ''`, never the placeholder, and must
    NOT be proposed, because a blank `raw_name` in the one human queue is not
    a reviewable name."""
    registry = make_registry([GARIBALDI_ENTRY])
    placeholder = f"(senza titolo) {GARIBALDI_PAGE}"
    for index, blank in enumerate(("", "   ", "\t\n"), start=1):
        record = make_record(id=f"deadbeef-0000-0000-0000-{index:012d}",
                             titolo=placeholder)
        result = canon.export_notion_page_to_canon(
            record, blank, target_dir, now=NOW, notion_kind="sponsor", registry=registry,
        )
        assert result.outcome == canon.OUTCOME_WRITTEN
        assert result.gmv_id is None
        assert result.proposal is None, "a blank name must never reach the identity queue"
        assert result.entity_name == ""
        text = result.target_path.read_text(encoding="utf-8")
        assert "(senza titolo)" not in text
        front = frontmatter_of(result.target_path)
        assert front["notion_title"] == ""
        assert "notion_title" in front, "a required field must be present, not omitted"
        assert "# NOTION TITLE\n\n" in text

    queue_path = tmp_path / "queue.jsonl"
    assert append_entity_identity_proposals((), queue_path, now=NOW) == 0
    assert not queue_path.exists()


# --- Q8/Q9: the resolver's ambiguity and a broken registry ---

def test_ambiguous_name_files_without_choosing_a_winner(target_dir: Path) -> None:
    """Q8: a name claimed by two registry entities. The resolver answers
    `None` (never the first match); this module proposes, which is what
    `propose_entity_identity()`'s own docstring says a homonym produces, and
    -- the change from Task 37 -- still writes the file. What matters here is
    that no `gmv_id` is chosen and no winner is implied by the file."""
    registry = make_registry([
        {**GARIBALDI_ENTRY, "canonical_name": "Studio Omonimo"},
        {"gmv_id": "GMV-000009", "entity_type": "INSTITUTION",
         "canonical_name": "Studio Omonimo", "aliases": [], "status": "ACTIVE"},
    ])
    result = canon.export_notion_page_to_canon(
        make_record(id="deadbeef-0000-0000-0000-000000000004", titolo="Studio Omonimo"),
        "Studio Omonimo", target_dir, now=NOW, notion_kind="istituzione", registry=registry,
    )
    assert result.outcome == canon.OUTCOME_WRITTEN
    assert result.gmv_id is None
    assert result.proposal is not None and result.proposal.raw_name == "Studio Omonimo"
    assert result.target_path.is_file()
    assert "gmv_id" not in frontmatter_of(result.target_path)


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
    the frontmatter gate on that route -- see the neighbouring test below for
    that state."""
    with pytest.raises(canon.CanonExportError) as excinfo:
        canon.export_notion_page_to_canon(
            make_record(), query_name, target_dir,
            now=NOW, notion_kind="artista", registry=make_registry(entities),
        )
    assert expected_message in str(excinfo.value)
    assert not target_dir.exists()


def test_blank_canonical_name_leaves_the_name_unresolvable(target_dir: Path) -> None:
    """Q9, the neighbouring real behaviour, pinned because it is easy to
    mistake for the case above: a registry entry whose `canonical_name` is
    blank is skipped by `resolve_entity_gmv_id()` (point 4 of its docstring),
    so a page titled with that name is FILED with no `gmv_id` and a proposal,
    not refused. Under the old gate it was simply skipped; the two states are
    different facts for a human fixing the registry, so both are pinned."""
    registry = make_registry([{**GARIBALDI_ENTRY, "canonical_name": "   "}])
    result = canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir,
        now=NOW, notion_kind="artista", registry=registry,
    )
    assert result.outcome == canon.OUTCOME_WRITTEN
    assert result.gmv_id is None
    assert result.proposal is not None
    assert result.target_path.is_file()
    assert "gmv_id" not in frontmatter_of(result.target_path)


# --- Q10: the hard wall ---

def test_module_never_imports_the_monad_or_atom_modules() -> None:
    """Q10, the constraint-1 non-interference check. `ast` over the module's
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
    reach `03_STATE/ombra/` or anywhere else on the user's disk. Both the
    resolved and the UNRESOLVED page are exported, because the redesign made
    the unresolved one write too."""
    seen: list[Path] = []
    real_atomic_write_text = canon.atomic_write_text

    def _recording(path: Path, text: str) -> None:
        seen.append(Path(path))
        real_atomic_write_text(path, text)

    monkeypatch.setattr(canon, "atomic_write_text", _recording)
    registry = make_registry([GARIBALDI_ENTRY])
    target_dir = tmp_path / "area35_canon"
    canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir, now=NOW, notion_kind="artista", registry=registry,
    )
    canon.export_notion_page_to_canon(
        make_record(id="deadbeef-0000-0000-0000-000000000005", titolo="Ignoto Uno"),
        "Ignoto Uno", target_dir, now=NOW, notion_kind="artista", registry=registry,
    )
    assert seen == [target_dir / f"{GARIBALDI_PAGE}.md", target_dir / "deadbeef-0000-0000-0000-000000000005.md"]
    assert all(path.parent == target_dir for path in seen)


# --- Q11: nothing Notion controls can reach a path ---

def test_hostile_notion_text_and_page_ids_cannot_escape_the_target_dir(target_dir: Path) -> None:
    """Q11, adversarial on both halves. Task 37 only had to keep Notion's
    title and body out of the path, because the file name came from the
    registry. Now the page's OWN ID is the file name, and that id is
    Notion-controlled, so it gets attacked directly: path traversal
    (`../../../../etc/passwd`), an absolute path, a backslash separator, a
    dot-file (which would collide with `secure_storage`'s `.<name>.` temp
    files), a NUL, and the empty string. All must raise and write nothing.

    The title/body hostility from Task 37 is kept, and applied the way a real
    caller applies it -- the hostile title IS the `entity_name` argument, since
    that is what `_export_one_data_source()` reads out of the Notion property
    (it no longer reads `record["titolo"]`, see Q6). It must reach neither the
    file name nor anything outside the two Notion sections and the
    `notion_title` field it is legitimately rendered into."""
    hostile = "../../../../etc/passwd"
    registry = make_registry([GARIBALDI_ENTRY])
    result = canon.export_notion_page_to_canon(
        make_record(id="deadbeef-0000-0000-0000-000000000001", titolo=hostile,
                    corpo=f"body line\n{hostile}\nsecond line"),
        hostile, target_dir, now=NOW, notion_kind="artista", registry=registry,
    )
    assert result.target_path == target_dir / "deadbeef-0000-0000-0000-000000000001.md"
    assert result.target_path.parent == target_dir
    assert result.target_path.is_file()
    assert sorted(p.name for p in target_dir.iterdir()) == [result.target_path.name]

    text = result.target_path.read_text(encoding="utf-8")
    generated, _, notional = text.partition("# NOTION PAGE")
    assert f"# NOTION TITLE\n{hostile}\n" in generated
    assert notional == f"\nbody line\n{hostile}\nsecond line\n"
    # Nothing Notion said reaches the frontmatter's governed fields: the only
    # frontmatter value carrying Notion's own text is `notion_title`, which is
    # exactly the field meant to hold it.
    front = frontmatter_of(result.target_path)
    assert front["notion_title"] == hostile
    assert front["source_notion_page_id"] == "deadbeef-0000-0000-0000-000000000001"
    assert set(front) == {
        "schema", "status", "source_notion_page_id", "notion_kind", "notion_title", "exported_at",
    }

    # The resolved path keeps the registry's own strings in the identity
    # fields even when the page text is hostile.
    resolved = canon.export_notion_page_to_canon(
        make_record(titolo=hostile, corpo=hostile), "Federico Garibaldi", target_dir,
        now=NOW, notion_kind="artista", registry=registry,
    )
    assert resolved.target_path == target_dir / f"{GARIBALDI_PAGE}.md"
    front = frontmatter_of(resolved.target_path)
    assert front["canonical_name"] == "Federico Garibaldi"
    assert set(front) == {
        "schema", "gmv_id", "entity_type", "canonical_name", "status",
        "source_notion_page_id", "notion_kind", "notion_title", "exported_at",
    }

    for bad_id in (hostile, "/etc/passwd", "a/b", "a\\b", "..", ".", ".hidden", "a b", "a\0b", ""):
        with pytest.raises(canon.CanonExportError) as excinfo:
            canon.export_notion_page_to_canon(
                make_record(id=bad_id), "Federico Garibaldi", target_dir,
                now=NOW, notion_kind="artista", registry=registry,
            )
        assert "cannot be used as a canon file name" in str(excinfo.value)
    # And nothing was added or removed by any of the refused writes.
    assert sorted(p.name for p in target_dir.iterdir()) == [
        f"{GARIBALDI_PAGE}.md", "deadbeef-0000-0000-0000-000000000001.md",
    ]


# --- Q12: write properties ---

def test_write_is_private_atomic_and_idempotent(target_dir: Path) -> None:
    """Q12: `secure_storage.atomic_write_text` gives 0700 directory / 0600 file
    (no partial file, no world-readable canon text) and a byte-identical
    second export for the same page and `now`."""
    import stat

    registry = make_registry([GARIBALDI_ENTRY])
    first = canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir,
        now=NOW, notion_kind="artista", registry=registry,
    )
    assert stat.S_IMODE(target_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(first.target_path.stat().st_mode) == 0o600
    assert [p.name for p in target_dir.iterdir()] == [f"{GARIBALDI_PAGE}.md"], "a temp file was left behind"

    second = canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir,
        now=NOW, notion_kind="artista", registry=registry,
    )
    assert first.target_path.read_bytes() == second.target_path.read_bytes()

    third = canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir,
        now="2026-10-06T00:00:00Z", notion_kind="artista", registry=registry,
    )
    assert frontmatter_of(third.target_path)["exported_at"] == "2026-10-06T00:00:00Z"


# --- Q13/Q14/Q15: the CLI caller ---

def test_cli_default_destination_is_the_canon_folder() -> None:
    """Q13: the wall against `03_STATE/ombra/` also holds at the CLI default.
    `CANON_DIR` is a sibling of `03_STATE/`, never the Monad folder, and it is
    inherited into the "never Git" class by `03_STATE/`'s existing
    governance row rather than needing an entry of its own.

    Q13's second half is the redesign's constraint 4: `--proposal-queue`
    DEFAULTS to the shared queue, so a plain run grows the human review queue
    without anyone passing a flag. Asserted on the REAL parser object
    (`build_parser()`), not by re-deriving the default from the source text."""
    assert canon.CANON_DIR == ROOT / "03_STATE" / "area35_canon"
    assert canon.CANON_DIR != ROOT / "03_STATE" / "ombra"
    assert canon.CANON_DIR.parent == ROOT / "03_STATE"
    assert "/03_STATE/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert canon.IDENTITY_PROPOSAL_QUEUE_PATH == (
        ROOT / "01_RUNTIME" / "gmv_crawler" / "entity_identity_proposal_queue.jsonl"
    )

    defaults = canon.build_parser().parse_args(["--now", NOW])
    assert defaults.proposal_queue == str(canon.IDENTITY_PROPOSAL_QUEUE_PATH)
    assert defaults.out_dir == str(canon.CANON_DIR)
    assert defaults.entities is None, "no data source is excluded unless asked for"



def test_export_run_files_every_page_and_never_writes_the_entity_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Q14: `main()`'s whole path, with the live Notion read replaced by the
    real `adapter_notion` functions returning a canned `artista` result (one
    resolvable page, one unknown, one untitled) plus a second `mostra` data
    source. Pinned: every page read produces a file -- including the unknown
    and the untitled one, which is the redesign -- the identity queue gets
    exactly the one unknown name and NOT the untitled one, and
    `00_CONFIG/gmv_entity_registry.json` is byte-identical before and after.
    The run proposes, it never mints."""
    real_registry_path = ROOT / "00_CONFIG" / "gmv_entity_registry.json"
    before = real_registry_path.read_bytes()

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "entita": {
            "artista": {
                "notion_database_id": "db-1",
                "biografia_in_corpo": True,
                "campi": {"nome": {"notion": "Nome"}, "anno_nascita": {"notion": "Anno"}},
                "relazioni": {}, "servizio": {},
            },
            "mostra": {
                "notion_database_id": "db-2", "biografia_in_corpo": True,
                "campi": {"titolo": {"notion": "Titolo"}},
            },
        },
    }), encoding="utf-8")
    token_path = tmp_path / "notion_token"
    token_path.write_text("ntn_fake_for_test_only\n", encoding="utf-8")

    artist_pages = [
        {"id": GARIBALDI_PAGE, "properties": {"Nome": {"type": "title", "title": [{"plain_text": "Federico Garibaldi"}]}}},
        {"id": "deadbeef-0000-0000-0000-00000000000a", "properties": {"Nome": {"type": "title", "title": [{"plain_text": "Ignota Novanta"}]}}},
        {"id": "deadbeef-0000-0000-0000-00000000000b", "properties": {}},
    ]
    show_pages = [
        {"id": "deadbeef-0000-0000-0000-00000000000c", "properties": {"Titolo": {"type": "title", "title": [{"plain_text": "Mostra Senza Registro"}]}}},
    ]

    def _fake_query(db_id: str, tok: str) -> list[dict]:
        return {"db-1": artist_pages, "db-2": show_pages}[db_id]

    bodies = {GARIBALDI_PAGE: "IDENTITÀ\nFederico Garibaldi"}
    monkeypatch.setattr(canon.adapter_notion, "_query_pagine", _fake_query)
    monkeypatch.setattr(canon.adapter_notion, "_corpo", lambda page_id, tok: bodies.get(page_id, ""))

    canon_dir = tmp_path / "area35_canon"
    queue_path = tmp_path / "entity_identity_proposal_queue.jsonl"
    exit_code = canon.main([
        "--config", str(config_path), "--token-file", str(token_path),
        "--out-dir", str(canon_dir), "--proposal-queue", str(queue_path),
        "--now", NOW,
    ])

    assert exit_code == 0
    assert sorted(p.name for p in canon_dir.iterdir()) == [
        f"{GARIBALDI_PAGE}.md",
        "deadbeef-0000-0000-0000-00000000000a.md",
        "deadbeef-0000-0000-0000-00000000000b.md",
        "deadbeef-0000-0000-0000-00000000000c.md",
    ]
    # The two data sources' own labels reached the files verbatim, and the
    # untitled page's placeholder did not.
    assert frontmatter_of(canon_dir / f"{GARIBALDI_PAGE}.md")["notion_kind"] == "artista"
    assert frontmatter_of(
        canon_dir / "deadbeef-0000-0000-0000-00000000000c.md"
    )["notion_kind"] == "mostra"
    untitled_text = (canon_dir / "deadbeef-0000-0000-0000-00000000000b.md").read_text(encoding="utf-8")
    assert "(senza titolo)" not in untitled_text

    lines = queue_path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["raw_name"] for line in lines] == ["Ignota Novanta", "Mostra Senza Registro"]
    assert real_registry_path.read_bytes() == before, "the run minted or edited a gmv_id"


def test_an_unwritable_queue_costs_no_canon_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Q15: the redesign's constraint 4 read as a guarantee rather than a
    claim -- "still propose unresolved names, but as a side effect, never a
    gate" means a proposal being queued must never decide whether a file
    exists. Here the queue path is a FILE where a directory is needed, so
    `append_entity_identity_proposals()` raises `OSError`; every canon file
    must still be on disk, the failure must be on stderr, and the exit code
    must be 1 rather than 0 (a scheduled caller must not read success over a
    run whose identity half did not happen)."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "entita": {"artista": {
            "notion_database_id": "db-1", "biografia_in_corpo": True,
            "campi": {"nome": {"notion": "Nome"}},
        }},
    }), encoding="utf-8")
    token_path = tmp_path / "notion_token"
    token_path.write_text("ntn_fake_for_test_only\n", encoding="utf-8")
    pages = [
        {"id": "deadbeef-0000-0000-0000-00000000000d", "properties": {"Nome": {"type": "title", "title": [{"plain_text": "Ignota Novanta"}]}}},
    ]
    monkeypatch.setattr(canon.adapter_notion, "_query_pagine", lambda db_id, tok: pages)
    monkeypatch.setattr(canon.adapter_notion, "_corpo", lambda page_id, tok: "")

    blocked_queue = tmp_path / "queue_is_a_file.jsonl"
    blocked_queue.write_text("not a directory\n", encoding="utf-8")

    canon_dir = tmp_path / "area35_canon"
    exit_code = canon.main([
        "--config", str(config_path), "--token-file", str(token_path),
        "--out-dir", str(canon_dir),
        "--proposal-queue", str(blocked_queue / "queue.jsonl"), "--now", NOW,
    ])

    assert exit_code == 1
    assert [p.name for p in canon_dir.iterdir()] == ["deadbeef-0000-0000-0000-00000000000d.md"]
    stderr = capsys.readouterr().err
    assert "coda proposte non scritta" in stderr
    assert blocked_queue.read_text(encoding="utf-8") == "not a directory\n"


# --- Q16/Q17: the Notion label is not mapped, the renderer is all-or-nothing ---

def test_notion_kind_is_the_raw_notion_label_and_is_never_mapped(target_dir: Path) -> None:
    """Q16: `notion_kind` is whatever `config.json`'s `entita` key said, and
    the governed `entity_type` vocabulary is NEVER inferred from it. The six
    real labels are used verbatim -- `opera` stays `opera` and never becomes
    `WORK`, `istituzione` never becomes `INSTITUTION` -- because that mapping
    is an unmade governance decision (Group B). For a page that DID resolve,
    `entity_type` still comes from the registry and the two coexist as
    separate, unmapped fields."""
    registry = make_registry([GARIBALDI_ENTRY])
    for kind in ("artista", "mostra", "persona", "istituzione", "opera", "sponsor"):
        page_id = f"deadbeef-0000-0000-0000-{abs(hash(kind)) % 10**12:012d}"
        result = canon.export_notion_page_to_canon(
            make_record(id=page_id, titolo=f"Pagina {kind}"),
            f"Pagina {kind}", target_dir, now=NOW, notion_kind=kind, registry=registry,
        )
        assert frontmatter_of(result.target_path)["notion_kind"] == kind
        assert "entity_type" not in frontmatter_of(result.target_path)
        assert result.notion_kind == kind

    resolved = canon.export_notion_page_to_canon(
        make_record(), "Federico Garibaldi", target_dir,
        now=NOW, notion_kind="artista", registry=registry,
    )
    front = frontmatter_of(resolved.target_path)
    assert front["notion_kind"] == "artista"
    assert front["entity_type"] == "ARTIST"

    # A blank notion_kind is refused rather than rendered as an empty required
    # field, and a `notion_kind` that happens to BE a governed value is still
    # passed through untouched (it is Notion's string, not ours to validate).
    with pytest.raises(canon.CanonExportError) as excinfo:
        canon.export_notion_page_to_canon(
            make_record(id="deadbeef-0000-0000-0000-0000000000ee"), "X",
            target_dir, now=NOW, notion_kind="   ", registry=registry,
        )
    assert "notion_kind is a required frontmatter field" in str(excinfo.value)

    passthrough = canon.export_notion_page_to_canon(
        make_record(id="deadbeef-0000-0000-0000-0000000000ff"), "Y",
        target_dir, now=NOW, notion_kind="ARTIST", registry=registry,
    )
    assert frontmatter_of(passthrough.target_path)["notion_kind"] == "ARTIST"


def test_renderer_refuses_a_partial_identity() -> None:
    """Q17: the three registry-only fields are all-or-nothing. A file carrying
    `gmv_id` without `canonical_name` is exactly the "this pipeline knows who
    this entity is" claim made on half the evidence, so the renderer refuses
    every partial set -- including one where a value is an empty string, which
    a per-key truthiness test would have rendered as `gmv_id: ''`."""
    common = {
        "source_notion_page_id": GARIBALDI_PAGE, "notion_kind": "artista",
        "notion_title": "Federico Garibaldi", "body_text": "", "now": NOW,
    }
    for partial in (
        {"gmv_id": "GMV-000001"},
        {"canonical_name": "Federico Garibaldi"},
        {"entity_type": "ARTIST"},
        {"gmv_id": "GMV-000001", "entity_type": "ARTIST"},
        {"gmv_id": "", "entity_type": "", "canonical_name": ""},
        {"gmv_id": "GMV-000001", "entity_type": "ARTIST", "canonical_name": "   "},
    ):
        with pytest.raises(canon.CanonExportError) as excinfo:
            canon.render_canon_markdown(**common, **partial)
        assert "must be supplied together and non-empty" in str(excinfo.value)

    # The empty set is not "partial" -- it is the unresolved page, and it works.
    assert "gmv_id" not in canon.render_canon_markdown(**common)
    assert canon.render_canon_markdown(
        **common, gmv_id="GMV-000001", entity_type="ARTIST", canonical_name="Federico Garibaldi",
    ).startswith("---\nschema: GMV_NOTION_CANON_SNAPSHOT_V1\ngmv_id: GMV-000001\n")


def test_cli_reports_a_data_source_it_could_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Q18, the failure half. One unreadable data source does not abandon the
    other one (the continue-and-report shape `adapter_notion.main()` already
    uses), but the run must not exit 0 either -- a scheduled caller reading
    the exit code would otherwise read a silent success over a run that
    exported nothing of that data source."""
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
    assert [p.name for p in (tmp_path / "canon_out").iterdir()] == [f"{GARIBALDI_PAGE}.md"]


def test_cli_rejects_unknown_entity_keys(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Q19: a typo in `--entities` is a 2, not a silent run that read nothing."""
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
