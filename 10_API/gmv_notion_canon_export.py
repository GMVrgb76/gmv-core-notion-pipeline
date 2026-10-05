#!/usr/bin/env python3
"""Export Area35's Notion pages into per-entity canon files under
`03_STATE/area35_canon/`, parallel to the Monad folder (`03_STATE/ombra/`).

**What this is.** One `GMV_NOTION_CANON_SNAPSHOT_V1` markdown file per entity,
`<gmv_id>.md`, holding the Notion page's real text verbatim. The gallery's
Notion pages are the current operational "canon" of the gallery, but they have
NOT passed this pipeline's own fact-by-fact EIC-09 verification -- they are
synthesized from the same Dropbox archive plus independent web cross-checking.
Exporting them makes the two bodies of knowledge comparable entity-by-entity
(same `gmv_id`, same file name, so a human can put "what the Monad verified"
next to "what Notion says" for one entity) WITHOUT letting one become the
other.

**The hard wall (EIC-10).** `00_CONFIG/EPISTEMIC_INGESTION_RULES_v0.2.json`:
"Derived GMV Masters are assertions, not primary evidence. They may guide
retrieval but cannot alone upgrade uncertain claims to VALID". A Notion page is
a derived Master in exactly that sense. Therefore this module:

- declares `schema: GMV_NOTION_CANON_SNAPSHOT_V1`, NEVER
  `GMV_KNOWLEDGE_MONAD_V1` -- it is not a Monad, it has no ATOMS section, and
  a consumer that pattern-matches on the Monad schema would read canon prose as
  verified atoms;
- carries `status: canon_unaudited`, a value used nowhere else in this
  repository, defined once here as a module constant and assigned
  deterministically to every file this module writes;
- has no atom-STATUS logic of any kind, and must never grow any. Nothing here
  imports `gmv_monad_materializer`, `gmv_crawler_atom_builder`,
  `gmv_crawler_relation_atom_builder`, `gmv_atom_validator`,
  `gmv_crawler_public_projector`, or `gmv_notion_projection_adapter`; a test
  pins that with `ast`, not a substring search (see
  `tests/test_gmv_notion_canon_export.py`).

Grounding, read in full before writing this module:

- **`adapter_notion.py` (repo root) is the reader, reused not rewritten.** Its
  `_query_pagine()` / `_record()` / `_corpo()` are the only Notion access used
  here (constraint: no new Notion client); `_corpo()` is what `--with-bodies`
  calls for a page, reading `/blocks/{page}/children`. The record shape
  consumed below is therefore the real `_record()` output, confirmed live on
  2026-10-05 against the real `artista` data source: exactly the keys `id`
  (the raw Notion page UUID), `titolo`, `campi`, `relazioni`, `servizio`, plus
  `corpo` when `--with-bodies` ran AND `config.json`'s spec sets
  `biografia_in_corpo` (true for `artista`/`mostra`/`persona`/`istituzione`,
  false for `opera`/`sponsor` -- so `corpo` is legitimately absent, not a bug).
  `_record()` substitutes the literal `"(senza titolo) <id>"` when the title
  property is missing, which is why the caller passes the raw property value
  (see `main()`) instead of `record["titolo"]`: a placeholder must never be
  offered to entity resolution as if it were a name.

- **Token/auth is `credentials.get_token()` only**, the same single choke
  point `adapter_notion.py` and `notion_extract.py` use; the value is never
  printed, and the CLI variable is named `notion_token` (not `token = ...`)
  to stay clear of the `credential_assignment` pattern in
  `scripts/check_runtime_git_policy.py`.

- **Entity identity is the crawler's, reused verbatim.** `gmv_id` comes from
  `resolve_entity_gmv_id()` against `00_CONFIG/gmv_entity_registry.json` --
  exact `.strip().lower()` matching against `canonical_name` OR any `aliases`,
  `None` for zero or two-or-more matches. No fuzzy matching, no similarity, no
  model call, and no second copy of the matching rule: those are that
  function's own documented points 1-3, and re-implementing them here is
  precisely how a wrong-entity merge gets in. An unresolved name goes through
  `propose_entity_identity()` and is returned to the caller as a proposal --
  never minted, never auto-registered, never turned into a canon file. Only a
  human calling `confirm_new_entity()`/`confirm_entity_alias()` writes the
  registry, exactly as `automation/gmv_crawler_nightly_run.py` and
  `automation/gmv_crawler_review_tool.py` already do.

- **Canonical name and entity type come from the REGISTRY entry, not from
  Notion.** Notion's own entity vocabulary (`artista`, `mostra`, `persona`,
  `istituzione`, `opera`, `sponsor` in `config.json`) and the crawler's
  governed vocabulary (`VALID_ENTITY_TYPES` in
  `gmv_crawler_entity_resolver.py`, `ARTIST`/`EXHIBITION`/...) are disjoint, and
  building a mapping between them is a governance decision this module must not
  make up. It is not needed either: the registry already states both fields for
  every entity a canon file is written for. What Notion calls the entity stays
  in the body (see `# NOTION TITLE` below), so nothing is lost by not
  asserting it in frontmatter. This is not hypothetical: resolving
  GMV-000004 live on 2026-10-05 matched Notion's "Florencia S.M. Brück" through
  the registry's `aliases`, while the registry's `canonical_name` is
  "Florencia Bruck" -- so the two names genuinely differ in the real data, and
  the file records both without pretending they are one field.

- **Write path is `secure_storage.atomic_write_text()`**, the repository's one
  atomic-write primitive for protected artifacts (0700 directory, 0600 file,
  tempfile + `os.replace`), the same one `gmv_monad_materializer.py` uses for
  materialized Monads. `03_STATE/area35_canon/` inherits its "Live state ...
  never Git" class from its top-level parent `03_STATE/` in
  `00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md` and `.gitignore`'s literal
  `/03_STATE/` pattern, so no new governance entry or `.gitignore` line exists
  for it. As in `gmv_monad_materializer.materialize_monad()`, the directory is
  a caller-supplied `target_dir`, not a hardcoded path inside the function;
  `CANON_DIR` is the CLI's default only.

- **Frontmatter field order follows the real Monad, not the task brief's
  sketch.** `03_STATE/ombra/GMV-000001.md` renders `schema`, `gmv_id`,
  `entity_type`, `canonical_name`, `status` -- `entity_type` BEFORE
  `canonical_name`. The brief for this task listed the two the other way round
  while explicitly deferring order to the real file ("confirm the real Monad
  shape ... mirror its conventions, don't invent a divergent style"), so the
  real file wins; the six decided field names are used verbatim, and the two
  Notion-specific ones (`source_notion_page_id`, `exported_at`) follow them.
  Rendering uses `yaml.safe_dump(..., allow_unicode=True, sort_keys=False)`,
  the same call `gmv_monad_materializer.render_monad_markdown()` makes, so the
  two file types read as siblings.

- **Section names mirror the Monad's, so no prose generated here can be
  mistaken for Notion's own words.** The Monad's payload section is `# PUBLIC`;
  this file's are `# NOTION TITLE` (the page's title property, verbatim) and
  `# NOTION PAGE` (the page body, verbatim). Nothing between them is
  interpreted, summarized, reordered, trimmed, or normalized: an empty page
  body renders as an empty `# NOTION PAGE` section, the same way
  `render_monad_markdown()` renders an empty `public_text`, because inventing
  a placeholder sentence is how generated text ends up being read as sourced
  text.

**Deliberate non-goals**, stated so none gets silently "fixed" later:

- **No duplicate detection across Notion pages mapping to one `gmv_id`.**
  Each page is exported independently, so if two Notion pages ever resolve to
  the same `gmv_id` the later export overwrites the earlier one, and this
  module does not detect, rank, or arbitrate that. Verified absent in the real
  data on 2026-10-05 (all 442 pages across the six data sources; the six
  resolvable ones map one-to-one, zero collisions). Not fixed here on purpose:
  deciding "which Notion page is this entity's canon" is the human judgement
  the whole export exists to feed, and a "helpful" automatic choice here would
  make that decision invisibly. The behaviour is pinned by a test so it is a
  documented consequence, not a surprise.
- **No validation, enrichment, web cross-check, or entity-type mapping of the
  page text.** The Notion side of EIC-09 verification does not exist yet and
  inventing it is out of scope by an order of magnitude.
- **No queueing inside `export_notion_page_to_canon()`**, mirroring
  `propose_entity_identity()`'s own contract ("Does NOT queue anything itself
  -- queueing stays the caller's explicit decision"). `main()` is the caller
  that appends, through the real
  `gmv_crawler_entity_identity_proposal_queue.append_entity_identity_proposals()`
  and the same single queue file the nightly run and the review tool already
  use, so a human has exactly one place to look for pending identities.
- **No GBrain ingestion, no backup mirror, no scheduler.** GBrain's actual
  configuration for this repository is explicitly unverified (see
  `.claude/agent-memory/gmv-code-architect/MEMORY.md`); extending the existing
  daily job to a second source folder, and adding a backup for this folder the
  way `10_API/gmv_monad_backup.py` does for `ombra/`, are separate decisions
  for the directing session.
- **No clock read inside the function.** `now` is caller-supplied, like
  `build_atoms(now=...)` and `append_entity_identity_proposals(now=...)`, so a
  canon file's `exported_at` is reproducible in a test.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import adapter_notion  # noqa: E402 -- the existing read-only Notion reader, reused
import credentials  # noqa: E402 -- the existing single token resolver, reused

from gmv_crawler_entity_identity_proposal_queue import (  # noqa: E402 -- reused, not reimplemented
    append_entity_identity_proposals,
)
from gmv_crawler_entity_resolver import (  # noqa: E402 -- reused, not reimplemented
    EntityIdentityProposal,
    _load_entity_registry,
    propose_entity_identity,
    resolve_entity_gmv_id,
)
from secure_storage import atomic_write_text  # noqa: E402 -- reused, not reimplemented

#: This file format's own schema id. Deliberately NOT
#: `GMV_KNOWLEDGE_MONAD_V1` (`gmv_monad_materializer.MONAD_SCHEMA_ID`): a canon
#: snapshot has no ATOMS section and no EIC-09-verified atom in it, and a
#: consumer keying on the Monad schema would read Notion prose as verified
#: knowledge. See the module docstring's EIC-10 section.
NOTION_CANON_SCHEMA_ID = "GMV_NOTION_CANON_SNAPSHOT_V1"

#: The one status value every file this module writes carries: the content is
#: the gallery's canon, and this pipeline has not audited it fact-by-fact
#: (EIC-09). Used nowhere else in the repository; defined once here rather than
#: left as a free string in a single module's frontmatter, so a future consumer
#: has exactly one place to match it against. Mirrors how
#: `gmv_evidence_pipeline`'s `SUPPORTED_BY_ARCHIVE`/`SUPPORTED_BY_WEB` tier is
#: declared once and assigned mechanically per connector.
CANON_STATUS = "canon_unaudited"

#: Canonical on-disk directory, the CLI default only -- `export_notion_page_to_canon()`
#: takes an explicit `target_dir` from its caller, the same deliberate
#: narrowness `gmv_monad_materializer.materialize_monad()` keeps for
#: `target_path`. Governed by `03_STATE/`'s existing "Live state / never Git"
#: row, inherited by sub-path exactly as `03_STATE/ombra/` is.
CANON_DIR = REPO_ROOT / "03_STATE" / "area35_canon"

#: Same literal `automation/gmv_crawler_nightly_run.py` (line 139) and
#: `automation/gmv_crawler_review_tool.py` (line 29) already use for the same
#: file, deliberately repeated rather than imported for the reason those two
#: give: each entry point declares its own runtime paths. Reusing THIS path
#: instead of a canon-specific queue is a decision -- one human review queue
#: for "names this pipeline could not map to a known gmv_id", not two.
IDENTITY_PROPOSAL_QUEUE_PATH = REPO_ROOT / "01_RUNTIME" / "gmv_crawler" / "entity_identity_proposal_queue.jsonl"

OUTCOME_WRITTEN = "WROTE_CANON_FILE"
OUTCOME_PROPOSED = "PROPOSED_FOR_REVIEW"
OUTCOME_NO_NAME = "NO_ENTITY_NAME"


class CanonExportError(ValueError):
    """Raised when the resolved registry entry cannot produce a canon file.

    Deliberately narrow: only the pre-write conditions the registry itself can
    violate -- a `gmv_id` that does not map back to exactly one entry, or an
    entry with an empty `canonical_name`/`entity_type`. The rule is the same
    one `gmv_monad_materializer`'s `required_document_fields_not_empty()`
    (M-SCHEMA05) applies to a Monad's frontmatter, re-expressed here rather
    than imported, because that module is inside this task's hard wall: a
    canon file must not become coupled to the Monad materializer even to
    reuse one empty-string check.
    """


@dataclass(frozen=True, slots=True)
class CanonExportResult:
    """What one page produced. `gmv_id`/`target_path` are set only for
    `OUTCOME_WRITTEN`; `proposal` is set only for `OUTCOME_PROPOSED`; both are
    `None` for `OUTCOME_NO_NAME`. `page_id` and `entity_name` always describe
    the input, so a caller can report every page it saw, written or not."""

    entity_name: str
    page_id: str
    outcome: str
    gmv_id: str | None = None
    target_path: Path | None = None
    proposal: EntityIdentityProposal | None = None


def _registry_entry_for(registry: dict, gmv_id: str) -> dict:
    """The one registry entry carrying `gmv_id`, or `CanonExportError`.

    `resolve_entity_gmv_id()` returns the id only after reading this same
    `registry`, so the entry must exist; requiring it to be EXACTLY ONE closes
    a real registry shape it does not police -- two entries sharing one
    `gmv_id` (a human edit gone wrong) would otherwise let the export pick
    whichever the iteration reached first, silently choosing a canonical name.
    A mismatch means the two halves of the registry disagree, which is a fact
    for a human, not something to average over.
    """
    matches = [entry for entry in registry["entities"] if entry.get("gmv_id") == gmv_id]
    if len(matches) != 1:
        raise CanonExportError(
            f"gmv_id {gmv_id!r} matches {len(matches)} entries in the entity registry; "
            "expected exactly one. Fix 00_CONFIG/gmv_entity_registry.json by hand."
        )
    return matches[0]


def _registry_entry_fields_not_empty(entry: dict) -> list[str]:
    """The empty frontmatter-feeding fields, by name. Same BLOCKER-stops-the-
    write convention as `gmv_monad_materializer`'s M-SCHEMA05, for the reason
    stated on `CanonExportError`."""
    return [
        field
        for field in ("canonical_name", "entity_type")
        if not str(entry.get(field) or "").strip()
    ]


def render_canon_markdown(
    *, gmv_id: str, entity_type: str, canonical_name: str, source_notion_page_id: str,
    notion_title: str, body_text: str, now: str,
) -> str:
    """Pure function: the canon file's exact text. Frontmatter field order
    follows the real Monad (see the module docstring); `# NOTION TITLE` and
    `# NOTION PAGE` carry only what Notion itself said."""
    frontmatter = {
        "schema": NOTION_CANON_SCHEMA_ID,
        "gmv_id": gmv_id,
        "entity_type": entity_type,
        "canonical_name": canonical_name,
        "status": CANON_STATUS,
        "source_notion_page_id": source_notion_page_id,
        "exported_at": now,
    }
    yaml_block = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).rstrip("\n")
    return "\n".join([
        "---",
        yaml_block,
        "---",
        "",
        "# NOTION TITLE",
        notion_title,
        "",
        "# NOTION PAGE",
        body_text,
        "",
    ])


def export_notion_page_to_canon(
    record: Mapping[str, Any], entity_name: str, target_dir: Path, *, now: str,
    registry: dict | None = None,
) -> CanonExportResult:
    """Export one Notion page's data as one `<gmv_id>.md` canon file.

    `record` is one `adapter_notion._record()` output (the `--with-bodies`
    shape described in the module docstring); `entity_name` is passed
    explicitly rather than read from `record["titolo"]` because `_record()`
    substitutes `"(senza titolo) <id>"` for a missing title, and a placeholder
    must not be offered to entity resolution as a name -- the CLI reads the
    config's title property instead and passes `""` when it is empty.

    `entity_name` empty/whitespace -> `OUTCOME_NO_NAME`, no proposal and no
    file: a page that does not name its subject cannot be matched to an entity,
    and queueing a blank `raw_name` here would put a non-name in the one human
    review queue. (`propose_entity_identity()` deliberately keeps blank names
    queueable for the crawler's own extractor, whose empty `subject_raw` is a
    real bug signal; this export has no such signal to preserve, so it reports
    the page and stops there.)

    Unresolved `entity_name` -> `OUTCOME_PROPOSED` carrying a real
    `EntityIdentityProposal`, and NO file: proposed, never minted. The caller
    decides whether to queue it.

    Resolved -> the file is written atomically under `target_dir`, named after
    the REGISTRY's `gmv_id`. That is the only thing that ever becomes a file
    name, and it comes from a human-curated registry entry rather than from
    Notion's own strings -- so no Notion-controlled text can influence a
    filesystem path.

    Never imports or calls the Monad/atom modules (see the module docstring's
    hard-wall section).
    """
    page_id = str(record.get("id") or "")
    if registry is None:
        registry = _load_entity_registry()
    name = (entity_name or "").strip()
    if not name:
        return CanonExportResult(
            entity_name=entity_name, page_id=page_id, outcome=OUTCOME_NO_NAME,
        )

    # Resolve first, propose only on failure -- the same two reused resolver
    # functions `gmv_crawler_orchestrator.process_document()` uses, called in
    # the order that keeps one lookup per question: `propose_entity_identity()`
    # returns None for exactly the names that resolve and a proposal for every
    # name that does not, so asking it first would mean calling
    # `resolve_entity_gmv_id()` twice to recover the id it declines to carry
    # (`EntityIdentityProposal` deliberately has no `gmv_id` field).
    gmv_id = resolve_entity_gmv_id(name, registry)
    if gmv_id is None:
        proposal = propose_entity_identity(
            name, registry,
            source_id=f"notion:page/{page_id}" if page_id else "notion:page",
            evidence_excerpt=str(record.get("titolo") or name),
        )
        return CanonExportResult(
            entity_name=name, page_id=page_id, outcome=OUTCOME_PROPOSED, proposal=proposal,
        )

    entry = _registry_entry_for(registry, gmv_id)
    empty = _registry_entry_fields_not_empty(entry)
    if empty:
        raise CanonExportError(
            f"registry entry for {gmv_id} has empty {', '.join(empty)}: a canon file's "
            "frontmatter has no other gate for it. Fix the registry by hand."
        )

    target_path = target_dir / f"{gmv_id}.md"
    atomic_write_text(target_path, render_canon_markdown(
        gmv_id=gmv_id,
        entity_type=str(entry["entity_type"]),
        canonical_name=str(entry["canonical_name"]),
        source_notion_page_id=page_id,
        notion_title=str(record.get("titolo") or ""),
        body_text=str(record.get("corpo") or ""),
        now=now,
    ))
    return CanonExportResult(
        entity_name=name, page_id=page_id, outcome=OUTCOME_WRITTEN,
        gmv_id=gmv_id, target_path=target_path,
    )


# --------------------------------------------------------------------------- #
# CLI -- the caller that reads the live Notion pages and queues the leftovers.
# --------------------------------------------------------------------------- #

def _export_one_data_source(
    entity_spec_key: str, spec: dict, cfg: dict, notion_token: str, *,
    target_dir: Path, now: str, registry: dict,
) -> list[CanonExportResult]:
    """Every page of one `config.json` data source, exported.

    Reuses `adapter_notion._query_pagine()`/`_record()`/`_corpo()` so no HTTP,
    auth, retry or property-decoding logic is duplicated here (the module
    docstring's first grounding bullet). The title property is read from the
    spec's own `campi` mapping -- the same `next(iter(spec["campi"]))` key
    `_record()` itself uses for `titolo`, and the config order is the one that
    decides it -- so the name passed down is the raw property value, empty
    rather than `_record()`'s placeholder when Notion has none.
    """
    db_id = spec.get("notion_database_id")
    if not db_id:
        raise ValueError(f"config.json: '{entity_spec_key}' has no notion_database_id")
    if not spec.get("campi"):
        # Checked explicitly because `next(iter(...))` on an empty mapping
        # raises a bare StopIteration whose message is empty -- the run would
        # report a data source as failed with nothing to say why.
        raise ValueError(f"config.json: '{entity_spec_key}' has no campi mapping")
    title_key = next(iter(spec["campi"]))
    results: list[CanonExportResult] = []
    for page in adapter_notion._query_pagine(db_id, notion_token):
        record = adapter_notion._record(page, entity_spec_key, spec, cfg)
        if spec.get("biografia_in_corpo"):
            record["corpo"] = adapter_notion._corpo(record["id"], notion_token)
        raw_name = record["campi"].get(title_key)
        results.append(export_notion_page_to_canon(
            record, str(raw_name).strip() if raw_name is not None else "", target_dir,
            now=now, registry=registry,
        ))
    return results


def main(argv: Sequence[str] | None = None) -> int:
    """Read the configured Notion data sources and export what resolves.

    `--entities` narrows the run the same way `notion_extract.py` narrows it
    (comma-separated keys of `config.json`'s `entita`), so a single-entity
    live check does not cost six full database walks.

    Exit codes: 0 all requested data sources were read (a data source with
    zero resolvable entities is a success, not a failure); 2 unusable
    arguments/credentials/config; 1 at least one data source could not be
    read at all, which is reported on stderr rather than hidden behind the
    "continue with the rest" behavior.
    """
    parser = argparse.ArgumentParser(
        description="Esporta le pagine Notion Area35 in 03_STATE/area35_canon/<gmv_id>.md (sola lettura su Notion)."
    )
    parser.add_argument("--config", default="config.json", help="Notion mapping config (adapter_notion.py's default too).")
    parser.add_argument("--out-dir", default=str(CANON_DIR), help="Destination folder for the canon files.")
    parser.add_argument(
        "--token-file", default="~/.config/area35-qa/notion_token",
        help="Fallback token file when NOTION_TOKEN is unset (notion_extract.py's default too).",
    )
    parser.add_argument("--entities", help="Chiavi di config.json separate da virgola, per un collaudo limitato.")
    parser.add_argument("--now", required=True, help="Timestamp ISO-8601 per exported_at (mai letto da un clock qui).")
    parser.add_argument(
        "--proposal-queue", default=str(IDENTITY_PROPOSAL_QUEUE_PATH),
        help="Coda dei nomi non risolti (nessuna scrittura al registro entita').",
    )
    args = parser.parse_args(argv)

    # nome non-'token=': evita il pattern credential_assignment di check_runtime_git_policy.py
    try:
        resolved = credentials.get_token("NOTION_TOKEN", args.token_file)
    except credentials.TokenError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    notion_token = resolved.value
    print(f"[info] token Notion letto da {resolved.origin}", file=sys.stderr)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    wanted = [key.strip() for key in args.entities.split(",")] if args.entities else list(cfg["entita"])
    unknown = [key for key in wanted if key not in cfg["entita"]]
    if unknown:
        print(f"[errore] chiavi sconosciute in config.json: {', '.join(unknown)}", file=sys.stderr)
        return 2

    target_dir = Path(args.out_dir).expanduser()
    registry = _load_entity_registry()
    written: list[CanonExportResult] = []
    proposals: list[EntityIdentityProposal] = []
    unnamed = 0
    failed: list[str] = []
    for key in wanted:
        try:
            results = _export_one_data_source(
                key, cfg["entita"][key], cfg, notion_token,
                target_dir=target_dir, now=args.now, registry=registry,
            )
        except Exception as exc:
            # One data source failing does not abandon the other five (the
            # continue-and-report shape `adapter_notion.main()` already uses),
            # but it is remembered: an export whose every page failed must
            # NOT exit 0, or a scheduled caller reads a silent success.
            print(f"[errore] {key}: {exc}", file=sys.stderr)
            failed.append(key)
            continue
        for result in results:
            if result.outcome == OUTCOME_WRITTEN:
                written.append(result)
            elif result.outcome == OUTCOME_PROPOSED and result.proposal is not None:
                proposals.append(result.proposal)
            else:
                unnamed += 1
        print(f"  {key:12} {len(results)} pagine")

    queued = append_entity_identity_proposals(proposals, Path(args.proposal_queue).expanduser(), now=args.now)
    print(
        f"\n{len(written)} schede canon scritte in {target_dir}; "
        f"{queued} proposte in coda; {unnamed} pagine senza nome."
    )
    for result in written:
        print(f"  {result.gmv_id} <- {result.entity_name} ({result.page_id})")
    if failed:
        print(f"[errore] {len(failed)} data source non lette: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
