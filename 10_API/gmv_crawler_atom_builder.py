#!/usr/bin/env python3
"""GMV Crawler — BUILD ATOMS v0, a deliberately narrow first slice.

Translates a `CandidateProposition` (`gmv_crawler_candidate_extractor.py`,
step 11) into an `AtomCandidate` (`gmv_atom_validator.py`, step 7) for
exactly the subset that needs no entity resolution: every registered
`ATTRIBUTE`-class predicate whose declared `range` is a single LITERAL
type -- never an entity type. In `GMV_ONTOLOGY_REGISTRY_v0.1.json` as of
2026-09-27 that is five predicates, three of them `["integer"]`
(`edition_size`, `edition_number`, `creation_year`) and two of them
`["string"]` (`dimensions`, `medium`). For each, `object_type` is that
one literal type, read from the registry entry rather than hardcoded --
zero RESOLVE ENTITIES needed, which is the whole reason this narrow slice
is buildable at all. Every other predicate (unregistered, registered with
a non-ATTRIBUTE class, or an ATTRIBUTE predicate whose range is
entity-typed or `["ANY"]`) is rejected with a structured
`RejectedCandidate`, never forced through and never silently ignored.

Widened from two predicates to five on 2026-09-27 (task brief
opencode_task_16.md) when three new CANDIDATE ATTRIBUTE predicates were
registered: `dimensions`/`medium` (range `["string"]`) and
`creation_year` (range `["integer"]`). The generalizing change is that
`object_type` is now DERIVED from the registry entry instead of being the
constant `"integer"`, and object validation branches on it. What did not
change is everything the two original predicates depended on: the same
`.isdigit()` check, the same `OBJECT_NOT_INTEGER` reason code, the same
`atom_id` scheme, the same fixed literals, the same rejections.

The two object types are genuinely asymmetric, and deliberately so:

- `["integer"]` predicates get a real content check. `.isdigit()` is a
  conservative "all decimal digits" test (no sign, no decimal point, no
  inner space), so `circa 2013` and `3/10` are rejected rather than
  guessed at, with `OBJECT_NOT_INTEGER`.
- `["string"]` predicates get NO content check, because there is nothing
  to check: any non-empty string is a valid literal, and
  `CandidateProposition.__post_init__` already guarantees `object_raw` is
  non-empty. Inventing a fifth reason_code to reject a badly-shaped
  dimensions string would be a policy decision about corpus text, not a
  validation rule, and would be out of scope here.
  `CandidateProposition.__post_init__` guarantees non-empty, not
  non-BLANK, so a whitespace-only `object_raw` is the one constructible
  input that slips past it; it strips to `""` here and is caught by
  `validate_atom()`'s own A-SCHEMA04 mandatory-field check as a BLOCKER,
  which this module already turns into `VALIDATION_FAILED`. That was
  verified empirically, not assumed -- see
  `test_build_atom_blank_object_rejects_for_a_string_range_predicate`.

This slice was judged safe to delegate despite BUILD ATOMS remaining a
Group B item in AGENTS.md: every design decision below was already made
by the user and is specified exactly in the task brief (opencode_task_6.md
for the original integer-only slice, opencode_task_16.md for this
widening) -- this module translates that specification into code, it does
not attempt the general Candidate->Atom conversion (which for the 14
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

#: Every ATTRIBUTE-class predicate in GMV_ONTOLOGY_REGISTRY_v0.1.json whose
#: declared `range` is a single literal type, mapped to that type -- the
#: registry's own answer to "what object_type does this predicate take?",
#: read rather than hardcoded, so adding a predicate or widening one
#: cannot leave this module asserting a type the registry contradicts.
#:
#: The `entry.get("range") in (["integer"], ["string"])` filter is the
#: module's entire definition of its own scope, and it is an ALLOW-list of
#: two literal types on purpose. An ATTRIBUTE predicate whose range is
#: entity-typed (`["PLACE"]`, `["WORK"]`) or `["ANY"]` is excluded even
#: though it is nominally ATTRIBUTE-class, because this module's reason to
#: exist is the subset needing no entity resolution; widening the allow-list
#: is how that boundary would be crossed, and this line is where that
#: decision would have to be made on purpose. `predicate_class ==
#: "ATTRIBUTE"` is kept in the filter as well: the range check alone would
#: not be sufficient, and the registry currently happens to make it so.
#: Verified against the real registry: all 14 RELATION predicates have
#: entity-typed or `["ANY"]` ranges, and all 5 ATTRIBUTE ones are
#: single-literal (see
#: tests/test_gmv_crawler_atom_builder.py::test_module_attribute_literal_predicate_object_types_
#: matches_real_registry, which re-derives this independently).
_ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES: dict[str, str] = {
    entry["predicate_id"]: entry["range"][0]
    for entry in _load_ontology_registry()["predicates"]
    if entry["predicate_class"] == "ATTRIBUTE" and entry.get("range") in (["integer"], ["string"])
}

#: The exact id -> object_type map this module was written against, pinned at
#: import -- an assertion, not a runtime check, for the same fail-loudly
#: reason derive_relations() uses for its "RELATION" literal: if the registry
#: ever grows a sixth literal-range ATTRIBUTE predicate, or changes one of
#: these five's declared range, this module's object validation and object_type
#: assignment must not silently keep operating on an unanticipated predicate.
#: Both halves are pinned deliberately: the KEY SET alone would miss a range
#: change (flipping `dimensions` to `["integer"]` would keep all five keys and
#: pass a set-only check, while every dimensions atom silently became
#: object_type="integer"), so the values are asserted too.
_EXPECTED_ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES: dict[str, str] = {
    "edition_size": "integer",
    "edition_number": "integer",
    "creation_year": "integer",
    "dimensions": "string",
    "medium": "string",
}
if _ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES != _EXPECTED_ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES:
    raise RuntimeError(
        "gmv_crawler_atom_builder's ATTRIBUTE literal-range predicate set is stale: "
        "the ontology registry now declares "
        f"{dict(sorted(_ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES.items()))}, "
        f"expected {dict(sorted(_EXPECTED_ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES.items()))}. "
        "Widen this module deliberately (its whole scope is 'ATTRIBUTE with a literal "
        "range'), never by letting the registry change underneath it."
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
    2. Resolved but `predicate_class != "ATTRIBUTE"` (the 14 RELATION
       predicates would need entity resolution; IDENTITY/EVENT/MEASURE/
       EPISTEMIC likewise) -> PREDICATE_NOT_YET_SUPPORTED.
    3. Added 2026-09-27: resolved, ATTRIBUTE-class, but its
       `predicate_id` is not a key of
       `_ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES` -> also
       PREDICATE_NOT_YET_SUPPORTED, same reason code as step 2. Today
       every ATTRIBUTE predicate in the registry is a key of that map
       (the import-time guard above pins that), so this branch is
       future-proofing rather than a live path -- but it is the branch
       that would otherwise have no home, since an entity-ranged
       ATTRIBUTE predicate is exactly the case this module must not
       build. It shares step 2's code because the judgement is the same:
       "this predicate needs a decision this slice does not make".
    4. `object_type` is DERIVED, never hardcoded: the map's value for the
       canonical `predicate_id`. Object validation then branches on it:
       - `"integer"` -> `object_raw.strip()` must be an all-decimal-digit
         string (`str.isdigit()` -- no sign, no decimal, no inner space;
         any borderline case is rejected with OBJECT_NOT_INTEGER rather
         than accepted). Byte-for-byte the pre-2026-09-27 behaviour,
         which was this check unconditionally.
       - `"string"` -> no additional check: any non-empty string is a
         valid literal and `CandidateProposition.__post_init__` already
         guarantees non-empty. A blank-after-strip object is still
         caught, downstream and for free, by `validate_atom()`'s
         A-SCHEMA04 BLOCKER (see the module docstring).
    5. Atom built with the fixed literals documented in the module
       docstring; `atom_id` from sha256(source_id|extraction_claim_ref),
       unique per extraction, not per semantic fact.
    6. `validate_atom(atom, registry)`: any Issue with `severita ==
       "BLOCKER"` -> VALIDATION_FAILED with a readable detail listing
       each blocker's codice+messaggio; otherwise the atom is returned
       as-is (non-blocker issues do not block, but none are expected
       with these fixed fields -- if an unexpected one appears, that is
       a signal to stop and investigate, not to ignore).

    One deliberate coupling worth stating rather than leaving to be
    discovered, because it was checked rather than assumed: steps 1-2 and
    6 read the CALLER's `registry` parameter, while steps 3-4 read the
    module-level map computed at import from the real registry. A caller
    passing a registry that disagrees with the import-time one (e.g. real
    `dimensions` re-declared with an entity range) would produce an atom
    whose object_type contradicts that registry's own declared range.
    It is NOT rejected: `object_type_matches_predicate_range()` reports
    that as A-SCHEMA05 with severita "MAJOR", and this module blocks only
    on "BLOCKER" (step 6, unchanged behaviour). So the atom is returned,
    carrying a visible non-blocking issue that `validate_atom(atom,
    registry)` reports to the caller. Disclosed rather than papered over
    because the alternative -- treating a MAJOR as blocking -- would
    change behaviour for the two original predicates and is out of
    scope. No caller in this repository passes a non-None `registry`
    (every call site, production and test, lets it load the real file),
    so in practice the two are the same object and the case is
    unreachable. Pinned by
    test_registry_disagreeing_with_the_import_time_map_surfaces_a_major_issue.
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
    predicate_id = entry["predicate_id"]
    if predicate_id not in _ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES:
        return _rejected(
            proposition, "PREDICATE_NOT_YET_SUPPORTED",
            f"predicate {proposition.predicate!r} resolves to ATTRIBUTE predicate "
            f"{predicate_id!r}, which this module does not build: it is not one of the "
            "literal-range ATTRIBUTE predicates it knows how to validate (an "
            "entity-typed or ['ANY'] range needs entity resolution, which does not "
            "exist yet). Widen the module on purpose rather than forcing it through.",
        )
    object_type = _ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES[predicate_id]
    object_value = proposition.object_raw.strip()
    if object_type == "integer" and not object_value.isdigit():
        return _rejected(
            proposition, "OBJECT_NOT_INTEGER",
            f"object_raw {proposition.object_raw!r} is not an all-decimal-digit "
            f"string, but predicate {predicate_id!r} declares range "
            "['integer']",
        )
    atom_id = "ATOM-" + hashlib.sha256(
        f"{proposition.source_id}|{proposition.extraction_claim_ref}".encode("utf-8")
    ).hexdigest()[:16]
    atom = AtomCandidate(
        atom_id=atom_id,
        subject=proposition.subject_raw,  # verbatim, no normalization
        predicate=predicate_id,  # canonical id, not the raw spelling
        predicate_class="ATTRIBUTE",
        object=object_value,
        object_type=object_type,
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