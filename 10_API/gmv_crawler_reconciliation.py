#!/usr/bin/env python3
"""GMV Crawler — Reconciliation engine (crawler preplan step 12 / spec v0.2 §15-20).

RECONCILE stage (§3): a new `AtomCandidate` (step 7) vs. atoms that
already exist, classified into one of the crawler spec's reconciliation
outcomes ("NEW / IDENTICAL / SUPPORTING / CONFLICTING / SUPERSEDING /
CORRECTING, mai overwrite distruttivo -- coerente con il vocabolario
epistemico canonico ... gia' in uso").

Grounding, read in full before writing this module:

- `GMV_KNOWLEDGE_MONAD_SPEC_v1.0` §9 (Lifecycle e correzioni, fetched
  fresh from Notion this session, not assumed from memory): tombstoning
  is `STATUS=INVALIDATED, END_REASON=CORRECTED`, with `SUPERSEDES`/
  `SUPERSEDED_BY` used "quando esiste un vero successore atomico
  identificabile" -- `SUPERSEDED_BY` is explicitly NOT always required.
  This frozen spec does **not** define the six-value reconciliation
  outcome vocabulary itself -- that is the crawler spec's own addition,
  a new crawler-layer vocabulary describing *how* a candidate relates to
  existing atoms, which then determines *whether* the frozen tombstoning
  fields get applied. Same relationship as step 5's `Gate` type to
  `gate()`'s real vocabulary: a new name, not a reused one -- documented
  as such, not silently claimed as "already existing."
- `area35_validator.py::r_duplicati()` (Correction 3's cited reuse
  target): only *flags* duplicate identity keys and probable same-entity
  name variants as review issues (`D01`/`D02`). It does not merge, does
  not supersede, does not have any notion of a reconciliation state
  machine -- there is no existing reconciliation engine anywhere in this
  repository to wrap, unlike steps 9-11. This module is new design, not
  a wrapper, and is scoped down accordingly (see below).
- `gmv_evidence_pipeline.py::consolidate_claims()` groups already-
  *resolved* claims by `(resolved_subject_id, predicate, resolved_object_id,
  qualifiers)` -- the full triple, identical in shape to
  `compute_atom_fingerprint()` (step 7). No code anywhere in this repo
  groups by subject+predicate alone (a "slot", ignoring object) -- the
  comparison key a genuine CONFLICTING/SUPERSEDING check would need
  (same subject+predicate, *different* object, e.g. "resides in Rome"
  today vs. "resides in Milan" a year later -- these do NOT share a
  fingerprint, since OBJECT differs, so fingerprint-matching alone can
  never surface them).

**Deliberate v1 scope: only NEW / IDENTICAL / SUPPORTING are
implemented.** CONFLICTING, SUPERSEDING and CORRECTING all require that
"slot" comparison key (subject+predicate, object-agnostic) plus a policy
for *when* a same-slot, different-object pair is a genuine temporal
update (SUPERSEDING), a human correction (CORRECTING), or an unresolved
contradiction (CONFLICTING) -- e.g. whether a given PREDICATE_CLASS
(RELATION vs. MEASURE vs. ATTRIBUTE) even permits multiple simultaneous
valid values at all. None of that governance exists yet anywhere in this
repo (not in `GMV_ONTOLOGY_REGISTRY_v0.1.json`, not in the frozen Monad
spec, not in any prior crawler step). Inventing a slot-comparison
heuristic now, with no governed basis for the multiplicity/temporal
policy it would require, would be exactly the kind of unfounded,
ungrounded heuristic this session's own discipline (and the Epistemic
Ingestion Constitution's "never increase epistemic strength" /
Correction on entity resolution's "mai fuzzy-match -> merge automatico")
warns against -- so it is not attempted here. `ReconciliationOutcome`
still names all six values (matching the crawler spec's own vocabulary
literally, so a future extension does not need to invent new literal
names), but `reconcile()` itself can only ever return the three it can
soundly compute; this is documented, not silently narrowed.

Because none of CONFLICTING/SUPERSEDING/CORRECTING are reachable in v1,
this module never applies the frozen tombstoning rule (STATUS=INVALIDATED
+ END_REASON=CORRECTED, SUPERSEDES/SUPERSEDED_BY) -- no outcome this
version produces ever invalidates an existing atom. That rule's real
implementation is deferred to whichever future step actually builds the
slot-comparison capability above.

**Inherited, not fixed here: SUPPORTING can fire on two OBJECT values
that are not actually the same real-world thing.** `compute_atom_fingerprint()`
(step 7) normalizes OBJECT with `_forma()` (word-order-invariant, not
OBJECT_TYPE-aware) -- that function's own docstring already documents the
risk for multi-word non-person text ("Venice Biennale" vs. "Biennale
Venice" collide). Reusing it here means `reconcile()` inherits the exact
same risk: two atoms whose OBJECT strings are literally different but
happen to `_forma()`-normalize identically will share a fingerprint and
be classified SUPPORTING ("independent corroboration of the same claim")
even though they may not, in fact, be the same claim. `GMV_CRAWLER_HANDOFF.md`
already flagged this step by name as "likely where the atom_fingerprint
trade-off needs to be resolved for real" -- it is not resolved here. A
real fix needs OBJECT_TYPE-aware normalization (order-invariant only for
identity-like types such as PERSON), which step 7 deferred and this
module also defers, deliberately, rather than silently inheriting the
risk without saying so.

No `atoms_runtime`/`candidate_atoms` persistence table exists yet (spec
§27 names them; no migration for them has been written by any step so
far). `reconcile()` therefore takes `existing_atoms` as an explicit,
caller-supplied sequence -- the same "accept from the caller what no
upstream engine yet produces automatically" pattern steps 9/10/11 already
established (`DropboxConnector`'s injected `session`,
`extract_document()`'s `source_hash`, `extract_candidates()`'s
`evidence_ids`).
"""
from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_atom_validator import AtomCandidate, compute_atom_fingerprint  # noqa: E402 -- reused, not reimplemented

ReconciliationOutcome = Literal[
    "NEW", "IDENTICAL", "SUPPORTING", "CONFLICTING", "SUPERSEDING", "CORRECTING"
]

# The subset reconcile() can actually produce in v1 -- see module docstring
# for why CONFLICTING/SUPERSEDING/CORRECTING are not reachable yet.
REACHABLE_OUTCOMES = frozenset({"NEW", "IDENTICAL", "SUPPORTING"})


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Outcome of reconciling one `AtomCandidate` against whatever atoms
    already exist for the same subject. `matched_atoms` is empty only for
    NEW; for IDENTICAL it holds exactly the one atom that makes `candidate`
    redundant (same fingerprint, same SOURCE); for SUPPORTING it holds
    every existing atom sharing the candidate's fingerprint from a
    different SOURCE (independent corroboration, not a single arbitrarily
    -picked match)."""

    outcome: ReconciliationOutcome
    candidate: AtomCandidate
    matched_atoms: tuple[AtomCandidate, ...]

    def __post_init__(self) -> None:
        if self.outcome not in REACHABLE_OUTCOMES:
            raise ValueError(
                f"outcome must be one of {sorted(REACHABLE_OUTCOMES)} "
                f"(this module's v1 does not yet compute {sorted(set(ReconciliationOutcome.__args__) - REACHABLE_OUTCOMES)}), "
                f"got {self.outcome!r}"
            )
        if self.outcome == "NEW" and self.matched_atoms:
            raise ValueError("NEW must not carry matched_atoms")
        if self.outcome != "NEW" and not self.matched_atoms:
            raise ValueError(f"{self.outcome} must carry at least one matched atom")
        if self.outcome == "IDENTICAL" and len(self.matched_atoms) != 1:
            raise ValueError("IDENTICAL must carry exactly one matched atom")


def reconcile(
    candidate: AtomCandidate, existing_atoms: Sequence[AtomCandidate]
) -> ReconciliationResult:
    """Classify `candidate` against `existing_atoms` using
    `compute_atom_fingerprint()` (step 7, reused) as the identity key --
    same SUBJECT/PREDICATE/OBJECT (normalized), regardless of SOURCE or
    any temporal/lifecycle field, exactly matching that function's own
    documented purpose ("external deduplication key").

    No match -> NEW. A match from the *same* SOURCE -> IDENTICAL (the
    identical evidence produced this claim again, e.g. a re-scan; the
    candidate is redundant, not a second independent assertion). Matches
    from a *different* SOURCE (and no same-SOURCE match) -> SUPPORTING
    (independent corroboration of the same claim; both the candidate and
    every match remain valid, none is superseded -- ATOM's own `SOURCE`
    field is singular, so this is how multiple sources for one fact
    coexist, not by merging into one atom).

    Does not filter `existing_atoms` by STATUS -- whether an already-
    INVALIDATED atom should still count as a match (and if so, whether
    that changes IDENTICAL/SUPPORTING to something else entirely) is
    exactly the kind of judgment call left to CONFLICTING/SUPERSEDING/
    CORRECTING's future implementation, not decided by omission here. A
    caller who wants only active atoms considered must filter
    `existing_atoms` before calling.
    """
    fingerprint = compute_atom_fingerprint(candidate)
    matches = tuple(a for a in existing_atoms if compute_atom_fingerprint(a) == fingerprint)
    if not matches:
        return ReconciliationResult("NEW", candidate, ())
    same_source = tuple(a for a in matches if a.source == candidate.source)
    if same_source:
        return ReconciliationResult("IDENTICAL", candidate, same_source[:1])
    return ReconciliationResult("SUPPORTING", candidate, matches)
