#!/usr/bin/env python3
"""GMV Crawler — Projection Adapter contract (crawler preplan step 4-bis / step 5).

Symmetric to gmv_crawler_contracts.SourceConnector, but outbound: receives
already-materialized Monads/ATOMs and translates them into a specific
consumption target's format. The crawler engine knows only this contract,
never a specific target.

No target-specific vocabulary (Notion table names, property names, the
six ARTISTI/MOSTRE/PERSONE/ISTITUZIONI/OPERE/SPONSOR tables) appears in
this file. That logic belongs exclusively inside a concrete adapter.

This is the contract only -- §33 of the crawler spec places it explicitly
BEFORE generalizing gmv_notion_multi_candidate.py behind it (step 16, much
later), precisely so the NOTION_PATCH.json format never gets confused with
this abstract interface. No existing module is modified or wrapped here.

Grounding, verified against the real code by executing it, not just
reading it (an earlier draft of this file made three vocabulary "reuse"
claims that turned out to be false on inspection -- corrected below with
what is actually true):

- TargetPayload mirrors the shape build_entity_patch() in
  10_API/gmv_notion_multi_candidate.py already produces (entity_type,
  operation, a list of per-field operations, a gate, optional body text
  with its own gate) -- genericized, with Notion property names and
  table names stripped out.

- OperationAction ("ADD"/"UPDATE"/"CONFLICT") IS reused, but not the set
  an earlier draft claimed, and not from one file: gmv_notion_multi_
  candidate.py::build_entity_patch (lines 201/210/224/230) emits only
  {"ADD", "CONFLICT"} -- confirmed by running it on a synthetic claim
  set, and "UPDATE" never appears there (grep confirms zero occurrences
  of that literal in that file). gmv_notion_candidate.py::
  build_incremental_patch is the source of "UPDATE" (its own
  action = "ADD"/"KEEP"/"UPDATE" branch), confirmed by running it on a
  synthetic claim set with an existing, differing property value. The
  union across both real modules is exactly {"ADD", "UPDATE",
  "CONFLICT"}. "CREATE" is NOT a per-field action anywhere in
  real code -- it only exists as TargetPayload.operation's *entity-level*
  value (create-vs-update the whole page, a different concept). "KEEP" is
  never an explicit action either: real code represents "field already
  matches, nothing to do" by omitting an operations entry entirely, not
  by appending one -- so this contract does the same, deliberately, not
  by oversight. A fourth value, "RELATE", is checked for in
  gmv_notion_multi_candidate.py:314 but never produced by any code path
  (pre-existing dead branch in that file, not introduced or fixed here) --
  excluded from this vocabulary because nothing real ever emits it.

- Gate (AUTO_ACCEPT/REVIEW_REQUIRED/BLOCKED) is NOT reused from live code
  -- an earlier draft claimed it was "reused from crawler spec §29" and
  left the impression it matched something already running. It does not.
  The real, live entity-level gate vocabulary, computed by gate() in
  10_API/gmv_evidence_pipeline.py and consumed by
  gmv_notion_publish.py::publish_bundle() (which literally checks the
  string "READY_FOR_NOTION"), is {"READY_FOR_NOTION", "REVIEW_REQUIRED",
  "INSUFFICIENT_EVIDENCE"} -- Notion-flavored wording that has no place in
  a target-agnostic contract per this file's own constraint (no
  target-specific vocabulary here). The real body-level gate is a
  *separate*, narrower, 2-value vocabulary,
  {"BODY_PATCH_READY", "BODY_REVIEW_REQUIRED"}
  (gmv_notion_candidate.py's attach_body_adapter) -- not the same concept
  as the entity-level gate and not interchangeable with it. Gate below is
  therefore a genuinely new, crawler-level vocabulary, named after the
  human-review states crawler spec §29 describes in prose. A concrete
  Notion adapter's project()/publish() will have to translate explicitly
  in both directions (entity gate: 3 values <-> 3 values, different
  names; body gate: 3 values <-> 2 values) -- that translation does not
  exist anywhere yet and is not performed by this contract.

- PublishOutcome's six values map to gmv_notion_publish.py::
  publish_bundle()'s six real `return` statements (0 published,
  1 cancelled, 2 auth error, 3 already published, 4 gate not ready,
  5 stale-or-duplicate -- two distinct branches, duplicate title found
  and staleness check failed, share return code 5), read from that
  function's actual source. This is not a claim of totality: the function
  can also raise uncaught exceptions outside these six paths (e.g.
  FileNotFoundError/ValueError from load_bundle(), a KeyError if
  bundle.entity_type isn't in the config, real HTTP errors from Notion),
  which a concrete adapter's publish() must still handle -- this contract
  only names the six *intentional* return paths, not every way the
  underlying call can fail.

- Relation writes: 10_API/gmv_notion_multi_candidate.py::build_entity_patch
  always resolves a relation-type claim to CONFLICT -- "No relation-writer
  exists anywhere in this codebase today" (verbatim comment in that
  function). This contract does not invent a relation-writing mechanism;
  FieldOperation.action == "CONFLICT" is how a concrete adapter must keep
  representing this today, not a gap this contract silently papers over.

- reconcile_correction() has no existing implementation to ground it in
  anywhere in this repository -- §30 describes the flow (target
  correction -> proposed semantic patch -> provenance/authority check ->
  Monad update) but no code builds it yet. ProposedPatch below follows
  the spec's description only; treat its shape as more tentative than
  TargetPayload/OperationAction/PublishOutcome, which are grounded in
  real, executed code, not just read.

Open gap, flagged rather than resolved here (out of scope for a contract
definition): entity_type strings in the real Notion pipeline are lowercase
Italian ("artista", "mostra", "istituzione", from page_templates.json's
`entita` keys), while 00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json's
entity_classes use uppercase English class_ids (ARTIST, EXHIBITION,
INSTITUTION). No mapping between the two exists yet. A concrete adapter
implementing supports()/project() will have to bridge this; this contract
does not decide the mapping.

monad/target_change parameters below are typed loosely (object) rather
than with a concrete Monad/Atom class: no such Python type exists yet in
this repository (Entity Registry, Atom builder and Monad materializer are
still-unbuilt steps 6-8). Tightening this typing is future work, not
guessed at here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

# Reused, verified by executing build_entity_patch() on a synthetic
# claim set: the real per-field vocabulary gmv_notion_candidate.py and
# gmv_notion_multi_candidate.py emit is exactly these three. "CREATE"
# and "KEEP" are deliberately excluded -- see module docstring.
OperationAction = Literal["ADD", "UPDATE", "CONFLICT"]

# NOT reused from live code -- a new crawler-level vocabulary named after
# crawler spec §29's prose, not a mirror of gate()'s real
# READY_FOR_NOTION/REVIEW_REQUIRED/INSUFFICIENT_EVIDENCE (entity-level) or
# attach_body_adapter's BODY_PATCH_READY/BODY_REVIEW_REQUIRED (body-level,
# a different 2-value vocabulary). See module docstring.
Gate = Literal["AUTO_ACCEPT", "REVIEW_REQUIRED", "BLOCKED"]

# One-to-one mapping of gmv_notion_publish.py::publish_bundle()'s six real
# return codes (0-5), Notion-specific wording stripped.
PublishOutcome = Literal[
    "PUBLISHED",
    "CANCELLED",
    "ALREADY_PUBLISHED",
    "BLOCKED_GATE_NOT_READY",
    "BLOCKED_STALE_OR_DUPLICATE",
    "FAILED_AUTHENTICATION",
]


@dataclass(frozen=True, slots=True)
class FieldOperation:
    """One proposed change to one generic field/relation of the target
    entity. `field` is the crawler-side generic name (an ontology
    predicate or attribute id), never a target's own property/column
    name -- that translation is the concrete adapter's job, not this
    contract's."""

    action: OperationAction
    field: str
    value: object
    claim_id: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.field:
            raise ValueError("field must not be empty")
        if self.action == "CONFLICT" and not self.reason:
            raise ValueError("a CONFLICT operation must carry a reason")


@dataclass(frozen=True, slots=True)
class TargetPayload:
    """What ProjectionAdapter.project() returns: a target-agnostic
    envelope, not yet translated into any specific target's wire format.
    entity_type is the crawler's own vocabulary (see the open gap noted
    in this module's docstring), never a target-specific table name.

    `name` added during step 16 (the first concrete adapter this contract
    was ever built against), not present in the original step-5 draft --
    a real gap found empirically, not theorized: `write_entity_bundle()`/
    `publish_bundle()`/the audit record all need the entity's own
    name/title (for the bundle folder, `entity.json`, and the Notion page
    title itself), and nothing else on this dataclass carries it. Added
    as a required field, not optional-with-a-default: a payload naming no
    entity cannot be meaningfully published to anything. This changed one
    existing call site (`tests/test_gmv_projection_adapter_contracts.py`'s
    `_payload()` helper), not a source-breaking change to any real caller
    (none existed before step 16).
    """

    entity_type: str
    name: str
    operation: Literal["CREATE", "UPDATE"] | None
    operations: tuple[FieldOperation, ...]
    gate: Gate
    body_text: str | None = None
    body_gate: Gate = "REVIEW_REQUIRED"
    existing_target_reference: str | None = None
    """The target's own identifier for an already-existing entity (a
    Notion page id) when `operation == "UPDATE"`, `None` for `CREATE` --
    same naming convention as `PublishResult.target_reference`, added
    alongside `name` for the same reason (found missing while implementing
    `publish()` in step 16: the old dict shape's `existing_notion_id`
    has no home on this dataclass otherwise, and `publish_bundle()`'s own
    duplicate-detection branch keys off exactly this being present or
    absent)."""
    keep_properties: dict[str, object] = field(default_factory=dict)
    """Property values on the target that this payload leaves unchanged
    (not part of `operations`, since nothing is being proposed for them)
    but that must still match the target's live state before publishing
    -- the input `notion_publish.py::check_staleness()` needs to detect a
    page edited on Notion since this payload was built. Missing from the
    original step-5 draft; found the expensive way in step 16 -- an
    earlier draft of the concrete Notion adapter omitted this, which
    silently made `check_staleness()` a permanent no-op (it iterates
    `patch.get("keep", {}).get("properties", {})`; an absent/empty dict
    means zero diffs are ever possible, `stale` is always `False`) for
    every bundle that adapter produced -- caught by adversarial review
    reproducing it empirically against a fake client returning different
    live values, not by reading the code. Empty by default (a `CREATE`
    payload has no existing page to go stale against)."""

    def __post_init__(self) -> None:
        if not self.entity_type:
            raise ValueError("entity_type must not be empty")
        if not self.name:
            raise ValueError("name must not be empty")
        # This is a NEW invariant this contract introduces, not a mirror
        # of today's real behavior: gate(), the live entity-level gate
        # computation in gmv_evidence_pipeline.py, can currently produce
        # READY_FOR_NOTION alongside an unresolved CONFLICT operation on
        # any non-required field/relation (verified by running
        # build_entity_patch() -- e.g. every relation is always CONFLICT,
        # "no relation-writer exists," yet the entity gate does not look
        # at `operations` at all and stays unaffected). This contract
        # deliberately tightens that: an adapter satisfying
        # ProjectionAdapter must not report AUTO_ACCEPT while any
        # operation is still CONFLICT, even though the pre-existing
        # Notion pipeline this contract is modeled on does not yet
        # enforce that itself.
        if any(op.action == "CONFLICT" for op in self.operations) and self.gate == "AUTO_ACCEPT":
            raise ValueError(
                "gate cannot be AUTO_ACCEPT while any operation is CONFLICT -- "
                "an unresolved conflict must never be silently auto-accepted"
            )


@dataclass(frozen=True, slots=True)
class PublishResult:
    """What ProjectionAdapter.publish() returns. target_reference is
    opaque to the crawler (a target's own identifier for what got
    written, e.g. a page id) -- the crawler stores it for provenance, it
    never interprets it."""

    outcome: PublishOutcome
    target_reference: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.outcome == "PUBLISHED" and not self.target_reference:
            raise ValueError("a PUBLISHED outcome must carry a target_reference")


@dataclass(frozen=True, slots=True)
class ProposedPatch:
    """Output of ProjectionAdapter.reconcile_correction(): a human
    correction observed on the target becomes a proposed patch back to
    the Monad, gated by a provenance/authority check before it can be
    applied -- never an immediate, silent canonical overwrite (crawler
    spec §30). No existing code implements this flow yet; this shape
    follows the spec's description, not a working precedent."""

    entity_type: str
    field: str
    observed_target_value: object
    proposed_monad_value: object
    authority_check_passed: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.entity_type:
            raise ValueError("entity_type must not be empty")
        if not self.field:
            raise ValueError("field must not be empty")
        if not self.authority_check_passed and not self.reason:
            raise ValueError("a failed authority check must carry a reason")


@runtime_checkable
class ProjectionAdapter(Protocol):
    """Structural contract every projection target must satisfy. The
    crawler engine depends only on this Protocol -- it can hold several
    active adapters at once, each toward a different target, without
    engine changes (crawler spec §4-bis).

    @runtime_checkable's isinstance() checks only that these four method
    names exist on a class, not their parameter/return signatures --
    same caveat as gmv_crawler_contracts.SourceConnector.
    """

    def supports(self, entity_type: str) -> bool:
        """Declare whether this adapter can project the given entity_type.
        Lets the crawler route work to the right adapter(s) without the
        engine knowing what any adapter actually does."""
        ...

    def project(self, monad: object) -> TargetPayload:
        """Translate an already-materialized Monad/ATOM into this
        target's payload shape. Must not invent facts not present in the
        Monad -- this is translation, not inference."""
        ...

    def publish(self, payload: TargetPayload) -> PublishResult:
        """Attempt to write payload to the target. A concrete adapter
        must be able to return every PublishOutcome value, not just
        PUBLISHED -- a target-side gate/staleness/duplicate/auth check
        blocking the write is an expected, correctly-handled outcome,
        not an error path to collapse into a bare failure."""
        ...

    def reconcile_correction(self, target_change: object) -> ProposedPatch:
        """A human correction made directly on the target flows back
        through here as a proposed patch to the Monad, gated by
        provenance/authority check -- never applied silently."""
        ...


@dataclass(frozen=True, slots=True)
class MultiAdapterRegistry:
    """Optional convenience for holding several active ProjectionAdapter
    instances and routing by entity_type via supports() -- not part of
    the ProjectionAdapter contract itself, just a thin helper a crawler
    engine may or may not use."""

    adapters: tuple[ProjectionAdapter, ...] = field(default_factory=tuple)

    def adapters_for(self, entity_type: str) -> tuple[ProjectionAdapter, ...]:
        return tuple(adapter for adapter in self.adapters if adapter.supports(entity_type))
