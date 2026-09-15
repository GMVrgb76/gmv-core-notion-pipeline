#!/usr/bin/env python3
"""GMV Crawler — Atom validator (crawler preplan step 7 / Correzione 3).

Validates ATOM candidates the crawler produces before Monad
materialization, against the frozen 18-field ATOM schema
(GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §2.3), the Epistemic Ingestion Rules
(00_CONFIG/EPISTEMIC_INGESTION_RULES_v0.2.json, committed on this
branch), and the Ontology Registry (00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json,
also committed on this branch).

Grounding, verified by reading area35_validator.py in full before writing
this file (not assumed from the crawler spec's Correction 3 prose alone):

- Correction 3 says the Atom validator "extends area35_validator.py,
  does not replace it." Read literally and checked against the real
  code, that does not mean editing r_monade() or any function in
  REGOLE: area35_validator.py's Record dataclass (entita/titolo/campi/
  relazioni/servizio/corpo) is shaped for already-exported Notion pages,
  read from config.json's Notion-schema description. It has no fields
  for STATUS/CONFIDENCE/VALID_FROM/SUPERSEDES or any of the frozen ATOM
  schema's 18 fields -- there is no structural way to run an ATOM
  candidate through r_monade() without inventing a fake Record, which
  would misrepresent what a Record is. The two validate different
  things at different pipeline moments: r_monade() checks a Notion row
  *before* a Monad is generated from it; this module checks an ATOM
  candidate the crawler itself builds, upstream of any Notion
  representation. "Extends" is honored at the family-taxonomy and
  utility level instead, not by literal code insertion into r_monade():
  the Issue/SEV vocabulary is imported and reused unchanged (not
  reinvented), and text normalization for atom_fingerprint reuses
  area35_validator._forma() by import (not just norm() -- see
  compute_atom_fingerprint's own docstring for why), per Correction 3's
  explicit instruction ("la logica di deduplication/normalization gia
  presente va riusata per atom_fingerprint, invece di reimplementarla").

- Severity mapping: EPISTEMIC_INGESTION_RULES_v0.2.json uses BLOCKING/
  DEFECT (WEAKNESS is declared as a valid value in that file but never
  actually used by any of the 19 rules -- verified by inspection).
  area35_validator.py uses BLOCKER/MAJOR/MINOR/INFO. These are two real,
  already-committed vocabularies on this branch, not one -- reusing
  area35_validator's Issue class means an explicit translation is
  required, not a silent assumption that the words line up. Mapping
  used here: BLOCKING -> BLOCKER (an INGESTION_DISCIPLINE_FAILURE must
  stop export, same severity area35_validator gives to blocking
  structural/provenance failures). DEFECT -> MAJOR is the declared
  mapping for rules 13-15, but is not currently exercised by any code in
  this module: every DEFECT-severity rule (13, 14, 15) is in
  UNENFORCED_RULE_IDS below, not mechanically checked. The one MAJOR
  this module does emit (predicate_class mismatch, codice A-SCHEMA03) is
  NOT derived from that mapping -- it is an independent internal-
  consistency check (does the atom's own declared predicate_class match
  what the registry says for that predicate), chosen as MAJOR on its own
  merits, not because it enforces a DEFECT-severity EIC rule. It is
  reported separately from A-EIC07 (registration gate, BLOCKER, EIC-07's
  real severity in the JSON is BLOCKING) precisely to avoid implying a
  severity-mapping connection that does not exist.

- Not all 19 Epistemic Ingestion Rules are mechanically checkable from
  an already-built ATOM candidate's 18 fields in isolation. This module
  enforces only the subset that is: rules about *how a value was
  derived* (EIC-01, temporal-inference rules EIC-05/06/11, EIC-17) are
  executor-discipline at generation time, not something a post-hoc
  structural check on the finished ATOM can detect (a wrongly-promoted
  VALID_TO looks identical, in the finished data, to a correctly-sourced
  one). EIC-14 (do not maximize atom count) and EIC-19 (atomicity) are
  corpus-level judgments about *how many* atoms were extracted from a
  passage, not properties of one atom in isolation -- out of scope for a
  per-atom validator. What IS enforced: EIC-09 (every VALID atom needs
  explicit SOURCE), EIC-16 (tombstoning: INVALIDATED requires
  END_REASON), required_fields_not_empty (subject/object/atom_id must be
  non-empty -- the direct analog of area35_validator's own S01 "campo
  obbligatorio assente" check, which an earlier version of this module
  omitted despite claiming to reuse area35_validator's checks; caught by
  review), and ontology governance: PREDICATE must be registered in
  GMV_ONTOLOGY_REGISTRY_v0.1.json (predicate_is_governed), and
  OBJECT_TYPE must fall within that predicate's declared `range` in the
  same registry when the range is not "ANY" (object_type_matches_
  predicate_range) -- an earlier version of this module's docstring
  claimed this OBJECT_TYPE check existed without any code implementing
  it; caught by review, now actually implemented, not just described.
  Each unenforced rule is listed explicitly in UNENFORCED_RULE_IDS
  below, not silently dropped.

- PREDICATE_CLASS is constrained to the six frozen values from
  GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §3 (IDENTITY/ATTRIBUTE/RELATION/EVENT/
  MEASURE/EPISTEMIC) -- confirmed frozen, not open to extension without
  a documented schema failure per that spec's own change-control rules
  (§18).

- SUPERSEDED_BY is deliberately NOT required when STATUS=SUPERSEDED:
  GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §9 says it "identifica il successore
  solo quando direttamente risolvibile" -- absence is a legitimate,
  spec-sanctioned state, not a defect. Requiring it here would
  contradict the frozen spec this validator is supposed to enforce.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from area35_validator import SEV, Issue, _forma  # noqa: E402 -- reused, not reimplemented

ONTOLOGY_REGISTRY_PATH = (
    Path(__file__).resolve().parents[1] / "00_CONFIG" / "GMV_ONTOLOGY_REGISTRY_v0.1.json"
)

FROZEN_PREDICATE_CLASSES = frozenset(
    {"IDENTITY", "ATTRIBUTE", "RELATION", "EVENT", "MEASURE", "EPISTEMIC"}
)

# EIC rule_ids this module does NOT mechanically enforce, and why -- see
# module docstring. Not a silent gap: a dedicated test pins this exact
# set so a future edit that changes coverage must update this list
# deliberately, not by accident.
UNENFORCED_RULE_IDS = frozenset(
    {
        "EIC-01",  # requires knowing source wording strength, not just the finished atom
        "EIC-02",  # absence-of-evidence discipline is an extraction-time judgment
        "EIC-03",  # document-assertion-vs-fact is a modeling judgment at extraction time
        "EIC-04",  # same class as EIC-03
        "EIC-05",  # requires the source's stated event state, not present on ATOM alone
        "EIC-06",  # same class as EIC-05 (occurrence-semantic promotion)
        # EIC-07 is NOT listed here: predicate_is_governed() below enforces
        # its "must be registered before use" half mechanically (codice
        # A-EIC07). The other half -- "reused predicate must be
        # semantically equivalent, not just adjacent" -- is a judgment
        # this validator cannot make; only the registration-gate half is
        # enforced.
        "EIC-08",  # entity typing discipline at candidate-extraction time
        "EIC-10",  # derived-master provenance judgment, not a single-atom property
        "EIC-11",  # VALID_TO=unknown-is-not-current is an inference-time discipline
        "EIC-12",  # "choose the less assertive interpretation" is a judgment call
        "EIC-13",  # schema-change discipline is a process rule (do not add ATOM fields), not a per-atom property
        "EIC-14",  # corpus-level (atom count), not per-atom
        "EIC-15",  # "if uncertain, do not infer" is an extraction-time judgment
        "EIC-17",  # object-time vs proposition-time separation is a modeling judgment
        "EIC-18",  # WORK vs ARTWORK_INSTANCE is an entity-modeling judgment, enforced by GMV_ONTOLOGY_REGISTRY_v0.1.json's class governance, not here
        "EIC-19",  # corpus-level (atomicity), not per-atom
    }
)


def _load_ontology_registry() -> dict:
    import json

    return json.loads(ONTOLOGY_REGISTRY_PATH.read_text(encoding="utf-8"))


def _known_predicates(registry: dict) -> dict[str, dict]:
    """Maps every registered predicate_id AND every alias to its entry,
    so an alias resolves to the same governance as its canonical id --
    the same reuse-before-invention discipline GMV_ONTOLOGY_REGISTRY_v0.1.json
    itself documents for 'evidences' -> 'source_for'."""
    known: dict[str, dict] = {}
    for entry in registry["predicates"]:
        known[entry["predicate_id"]] = entry
        for alias in entry.get("aliases", []):
            known[alias] = entry
    return known


@dataclass(frozen=True, slots=True)
class AtomCandidate:
    """The frozen 18-field ATOM schema (GMV_KNOWLEDGE_MONAD_SPEC_v1.0
    §2.3), unchanged -- no field added, removed, or renamed. This is a
    validation-time representation only; it does not decide how atoms
    are persisted (that is Monad materialization, a later, still-unbuilt
    step)."""

    atom_id: str
    subject: str
    predicate: str
    predicate_class: str
    object: str
    object_type: str
    source: str
    status: str
    valid_from: str | None
    valid_to: str | None
    asserted_at: str
    ingested_at: str
    asserted_by: str
    confidence: float
    visibility: str
    end_reason: str | None = None
    supersedes: str | None = None
    superseded_by: str | None = None


def _iss(atom: AtomCandidate, codice: str, severita: str, campo: str, messaggio: str,
         azione: str = "") -> Issue:
    """Maps ATOM fields onto area35_validator.Issue's Record-shaped
    fields (entita/record_id/titolo), reusing the class rather than
    defining a parallel one."""
    return Issue(
        codice, severita, "atom", atom.atom_id,
        f"{atom.subject} {atom.predicate} {atom.object}", campo, messaggio, azione,
    )


def eic09_valid_requires_source(atom: AtomCandidate) -> list[Issue]:
    """Direct analog of area35_validator's own r_monade M02 ('fonte non
    valorizzata'), applied to ATOM candidates instead of Notion rows."""
    if atom.status == "VALID" and not (atom.source or "").strip():
        return [_iss(
            atom, "A-EIC09", "BLOCKER", "source",
            "STATUS=VALID senza SOURCE: nessuna evidenza esplicita a supporto (EIC-09).",
            "Abbassare lo STATUS o fornire SOURCE.",
        )]
    return []


def eic16_invalidated_requires_end_reason(atom: AtomCandidate) -> list[Issue]:
    if atom.status == "INVALIDATED" and not (atom.end_reason or "").strip():
        return [_iss(
            atom, "A-EIC16", "BLOCKER", "end_reason",
            "STATUS=INVALIDATED senza END_REASON: tombstoning richiede la causa (EIC-16).",
            "Impostare END_REASON (es. CORRECTED).",
        )]
    return []


def predicate_class_is_frozen(atom: AtomCandidate) -> list[Issue]:
    if atom.predicate_class not in FROZEN_PREDICATE_CLASSES:
        return [_iss(
            atom, "A-SCHEMA01", "BLOCKER", "predicate_class",
            f"PREDICATE_CLASS '{atom.predicate_class}' non e' una delle sei classi congelate "
            f"(GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §3).",
        )]
    return []


def predicate_is_governed(atom: AtomCandidate, registry: dict) -> list[Issue]:
    """Reuse-before-invention made structural: an unregistered predicate
    is not silently accepted into an atom. It must first exist in
    GMV_ONTOLOGY_REGISTRY_v0.1.json, as CORE/DOMAIN or at minimum
    CANDIDATE -- never invented ad hoc at atom-build time. This is the
    "must be registered" half of EIC-07 only; it cannot judge the other
    half (whether a reused predicate is truly semantically equivalent to
    what it is replacing, not merely adjacent to it) -- that remains a
    human/LLM judgment call this module does not attempt."""
    known = _known_predicates(registry)
    entry = known.get(atom.predicate)
    if entry is None:
        return [_iss(
            atom, "A-EIC07", "BLOCKER", "predicate",
            f"Predicato '{atom.predicate}' non registrato in GMV_ONTOLOGY_REGISTRY_v0.1.json: "
            "reuse-before-invention violato.",
            "Registrare come CANDIDATE nel registry prima di usarlo, o riusare un predicato esistente equivalente.",
        )]
    if entry["predicate_class"] != atom.predicate_class:
        return [_iss(
            atom, "A-SCHEMA03", "MAJOR", "predicate_class",
            f"Predicato '{atom.predicate}' registrato come {entry['predicate_class']}, "
            f"ma l'atomo dichiara predicate_class={atom.predicate_class!r}: incoerenza interna, "
            "non un'applicazione di EIC-07.",
        )]
    return []


def object_type_matches_predicate_range(atom: AtomCandidate, registry: dict) -> list[Issue]:
    """Checks OBJECT_TYPE against the predicate's own declared `range` in
    GMV_ONTOLOGY_REGISTRY_v0.1.json, rather than a blanket check against
    every known entity_class: `range` already encodes, per predicate,
    which classes (or the literal 'integer' for ATTRIBUTE predicates
    like edition_size) are valid objects -- more precise than a generic
    membership check, and avoids false positives on ATTRIBUTE predicates
    whose objects are literals, not entities. Skipped when the predicate
    is unregistered (predicate_is_governed already reports that) or when
    its range is declared 'ANY' (e.g. related_to, source_for -- those
    predicates are deliberately unconstrained, see
    GMV_ONTOLOGY_REGISTRY_v0.1.json's own notes on those entries).
    Codice is A-SCHEMA05, following the same A-SCHEMA01-04 convention as
    the other internal-consistency checks in this module, not A-EICnn:
    range mismatch is not what EIC-07 is actually about (predicate
    semantic equivalence), the same mis-attribution review had just
    caught for the predicate_class mismatch check (A-SCHEMA03) -- fixed
    here from the start instead of repeating it."""
    known = _known_predicates(registry)
    entry = known.get(atom.predicate)
    if entry is None:
        return []  # already reported by predicate_is_governed
    allowed = entry.get("range", [])
    if "ANY" in allowed:
        return []
    if atom.object_type not in allowed:
        return [_iss(
            atom, "A-SCHEMA05", "MAJOR", "object_type",
            f"OBJECT_TYPE '{atom.object_type}' non e' nel range dichiarato per il predicato "
            f"'{atom.predicate}' in GMV_ONTOLOGY_REGISTRY_v0.1.json: {allowed}.",
        )]
    return []


def required_fields_not_empty(atom: AtomCandidate) -> list[Issue]:
    """Direct analog of area35_validator's own r_struttura S01 ('campo
    obbligatorio assente'). An earlier version of this module claimed to
    reuse area35_validator's checks but omitted this one -- caught by
    review: an atom with empty subject/object/atom_id passed every other
    rule with zero issues."""
    issues: list[Issue] = []
    for field_name, value in (
        ("atom_id", atom.atom_id), ("subject", atom.subject), ("object", atom.object),
    ):
        if not (value or "").strip():
            issues.append(_iss(
                atom, "A-SCHEMA04", "BLOCKER", field_name,
                f"Campo obbligatorio '{field_name}' vuoto.",
            ))
    return issues


def confidence_in_bounds(atom: AtomCandidate) -> list[Issue]:
    if not (0.0 <= atom.confidence <= 1.0):
        return [_iss(
            atom, "A-SCHEMA02", "BLOCKER", "confidence",
            f"CONFIDENCE fuori intervallo [0,1]: {atom.confidence}.",
        )]
    return []


def valid_to_not_before_valid_from(atom: AtomCandidate) -> list[Issue]:
    """Same check TYPE area35_validator's r_temporale T01 already applies
    to Notion mostra dates (end not before start) -- reapplied here to
    the ATOM's own VALID_FROM/VALID_TO, not reusing that function
    directly (it is Record-shaped), but reusing the pattern."""
    if atom.valid_from and atom.valid_to and atom.valid_to < atom.valid_from:
        return [_iss(
            atom, "A-TIME01", "BLOCKER", "valid_to",
            f"VALID_TO ({atom.valid_to}) anteriore a VALID_FROM ({atom.valid_from}).",
        )]
    return []


ATOM_RULES = (
    eic09_valid_requires_source,
    eic16_invalidated_requires_end_reason,
    required_fields_not_empty,
    predicate_class_is_frozen,
    confidence_in_bounds,
    valid_to_not_before_valid_from,
)
ONTOLOGY_RULES = (predicate_is_governed, object_type_matches_predicate_range)


def validate_atom(atom: AtomCandidate, registry: dict | None = None) -> list[Issue]:
    """Runs every mechanically-enforced rule against one ATOM candidate.
    registry is accepted as a parameter (not always reloaded from disk)
    so a caller validating many atoms can load
    GMV_ONTOLOGY_REGISTRY_v0.1.json once."""
    if registry is None:
        registry = _load_ontology_registry()
    issues: list[Issue] = []
    for rule in ATOM_RULES:
        issues += rule(atom)
    for rule in ONTOLOGY_RULES:
        issues += rule(atom, registry)
    issues.sort(key=lambda i: (SEV.get(i.severita, 9), i.codice))
    return issues


def compute_atom_fingerprint(
    atom: AtomCandidate,
    subject_gmv_id: str | None = None,
    object_gmv_id: str | None = None,
) -> str:
    """External deduplication key (crawler spec §16), computed by
    reusing area35_validator's own normalization -- imported, not
    reimplemented, per Correction 3's explicit instruction. Uses
    _forma(), not plain norm(), for subject/object: an earlier version
    of this function used norm() alone, which does not reorder tokens,
    so "Federico Garibaldi" and "Garibaldi, Federico" -- the same
    subject, written in a different order by two different extraction
    passes -- fingerprinted differently, a real dedup false-negative.
    _forma() already solves exactly this in area35_validator.py (used
    there by r_duplicati/D02 for artista/persona name matching); reusing
    it here instead of only norm() closes the same gap for ATOM
    fingerprinting, not just for Notion row deduplication. predicate is
    NOT passed through _forma()/norm(): it comes from a governed,
    canonical vocabulary (GMV_ONTOLOGY_REGISTRY_v0.1.json), not free
    text, so token-reordering has no meaning there and would only risk
    collapsing genuinely different predicates that happen to share
    words. Deliberately excludes ATOM_ID, SOURCE, and every temporal/
    lifecycle field: two atoms asserting the same SUBJECT/PREDICATE/
    OBJECT from different sources, or re-derived after a re-scan, are
    the same semantic claim and must fingerprint identically, not
    diverge because of provenance metadata.

    subject_gmv_id/object_gmv_id: the resolved entity identity
    (Entity Registry, gmv_core/migration_sql/010_entity_registry.sql --
    gmv_id, stable and independent of the canonical name) for this
    atom's subject/object, when it exists. When provided, that id is
    used verbatim in place of _forma(subject)/_forma(object) for the
    corresponding fingerprint component -- two differently-worded
    extraction passes of the same already-resolved entity collapse to
    the same fingerprint through their shared gmv_id, even where the
    raw texts would not _forma()-collapse at all (closing, for resolved
    entities, the word-order/OBJECT_TYPE collision risk on multi-word
    non-person text documented below: "Venice Biennale" vs. "Biennale
    Venice" now fingerprint differently whenever each is bound to a
    different gmv_id, and identically whenever both resolve to the
    same one). The id is used verbatim, not normalized: it is a
    governed, name-independent identity, so none of the token
    normalization _forma() exists for applies to it. Absent (default
    None) means the entity has not been resolved yet -- no entity-
    resolution engine exists anywhere upstream to produce these ids
    automatically (Group B, see AGENTS.md) -- and the component falls
    back to _forma() exactly as before, byte for byte, so every
    existing single-argument call keeps its exact current fingerprint.
    This is the same "accept from the caller what no upstream engine
    yet produces automatically" pattern already used by
    derive_current_state()'s ``registry`` and reconcile()'s
    ``existing_atoms``.

    Known accepted trade-off, not eliminated here: when neither
    subject_gmv_id nor object_gmv_id is provided, area35_validator.py
    only ever calls _forma() for entita in ("artista", "persona")
    (r_duplicati) -- this function applies it to every ATOM's
    subject/object regardless of OBJECT_TYPE, a broader use than
    anything validated in area35_validator.py. _forma() sorts ALL
    tokens alphabetically, not just comma-separated name parts, so two
    genuinely different multi-word values that happen to share the same
    words in a different order -- e.g. "Venice Biennale" and "Biennale
    Venice" -- collide (see test_fingerprint_collides_on_reordered_
    non_person_text, which documents this rather than hiding it). For
    the entity types this validator has real coverage for today
    (PERSON/ARTIST names, where order genuinely carries no meaning),
    this is the correct behavior; for PLACE/EVENT/DOCUMENT-typed objects
    it is a real, currently-accepted risk of a false-positive dedup
    match, not a false negative like the bug this fix closes. The
    subject_gmv_id/object_gmv_id parameters are the first concrete
    realization of the "key normalization on resolved identity" direction
    -- a correct full fix would also key normalization on OBJECT_TYPE
    (order-invariant only for identity-like types) for unresolved
    entities, which is not decided here and is deferred to whichever step
    actually consumes fingerprints for real deduplication."""
    subject_component = _forma(atom.subject) if subject_gmv_id is None else subject_gmv_id
    object_component = _forma(atom.object) if object_gmv_id is None else object_gmv_id
    normalized = "|".join((subject_component, atom.predicate, object_component))
    import hashlib

    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()
