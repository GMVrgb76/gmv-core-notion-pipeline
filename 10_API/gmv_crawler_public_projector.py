#!/usr/bin/env python3
"""GMV Crawler — PUBLIC projector (crawler preplan step 15 / spec v0.2 §33).

Computes what `gmv_monad_materializer.MonadDocument.public_text` (step 8)
should actually contain. Step 8's own module docstring is explicit that
`materialize_monad()` takes `public_text` as a caller-supplied string and
writes it verbatim -- it does not compute or validate PUBLIC content. This
module is that computation: `AtomCandidate` sequence (+ optional SOURCES
manifest) -> the PUBLIC section text, never the other way around (this
module never writes a Monad file itself, and does not import
`materialize_monad`/`render_monad_markdown`/`atomic_write_text`).

Grounding, read in full before writing this module:

- GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §14 (Notion id 3b95a429-a028-8116-a236-
  d8867862d077, re-fetched this session, FORMAL FREEZE 11 August 2026)
  states PUBLIC must exclude: INTERNAL facts; unattributed UNVERIFIED
  claims; draft contracts and private economic data; inferences from
  blocked sources; scheduled events presented as occurred; historical
  states presented as current. It also requires every PUBLIC sentence to
  be traceable to atom(s)/source(s) compatible with publication.
- GMV Crawler spec v0.2 §15-20 (Notion id 3d95a429-a028-8111-bb14-
  e5811a4d3f9c, re-fetched this session) confirms the same rule
  operationally: "PUBLIC come proiezione editoriale generata solo da
  atomi compatibili con regole esplicite (STATUS=VALID + VISIBILITY
  pubblicabile), non scritta liberamente dal modello". This grounds two
  of this module's mechanical gates directly: only STATUS=VALID atoms
  are eligible at all, and VISIBILITY must be the publishable value.

Of §14's six exclusion rules, four are mechanically enforced here, two are
honestly not (see "What this module does NOT enforce" below) -- the same
enforce-what-is-checkable / disclose-what-is-not discipline
`gmv_atom_validator.UNENFORCED_RULE_IDS` already established for the
Epistemic Ingestion Rules:

1. **"fatti INTERNAL" / "claim UNVERIFIED non attribuite"**: enforced
   together by requiring STATUS=VALID (reusing
   `gmv_crawler_derived_views.derive_current_state()`'s own VALID-only
   filter, imported, not reimplemented -- see below) and
   VISIBILITY=="PUBLIC". No UNVERIFIED/DISPUTED/SUPERSEDED/INVALIDATED
   atom can reach PUBLIC at all, which trivially satisfies "no
   unattributed UNVERIFIED claims" (there are no UNVERIFIED claims of any
   kind, attributed or not). **VISIBILITY has no governed vocabulary
   anywhere in this repository** -- confirmed by grep: no
   `GMV_ONTOLOGY_REGISTRY_v0.1.json` entry, no closed-set check in
   `gmv_atom_validator.py`, every real test fixture across this branch
   (`tests/test_gmv_atom_validator.py`, `tests/test_gmv_crawler_
   reconciliation.py`, `tests/test_gmv_crawler_fulltext_index.py`,
   `tests/test_gmv_crawler_derived_views.py`,
   `tests/test_gmv_monad_materializer.py`) uses the literal string
   `"PUBLIC"` as its default value, and nothing else. This module treats
   `PUBLISHABLE_VISIBILITY = "PUBLIC"` as the one publishable value --
   the most defensible reading of "VISIBILITY pubblicabile" available
   given the existing precedent, but a deliberate decision of this
   module, not a transcription of a governed enum that does not exist
   yet. If a future step introduces a real closed VISIBILITY vocabulary
   (the same way PREDICATE_CLASS has one), this constant is the one place
   to update.
2. **"historical states presented as current"**: STATUS=VALID already
   excludes SUPERSEDED/INVALIDATED atoms outright. The subtler case is a
   slot with *multiple* competing VALID atoms -- `derive_current_state()`
   (step 14) already resolves this as `AMBIGUOUS` rather than picking one
   silently. **This module's own decision, made deliberately (not
   inherited from step 14, which left PUBLIC behavior on AMBIGUOUS
   explicitly undefined): AMBIGUOUS slots are excluded from PUBLIC
   entirely.** Publishing either competing atom as if it were the
   settled fact would itself be presenting an unresolved, contested state
   as current -- exactly what this exclusion rule forbids, one level
   removed. This inherits step 14's own disclosed limitation: a RELATION
   predicate that can legitimately hold several simultaneous true values
   (e.g. an artist `participated_in` several exhibitions) collides into
   one slot by SUBJECT+PREDICATE alone and is flagged AMBIGUOUS even
   though nothing is actually contested -- `derive_current_state()`'s own
   docstring already names this as an open, ungoverned policy question.
   This module does not fix it; it means some genuinely uncontested
   multi-valued RELATION facts are under-published in v1, a known,
   accepted trade-off, not a silent gap.
3. **"inferenze da fonti bloccate"**: when a `SourceManifestEntry`
   manifest is supplied, any atom whose `SOURCE` resolves to a manifest
   row with `extraction_status` other than `"SUCCESS"` is excluded.
   **Correction, made during this module's own adversarial review before
   commit:** an earlier draft of this gate used a standalone literal
   `BLOCKED_EXTRACTION_STATUS = "BLOCKED"`, claiming it matched
   `gmv_evidence_pipeline.py:538`'s `"status": "BLOCKED"` -- that claim
   was checked and found false: line 538 writes the whole-run manifest
   `status` field for the SEMANTIC (LLM entity/claim extraction) stage,
   an unrelated field on an unrelated pipeline stage, not a per-source
   `extraction_status`. The real, closed, already-committed per-source
   vocabulary this crawler subsystem actually produces is
   `gmv_crawler_extractor.STATUS_VALUES` (step 10: `SUCCESS`,
   `OCR_REQUIRED`, `UNSUPPORTED_FORMAT`, `EXTRACTION_FAILED`,
   `EXTRACTION_ABORTED_STALE_HASH`) -- it contains no `"BLOCKED"` value
   at all, so the original gate was dead code against any real data this
   pipeline can produce. Fixed: `BLOCKED_EXTRACTION_STATUSES` is now
   `STATUS_VALUES - {"SUCCESS"}`, computed from the real imported set
   (so it cannot silently drift if a future status value is added
   upstream), not a hardcoded duplicate. Every non-`SUCCESS` status in
   that set means the source's content was never reliably obtained
   (unsupported format, outright failure, aborted on a stale hash, or
   still pending OCR) -- none of those states should let an atom's
   claimed provenance stand as PUBLIC-safe. Note this is a distinct
   concept, at a distinct layer, from `crawler_source_registry.state`
   (migration 009, step 3), whose own closed vocabulary is `NEW`/
   `UNCHANGED`/`MODIFIED`/`MOVED`/`DELETED`/`FAILED` -- crawler spec v0.2
   §24's prose use of the word "BLOCKED" for an unreadable source refers
   to that DETECT-CHANGE-stage concept (whose actually-implemented
   literal is `FAILED`, not `BLOCKED`), not to this module's
   content-extraction-stage gate; the two must not be conflated. No
   production code constructs a real `SourceManifestEntry` yet (verified
   by repo-wide grep), so this gate has no live caller today -- it is
   grounded against the one real extraction-status vocabulary this
   subsystem has, ready for whichever future step wires a real SOURCES
   manifest through. When no manifest is supplied (the default,
   `sources=()`), this gate is a no-op: absence of SOURCES information is
   not evidence a source is blocked (the same EIC-02 "absence of evidence
   is not contradiction" discipline already governing every other stage
   of this pipeline), so nothing is excluded on that basis alone.

## What this module does NOT enforce (disclosed, not silently dropped)

- **"bozze contrattuali e dati economici privati"**: the frozen 18-field
  ATOM schema (GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §2.3) has no
  classification/sensitivity field of any kind, and neither does the
  SOURCES manifest this module can see (`SourceManifestEntry`, step 8).
  There is no structural signal to check. This is not an oversight: the
  crawler spec v0.2's own "Punti di attenzione aperti" #2 names exactly
  this gap ("Classificazione dei dati riservati già nell'Evidence Layer,
  non solo al gate PUBLIC... va deciso se l'Evidence store necessita di
  un proprio livello di classificazione interno") as an open, analytical
  point requiring a future decision, not something already resolved
  elsewhere in this repository. Inventing a heuristic here (e.g.
  pattern-matching predicate/object text for "contract"/"economic"
  wording) would be exactly the kind of ungrounded guess this session's
  working method warns against. A caller assembling atoms for this
  projector is responsible for not constructing PUBLIC-visibility,
  VALID-status atoms out of private economic/contractual evidence in the
  first place -- this module cannot catch that after the fact.
- **"scheduled events presented as occurred"**: this is the identical
  class of gap `gmv_atom_validator.UNENFORCED_RULE_IDS` already declines
  to check for EIC-05/EIC-06 -- whether an occurrence-semantic predicate
  (e.g. `exhibited_at`, per `GMV_ONTOLOGY_REGISTRY_v0.1.json`'s own notes
  on that predicate) was correctly promoted from a scheduled/planned
  event is an executor-discipline judgment made at candidate-extraction
  time; a finished ATOM with STATUS=VALID looks structurally identical
  whether that promotion was correct or not. No field in the frozen ATOM
  schema distinguishes them. This module inherits that same limitation
  rather than re-litigating it.

## Reuse, verified by import line in this file

`AtomCandidate` (`gmv_atom_validator`), `CurrentStateEntry` and
`derive_current_state()` (`gmv_crawler_derived_views`, step 14) are
imported below, not reimplemented -- `derive_current_state()` already
does the STATUS=VALID filtering, `atom_id` dedup, and predicate-alias-
aware (via the ontology registry) slot resolution this module needs; this
module only adds the VISIBILITY/blocked-source gates and the AMBIGUOUS-
excludes-from-PUBLIC decision on top. `SourceManifestEntry`
(`gmv_monad_materializer`, step 8) is imported only for its type shape
(to look up `extraction_status` per `source_id`) -- this module never
calls `materialize_monad()`/`render_monad_markdown()`/`atomic_write_text`
from that module. `STATUS_VALUES` (`gmv_crawler_extractor`, step 10) is
imported to compute `BLOCKED_EXTRACTION_STATUSES` from the real,
already-grounded closed set, not a second hardcoded assumption of what
that set is.

## Rendering is deliberately not natural-language generation

`render_public_text()` renders one deterministic line per eligible atom
(`- {subject} — {predicate} — {object}`), sorted by `atom_id` for the
same determinism reason `render_monad_markdown()` (step 8) sorts before
rendering ("stesso stato epistemico in ingresso -> stesso file logico in
uscita", §2). `predicate` is rendered as its raw, verbatim token (e.g.
`participated_in`), not translated into prose -- no natural-language
generation component exists anywhere in this codebase for this purpose,
and inventing one here would be exactly the "premature engine" this
session's working method warns against. This is a literal fact
enumeration, the same rendering register `_atom_row()`/`_table()` (step
8) already use for the ATOMS/SOURCES sections, applied to the PUBLIC
section instead of a human-authored editorial paragraph. A future step
turning this into real human-readable prose is a presentation
enhancement on top of this module's selection logic, not a change to
what counts as PUBLIC-eligible.
"""
from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_atom_validator import AtomCandidate  # noqa: E402 -- reused, not reimplemented
from gmv_crawler_derived_views import (  # noqa: E402 -- reused, not reimplemented
    CurrentStateEntry,
    derive_current_state,
)
from gmv_crawler_extractor import STATUS_VALUES  # noqa: E402 -- reused, not reimplemented
from gmv_monad_materializer import SourceManifestEntry  # noqa: E402 -- reused, not reimplemented

PUBLISHABLE_VISIBILITY = "PUBLIC"

# Every real per-source extraction_status this crawler subsystem can
# produce (gmv_crawler_extractor.STATUS_VALUES, step 10) except SUCCESS --
# computed from the real imported set, not a hardcoded duplicate. See
# module docstring point 3 for why "BLOCKED" (an earlier draft's literal)
# was wrong: no real code in this repository ever writes that value to a
# per-source extraction_status field.
BLOCKED_EXTRACTION_STATUSES = frozenset(STATUS_VALUES - {"SUCCESS"})


def _blocked_source_ids(sources: Sequence[SourceManifestEntry]) -> frozenset[str]:
    return frozenset(
        source.source_id for source in sources
        if source.extraction_status in BLOCKED_EXTRACTION_STATUSES
    )


def select_public_atoms(
    atoms: Sequence[AtomCandidate],
    sources: Sequence[SourceManifestEntry] = (),
    *,
    registry: dict | None = None,
    current_state: Sequence[CurrentStateEntry] | None = None,
) -> tuple[AtomCandidate, ...]:
    """The atoms PUBLIC is allowed to be built from -- every exclusion
    rule this module mechanically enforces, applied in one place. See
    the module docstring for what each gate is and why.

    `current_state` lets a caller who already computed
    `derive_current_state()` (e.g. via `gmv_crawler_derived_views.
    derive_views()`) reuse that result instead of recomputing it -- the
    same injectable-but-defaulted pattern `derive_current_state()` itself
    uses for `registry`. When omitted, it is computed here from `atoms`
    and `registry`. When supplied, `atoms` is not otherwise consulted --
    the same trust-the-caller contract `derive_current_state()`'s own
    `registry` parameter already has (a stale/mismatched value supplied
    on purpose is not detected or corrected here).
    """
    if current_state is None:
        current_state = derive_current_state(atoms, registry)

    blocked = _blocked_source_ids(sources)

    eligible = [
        entry.atom for entry in current_state
        if entry.resolution == "RESOLVED"
        and entry.atom.visibility == PUBLISHABLE_VISIBILITY
        and entry.atom.source not in blocked
    ]
    return tuple(sorted(eligible, key=lambda a: a.atom_id))


def _line(value: object) -> str:
    """Collapse embedded newlines so one atom always renders as exactly
    one line -- the same reason `gmv_monad_materializer._cell()` does the
    same thing for Markdown table cells, applied here to a bullet list
    instead of a table."""
    return str(value).replace("\n", " ").replace("\r", " ")


def render_public_text(atoms: Sequence[AtomCandidate]) -> str:
    """Pure function: an already-PUBLIC-eligible atom sequence -> the
    PUBLIC section text. Does not itself decide eligibility -- callers
    almost always want `project_public()` below, which composes this
    with `select_public_atoms()`. Kept separate so a caller can render
    a different (e.g. already-filtered-elsewhere) atom set without
    going through selection again. Empty input renders to an empty
    string -- no placeholder sentence is invented for the no-public-
    knowledge-yet case; that is a presentation decision for whatever
    future step turns this into human-edited prose, not this module's
    to guess at."""
    lines = [
        f"- {_line(atom.subject)} — {_line(atom.predicate)} — {_line(atom.object)}"
        for atom in sorted(atoms, key=lambda a: a.atom_id)
    ]
    return "\n".join(lines)


def project_public(
    atoms: Sequence[AtomCandidate],
    sources: Sequence[SourceManifestEntry] = (),
    *,
    registry: dict | None = None,
) -> str:
    """One-call convenience: atoms (+ optional SOURCES manifest) -> the
    exact string a caller should pass as
    `gmv_monad_materializer.MonadDocument.public_text`."""
    return render_public_text(select_public_atoms(atoms, sources, registry=registry))
