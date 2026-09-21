#!/usr/bin/env python3
"""GMV Crawler — BUILD ATOMS v0, a deliberately narrow first slice.

Translates a `CandidateProposition` (`gmv_crawler_candidate_extractor.py`,
step 11) into an `AtomCandidate` (`gmv_atom_validator.py`, step 7) for
exactly the subset that needs no entity resolution: the two registered
`ATTRIBUTE`-class predicates whose declared `range` is the literal
`["integer"]` (`edition_size`, `edition_number` in
`GMV_ONTOLOGY_REGISTRY_v0.1.json`). For those two, `object_type` is
always and only `"integer"` -- zero RESOLVE ENTITIES needed, which is
the whole reason this narrow slice is buildable at all. Every other
predicate (unregistered, or registered with a non-ATTRIBUTE class) is
rejected with a structured `RejectedCandidate`, never forced through
and never silently ignored.

This slice was judged safe to delegate despite BUILD ATOMS remaining a
Group B item in AGENTS.md: every design decision below was already made
by the user and is specified exactly in the task brief (opencode_task_6.md)
-- this module translates that specification into code, it does not
attempt the general Candidate->Atom conversion (which for the 11
RELATION predicates would require knowing what *kind of entity* the
object is: RESOLVE ENTITIES, unbuilt).

Non-negotiable boundaries, mirrored in the code, not just this docstring:

- `CandidateEntity` is never touched: it has no well-defined
  subject-predicate-object shape and no governed home in this module yet.
- No RELATION predicate is handled, "obvious"-looking cases included.
- Fixed literals are exactly that: `status="UNVERIFIED"` (nothing here
  has passed a real epistemic verification, and STATUS=VALID would fail
  EIC-09 without any real source discipline), `asserted_by=
  "crawler_llm_extraction"`, `confidence=0.5` (declared unrefined),
  `visibility="INTERNAL"` (never `"PUBLIC"`: step 15 publishes only
  VISIBILITY=="PUBLIC", so no atom built here is ever publishable
  without a later, deliberate, explicitly out-of-scope decision).
- `atom_id` is `"ATOM-" + sha256(source_id|extraction_claim_ref)[:16]`:
  unique per single extraction, NOT per semantic fact. Deliberately does
  NOT reuse `compute_atom_fingerprint()`: that key exists to recognize
  the *same fact* told by different sources, and two atoms sharing a
  fingerprint but coming from different sources must be able to coexist
  (step 12 `reconcile()`'s SUPPORTING outcome) -- using it as the id
  would collapse them onto one id.
- Rejections are one of exactly four reason_codes
  (UNKNOWN_PREDICATE / PREDICATE_NOT_YET_SUPPORTED / OBJECT_NOT_INTEGER /
  VALIDATION_FAILED), never a fifth invented value. Building the
  human-review queue for those rejections is out of scope here; the
  structured `RejectedCandidate` is the raw material for it.
"""

from __future__ import annotations

import hashlib
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
from gmv_crawler_candidate_extractor import CandidateProposition  # noqa: E402 -- reused, not reimplemented

# The only two ATTRIBUTE-class predicates in GMV_ONTOLOGY_REGISTRY_v0.1.json
# (verified by reading that file: 13 predicates total, 11 RELATION). An
# assertion at import time -- same fail-loudly guard derive_relations()
# already uses for its "RELATION" literal -- so if the registry ever grows
# a third ATTRIBUTE predicate, this module's hardcoded object_type stops
# hiding it instead of silently operating on an unanticipated predicate.
_ATTRIBUTE_INTEGER_PREDICATE_IDS: frozenset[str] = frozenset(
    entry["predicate_id"] for entry in _load_ontology_registry()["predicates"]
    if entry["predicate_class"] == "ATTRIBUTE" and entry.get("range") == ["integer"]
)
if _ATTRIBUTE_INTEGER_PREDICATE_IDS != frozenset({"edition_size", "edition_number"}):
    raise RuntimeError(
        "gmv_crawler_atom_builder's ATTRIBUTE/integer predicate set is stale: "
        f"the ontology registry now declares {sorted(_ATTRIBUTE_INTEGER_PREDICATE_IDS)}, "
        "expected {'edition_size', 'edition_number'}"
    )


@dataclass(frozen=True, slots=True)
class RejectedCandidate:
    """A `CandidateProposition` this module refused to turn into an atom,
    with a structured reason instead of a silent drop. The human-review
    queue's raw material.

    `subject_raw`/`object_raw`/`evidence_excerpt` added 2026-09-21: without
    them, a human reviewing `PREDICATE_TEXT_NOT_MAPPED` entries later could
    see a raw predicate's TEXT and its FREQUENCY, but never who the claim
    was actually about or the real sentence it came from -- exactly the
    real-example domain/range check `00_CONFIG/crawler_predicate_text_
    mapping.json`'s own governance note requires before adding a mapping
    ("Every entry here was checked by a human against the target
    predicate's real domain/range"). A live audit this session found the
    OLD 5-field record made that verification impossible after the fact
    (10296 real rejected claims accumulated with no way to recover their
    subject/object/quote). These three fields were already on
    `CandidateProposition` the whole time -- simply never copied over."""

    source_id: str
    extraction_claim_ref: str
    raw_predicate: str
    reason_code: str  # exactly one of the four documented below, never a fifth
    detail: str
    subject_raw: str
    object_raw: str
    evidence_excerpt: str


def _rejected(proposition: CandidateProposition, reason_code: str, detail: str) -> RejectedCandidate:
    return RejectedCandidate(
        source_id=proposition.source_id,
        extraction_claim_ref=proposition.extraction_claim_ref,
        raw_predicate=proposition.predicate,
        reason_code=reason_code,
        detail=detail,
        subject_raw=proposition.subject_raw,
        object_raw=proposition.object_raw,
        evidence_excerpt=proposition.evidence_excerpt,
    )


def build_atom(
    proposition: CandidateProposition, *, now: str, registry: dict | None = None
) -> AtomCandidate | RejectedCandidate:
    """One `CandidateProposition` -> atom or structured rejection.

    Exact algorithm (task brief opencode_task_6.md), no interpretation:

    1. `proposition.predicate` is resolved through
       `_known_predicates(registry)` -- both canonical ids and registered
       aliases (e.g. `evidences` -> `source_for`), so an alias resolves
       to its canonical entry, never to its own spelling. Unresolvable
       -> UNKNOWN_PREDICATE.
    2. Resolved but `predicate_class != "ATTRIBUTE"` (the 11 RELATION
       predicates would need entity resolution; IDENTITY/EVENT/MEASURE/
       EPISTEMIC likewise) -> PREDICATE_NOT_YET_SUPPORTED.
    3. `object_raw.strip()` is not an all-decimal-digit string
       (`str.isdigit()` -- no sign, no decimal, no inner space; any
       borderline case is rejected with this code rather than accepted)
       -> OBJECT_NOT_INTEGER.
    4. Atom built with the fixed literals documented in the module
       docstring; `atom_id` from sha256(source_id|extraction_claim_ref),
       unique per extraction, not per semantic fact.
    5. `validate_atom(atom, registry)`: any Issue with `severita ==
       "BLOCKER"` -> VALIDATION_FAILED with a readable detail listing
       each blocker's codice+messaggio; otherwise the atom is returned
       as-is (non-blocker issues do not block, but none are expected
       with these fixed fields -- if an unexpected one appears, that is
       a signal to stop and investigate, not to ignore).
    """
    if registry is None:
        registry = _load_ontology_registry()
    known = _known_predicates(registry)
    entry = known.get(proposition.predicate)
    if entry is None:
        return _rejected(
            proposition, "UNKNOWN_PREDICATE",
            f"predicate {proposition.predicate!r} is neither a registered canonical "
            "id nor a registered alias in GMV_ONTOLOGY_REGISTRY_v0.1.json",
        )
    if entry["predicate_class"] != "ATTRIBUTE":
        return _rejected(
            proposition, "PREDICATE_NOT_YET_SUPPORTED",
            f"predicate {proposition.predicate!r} resolves to "
            f"{entry['predicate_id']!r}, class {entry['predicate_class']!r}; only "
            "ATTRIBUTE predicates are supported in this v0 slice (the rest need "
            "entity resolution, which does not exist yet)",
        )
    object_value = proposition.object_raw.strip()
    if not object_value.isdigit():
        return _rejected(
            proposition, "OBJECT_NOT_INTEGER",
            f"object_raw {proposition.object_raw!r} is not an all-decimal-digit "
            f"string, but predicate {entry['predicate_id']!r} declares range "
            "['integer']",
        )
    atom_id = "ATOM-" + hashlib.sha256(
        f"{proposition.source_id}|{proposition.extraction_claim_ref}".encode("utf-8")
    ).hexdigest()[:16]
    atom = AtomCandidate(
        atom_id=atom_id,
        subject=proposition.subject_raw,  # verbatim, no normalization
        predicate=entry["predicate_id"],  # canonical id, not the raw spelling
        predicate_class="ATTRIBUTE",
        object=object_value,
        object_type="integer",
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
    blockers = [i for i in validate_atom(atom, registry) if i.severita == "BLOCKER"]
    if blockers:
        detail = "; ".join(f"{i.codice}: {i.messaggio}" for i in blockers)
        return _rejected(proposition, "VALIDATION_FAILED", detail)
    return atom


def build_atoms(
    propositions: Sequence[CandidateProposition], *, now: str, registry: dict | None = None
) -> tuple[tuple[AtomCandidate, ...], tuple[RejectedCandidate, ...]]:
    """Batch form of `build_atom()`. Loads the registry once (if None)
    and passes it to every call -- the same reason validate_atom()/
    derive_current_state() accept `registry` as a parameter. One element
    must never fail the whole batch: iterated explicitly, not built with
    a comprehension that would propagate an exception (the exact
    all-or-nothing bug extract_candidates() already fixed for its own
    per-item isolation -- see that function's docstring). Every
    rejection path of build_atom() returns a RejectedCandidate, so
    nothing here can raise on candidate data; `registry` is the only
    caller-supplied input that could, and a malformed registry is a
    caller bug, not a per-item outcome."""

    if registry is None:
        registry = _load_ontology_registry()
    built: list[AtomCandidate] = []
    rejected: list[RejectedCandidate] = []
    for proposition in propositions:
        result = build_atom(proposition, now=now, registry=registry)
        if isinstance(result, RejectedCandidate):
            rejected.append(result)
        else:
            built.append(result)
    return tuple(built), tuple(rejected)