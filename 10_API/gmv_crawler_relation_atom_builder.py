#!/usr/bin/env python3
"""GMV Crawler — BUILD ATOMS for RELATION predicates (narrow slice: `located_at`).

Connects three already-built pieces -- the curated raw-text->predicate
mapping (`00_CONFIG/crawler_predicate_text_mapping.json`), entity type
classification (`classify_entity_types()`, Task 8), and the atom itself
(`AtomCandidate`/`validate_atom()`) -- for exactly the 2 raw predicates
observed on real Garibaldi data ("was held at", "was presented at"), both
mapping to `located_at`. Deliberately not generalized: nothing else is
attempted, "acquired"->owned_by inversion included.

DISCLOSED DEVIATION from the task brief (opencode_task_10.md), found by
reading the real code and confirmed empirically before writing this
module, and NOT a silent workaround -- the brief itself says to stop and
flag when the real code contradicts it:

- Brief step 6 says: reject when `validate_atom()` yields "at least one
  Issue with severita == "BLOCKER" -- and then asserts this is the point
  where a wrong `object_type` (model classifying a venue as EXHIBITION
  instead of PLACE) is caught mechanically, and its most-important test
  mandates `VALIDATION_FAILED` for exactly that case.
- The real validator does NOT do that: `object_type_matches_predicate_range()`
  (gmv_atom_validator.py) reports a range mismatch as A-SCHEMA05 with
  severity MAJOR, never BLOCKER (verified by running `validate_atom()`
  on an EXHIBITION-typed located_at atom: exactly one Issue, A-SCHEMA05,
  MAJOR). A pure BLOCKER rule would ACCEPT the mis-typed atom and the
  brief's most-important test would fail.

Resolution: this module treats as fatal any Issue with severity BLOCKER
OR codice A-SCHEMA05 (the object_type-vs-range check -- selected by
codice, not severity, so the deviation stays exactly as narrow as the
problem it exists for). Every other MAJOR (e.g. A-SCHEMA03 predicate-
class inconsistency) remains non-fatal exactly like Task 6. This is the
minimal behavior the brief's own mandated test requires; flagged loudly
here, in the commit, and in the work log -- the directing session
re-verifies.

The brief's other intent clause -- predicate_class must come from the
REAL registry, never a hardcoded "RELATION", so a wrong-class predicate
added to the mapping file must surface -- is implemented two ways: the
atom's `predicate_class` is read from the registry entry, AND an
import-time guard (same fail-loud pattern as Task 6's ATTRIBUTE guard)
asserts every predicate_id shipped in the mapping file is registered and
is of class RELATION, so a mistaken entry aborts at import, never runs.

Why `object_type` (and never `subject_type`): `validate_atom()` has zero
references to "domain" anywhere (verified by grep) -- it only checks
`object_type` against the predicate's declared `range`. So resolving the
OBJECT's type is precisely what makes a RELATION atom validatable; the
subject is passed through verbatim, no resolution attempted.

`BuiltRelationAtom` carries the full `object_type_proposal` (not just the
type string) because `AtomCandidate` is frozen by spec -- 18 fields, no
room for "was this type verified or inferred". The consumer decides what
`needs_verification=True` means (e.g. route to Task 9's
`append_entity_proposals()`), never this module.

Out of scope, per brief: no edit to gmv_crawler_atom_builder.py (Task 6,
kept fully decoupled); no extension of the mapping file; no subject/object
inversion handling; no Entity Registry writes; no pipeline wiring; NO
automatic call to Task 9's queue from here.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_atom_validator import (  # noqa: E402 -- reused, not reimplemented
    AtomCandidate,
    _known_predicates,
    _load_ontology_registry,
    validate_atom,
)
from gmv_crawler_atom_builder import RejectedCandidate  # noqa: E402 -- same dataclass, import direct, never redefined
from gmv_crawler_candidate_extractor import (  # noqa: E402 -- reuse, not redefine (Task 8 pattern)
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    CandidateEntity,
    CandidateProposition,
)
from gmv_crawler_entity_resolver import (  # noqa: E402 -- reuse, not reimplement
    EntityTypeProposal,
    classify_entity_types,
)

PREDICATE_MAPPING_PATH = REPO_ROOT / "00_CONFIG" / "crawler_predicate_text_mapping.json"

#: The one nontrivial decision this module makes beyond Task 6, fully
#: disclosed in the module docstring: `object_type_matches_predicate_range()`
#: reports a wrong object type as A-SCHEMA05 with severity MAJOR, so a
#: BLOCKER-only rule would silently ACCEPT the mis-typed atom that the
#: task brief's most-important test explicitly demands be rejected.
#: Selected by codice, not severity, to stay exactly as narrow as the
#: problem.
_RANGE_MISMATCH_IS_FATAL = "A-SCHEMA05"


def _load_predicate_mapping() -> dict[str, str]:
    """The curated human-edited mapping file, as `dict[normalized_raw_text,
    predicate_id]`. Key normalization is `.strip().lower()` -- the ONLY
    normalization, exactly as the brief specifies: equality, never fuzzy
    matching."""
    data = json.loads(PREDICATE_MAPPING_PATH.read_text(encoding="utf-8"))
    return {
        entry["raw_predicate_text"].strip().lower(): entry["predicate_id"]
        for entry in data["mappings"]
    }


#: Import-time fail-loud guard, same shape as Task 6's ATTRIBUTE/integer
#: guard and for the same reason: if the human-curated mapping file ever
#: points at an unregistered or non-RELATION predicate_id, that is an
#: editorial error that must surface at import, never silently operate.
#: (The brief's own "resolve predicate_class from the real registry"
#: clause cannot alone surface this -- predicate_class read from the same
#: entry the atom declares is always self-consistent, so the guard is
#: what actually makes a wrong-class entry visible.)
_MAPPED_PREDICATE_IDS: frozenset[str] = frozenset(_load_predicate_mapping().values())
if _MAPPED_PREDICATE_IDS:
    _mapped_registry = _load_ontology_registry()
    _mapped_known = _known_predicates(_mapped_registry)
    _not_registered = _MAPPED_PREDICATE_IDS - _mapped_known.keys()
    if _not_registered:
        raise RuntimeError(
            "gmv_crawler_relation_atom_builder: crawler_predicate_text_mapping.json "
            f"points at unregistered predicates {sorted(_not_registered)!r} in "
            "GMV_ONTOLOGY_REGISTRY_v0.1.json"
        )
    _non_relation = {
        pid for pid in _MAPPED_PREDICATE_IDS
        if _mapped_known[pid]["predicate_class"] != "RELATION"
    }
    if _non_relation:
        raise RuntimeError(
            "gmv_crawler_relation_atom_builder: crawler_predicate_text_mapping.json "
            f"maps to non-RELATION predicate(s) {sorted(_non_relation)!r}; this "
            "module is the RELATION slice only"
        )


@dataclass(frozen=True, slots=True)
class BuiltRelationAtom:
    """A successfully built RELATION atom plus the object-type proposal it
    was built from. The proposal rides along because `AtomCandidate` is
    frozen by spec and cannot carry "was this object type verified or
    inferred" -- `needs_verification` stays attached to what produced it,
    and whoever consumes `BuiltRelationAtom` decides what to do with it
    (e.g. Task 9's queue, when True)."""

    atom: AtomCandidate
    object_type_proposal: EntityTypeProposal


def _rejected(proposition: CandidateProposition, reason_code: str, detail: str) -> RejectedCandidate:
    return RejectedCandidate(
        source_id=proposition.source_id,
        extraction_claim_ref=proposition.extraction_claim_ref,
        raw_predicate=proposition.predicate,
        reason_code=reason_code,
        detail=detail,
    )


def _link_object_to_entity(
    object_raw: str, entities: Sequence[CandidateEntity]
) -> CandidateEntity | None:
    """Find the batch entity whose name is a prefix of `object_raw`.

    Both `object_raw` and each `entity.name` are normalized with
    `.strip().lower()` before comparison (verified on real Garibaldi
    cases: "Le Stanze della Fotografia, Venice (2025)" starts with
    "le stanze della fotografia"; "Area35 Art Gallery in 2019" starts
    with "area35 art gallery"). When more than one entity matches as a
    prefix, the one with the LONGEST normalized name wins (most specific
    match); an exact tie in normalized length between DIFFERENT matchers
    is a real ambiguity -> None (the caller rejects it, never an
    arbitrary pick). No match -> None. Pure function, no I/O."""
    normalized_object = object_raw.strip().lower()
    matchers: list[tuple[int, CandidateEntity]] = []
    for entity in entities:
        normalized_name = entity.name.strip().lower()
        if normalized_object.startswith(normalized_name):
            matchers.append((len(normalized_name), entity))
    if not matchers:
        return None
    longest_length = max(length for length, _ in matchers)
    longest = [entity for length, entity in matchers if length == longest_length]
    if len(longest) > 1:
        return None
    return longest[0]


def build_relation_atoms(
    propositions: Sequence[CandidateProposition],
    entities: Sequence[CandidateEntity],
    *,
    now: str,
    registry: dict | None = None,
    predicate_mapping: dict[str, str] | None = None,
    known_artists: frozenset[str] | None = None,
    known_institutions: frozenset[str] | None = None,
    endpoint: str = DEFAULT_ENDPOINT,
    model: str = DEFAULT_MODEL,
    timeout: int = 60,
    temperature: float | None = None,
    seed: int | None = None,
) -> tuple[tuple[BuiltRelationAtom, ...], tuple[RejectedCandidate, ...]]:
    """Batch CandidateProposition -> RELATION atoms or structured rejections.

    `temperature`/`seed` (default None) pass straight through to
    `classify_entity_types()` -- see that function's own docstring for
    why they exist (a live, reproduced finding: the same entity can be
    classified differently on separate calls with Ollama's default
    sampling).

    `propositions` and `entities` MUST come from the same extraction/
    document (same `source_id`) -- the caller's responsibility, documented
    here, never validated in code (no clean way to check it without
    inventing a constraint a caller could still violate).

    Two passes, so there is exactly ONE `classify_entity_types()` call per
    batch, never one per proposition:

    Pass 1 (no network): resolve each `proposition.predicate.strip().lower()`
    through the mapping (`predicate_mapping`, loaded from the curated file
    when None). Unmapped -> `PREDICATE_TEXT_NOT_MAPPED` and dropped here.
    Mapped: `_link_object_to_entity(proposition.object_raw, entities)`; no
    (or ambiguous) link -> `OBJECT_NOT_LINKED_TO_KNOWN_ENTITY`. Survivors
    are staged with their resolved predicate_id and linked entity, and the
    DISTINCT entities (by `entity.name`) are collected.

    Pass 2 (one call): if any distinct entity needs classifying,
    `classify_entity_types()` is called ONCE for the whole batch
    (known_artists/endpoint/model/timeout passed straight through). A
    network/Ollama failure here propagates -- same behavior as that
    function itself, never swallowed into a fake rejection. Each staged
    proposition gets its proposal by EXACT `entity_name`. Then the atom is
    built with the Task 6 fixed literals verbatim
    (`status="UNVERIFIED"`, `confidence=0.5`, `visibility="INTERNAL"`,
    `asserted_by="crawler_llm_extraction"`, `asserted_at=ingested_at=now`,
    `valid_from=valid_to=end_reason=supersedes=superseded_by=None`,
    `atom_id="ATOM-"+sha256(source_id|extraction_claim_ref)[:16]`,
    `subject=subject_raw` verbatim, `predicate=predicate_id`,
    `predicate_class` from the registry entry, `object=object_raw.strip()`,
    `object_type=proposal.entity_type`) and validated with
    `validate_atom(atom, registry)`. Fatal = any BLOCKER issue OR any
    A-SCHEMA05 range-mismatch issue (see module docstring for the
    disclosed deviation) -> `VALIDATION_FAILED` with each fatal issue's
    codice+messaggio; otherwise a `BuiltRelationAtom`.

    Non-blocker MAJOR issues that are NOT the object-range mismatch stay
    non-fatal exactly like Task 6, but they are also not expected with
    these fixed fields -- one appearing is a signal to investigate, not
    to ignore.
    """
    if registry is None:
        registry = _load_ontology_registry()
    if predicate_mapping is None:
        predicate_mapping = _load_predicate_mapping()
    known = _known_predicates(registry)

    staged: list[tuple[CandidateProposition, str, CandidateEntity]] = []
    rejected: list[RejectedCandidate] = []
    distinct_entities: list[CandidateEntity] = []
    seen_names: set[str] = set()
    for proposition in propositions:
        predicate_id = predicate_mapping.get(proposition.predicate.strip().lower())
        if predicate_id is None:
            rejected.append(_rejected(
                proposition, "PREDICATE_TEXT_NOT_MAPPED",
                f"raw predicate {proposition.predicate!r} is not in the curated "
                "text->predicate mapping (00_CONFIG/crawler_predicate_text_mapping.json); "
                "a real vocabulary gap or a future editorial decision, not attempted here",
            ))
            continue
        linked = _link_object_to_entity(proposition.object_raw, entities)
        if linked is None:
            rejected.append(_rejected(
                proposition, "OBJECT_NOT_LINKED_TO_KNOWN_ENTITY",
                f"object_raw {proposition.object_raw!r} has no unambiguous "
                "prefix match among this document's extracted entities",
            ))
            continue
        staged.append((proposition, predicate_id, linked))
        if linked.name not in seen_names:
            seen_names.add(linked.name)
            distinct_entities.append(linked)

    proposals_by_name: dict[str, EntityTypeProposal] = {}
    if distinct_entities:
        proposals_by_name = {
            proposal.entity_name: proposal
            for proposal in classify_entity_types(
                distinct_entities,
                known_artists=known_artists,
                known_institutions=known_institutions,
                endpoint=endpoint,
                model=model,
                timeout=timeout,
                temperature=temperature,
                seed=seed,
            )
        }

    built: list[BuiltRelationAtom] = []
    for proposition, predicate_id, linked in staged:
        proposal = proposals_by_name[linked.name]
        atom = AtomCandidate(
            atom_id="ATOM-" + hashlib.sha256(
                f"{proposition.source_id}|{proposition.extraction_claim_ref}".encode("utf-8")
            ).hexdigest()[:16],
            subject=proposition.subject_raw,
            predicate=predicate_id,
            predicate_class=known[predicate_id]["predicate_class"],
            object=proposition.object_raw.strip(),
            object_type=proposal.entity_type,
            source=proposition.source_id,
            status="UNVERIFIED",
            valid_from=None,
            valid_to=None,
            asserted_at=now,
            ingested_at=now,
            asserted_by="crawler_llm_extraction",
            confidence=0.5,
            visibility="INTERNAL",
            end_reason=None,
            supersedes=None,
            superseded_by=None,
        )
        issues = validate_atom(atom, registry)
        fatal = [
            issue for issue in issues
            if issue.severita == "BLOCKER" or issue.codice == _RANGE_MISMATCH_IS_FATAL
        ]
        if fatal:
            detail = "; ".join(f"{issue.codice}: {issue.messaggio}" for issue in fatal)
            rejected.append(_rejected(proposition, "VALIDATION_FAILED", detail))
        else:
            built.append(BuiltRelationAtom(atom=atom, object_type_proposal=proposal))
    return tuple(built), tuple(rejected)