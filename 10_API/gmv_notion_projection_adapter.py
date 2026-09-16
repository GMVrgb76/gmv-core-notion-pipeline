#!/usr/bin/env python3
"""GMV Crawler — Notion ProjectionAdapter (crawler preplan step 16 / spec v0.2 §33).

Generalizes `gmv_notion_multi_candidate.py` behind the `ProjectionAdapter`
contract (step 5) -- "generalizzazione, non riscrittura" (§33's own
words): `route_claim()`, `build_entity_patch()`, `build_entity_body()`,
`compare_entity()`, `gate()` are imported and called exactly as they
already exist, never reimplemented. This module's own code is entirely
translation -- crawler-shaped data in, legacy-shaped calls, legacy-shaped
results translated back out.

## The claim_id / evidence_id / ATOM_ID decision (this is what §33 means
by "la riconciliazione claim_id/evidence_id va chiusa qui, non prima")

User decision (2026-09-15): `claim_id` (pre-existing pipeline,
`gmv_evidence_pipeline.py::consolidate_claims()`) and the crawler's own
`evidence_id`/`ATOM_ID` lineage are related but structurally distinct --
`claim_id` is computed from *already-resolved* entity ids
(`resolved_subject_id`/`resolved_object_id`), while `ATOM_ID` and
`compute_atom_fingerprint()` (step 7) key off *raw text*
(`_forma(subject)`/predicate/`_forma(object)`). A concrete, worked
example: the same real-world fact worded two different ways
("mostra al MAXXI" vs. "esposizione del MAXXI") gets one `claim_id`
(entity resolution already normalized the wording away) but can get two
different `atom_fingerprint`s (text normalization does not always close
that gap -- see `compute_atom_fingerprint()`'s own documented word-order/
OBJECT_TYPE limitation, step 7).

**This module's concrete resolution, for the one place this actually
matters -- `FieldOperation.claim_id`, the per-operation provenance tag
the real Notion-writing code already threads through every patch
operation:** use `AtomCandidate.atom_id` directly. Not because it is the
*same computation* as the legacy `claim_id` (it provably is not, per the
example above), and **not because reconciliation (step 12) is guaranteed
to have already deduplicated equivalent atoms by the time one reaches
here** -- an earlier draft of this docstring claimed exactly that, and
adversarial review found it false on two counts, checked against the
real code, not assumed: (1) `gmv_crawler_reconciliation.py::reconcile()`'s
own docstring is explicit that its `SUPPORTING` outcome keeps *both*
atoms as independently valid, coexisting records ("not by merging into
one atom") -- it never collapses two differently-worded extractions of
the same fact down to a single `atom_id`, so the "mostra al MAXXI" vs.
"esposizione del MAXXI" example above is exactly the case `reconcile()`
would leave as two atoms, not one; (2) `reconcile()` is not called by
any production code path anywhere in this repository today (grepped) --
there is no wired pipeline guaranteeing it ever runs before an
`AtomCandidate` reaches this adapter, whether or not its outcome would
help. **The real justification is simpler and does not depend on either
claim:** `ATOM_ID` is the crawler's own stable, already-assigned identity
for the specific atom being published -- the only identity concept this
adapter has in hand at all, reconciliation history notwithstanding. If
two atoms describing the same real-world fact (worded differently, or
never reconciled together in the first place) both reach this adapter,
it will faithfully propose two separate Notion operations for what is,
semantically, one fact -- a real, live risk today, not a hedge against a
rare reconciliation-quality edge case. Closing that gap for real needs
either `compute_atom_fingerprint()` (step 7) keying off resolved entity
identity instead of normalized text, or `reconcile()` actually being
wired into a real ingestion pipeline (neither exists yet) -- not
something a projection adapter three layers downstream can or should
silently paper over by re-deriving its own competing notion of "same
claim."

## Two more real gaps found empirically while wiring this module, not
## theorized in advance (steps 5/9-15's own discipline: verify by
## running the real code, not by reading it)

1. **entity_type case/language mismatch, closed here.** Step 5's own
   contract docstring already flagged this as unresolved ("entity_type
   strings in the real Notion pipeline are lowercase Italian... while
   ...GMV_ONTOLOGY_REGISTRY_v0.1.json's entity_classes use uppercase
   English... No mapping between the two exists yet"). Confirmed by
   reading both real files: the registry's real class_ids are
   PERSON/ORGANIZATION/INSTITUTION/PLACE/EVENT/DOCUMENT/ARTIST/
   EXHIBITION/PROJECT/COLLECTION/WORK/ARTWORK_INSTANCE/ARTWORK(deprecated)/
   SPONSOR/CONTRACT; the real, live `00_CONFIG/notion_page_templates.json`
   only has six `entita` keys: artista/mostra/persona/istituzione/opera/
   sponsor. `CRAWLER_ENTITY_TYPE_TO_LEGACY` below is the explicit,
   grounded mapping for the 7 registry classes that have a real target
   (WORK and ARTWORK_INSTANCE both collapse to "opera" -- the legacy
   schema has no WORK/INSTANCE split, a real granularity loss, not an
   oversight). The other 8 registry classes (ORGANIZATION/PLACE/EVENT/
   DOCUMENT/PROJECT/COLLECTION/ARTWORK/CONTRACT) have no Notion table at
   all today -- `supports()` correctly returns `False` for them, not a
   guessed fallback.
2. **Predicate vocabulary mismatch, found but NOT closed here --
   disclosed as a real, load-bearing limitation.** `route_claim()`
   matches a claim's `predicate` against `page_templates.json`'s
   `relation_hints`/`field_hints`, which are real, natural-language
   English phrases extracted from actual Area35 corpus text (verified:
   `"is the author of"`, `"uses technique"`). The crawler's own governed
   predicate vocabulary (`GMV_ONTOLOGY_REGISTRY_v0.1.json`) is disjoint,
   short, snake_case tokens (`participated_in`, `source_for`,
   `exhibited_at`, ...) -- verified by direct comparison, zero overlap.
   **This means every `AtomCandidate` routed through this adapter today
   falls through to `route_claim()`'s free-text body layer -- the
   relation/field routing layers this adapter's whole value proposition
   depends on are, in practice, unreachable until a future step builds an
   explicit predicate -> hint-phrase mapping.** Building that mapping
   requires real domain judgment (which registry predicate corresponds
   to which of dozens of hint phrases, per entity type) this session does
   not have grounds to invent -- disclosed here, not silently degraded
   or hidden behind a passing test suite that only exercises the
   body-fallback path.

## Reuse, verified by import line in this file

`route_claim`, `build_entity_patch`, `build_entity_body`
(`gmv_notion_multi_candidate`), `norm` (`gmv_evidence_pipeline`),
`publish_bundle`, `load_bundle` (`gmv_notion_publish`), `AtomCandidate`
(`gmv_atom_validator`), `MonadDocument` (`gmv_monad_materializer`) are
imported below, not reimplemented.

## `reconcile_correction()` — not implemented, matching real precedent

Step 5's own contract docstring already states plainly: "No existing
code implements this flow yet." Nothing changed that between step 5 and
this step. Raises `NotImplementedError` explicitly rather than a fake
`ProposedPatch` this module has no grounds to construct.

## Relation-writer — still missing, preserved exactly as-is

`build_entity_patch()`'s own comment is unchanged and still true: "No
relation-writer exists anywhere in this codebase today." Every relation
claim this adapter routes stays `CONFLICT`. This adapter does not invent
one.
"""
from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gmv_atom_validator import AtomCandidate  # noqa: E402 -- reused, not reimplemented
from gmv_evidence_pipeline import norm  # noqa: E402 -- reused, not reimplemented
from gmv_monad_materializer import MonadDocument  # noqa: E402 -- reused, not reimplemented
from gmv_notion_multi_candidate import (  # noqa: E402 -- reused, not reimplemented
    build_entity_body,
    build_entity_patch,
)
from gmv_notion_publish import load_bundle, publish_bundle  # noqa: E402 -- reused, not reimplemented
from gmv_projection_adapter_contracts import (  # noqa: E402 -- reused, not reimplemented
    FieldOperation,
    Gate,
    ProposedPatch,
    PublishOutcome,
    PublishResult,
    TargetPayload,
)

# Grounded against 00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json's real
# entity_classes and 00_CONFIG/notion_page_templates.json's real "entita"
# keys (see module docstring point 1). WORK/ARTWORK_INSTANCE both map to
# "opera" -- a real granularity loss the legacy schema has no room for,
# not an oversight.
CRAWLER_ENTITY_TYPE_TO_LEGACY: dict[str, str] = {
    "ARTIST": "artista",
    "EXHIBITION": "mostra",
    "PERSON": "persona",
    "INSTITUTION": "istituzione",
    "WORK": "opera",
    "ARTWORK_INSTANCE": "opera",
    "SPONSOR": "sponsor",
}

# publish_bundle()'s hardcoded gate check ("!= 'READY_FOR_NOTION'") and
# gate()'s three real return values -- Notion-flavored wording, kept out
# of the crawler-level Gate vocabulary per step 5's own contract.
_ENTITY_GATE_READY = "READY_FOR_NOTION"
_ENTITY_GATE_REVIEW = "REVIEW_REQUIRED"
_ENTITY_GATE_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"

_CRAWLER_GATE_TO_ENTITY_GATE: dict[Gate, str] = {
    "AUTO_ACCEPT": _ENTITY_GATE_READY,
    "REVIEW_REQUIRED": _ENTITY_GATE_REVIEW,
    "BLOCKED": _ENTITY_GATE_INSUFFICIENT,
}

# gmv_notion_candidate.py::attach_body_adapter's real 2-value body-gate
# vocabulary. build_entity_patch() only ever emits BODY_REVIEW_REQUIRED
# in practice (its own comment: "always require manual review before any
# body text from this path is published") -- BODY_PATCH_READY's mapping
# is implemented for completeness of the vocabulary, not because any
# real code path exercises it today.
_BODY_GATE_READY = "BODY_PATCH_READY"
_BODY_GATE_REVIEW = "BODY_REVIEW_REQUIRED"


def _entity_gate_to_crawler_gate(entity_gate: str, *, has_conflict: bool) -> Gate:
    """READY_FOR_NOTION only becomes AUTO_ACCEPT when no operation is
    CONFLICT -- gate() itself does not look at `operations` at all
    (verified by reading it), so the real pipeline can and does produce
    READY_FOR_NOTION alongside unresolved CONFLICTs; TargetPayload's own
    __post_init__ forbids AUTO_ACCEPT with any CONFLICT present (step 5's
    own deliberately-tightened invariant), so this downgrade is not
    optional -- passing the raw mapping through would raise."""
    if entity_gate == _ENTITY_GATE_READY:
        return "REVIEW_REQUIRED" if has_conflict else "AUTO_ACCEPT"
    if entity_gate == _ENTITY_GATE_REVIEW:
        return "REVIEW_REQUIRED"
    if entity_gate == _ENTITY_GATE_INSUFFICIENT:
        return "BLOCKED"
    raise ValueError(f"unknown entity-level gate value: {entity_gate!r}")


def _body_gate_to_crawler_gate(body_gate: str) -> Gate:
    if body_gate == _BODY_GATE_READY:
        return "AUTO_ACCEPT"
    if body_gate == _BODY_GATE_REVIEW:
        return "REVIEW_REQUIRED"
    raise ValueError(f"unknown body-level gate value: {body_gate!r}")


def _crawler_gate_to_body_gate(gate: Gate) -> str:
    """Inverse of `_body_gate_to_crawler_gate()`, for `_write_bundle()`
    writing `NOTION_PATCH.json["body_gate"]` -- the literal string
    `plan_requests()`/`apply_patch()` (`notion_publish.py`) check before
    ever appending body text. The 2-value legacy body-gate vocabulary has
    no BLOCKED equivalent; anything other than AUTO_ACCEPT is treated as
    BODY_REVIEW_REQUIRED (never auto-publish body text when the overall
    payload is not itself ready), the same conservative default
    build_entity_patch() already applies unconditionally today."""
    return _BODY_GATE_READY if gate == "AUTO_ACCEPT" else _BODY_GATE_REVIEW


def _atoms_to_claims(atoms: Sequence[AtomCandidate]) -> list[dict]:
    """AtomCandidate -> the legacy claim-dict shape route_claim()/
    build_entity_patch()/build_entity_body() expect. claim_id=atom_id is
    this module's concrete resolution of the claim_id/ATOM_ID question --
    see module docstring."""
    return [
        {
            "claim_id": atom.atom_id,
            "subject": atom.subject,
            "predicate": atom.predicate,
            "object": atom.object,
            "status": atom.status,
            "source_file_ids": [atom.source] if atom.source else [],
        }
        for atom in atoms
    ]


def _patch_to_target_payload(patch: dict, body_text: str, *, crawler_entity_type: str) -> TargetPayload:
    """`crawler_entity_type` is threaded through explicitly rather than
    read from `patch["entity_type"]`: that key holds
    `legacy_entity_type.upper()` (e.g. "ARTISTA"), build_entity_patch()'s
    own internal display convention -- neither the crawler's real
    vocabulary (`monad.entity_type`, e.g. "ARTIST") nor a genuine Notion
    table/property name. TargetPayload.entity_type's own docstring is
    explicit that it must be "the crawler's own vocabulary... never a
    target-specific table name" -- patch["entity_type"] is actually
    neither, so using it here would violate the contract this function's
    entire job is to satisfy."""
    has_conflict = False
    operations = []
    for op in patch["operations"]:
        action = op["action"]
        if action == "CONFLICT":
            has_conflict = True
        # build_entity_patch()'s real operation dicts store the already-
        # resolved Notion property/relation name under "property" (field
        # ops) or nothing at all (schema-mismatch CONFLICTs carry only a
        # "reason"). The generic key (campo_key/relation_key) this
        # function routed on is not preserved in its output -- verified
        # by reading build_entity_patch() in full, not assumed -- so
        # there is nothing more specific to recover here without editing
        # that real, corpus-validated function, which "generalizzazione,
        # non riscrittura" rules out. `field` therefore holds the real
        # Notion property name for a resolved field/relation operation,
        # or a synthesized `<unresolved:REASON>` marker when even that is
        # absent -- a real, disclosed divergence from FieldOperation's
        # own docstring ("the crawler-side generic name... never a
        # target's own property/column name"), not a silent one.
        field_name = op.get("property") or op.get("relation") or f"<unresolved:{op.get('reason', '?')}>"
        operations.append(FieldOperation(
            action=action, field=field_name, value=op.get("value"),
            claim_id=op.get("claim_id"), reason=op.get("reason"),
        ))
    return TargetPayload(
        entity_type=crawler_entity_type,
        name=patch["name"],
        operation=patch["operation"],
        operations=tuple(operations),
        gate=_entity_gate_to_crawler_gate(patch["gate"], has_conflict=has_conflict),
        body_text=body_text,
        body_gate=_body_gate_to_crawler_gate(patch["body_gate"]),
        existing_target_reference=patch.get("existing_notion_id"),
        keep_properties=patch.get("keep", {}).get("properties", {}),
    )


def _safe_folder_name(name: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "unnamed"


def _write_bundle(run_dir: Path, payload: TargetPayload) -> Path:
    """Writes the same three files load_bundle()/publish_bundle() read
    (entity.json, NOTION_PATCH.json, NOTION_PAYLOAD.json), reconstructed
    from the generic TargetPayload rather than call-through to
    write_entity_bundle() (gmv_notion_multi_candidate.py): that function
    needs Notion-specific bookkeeping (notion_status, the full raw claims
    list) TargetPayload deliberately does not carry, by design of the
    contract it is implementing -- see module docstring. `keep`/
    `body_gate` ARE written (an earlier draft omitted both -- caught by
    adversarial review reproducing empirically that this silently
    disabled notion_publish.py::check_staleness() and the body-append
    path entirely; see TargetPayload.keep_properties's own docstring for
    the staleness half).

    Bundle-folder naming uses the crawler English vocabulary
    (`payload.entity_type`, e.g. "artist") -- deliberately NOT
    write_entity_bundle()'s legacy-Italian vocabulary
    (gmv_notion_multi_candidate.py, e.g. "artista"). This is a
    stylistic difference, not a bug: load_bundle() (gmv_notion_publish.py:55)
    receives `bundle_dir` already resolved and never reads the folder
    name -- it reads only the three fixed filenames inside
    (entity.json / NOTION_PATCH.json / NOTION_PAYLOAD.json), so either
    naming loads identically. Do not "fix" the naming by threading
    `legacy_entity_type` through the shared TargetPayload contract to
    match write_entity_bundle() -- that would change a shared
    projection-adapter contract for a cosmetic reason."""
    import json

    bundle_dir = run_dir / "entities" / f"{payload.entity_type.lower()}__{_safe_folder_name(payload.name)}"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "entity.json").write_text(
        json.dumps({"entity_type": payload.entity_type, "name": payload.name}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    patch = {
        "operation": payload.operation,
        "existing_notion_id": payload.existing_target_reference,
        "operations": [
            {"action": op.action, "property": op.field, "value": op.value,
             "claim_id": op.claim_id, "reason": op.reason}
            for op in payload.operations
        ],
        "body": {"proposed_markdown": payload.body_text or ""},
        "body_gate": _crawler_gate_to_body_gate(payload.body_gate),
        # check_staleness() only ever reads ["keep"]["properties"] (verified
        # by reading it) -- "relations" is included for shape parity with
        # the real patch dict, always empty: TargetPayload has no relations-
        # kept-state field, and no real code path reads it today.
        "keep": {"properties": payload.keep_properties, "relations": {}},
    }
    (bundle_dir / "NOTION_PATCH.json").write_text(
        json.dumps(patch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    entity_gate = _CRAWLER_GATE_TO_ENTITY_GATE[payload.gate]
    (bundle_dir / "NOTION_PAYLOAD.json").write_text(
        json.dumps({"gate": entity_gate}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return bundle_dir


_PUBLISH_BUNDLE_OUTCOME: dict[int, PublishOutcome] = {
    0: "PUBLISHED",
    1: "CANCELLED",
    2: "FAILED_AUTHENTICATION",
    3: "ALREADY_PUBLISHED",
    4: "BLOCKED_GATE_NOT_READY",
    5: "BLOCKED_STALE_OR_DUPLICATE",
}


@dataclass
class MultiCandidateNotionAdapter:
    """Concrete ProjectionAdapter wrapping gmv_notion_multi_candidate.py's
    real fan-out engine for one primary entity's Monad. Does NOT
    replicate discover_entities()'s multi-entity discovery-from-raw-text
    fan-out (proposing OTHER entities mentioned in the claims) -- that
    capability discovers entities the crawler itself does not yet know
    about, which is exactly the job the crawler's own RESOLVE ENTITIES
    stage (Entity Registry, step 6) is meant to own going forward, not
    something a one-Monad-in/one-TargetPayload-out project() call can do.
    A future engine step producing one MonadDocument per resolved entity
    and calling project() once per Monad is how multi-entity fan-out
    should work against this contract -- not built here, not assumed
    solved.

    `config` and `config_path` are both required, deliberately not just
    one: `build_entity_patch()`/`route_claim()` take the parsed dict;
    `publish_bundle()` (`gmv_notion_publish.py`) takes a file path and
    re-reads `entita.<type>.notion_database_id` from it itself, on every
    call -- a real, pre-existing seam between the two real modules this
    adapter bridges, not something introduced here.
    """

    rows: dict
    config: dict
    config_path: Path
    page_templates: dict
    run_dir: Path

    def supports(self, entity_type: str) -> bool:
        return entity_type in CRAWLER_ENTITY_TYPE_TO_LEGACY

    def project(self, monad: MonadDocument) -> TargetPayload:
        if not self.supports(monad.entity_type):
            raise ValueError(
                f"entity_type {monad.entity_type!r} has no legacy Notion target -- "
                "check supports() before calling project()"
            )
        legacy_entity_type = CRAWLER_ENTITY_TYPE_TO_LEGACY[monad.entity_type]
        # Only STATUS=VALID atoms are eligible for proposal -- an
        # UNVERIFIED/DISPUTED/SUPERSEDED/INVALIDATED atom is not a
        # settled current fact (GMV_KNOWLEDGE_MONAD_SPEC_v1.0 §5) and
        # must never be proposed as Notion page content. A MonadDocument
        # can legitimately carry non-VALID atoms (tombstoning preserves
        # history, §9); an earlier draft of this method did not filter
        # them, so an INVALIDATED atom could reach a Notion CREATE/UPDATE
        # proposal indistinguishably from a real one -- caught by
        # adversarial review, not by this method's own tests. Same
        # STATUS=VALID-only policy gmv_crawler_public_projector.py (step
        # 15) already applies for the same reason, not a new invention.
        valid_atoms = tuple(atom for atom in monad.atoms if atom.status == "VALID")
        claims = _atoms_to_claims(valid_atoms)
        discovered_index = {
            norm(monad.canonical_name): {"name": monad.canonical_name, "entity_type": legacy_entity_type},
        }
        patch = build_entity_patch(
            monad.canonical_name, legacy_entity_type, claims,
            self.rows, self.config, self.page_templates, discovered_index,
        )
        body_text = build_entity_body(monad.canonical_name, legacy_entity_type, claims, self.page_templates)
        return _patch_to_target_payload(patch, body_text, crawler_entity_type=monad.entity_type)

    def publish(self, payload: TargetPayload) -> PublishResult:
        """Deliberately does not wrap `publish_bundle()` in a broad
        `try/except`: the ProjectionAdapter contract's own docstring
        names `FileNotFoundError`/`ValueError` from `load_bundle()`, a
        `KeyError` if `entity_type` is missing from `config.json`, and
        real HTTP errors as failure modes "a concrete adapter's publish()
        must still handle" -- none of `PublishOutcome`'s six values
        represents "environment/configuration is broken," and inventing
        a seventh to swallow arbitrary exceptions into would misrepresent
        a real implementation-level failure as one of the six
        intentional, recoverable outcomes this contract models. "Handled"
        here means: these propagate as real exceptions to the caller,
        not silently, not converted into a misleading `PublishResult` --
        the caller (whatever drives the crawler's publish loop) decides
        what to do with an environment failure, this adapter does not
        guess."""
        bundle_dir = _write_bundle(self.run_dir, payload)
        code = publish_bundle(bundle_dir, config_path=self.config_path)
        outcome = _PUBLISH_BUNDLE_OUTCOME.get(code)
        if outcome is None:
            raise ValueError(f"publish_bundle() returned an unrecognized code: {code!r}")
        bundle = load_bundle(bundle_dir)
        target_reference = None
        published_path = bundle_dir / "PUBLISHED.json"
        if outcome == "PUBLISHED" and published_path.is_file():
            import json
            target_reference = json.loads(published_path.read_text(encoding="utf-8")).get("notion_page_id")
        return PublishResult(outcome=outcome, target_reference=target_reference, detail=bundle.entity_name)

    def reconcile_correction(self, target_change: object) -> ProposedPatch:
        raise NotImplementedError(
            "reconcile_correction() has no real implementation anywhere in this "
            "repository (step 5's own contract docstring already states this; "
            "unchanged by step 16) -- crawler spec v0.2 §30 describes the intended "
            "flow (target correction -> proposed semantic patch -> provenance/"
            "authority check -> Monad update), not something to guess a shape for."
        )
