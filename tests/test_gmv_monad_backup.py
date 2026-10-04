"""GMV Crawler — standalone backup for materialized Monads
(`gmv_monad_backup.py`).

The headline tests do not use a hand-written `.md` fixture. They call the
REAL `materialize_monad()` to produce a real Monad file, then back that
up, because "a real materialized Monad" is the thing this module copies
and a hand-written string would not prove the two halves compose. No
test reads `03_STATE/`: `00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md` classes
`tests/` as "Fixture" with "live data prohibited", so the real on-disk
Ombra is proven in the live proof, not here.

Every test that lets the module pick its own destination relies on the
autouse `isolated_gmv` fixture in `tests/conftest.py` setting `HOME` to
`tmp_path`. That is asserted directly in
`test_default_backup_dir_follows_the_home_redirect` rather than assumed,
so a future change to that fixture cannot silently redirect these tests
back at the operator's real backup directory.
"""

from __future__ import annotations

import ast
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "10_API"))
sys.path.insert(0, str(ROOT))

import gmv_monad_materializer as mm  # noqa: E402
from gmv_atom_validator import AtomCandidate  # noqa: E402

import gmv_monad_backup as mb  # noqa: E402

REGISTRY_PATH = ROOT / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_v0.1.json"


@pytest.fixture(scope="module")
def registry() -> dict:
    import json

    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


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
        "path": "dropbox:/gmv_master_system/artist_profile.md",
        "source_type": "MD",
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


def _materialize(tmp_path: Path, gmv_id: str, registry: dict) -> Path:
    """Produce a REAL Monad file with the REAL materializer, under
    `tmp_path/03_STATE/ombra/` -- the same relative layout the production
    directory has, so nothing about the backup path is special-cased."""
    target = tmp_path / "03_STATE" / "ombra" / f"{gmv_id}.md"
    document = _document(
        gmv_id=gmv_id, canonical_name=f"Entity {gmv_id}", atoms=(), public_text=""
    )
    mm.materialize_monad(document, target, registry)
    return target


# --- the two behaviours the task brief mandates ---


def test_a_real_materialized_monad_is_backed_up_byte_identically(
    tmp_path: Path, registry: dict
) -> None:
    """Real producer -> real backup. The source file is written by
    `materialize_monad()`, not written by this test, so what is asserted
    is that the two real components compose."""
    source = _materialize(tmp_path, "GMV-000001", registry)
    destination = tmp_path / "backup" / "ombra"

    written = mb.backup_materialized_monads(source.parent, destination)

    assert written == (destination / "GMV-000001.md",)
    assert written[0].exists()
    # Byte-for-byte, not string-for-string: a backup that differs by a
    # newline is not a backup.
    assert written[0].read_bytes() == source.read_bytes()
    assert written[0].read_text(encoding="utf-8") == mm.render_monad_markdown(
        _document(gmv_id="GMV-000001", canonical_name="Entity GMV-000001", atoms=(), public_text="")
    )
    assert "GMV-000001" in written[0].read_text(encoding="utf-8")


def test_an_empty_ombra_is_a_clean_no_op_not_an_error(tmp_path: Path) -> None:
    """The directory exists and holds no Monads: nothing is created and
    nothing is raised. A maintenance script run before the first Monad is
    materialized must not crash."""
    empty = tmp_path / "03_STATE" / "ombra"
    empty.mkdir(parents=True)
    destination = tmp_path / "backup" / "ombra"

    assert mb.backup_materialized_monads(empty, destination) == ()
    assert not destination.exists()


# --- the "is it really empty / really absent" cases, stated not assumed ---


def test_an_absent_source_directory_is_also_a_clean_no_op(tmp_path: Path) -> None:
    """`03_STATE/` is gitignored, so on a fresh clone the Ombra does not
    exist at all. Documented consequence of the same choice: a typo'd
    source path is a quiet no-op too, which is why the CLI prints the
    source it used."""
    destination = tmp_path / "backup" / "ombra"
    assert mb.backup_materialized_monads(tmp_path / "does_not_exist", destination) == ()
    assert not destination.exists()


def test_a_source_directory_holding_no_markdown_backs_up_nothing(tmp_path: Path) -> None:
    """Only `*.md` is copied. A stray non-Monad file in the directory is
    not presented as a backed-up Monad."""
    source = tmp_path / "ombra"
    source.mkdir()
    (source / "notes.txt").write_text("not a monad", encoding="utf-8")
    (source / ".DS_Store").write_bytes(b"\x00\x01")
    destination = tmp_path / "backup"

    assert mb.backup_materialized_monads(source, destination) == ()
    assert not destination.exists()


# --- byte fidelity: the real trap in a read/write round trip ---


def test_crlf_line_endings_survive_the_round_trip_byte_for_byte(tmp_path: Path) -> None:
    """Adversarial test for this module's one real correctness risk.

    `Path.read_text()` defaults to universal-newline mode, which rewrites
    `\\r\\n` to `\\n` on read. Writing that back out through
    `atomic_write_text()` would produce a backup with silently normalized
    line endings -- content changed, no error raised. This asserts the
    module reads with `newline=""` by feeding it the one input that
    distinguishes the two."""
    source = tmp_path / "ombra"
    source.mkdir()
    original = b"line one\r\nline two\r\nline three\r\n"
    (source / "GMV-000009.md").write_bytes(original)
    destination = tmp_path / "backup"

    written = mb.backup_materialized_monads(source, destination)

    assert len(written) == 1
    assert written[0].read_bytes() == original, "line endings were translated"
    # And the naive alternative really would have failed, so this test is
    # not passing for an unrelated reason.
    assert (source / "GMV-000009.md").read_text(encoding="utf-8").encode("utf-8") != original


def test_a_lone_carriage_return_also_survives(tmp_path: Path) -> None:
    """Universal-newline mode also rewrites a lone `\\r`. Same guarantee,
    second shape, because the first test alone would not catch a
    fix that only handled `\\r\\n`."""
    source = tmp_path / "ombra"
    source.mkdir()
    original = b"before\rafter\r"
    (source / "GMV-000010.md").write_bytes(original)

    written = mb.backup_materialized_monads(source, tmp_path / "backup")

    assert written[0].read_bytes() == original


def test_non_utf8_source_fails_loudly_instead_of_being_backed_up_corrupted(
    tmp_path: Path,
) -> None:
    """The honest precondition of a text round trip, pinned rather than
    hidden: a source that is not valid UTF-8 raises, and leaves no
    partial backup behind. Every file `materialize_monad()` writes is
    UTF-8 by construction, so this is the producer's property, not a new
    restriction imposed here."""
    source = tmp_path / "ombra"
    source.mkdir()
    (source / "GMV-000011.md").write_bytes(b"caf\xe9 not utf-8\n")
    destination = tmp_path / "backup"

    with pytest.raises(UnicodeDecodeError):
        mb.backup_materialized_monads(source, destination)
    assert not destination.exists()


# --- scope: "under" is recursive and mirrored, so nothing is skipped ---


def test_a_nested_monad_is_backed_up_not_silently_skipped(tmp_path: Path) -> None:
    """`glob("*.md")` would skip this file and still report success. The
    recursive form is chosen so that a backup can never quietly miss a
    file."""
    source = tmp_path / "ombra"
    (source / "archive").mkdir(parents=True)
    (source / "GMV-000001.md").write_text("top level\n", encoding="utf-8")
    (source / "archive" / "GMV-000002.md").write_text("nested\n", encoding="utf-8")
    destination = tmp_path / "backup"

    written = mb.backup_materialized_monads(source, destination)

    assert sorted(written) == sorted((
        destination / "GMV-000001.md",
        destination / "archive" / "GMV-000002.md",
    ))
    assert (destination / "archive" / "GMV-000002.md").read_text(encoding="utf-8") == "nested\n"


def test_same_filename_in_two_subdirectories_does_not_collide(tmp_path: Path) -> None:
    """The other silent failure of a flat destination: two files with the
    same name in different subdirectories would overwrite each other and
    the backup would still claim success. Mirroring the relative path is
    what prevents it."""
    source = tmp_path / "ombra"
    (source / "a").mkdir(parents=True)
    (source / "b").mkdir(parents=True)
    (source / "a" / "GMV-000001.md").write_text("from a\n", encoding="utf-8")
    (source / "b" / "GMV-000001.md").write_text("from b\n", encoding="utf-8")
    destination = tmp_path / "backup"

    written = mb.backup_materialized_monads(source, destination)

    assert len(written) == 2
    assert (destination / "a" / "GMV-000001.md").read_text(encoding="utf-8") == "from a\n"
    assert (destination / "b" / "GMV-000001.md").read_text(encoding="utf-8") == "from b\n"


# --- reusing secure_storage's primitive is observable, not just claimed ---


def test_backups_are_written_with_the_secure_permissions_secure_storage_enforces(
    tmp_path: Path, registry: dict
) -> None:
    """If this module ever stopped going through `atomic_write_text()`
    and used a plain write, these two assertions are what would catch it."""
    source = _materialize(tmp_path, "GMV-000001", registry)
    destination = tmp_path / "backup" / "ombra"

    mb.backup_materialized_monads(source.parent, destination)

    written = destination / "GMV-000001.md"
    assert stat.S_IMODE(written.stat().st_mode) == 0o600
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700


def test_a_world_readable_destination_file_is_refused_not_overwritten(
    tmp_path: Path, registry: dict
) -> None:
    """`secure_storage.require_private()` raises on a pre-existing
    destination file with loose permissions. Proves the reuse is real and
    that a backup cannot quietly launder an already-exposed file."""
    source = _materialize(tmp_path, "GMV-000001", registry)
    destination = tmp_path / "backup" / "ombra"
    destination.mkdir(parents=True)
    planted = destination / "GMV-000001.md"
    planted.write_text("previous content\n", encoding="utf-8")
    planted.chmod(0o644)

    with pytest.raises(PermissionError):
        mb.backup_materialized_monads(source.parent, destination)

    assert planted.read_text(encoding="utf-8") == "previous content\n"
    assert stat.S_IMODE(planted.stat().st_mode) == 0o644


# --- the module's own guarantees ---


def test_the_source_directory_is_never_modified(tmp_path: Path, registry: dict) -> None:
    """`03_STATE/` is live state. A backup that mutated it would be a
    far worse bug than one that fails."""
    source = _materialize(tmp_path, "GMV-000001", registry)
    before = {p: p.read_bytes() for p in sorted(source.parent.rglob("*")) if p.is_file()}
    before_modes = {p: stat.S_IMODE(p.stat().st_mode) for p in before}

    mb.backup_materialized_monads(source.parent, tmp_path / "backup")

    after = {p: p.read_bytes() for p in sorted(source.parent.rglob("*")) if p.is_file()}
    assert after == before
    assert {p: stat.S_IMODE(p.stat().st_mode) for p in after} == before_modes


def test_a_second_run_replaces_the_copy_with_the_newer_content(
    tmp_path: Path, registry: dict
) -> None:
    """Current-state mirror, not an archive: documented behavior, pinned
    so that "the backup is stale" can never be a surprise."""
    source = _materialize(tmp_path, "GMV-000001", registry)
    destination = tmp_path / "backup"
    mb.backup_materialized_monads(source.parent, destination)

    source.write_text("---\nrewritten\n---\n", encoding="utf-8")
    mb.backup_materialized_monads(source.parent, destination)

    assert (destination / "GMV-000001.md").read_text(encoding="utf-8") == "---\nrewritten\n---\n"
    assert (destination / "GMV-000001.md").read_bytes() == source.read_bytes()


def test_returned_paths_are_sorted_and_reported_not_guessed(tmp_path: Path, registry: dict) -> None:
    """The return value is what a caller reports to a human, so it must
    be exactly what was written, in a deterministic order."""
    for gmv_id in ("GMV-000003", "GMV-000001", "GMV-000002"):
        _materialize(tmp_path, gmv_id, registry)
    destination = tmp_path / "backup"

    written = mb.backup_materialized_monads(tmp_path / "03_STATE" / "ombra", destination)

    assert [p.name for p in written] == ["GMV-000001.md", "GMV-000002.md", "GMV-000003.md"]
    assert all(p.exists() for p in written)
    assert all(p.parent == destination for p in written)


# --- the default destination, and the isolation that makes it testable ---


def test_default_backup_dir_follows_the_home_redirect(tmp_path: Path) -> None:
    """Asserted, not assumed: `tests/conftest.py`'s autouse fixture sets
    `HOME` to `tmp_path`, which is the only reason letting this module
    pick its own destination is safe in a test suite at all."""
    assert mb.default_backup_dir() == Path.home() / ".gmv_backups" / "ombra"
    assert str(mb.default_backup_dir()).startswith(str(tmp_path))
    assert not str(mb.default_backup_dir()).startswith(str(Path.home().home))


def test_default_destination_lives_under_the_same_root_backup_service_uses() -> None:
    """Grounded in `backup_service.py::main()`'s real CLI default (line
    436), read from that file rather than restated from the brief."""
    import inspect

    import backup_service

    source = inspect.getsource(backup_service.main)
    assert 'Path.home() / ".gmv_backups"' in source
    assert mb.default_backup_dir() == Path.home() / ".gmv_backups" / "ombra"
    # ...and in its own subfolder, so it can never collide with the
    # `sets/<BKP-id>/` structure that module owns.
    assert mb.default_backup_dir().name == "ombra"
    assert mb.default_backup_dir().parent.name == ".gmv_backups"


def test_default_destination_is_never_inside_the_sets_structure(tmp_path: Path) -> None:
    destination = mb.default_backup_dir()
    assert "sets" not in destination.parts
    assert destination != Path.home() / ".gmv_backups"


# --- scope: this module owns nothing else ---


def _module_ast() -> ast.Module:
    return ast.parse((ROOT / "10_API" / "gmv_monad_backup.py").read_text(encoding="utf-8"))


def _imported_modules(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _called_names(tree: ast.Module) -> set[str]:
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
    return called


def _code_string_literals(tree: ast.Module) -> set[str]:
    """Every string constant EXCEPT the module docstring. The docstring
    legitimately names the things this module refuses to touch; only the
    executable code is in scope for these assertions. Checking the raw
    source text instead would flag its own explanation."""
    docstring = tree.body[0].value if isinstance(tree.body[0], ast.Expr) else None
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node is not docstring
    }


def test_no_sqlite_import_and_no_database_path_in_code() -> None:
    """`backup_service.py` owns the database concern and is not modified;
    this module must not grow a second path to `09_DATABASE/GMV.db`.
    Checked over the AST, following the same approach
    `tests/test_write_authorization.py` uses for its own static DML/DDL
    scan, rather than by grepping text that also contains this module's
    docstring explaining the exclusion."""
    tree = _module_ast()
    assert "sqlite3" not in _imported_modules(tree)
    assert "09_DATABASE" not in _code_string_literals(tree)
    assert not {"connect", "execute", "executemany", "executescript"} & _called_names(tree)


def test_the_copy_goes_through_secure_storage_not_a_second_write_mechanism() -> None:
    """The task's constraint 3: reuse `secure_storage.atomic_write_text`,
    don't invent a second write path. This is the assertion that would
    fail first if someone 'simplified' it into `shutil.copy` or a bare
    `write_text`."""
    tree = _module_ast()
    assert "secure_storage" in _imported_modules(tree)
    assert "shutil" not in _imported_modules(tree)
    assert "atomic_write_text" in _called_names(tree)
    assert not {"copy", "copyfile", "copy2", "copytree"} & _called_names(tree)


def test_module_does_not_call_the_materializer_or_the_other_backup_module() -> None:
    """It copies files that already exist. Calling the producer from the
    backup would mean a backup run silently materializing new Monads, and
    calling `create_backup()` would drag in the SQL database path this
    module is scoped away from."""
    assert not {"materialize_monad", "create_backup", "verify_backup"} & _called_names(
        _module_ast()
    )


def test_cli_entry_point_runs_and_reports(tmp_path: Path, registry: dict, capsys) -> None:
    """The brief's step 3: a plain `__main__` block in this file, no
    `11_CLI/gmv` subcommand. Exercised through `main()` because that is
    what `__main__` calls."""
    source = _materialize(tmp_path, "GMV-000001", registry)
    destination = tmp_path / "backup"

    assert mb.main(["--source", str(source.parent), "--destination", str(destination)]) == 0

    out = capsys.readouterr().out
    assert str(source.parent) in out
    assert str(destination) in out
    assert "backed up   : 1" in out
    assert "GMV-000001.md" in out
    assert (destination / "GMV-000001.md").read_bytes() == source.read_bytes()


def test_cli_reports_zero_for_an_empty_directory(tmp_path: Path, capsys) -> None:
    empty = tmp_path / "ombra"
    empty.mkdir()

    assert mb.main(["--source", str(empty), "--destination", str(tmp_path / "backup")]) == 0

    out = capsys.readouterr().out
    assert "backed up   : 0" in out