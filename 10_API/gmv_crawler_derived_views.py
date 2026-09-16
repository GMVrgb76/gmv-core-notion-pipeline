#!/usr/bin/env python3
"""GMV Crawler — Derived View Spec (crawler preplan step 14 /
GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §11-12, crawler spec v0.2 §15-20's own
"DERIVED_VIEW_SPEC ... fuori dallo schema canonico" note).

GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §11 names six non-canonical, rebuildable
structures -- STATE, TIMELINE, RELATIONS/GRAPH, CLAIMS, LEDGER, plus
OBSIDIAN VIEWS/consumer projections generally -- "devono essere
ricostruibili da IDENTITY + ATOMS + SOURCES e dalle regole di
derivazione." §12 says those reconstruction rules "devono essere
formalizzate in un componente system-level separato: DERIVED_VIEW_SPEC."
This module is that component's first real implementation: pure
functions from a list of `AtomCandidate` (step 7) to each named view, no
persistence, no engine. One exception, added during the same session
that first wrote this module (see `derive_current_state()` below): by
default it reads `GMV_ONTOLOGY_REGISTRY_v0.1.json` from disk once per
call (to resolve predicate aliases), unless a caller passes an
already-loaded `registry` -- the same injectable-but-defaulted pattern
`gmv_atom_validator.validate_atom()` already uses, not a new one.

**PUBLIC is deliberately excluded here even though the crawler spec's
own §15-20 summary lists it alongside the other five views.**
`gmv_monad_materializer.py` (step 8) already grounded this: §33 names
"PUBLIC projector" as its own step 15, generating PUBLIC text from
ATOMS per `GMV_KNOWLEDGE_MONAD_SPEC_v1.0` §14's exclusion rules (no
INTERNAL facts, no unattributed UNVERIFIED claims, etc.) is that step's
job, not this one's -- building it here would duplicate a step already
carved out, not close a gap.

**The spec text does not give field-level shapes for these five views**
(unlike, e.g., the 18-field ATOM schema or the SOURCES manifest) --
only names and one line of intent each. Every view's shape below is
this module's own grounded reading, not a literal transcription of a
spec table that does not exist:

- `derive_timeline()`: atoms sorted by `VALID_FROM` (proposition
  validity time, GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §6 -- "the temporal
  fields describe the validity of the proposition, not the object's own
  dates"). Atoms with `VALID_FROM = None` (unknown, a legitimate state
  per §6's own worked example) sort last, not dropped -- an unknown
  validity time is a real, recordable fact about the atom, not an
  absence to hide.
- `derive_ledger()`: atoms sorted by `INGESTED_AT` -- when the crawler
  learned the proposition, as distinct from `derive_timeline()`'s
  real-world validity ordering. The frozen 18-field schema has no
  per-status-transition timestamp (no `STATUS_CHANGED_AT`/
  `INVALIDATED_AT` field), so this is a single ingestion-order view, not
  a multi-event audit log of every lifecycle transition -- inventing a
  timestamp the frozen schema does not have would be exactly the kind of
  schema-shape violation `GMV_KNOWLEDGE_MONAD_SPEC_v1.0` §18 forbids
  without a documented failure/versioning process.
- `derive_relations()`: atoms whose `PREDICATE_CLASS == "RELATION"` --
  the literal is still a hardcoded string (there is no way to filter
  without one), but the module now imports `FROZEN_PREDICATE_CLASSES`
  and fails loudly at import time if `"RELATION"` is ever removed from
  that frozen set, rather than the filter silently degrading to
  matching nothing. An earlier draft's docstring claimed the literal was
  itself "imported" -- false (`FROZEN_PREDICATE_CLASSES` was not even
  imported into this module, only into its test file); caught by
  adversarial review via `grep`, fixed by actually importing and
  checking it, not just correcting the prose. A flat filtered list, not
  an assembled graph (nodes/adjacency/cycles) -- "/GRAPH" in the spec's
  own naming is a possible future presentation of this same data, not
  something this step builds; no real consumer exists yet to ground
  what graph structure it would actually need.
- `derive_claims()`: the spec gives no criterion distinguishing "CLAIMS"
  from the full atom set (unlike RELATIONS, which at least has
  PREDICATE_CLASS to filter on). The most defensible reading, absent
  any distinguishing rule, is that CLAIMS *is* the atom set -- every
  atom is already a claim in the frozen spec's own vocabulary (§8:
  "un atom deve rappresentare una proposizione"). This function exists
  mainly so a caller has one name per named view, not because it
  performs a real transformation -- documented honestly, not disguised
  as a filter that does not exist.
- `derive_current_state()`: the one view genuinely blocked by the same
  gap step 12 (Reconciliation engine) already documented -- CURRENT_STATE
  needs a "slot" identity (SUBJECT+PREDICATE, object-agnostic) to know
  which atoms compete for the same fact, and no governed policy exists
  for resolving multiple simultaneous VALID atoms in one slot (would
  depend on PREDICATE_CLASS: some RELATION predicates may legitimately
  allow several simultaneous values, others may not). Rather than
  inventing that policy here -- the same ungrounded-heuristic risk step
  12 already declined -- this function computes the slot grouping (reuse:
  `_forma()`, the same word-order-invariant normalization
  `compute_atom_fingerprint()` already uses, so "Federico Garibaldi" and
  "Garibaldi, Federico" group into the same slot) and returns each slot's
  resolution as either `RESOLVED` (exactly one `STATUS=VALID` atom) or
  `AMBIGUOUS` (more than one, with every competing atom surfaced in
  `candidates`, not silently narrowed to one) -- never a silent pick,
  matching the same "never auto-merge" principle entity resolution
  (step 6) and reconciliation (step 12) both already apply. Only
  `STATUS=VALID` atoms are considered "current" -- `UNVERIFIED` is
  pending, not current fact, per GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §5's own
  epistemic cautions.

**Two bugs adversarial review found and reproduced empirically in an
earlier draft of `derive_current_state()`, both fixed, not just noted:**
1. The slot key used the raw `predicate` string, not resolved through
   the ontology registry's alias table (`GMV_ONTOLOGY_REGISTRY_v0.1.json`,
   e.g. the real `source_for`/`evidences` alias pair) -- two
   governance-equivalent atoms differing only in which alias spelling
   they used landed in separate slots and were both reported `RESOLVED`
   instead of one `AMBIGUOUS`, directly falsifying the function's own
   "never a silent pick" guarantee. Fixed: the slot key now resolves
   `predicate` to its canonical `predicate_id` via
   `gmv_atom_validator._known_predicates()` (reused, not reimplemented)
   before grouping; an unregistered predicate (not in the ontology
   registry at all) falls back to grouping under its own literal string,
   since there is nothing to resolve it to.
2. No dedup by `atom_id` before grouping -- the exact same `AtomCandidate`
   object appearing twice in the input (a plausible caller bug, e.g. a
   list built by concatenating two overlapping queries) produced a false
   `AMBIGUOUS` between an atom and itself. Fixed: atoms are deduplicated
   by `atom_id` before slot grouping. Precisely what this dedup is and
   is not: `deduplicated = tuple({atom.atom_id: atom for atom in
   atoms}.values())` deduplicates by *string equality of `atom_id`* --
   not by Python object identity, not by content equality.  If two
   genuinely different `AtomCandidate`s (different `predicate`/`object`)
   were to share an `atom_id` (an upstream bug; no uniqueness guarantee
   exists before this function), the dict comprehension silently keeps
   whichever appears *last* in the caller's iteration order and drops
   the other with no signal.  That outcome is unspecified and must not
   be built on -- what to do about a real `atom_id` collision (raise? a
   third resolution state?) is a design question, not something this
   function promises.  See the pinned regression test.

**Two risks inherited, not fixed, disclosed honestly instead:**
- `STATUS=DISPUTED` atoms produce no `CURRENT_STATE` entry at all (only
  `VALID` is considered) -- indistinguishable, from this view alone, from
  a subject+predicate that was never asserted. A real contested claim
  and a claim that was simply never made look identical here. Not fixed
  in v1 -- a `DISPUTED`-aware presentation (e.g. a third resolution value)
  is deferred to whichever future step actually consumes this view for
  something a human or downstream process reads directly.
- `_forma()` on SUBJECT inherits the same word-order-collision risk
  already documented and accepted for OBJECT in `compute_atom_fingerprint()`
  (step 7) -- two genuinely different multi-word subjects (institutions,
  places, artworks) that happen to share words in a different order
  collide into the same slot. Structurally harder to bound here than for
  OBJECT: the frozen 18-field ATOM schema has an `OBJECT_TYPE` field but
  no `SUBJECT_TYPE` field, so a future type-aware fix (already deferred
  for OBJECT) has no equivalent schema hook for SUBJECT without a
  documented schema change.
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

from area35_validator import _forma  # noqa: E402 -- reused, not reimplemented
from gmv_atom_validator import (  # noqa: E402 -- reused, not reimplemented
    AtomCandidate,
    FROZEN_PREDICATE_CLASSES,
    _known_predicates,
    _load_ontology_registry,
)

if "RELATION" not in FROZEN_PREDICATE_CLASSES:
    raise RuntimeError(
        "gmv_atom_validator.FROZEN_PREDICATE_CLASSES no longer contains "
        "'RELATION' -- derive_relations()'s filter literal is stale"
    )

CurrentStateResolution = Literal["RESOLVED", "AMBIGUOUS"]


@dataclass(frozen=True, slots=True)
class CurrentStateEntry:
    """One SUBJECT+PREDICATE slot's currently-VALID value, or the
    unresolved ambiguity blocking one. `subject`/`predicate` are the
    verbatim values from `candidates[0]` after `candidates` is sorted by
    `atom_id` (display only, deterministic regardless of input order) --
    the real grouping key is `_forma(subject)` + the predicate's
    ontology-registry-resolved canonical id, not these display fields;
    two atoms with differently-worded but `_forma()`-equivalent subjects,
    or with governance-equivalent predicate aliases (e.g. `source_for`/
    `evidences`), land in the same entry."""

    subject: str
    predicate: str
    resolution: CurrentStateResolution
    atom: AtomCandidate | None
    candidates: tuple[AtomCandidate, ...]

    def __post_init__(self) -> None:
        if self.resolution == "RESOLVED":
            if self.atom is None:
                raise ValueError("RESOLVED must carry an atom")
            if len(self.candidates) != 1:
                raise ValueError("RESOLVED must carry exactly one candidate")
        else:
            if self.atom is not None:
                raise ValueError("AMBIGUOUS must not carry a resolved atom")
            if len(self.candidates) < 2:
                raise ValueError("AMBIGUOUS must carry 2 or more competing candidates")


def derive_timeline(atoms: Sequence[AtomCandidate]) -> tuple[AtomCandidate, ...]:
    dated = sorted((a for a in atoms if a.valid_from is not None), key=lambda a: a.valid_from)
    undated = [a for a in atoms if a.valid_from is None]
    return tuple(dated) + tuple(undated)


def derive_ledger(atoms: Sequence[AtomCandidate]) -> tuple[AtomCandidate, ...]:
    return tuple(sorted(atoms, key=lambda a: a.ingested_at))


def derive_relations(atoms: Sequence[AtomCandidate]) -> tuple[AtomCandidate, ...]:
    return tuple(a for a in atoms if a.predicate_class == "RELATION")


def derive_claims(atoms: Sequence[AtomCandidate]) -> tuple[AtomCandidate, ...]:
    return tuple(atoms)


def derive_current_state(
    atoms: Sequence[AtomCandidate], registry: dict | None = None
) -> tuple[CurrentStateEntry, ...]:
    """`registry` is accepted as a parameter (not always reloaded from
    disk), mirroring `gmv_atom_validator.validate_atom()`'s own pattern,
    so a caller processing many atom sets can load
    `GMV_ONTOLOGY_REGISTRY_v0.1.json` once."""
    if registry is None:
        registry = _load_ontology_registry()
    known_predicates = _known_predicates(registry)

    deduplicated = tuple({atom.atom_id: atom for atom in atoms}.values())

    slots: dict[tuple[str, str], list[AtomCandidate]] = {}
    for atom in deduplicated:
        if atom.status != "VALID":
            continue
        entry = known_predicates.get(atom.predicate)
        canonical_predicate = entry["predicate_id"] if entry is not None else atom.predicate
        key = (_forma(atom.subject), canonical_predicate)
        slots.setdefault(key, []).append(atom)

    entries = []
    for group in slots.values():
        ordered = tuple(sorted(group, key=lambda a: a.atom_id))
        if len(ordered) == 1:
            entries.append(CurrentStateEntry(
                subject=ordered[0].subject, predicate=ordered[0].predicate,
                resolution="RESOLVED", atom=ordered[0], candidates=ordered,
            ))
        else:
            entries.append(CurrentStateEntry(
                subject=ordered[0].subject, predicate=ordered[0].predicate,
                resolution="AMBIGUOUS", atom=None, candidates=ordered,
            ))
    return tuple(entries)


@dataclass(frozen=True, slots=True)
class DerivedViews:
    timeline: tuple[AtomCandidate, ...]
    ledger: tuple[AtomCandidate, ...]
    relations: tuple[AtomCandidate, ...]
    claims: tuple[AtomCandidate, ...]
    current_state: tuple[CurrentStateEntry, ...]


def derive_views(atoms: Sequence[AtomCandidate]) -> DerivedViews:
    """Compute every view this module supports in one call. PUBLIC is not
    here -- see module docstring."""
    return DerivedViews(
        timeline=derive_timeline(atoms),
        ledger=derive_ledger(atoms),
        relations=derive_relations(atoms),
        claims=derive_claims(atoms),
        current_state=derive_current_state(atoms),
    )
