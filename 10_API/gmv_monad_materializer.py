#!/usr/bin/env python3
"""GMV Crawler — Monad materializer v1.0 (crawler preplan step 8).

Renders a validated set of ATOM candidates plus their SOURCES manifest into
the canonical `.md` file GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §2/§19 freezes, and
writes it atomically. This is the first crawler artifact that owns a real
write path (steps 1-7 were schema/contract only) -- kept deliberately
narrow: a pure render function plus a thin, reused atomic-write wrapper,
not a pipeline or orchestration loop.

Grounding, read in full before writing this module:

- GMV_KNOWLEDGE_MONAD_SPEC_v1.0 (Notion id 3b95a429-a028-8116-a236-
  d8867862d077, fetched fresh this session, FORMAL FREEZE 11 August 2026).
  §2 fixes the four top-level sections (YAML/IDENTITY, PUBLIC, ATOMS,
  SOURCES); §19 gives the one concrete worked skeleton; §20 states exactly
  what is frozen (top-level structure, 18-field ATOM schema, predicate
  classes, canonical/derived separation, provenance requirement, lifecycle/
  tombstoning rule, temporal-semantics rule, entity-granularity principle,
  Constitution requirement) and, by omission, what is NOT frozen.

- §2.4 vs §19 disagree on the SOURCES manifest's exact column set: §2.4's
  prose lists SOURCE_ID/PATH/FILENAME/TYPE/SIZE/MODIFIED/HASH/
  EPISTEMIC_LEVEL/EXTRACTION_STATUS/"DUPLICATE / DERIVATION STATUS"/NOTES
  (11 items), but §19's actual worked table header has only 9 columns --
  no FILENAME, no DUPLICATE/DERIVATION STATUS. §2.4's own last sentence
  resolves this in favor of flexibility ("il dettaglio esatto del
  source-manifest puo' evolvere senza modificare l'ATOM schema, purche' la
  provenance rimanga deterministica e auditabile"), and §20's freeze list
  does not include the source-manifest's exact fields. This module follows
  §19's worked table literally (SOURCE_ID/PATH/TYPE/SIZE/MODIFIED/HASH/
  EPISTEMIC_LEVEL/EXTRACTION_STATUS/NOTES) since it is the one concrete
  rendering the frozen spec actually shows, not a silent pick between two
  equally-frozen options -- FILENAME/DUPLICATE-DERIVATION-STATUS can be
  added later (a source-manifest evolution, explicitly allowed) without
  touching the ATOM schema this file also renders.

- GMV Crawler spec v0.2 §33 step 15 ("PUBLIC projector") is a separate,
  not-yet-built step: generating PUBLIC text from ATOMS per the exclusion
  rules in GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §14 (no INTERNAL facts, no
  unattributed UNVERIFIED claims, etc.) is that step's job, not this one's.
  materialize_monad() takes `public_text` as a caller-supplied string and
  writes it verbatim -- it does not compute or validate PUBLIC content
  against §14. Building that logic here would be exactly the "premature
  engine" this session's working method warns against.

- Canonical on-disk directory for materialized Monad files (the "Ombra"):
  `03_STATE/ombra/`, a user decision recorded in this session and folded
  into 00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md. `03_STATE/` is already
  classified there as "Live state" (canonical, mutable, full-system
  backup, never Git) -- `ombra/` is a subdirectory of that existing
  classification, not a new top-level path, so it needed no new governance
  entry, only this note. materialize_monad() still takes an explicit
  `target_path` from its caller rather than hardcoding a location -- that
  is deliberate (narrower than deciding a directory layout, consistent
  with steps 1-7's own discipline of schema/contract before engine), not
  something this decision changes. A real caller writing an actual Monad
  should pass a `target_path` under `03_STATE/ombra/`; tests use this same
  relative shape under `tmp_path` for isolation (see
  tests/test_gmv_monad_materializer.py).

- Atomic writing reuses 10_API/secure_storage.py::atomic_write_text
  (0700 directory / 0600 file, tempfile + os.replace), not a new
  mechanism -- GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §2 requires materialization
  to be "deterministica, idempotente, atomica", and this repository
  already has exactly one atomic-write primitive for protected artifacts.
  Correzione 7 of the crawler spec names materialized Monads explicitly as
  within secure_storage.py's/backup_service.py's perimeter, not a reason
  to invent a second write path.

- Determinism is made robust to caller ordering, not just to caller
  discipline: render_monad_markdown() sorts atoms by atom_id and sources
  by source_id before rendering, so the same epistemic state (same set of
  atoms/sources) always renders identically regardless of the order the
  caller happened to collect them in -- a stronger reading of "stesso
  stato epistemico in ingresso -> stesso file logico in uscita" (§2) than
  "do not reorder what the caller passed".

- Validation gate before writing, not after: materialize_monad() refuses
  to write if any atom fails gmv_atom_validator.validate_atom() with
  BLOCKER severity (reusing that validator, step 7, rather than
  re-implementing ATOM-level checks), or if any atom's SOURCE does not
  resolve to a row in this same document's SOURCES manifest (the
  provenance chain ATOM -> SOURCE_ID -> canonical locator, §13, must
  actually close, not just have a non-empty SOURCE string), if
  canonical_name/status are empty (they feed the YAML frontmatter with no
  other gate), or if gmv_id/entity_type do not match the governance
  already built in steps 2 and 6
  (GMV_ONTOLOGY_REGISTRY_v0.1.json's CORE/DOMAIN entity classes; the
  entities.gmv_id CHECK format from migration 010). MAJOR-severity atom
  issues (e.g. predicate_class/object_type internal-consistency mismatches)
  do NOT block materialization here, matching the BLOCKER-stops-export /
  MAJOR-is-a-flagged-defect severity convention already established
  throughout area35_validator.py (S01/R01/T01/T03 = BLOCKER, everything
  else lower) -- not a new severity policy invented for this module.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from area35_validator import Issue  # noqa: E402 -- reused, not reimplemented

from gmv_atom_validator import (  # noqa: E402 -- reused, not reimplemented
    AtomCandidate,
    _load_ontology_registry,
    validate_atom,
)
from secure_storage import atomic_write_text  # noqa: E402 -- reused, not reimplemented

MONAD_SCHEMA_ID = "GMV_KNOWLEDGE_MONAD_V1"

# Column order matches AtomCandidate's own frozen field order (which in
# turn matches GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §2.3/§19 verbatim) -- see
# _atom_row(), which reads the dataclass fields in this same order.
ATOM_COLUMNS = (
    "ATOM_ID", "SUBJECT", "PREDICATE", "PREDICATE_CLASS", "OBJECT", "OBJECT_TYPE",
    "SOURCE", "STATUS", "VALID_FROM", "VALID_TO", "ASSERTED_AT", "INGESTED_AT",
    "ASSERTED_BY", "CONFIDENCE", "VISIBILITY", "END_REASON", "SUPERSEDES", "SUPERSEDED_BY",
)

# §19's worked SOURCES table header, literally -- see module docstring for
# why this, not §2.4's longer prose list, is what this module renders.
SOURCE_COLUMNS = (
    "SOURCE_ID", "PATH", "TYPE", "SIZE", "MODIFIED", "HASH",
    "EPISTEMIC_LEVEL", "EXTRACTION_STATUS", "NOTES",
)


class MonadMaterializationError(ValueError):
    """Raised with the full list of blocking Issues when a MonadDocument
    fails its pre-write gate. Never raised for MAJOR/MINOR/INFO-only
    findings -- those are defects to flag, not reasons to refuse a
    write, per the BLOCKER-stops-export convention this module reuses
    from area35_validator.py (see module docstring)."""

    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        summary = "; ".join(f"{i.codice}({i.campo}): {i.messaggio}" for i in issues)
        super().__init__(f"{len(issues)} blocking issue(s) refuse materialization: {summary}")


@dataclass(frozen=True, slots=True)
class SourceManifestEntry:
    """One row of the Monad's SOURCES section (GMV_KNOWLEDGE_MONAD_SPEC_v1.0
    §2.4/§19). `source_type`/`hash_value` are named to avoid shadowing the
    `type`/`hash` builtins; they render under the TYPE/HASH column headers
    (see SOURCE_COLUMNS, _source_row) -- the dataclass field name is not
    required to match the rendered column name."""

    source_id: str
    path: str
    source_type: str
    size: int
    modified: str
    hash_value: str
    epistemic_level: str
    extraction_status: str
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("source_id must not be empty")
        if not self.path:
            raise ValueError(
                "path must not be empty -- a SOURCES row with no canonical locator "
                "violates the crawler's foundational invariant (no SOURCE without "
                "canonical locator)"
            )
        if self.size < 0:
            raise ValueError(f"size must be >= 0, got {self.size}")


@dataclass(frozen=True, slots=True)
class MonadDocument:
    """Everything one materialize_monad() call needs: the frozen
    YAML/IDENTITY fields (§2.1), an already-computed PUBLIC string (§2.2,
    computed by a future step, not this one), the ATOM candidates (§2.3)
    and the SOURCES manifest (§2.4) for one entity's Monad."""

    gmv_id: str
    entity_type: str
    canonical_name: str
    status: str
    public_text: str
    atoms: tuple[AtomCandidate, ...]
    sources: tuple[SourceManifestEntry, ...]


def _doc_issue(document: MonadDocument, codice: str, severita: str, campo: str,
                messaggio: str, azione: str = "") -> Issue:
    return Issue(codice, severita, "monad", document.gmv_id, document.canonical_name,
                 campo, messaggio, azione)


def _atom_issue(atom: AtomCandidate, codice: str, severita: str, campo: str,
                 messaggio: str, azione: str = "") -> Issue:
    return Issue(codice, severita, "monad_atom", atom.atom_id,
                 f"{atom.subject} {atom.predicate} {atom.object}", campo, messaggio, azione)


def gmv_id_is_well_formed(document: MonadDocument) -> list[Issue]:
    """Same shape rule as entities.gmv_id's own CHECK in migration 010
    (GLOB 'GMV-*' AND length > length('GMV-')) -- re-expressed in Python,
    not redefined: tests/test_gmv_monad_materializer.py executes the real
    SQL CHECK against a battery of values and compares to this function,
    the same cross-check discipline steps 4/6 used for content_hash/
    entity_type."""
    value = document.gmv_id
    if not (value.startswith("GMV-") and len(value) > len("GMV-")):
        return [_doc_issue(
            document, "M-SCHEMA01", "BLOCKER", "gmv_id",
            f"gmv_id {value!r} non rispetta il formato 'GMV-<non vuoto>' richiesto da "
            "entities.gmv_id (gmv_core/migration_sql/010_entity_registry.sql).",
        )]
    return []


def entity_type_is_governed(document: MonadDocument, registry: dict) -> list[Issue]:
    """entity_type must be a CORE/DOMAIN class in GMV_ONTOLOGY_REGISTRY_v0.1.json
    -- the same governed set entities.entity_type's CHECK in migration 010
    already encodes (ARTWORK excluded as DEPRECATED, SPONSOR/CONTRACT
    excluded as CANDIDATE). Loaded from the registry, not hardcoded here a
    third time, per this session's own discipline (cross-check against the
    committed artifact, not a duplicated list)."""
    governed = frozenset(
        entry["class_id"] for entry in registry["entity_classes"]
        if entry["status"] in ("CORE", "DOMAIN")
    )
    if document.entity_type not in governed:
        return [_doc_issue(
            document, "M-SCHEMA02", "BLOCKER", "entity_type",
            f"entity_type {document.entity_type!r} non e' una classe CORE/DOMAIN in "
            "GMV_ONTOLOGY_REGISTRY_v0.1.json (o e' esclusa da entities.entity_type in "
            "migration 010, es. ARTWORK/SPONSOR/CONTRACT).",
        )]
    return []


def required_document_fields_not_empty(document: MonadDocument) -> list[Issue]:
    """Direct analog of gmv_atom_validator.required_fields_not_empty, at
    the document level: canonical_name and status feed straight into the
    YAML frontmatter (§2.1) with no gate anywhere else in this module --
    gmv_id's own emptiness is already caught by gmv_id_is_well_formed
    (a bare 'GMV-' prefix fails its length check), so it is not repeated
    here to avoid double-reporting the same field. Without this check, a
    MonadDocument with canonical_name="" or status="" would materialize
    to disk with zero issues -- the exact class of gap review found
    missing from gmv_atom_validator.py in step 7 (see that module's own
    docstring); caught here by this session's own adversarial re-read of
    this file, not by an external reviewer, so fixed before commit rather
    than left for a future one to find."""
    issues: list[Issue] = []
    for field_name, value in (
        ("canonical_name", document.canonical_name), ("status", document.status),
    ):
        if not (value or "").strip():
            issues.append(_doc_issue(
                document, "M-SCHEMA05", "BLOCKER", field_name,
                f"Campo obbligatorio '{field_name}' vuoto.",
            ))
    return issues


def no_duplicate_atom_ids(document: MonadDocument) -> list[Issue]:
    seen: set[str] = set()
    issues: list[Issue] = []
    for atom in document.atoms:
        if atom.atom_id in seen:
            issues.append(_atom_issue(
                atom, "M-SCHEMA03", "BLOCKER", "atom_id",
                f"ATOM_ID {atom.atom_id!r} compare piu' volte in questa Monade: tabella ATOMS ambigua.",
            ))
        seen.add(atom.atom_id)
    return issues


def no_duplicate_source_ids(document: MonadDocument) -> list[Issue]:
    seen: set[str] = set()
    issues: list[Issue] = []
    for source in document.sources:
        if source.source_id in seen:
            issues.append(_doc_issue(
                document, "M-SCHEMA04", "BLOCKER", "source_id",
                f"SOURCE_ID {source.source_id!r} compare piu' volte in questa Monade: tabella SOURCES ambigua.",
            ))
        seen.add(source.source_id)
    return issues


def atom_sources_are_resolvable(document: MonadDocument) -> list[Issue]:
    """Closes the provenance chain ATOM -> SOURCE_ID -> canonical locator
    (§13) structurally: a non-empty SOURCE string on an atom that does not
    match any row in this same document's SOURCES manifest is exactly the
    unresolvable-provenance case the frozen spec's non-negotiable
    invariant ('no ATOM without SOURCE') is meant to catch -- a SOURCE
    string existing without a corresponding manifest entry is not
    auditable."""
    known_source_ids = {source.source_id for source in document.sources}
    issues: list[Issue] = []
    for atom in document.atoms:
        if atom.source and atom.source not in known_source_ids:
            issues.append(_atom_issue(
                atom, "M-PROV01", "BLOCKER", "source",
                f"ATOM {atom.atom_id} referenzia SOURCE={atom.source!r}, assente dal "
                "manifest SOURCES di questa Monade: provenance non risolvibile.",
            ))
    return issues


def atoms_have_no_blocking_issues(document: MonadDocument, registry: dict) -> list[Issue]:
    """Reuses gmv_atom_validator.validate_atom() (step 7) in full rather
    than re-checking ATOM-level rules here -- only BLOCKER-severity
    results gate materialization, matching area35_validator.py's own
    BLOCKER-stops-export convention (see module docstring)."""
    issues: list[Issue] = []
    for atom in document.atoms:
        issues += [issue for issue in validate_atom(atom, registry) if issue.severita == "BLOCKER"]
    return issues


DOCUMENT_RULES = (
    gmv_id_is_well_formed,
    required_document_fields_not_empty,
    no_duplicate_atom_ids,
    no_duplicate_source_ids,
    atom_sources_are_resolvable,
)
ONTOLOGY_DOCUMENT_RULES = (entity_type_is_governed,)


def find_materialization_blockers(document: MonadDocument, registry: dict | None = None) -> list[Issue]:
    """Runs every gate this module enforces and returns only BLOCKER
    issues -- the exact set materialize_monad() refuses to write past.
    Exposed separately so a caller (e.g. a future reconciliation/audit
    step) can inspect blockers without attempting a write."""
    if registry is None:
        registry = _load_ontology_registry()
    issues: list[Issue] = []
    for rule in DOCUMENT_RULES:
        issues += rule(document)
    for rule in ONTOLOGY_DOCUMENT_RULES:
        issues += rule(document, registry)
    issues += atoms_have_no_blocking_issues(document, registry)
    issues.sort(key=lambda i: i.codice)
    return issues


def _cell(value: object) -> str:
    """Markdown-table-safe rendering of one cell. Backslash is escaped
    before pipe (not after) so a literal backslash immediately preceding
    a pipe cannot be misread as escaping it once rendered. Newlines are
    collapsed to spaces -- a Markdown table row must stay on one line."""
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _row(cells: tuple[object, ...]) -> str:
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def _atom_row(atom: AtomCandidate) -> str:
    return _row((
        atom.atom_id, atom.subject, atom.predicate, atom.predicate_class, atom.object,
        atom.object_type, atom.source, atom.status, atom.valid_from, atom.valid_to,
        atom.asserted_at, atom.ingested_at, atom.asserted_by, atom.confidence,
        atom.visibility, atom.end_reason, atom.supersedes, atom.superseded_by,
    ))


def _source_row(source: SourceManifestEntry) -> str:
    return _row((
        source.source_id, source.path, source.source_type, source.size, source.modified,
        source.hash_value, source.epistemic_level, source.extraction_status, source.notes,
    ))


def _table(columns: tuple[str, ...], rows: list[str]) -> list[str]:
    header = _row(columns)
    separator = "|" + "|".join(["---"] * len(columns)) + "|"
    return [header, separator, *rows]


def render_monad_markdown(document: MonadDocument) -> str:
    """Pure function: MonadDocument -> the exact canonical text
    GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §19 skeletons (YAML frontmatter, then
    # PUBLIC / # ATOMS / # SOURCES). Deterministic regardless of the
    order document.atoms/document.sources were collected in -- both are
    sorted by their id before rendering (see module docstring)."""
    frontmatter = {
        "schema": MONAD_SCHEMA_ID,
        "gmv_id": document.gmv_id,
        "entity_type": document.entity_type,
        "canonical_name": document.canonical_name,
        "status": document.status,
    }
    yaml_block = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).rstrip("\n")

    atoms_sorted = sorted(document.atoms, key=lambda a: a.atom_id)
    sources_sorted = sorted(document.sources, key=lambda s: s.source_id)

    lines = [
        "---",
        yaml_block,
        "---",
        "",
        "# PUBLIC",
        document.public_text,
        "",
        "# ATOMS",
        *_table(ATOM_COLUMNS, [_atom_row(a) for a in atoms_sorted]),
        "",
        "# SOURCES",
        *_table(SOURCE_COLUMNS, [_source_row(s) for s in sources_sorted]),
        "",
    ]
    return "\n".join(lines)


def materialize_monad(document: MonadDocument, target_path: Path,
                       registry: dict | None = None) -> Path:
    """Validates document (raises MonadMaterializationError on any
    BLOCKER-severity finding), renders it, and writes it atomically to
    target_path via secure_storage.atomic_write_text. Returns target_path
    on success. Does not decide target_path itself -- the canonical
    directory (03_STATE/ombra/) is decided (see module docstring), but a
    caller still supplies the concrete target_path explicitly rather than
    this function hardcoding it, by the same deliberate design as before
    the decision."""
    if registry is None:
        registry = _load_ontology_registry()
    blockers = find_materialization_blockers(document, registry)
    if blockers:
        raise MonadMaterializationError(blockers)
    atomic_write_text(target_path, render_monad_markdown(document))
    return target_path
