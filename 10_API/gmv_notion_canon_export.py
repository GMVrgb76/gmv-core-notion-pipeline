#!/usr/bin/env python3
"""Export Area35's Notion pages into per-entity canon files under
`03_STATE/area35_canon/`, parallel to the Monad folder (`03_STATE/ombra/`).

**What this is.** One `GMV_NOTION_CANON_SNAPSHOT_V1` markdown file per Notion
PAGE, `<notion_page_id>.md`, holding that page's real text verbatim. The
gallery's Notion pages are the current operational "canon" of the gallery, but
they have NOT passed this pipeline's own fact-by-fact EIC-09 verification --
they are synthesized from the same Dropbox archive plus independent web
cross-checking. Exporting them archives the gallery's own research as it
actually stands, so a human can put "what the Monad verified" next to "what
Notion says" for one entity WITHOUT letting one become the other.

**Every real page gets a file. Registry resolution is enrichment, never a
gate.** The first version of this module (2026-10-05, Task 37) wrote a canon
file ONLY for a name already registered in `00_CONFIG/gmv_entity_registry.json`.
That was the right answer to the question it was built for -- "compare Notion
against the Monad for the SAME entity" -- and measured against the real data
it answered almost nothing: of the 442 real pages across Area35's six Notion
data sources, exactly 6 resolved, because the registry holds 7 entities, all
of type ARTIST, and one of them (Danilo Bucchi, GMV-000002) has no Notion page
at all. The gate is GONE, by decision rather than because it was found
buggy: the pages are the gallery's own research and belong in the archive on
their own terms, and coverage must not be made to wait on a much smaller,
much slower-growing registry. `resolve_entity_gmv_id()` is now asked only for
enrichment -- a match adds `gmv_id`/`entity_type`/`canonical_name` to the
frontmatter, and no match leaves those three keys ABSENT (never `null`, never
`""`: a key present with an empty value reads as "the pipeline knows this
field and it is empty", which is a claim this module cannot make about an
identity it does not have).

**The file name is the Notion page id, for every page, uniformly.** Not
`gmv_id`, which the point above makes unavailable for ~99% of pages.
`source_notion_page_id` is always present, it is Notion's own primary key, and
two distinct Notion pages cannot share one, so naming on it also removes a
collision class the `<gmv_id>.md` naming had by construction (two pages
resolving to the same `gmv_id` silently overwrote each other).

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

- **Entity identity is the crawler's, reused verbatim, and it enriches rather
  than gates.** `gmv_id` comes from `resolve_entity_gmv_id()` against
  `00_CONFIG/gmv_entity_registry.json` -- exact `.strip().lower()` matching
  against `canonical_name` OR any `aliases`, `None` for zero or two-or-more
  matches. No fuzzy matching, no similarity, no model call, and no second copy
  of the matching rule: those are that function's own documented points 1-3,
  and re-implementing them here is precisely how a wrong-entity merge gets in.
  An unresolved name goes through `propose_entity_identity()` and is returned
  to the caller as a proposal -- never minted, never auto-registered, and now
  never a reason to skip the file either. Only a human calling
  `confirm_new_entity()`/`confirm_entity_alias()` writes the registry, exactly
  as `automation/gmv_crawler_nightly_run.py` and
  `automation/gmv_crawler_review_tool.py` already do. Queueing the unresolved
  names keeps the registry-growth path alive for a later export at no cost to
  today's coverage, which is the entire reason "file it" and "know what it is"
  are separate steps here.

- **`notion_kind` is Notion's OWN label for the data source, verbatim, and it
  is NOT mapped onto the governed `entity_type` vocabulary.** Notion calls its
  six collections `artista`/`mostra`/`persona`/`istituzione`/`opera`/`sponsor`
  (the keys of `config.json`'s `entita`) while the crawler's governed vocabulary
  is `VALID_ENTITY_TYPES` in `gmv_crawler_entity_resolver.py`
  (`ARTIST`/`EXHIBITION`/...); the two are disjoint and building a mapping
  between them is a governance decision this module must not invent. So the raw
  label is recorded as itself, and the governed `entity_type` appears only for
  pages that resolved, where it comes from the registry entry. Nothing is lost
  by leaving them unmapped: a human comparing the two vocabularies needs the
  real Notion label more than this module needs a normalized one.

- **`canonical_name` and `entity_type` come from the REGISTRY entry, never from
  Notion.** The governed value can only ever be asserted for a page that
  resolved, and then it is copied out of a human-curated entry rather than
  inferred. This is not hypothetical: resolving GMV-000004 live on 2026-10-05
  matched Notion's "Florencia S.M. Brück" through the registry's `aliases`,
  while the registry's `canonical_name` is "Florencia Bruck" -- so the two names
  genuinely differ in the real data, and the file records both (`canonical_name`
  says "Bruck", `notion_title` and `# NOTION TITLE` say "Brück") without
  pretending they are one field.

- **`notion_title` is built from the raw title property, never from
  `record["titolo"]`.** `adapter_notion._record()` substitutes the literal
  `"(senza titolo) <id>"` when the title property is missing, so reading that
  key here would put a synthesized placeholder into a field that is required on
  every file and is, for an unresolved page, its only human-readable
  identifier. The caller already has to pass the raw property value (see
  `export_notion_page_to_canon()`), because that value is also what entity
  resolution must see; reading `notion_title` from the same variable removes
  the placeholder structurally rather than by matching and stripping it. A page
  Notion left untitled therefore renders `notion_title: ''` -- present and
  empty, never a fake title -- the same rule the empty `# NOTION PAGE` section
  below already follows for an empty body.

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

- **Frontmatter field order follows the real Monad, not a task brief's
  sketch.** `03_STATE/ombra/GMV-000001.md` renders `schema`, `gmv_id`,
  `entity_type`, `canonical_name`, `status` -- `entity_type` BEFORE
  `canonical_name`. The Task 37 brief listed the two the other way round while
  explicitly deferring order to the real file ("confirm the real Monad shape ...
  mirror its conventions, don't invent a divergent style"), so the real file
  won; the decided field NAMES are used verbatim, and the Notion-specific ones
  (`source_notion_page_id`, `notion_kind`, `notion_title`, `exported_at`)
  follow them. `gmv_id`/`entity_type`/`canonical_name` are OPTIONAL and keep
  those three exact positions when present, so a resolved page's frontmatter is
  a prefix-for-prefix superset of the real Monad's first five keys (a test
  asserts that against the real `GMV-000001.md`) and an unresolved page's is
  the same file with those three lines simply not emitted -- they are not
  reordered to the end, because moving them would break the resemblance for the
  6 files that have them in order to help the 436 that do not.
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
  text. `notion_title` appears in BOTH frontmatter and `# NOTION TITLE` on
  purpose: the frontmatter field is the machine-readable identifier (the only
  one an unresolved page has), the section is the verbatim-not-interpreted
  record Task 37 pinned for the alias case. Both are rendered from the same
  single variable, so they cannot drift.

**Deliberate non-goals**, stated so none gets silently "fixed" later:

- **No duplicate detection, and none needed.** Every page is exported
  independently to `<its own page id>.md`, and Notion's page id is a primary
  key, so two distinct pages cannot land on one file -- re-derived on the real
  2026-10-05 run (442 pages across the six data sources, 442 distinct ids).
  The Task 37 version named files `<gmv_id>.md` and therefore had a real
  collision case (two pages resolving to the same `gmv_id` silently
  overwrote each other); that case is now impossible by construction rather
  than by arbitration, which is why this non-goal shrank instead of being
  "fixed". What is still deliberately NOT done: if the same page id ever
  arrived twice, this module does not detect or report it, it just rewrites.
- **No validation, enrichment, web cross-check, or entity-type mapping of the
  page text.** The Notion side of EIC-09 verification does not exist yet and
  inventing it is out of scope by an order of magnitude.
- **No queueing inside `export_notion_page_to_canon()`**, mirroring
  `propose_entity_identity()`'s own contract ("Does NOT queue anything itself
  -- queueing stays the caller's explicit decision"). `main()` is the caller
  that appends, through the real
  `gmv_crawler_entity_identity_proposal_queue.append_entity_identity_proposals()`
  and, by default, the same single queue file the nightly run and the review
  tool already use, so a human has exactly one place to look for pending
  identities. Queuing is a SIDE EFFECT of the export, never a precondition of
  it: `export_notion_page_to_canon()` writes the file first and hands the
  proposal back, so no queue failure can cost a page its file.
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
import re
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

#: The single outcome value: every page this module accepts produces a file.
#: Declared as a named constant rather than a bare string anyway, for the same
#: reason `CANON_STATUS` is -- a caller (and a test) matches against one place,
#: and if a second outcome is ever needed it has an obvious home next to this
#: one. Task 37 had three (`WROTE_CANON_FILE`/`PROPOSED_FOR_REVIEW`/
#: `NO_ENTITY_NAME`); the other two were skip outcomes, and skipping a real
#: page is exactly what this module must no longer do.
OUTCOME_WRITTEN = "WROTE_CANON_FILE"

#: The only characters allowed in a Notion page id used as a file name. Notion
#: page ids are UUIDs (`8-4-4-4-12` lowercase hex, dashes), verified on the
#: real 2026-10-05 run across all 442 pages of the six data sources. The shape
#: is deliberately checked as "a file-name-safe token that does not start with
#: a dot" rather than as "exactly a UUID": requiring the UUID form would make
#: a future, equally legitimate Notion id shape (32 hex digits with no dashes,
#: say) fail the export, while the actual requirement -- that `record["id"]`,
#: which is Notion-controlled, carries no path separator (`/`, `\`), no NUL, no
#: space or shell/glob metacharacter, is not `.`/`..`, and is not a dot-file
#: (a shape Notion never emits) -- is fully expressed by this character class
#: plus the first-character rule. `re.fullmatch` anchors both ends with no
#: `.*` anywhere, which is what makes that first-character rule bite.
_SAFE_PAGE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class CanonExportError(ValueError):
    """Raised when a page cannot produce a canon file.

    Deliberately narrow: only pre-write conditions that would otherwise force
    this module to write an unusable or misleading file.

    - the page has no id, or one this module refuses to put in a path (see
      `_SAFE_PAGE_ID`) -- the file name IS the page id now, so there is
      nothing honest to name the file after;
    - the page has no `notion_kind`, which is a REQUIRED frontmatter field on
      every file, and emitting it empty would assert "Notion says this page is
      of kind nothing";
    - the resolved registry entry cannot state an identity -- a `gmv_id` that
      does not map back to exactly one entry, or an entry with an empty
      `canonical_name`/`entity_type`.

    The registry cases are the same rule
    `gmv_monad_materializer`'s `required_document_fields_not_empty()`
    (M-SCHEMA05) applies to a Monad's frontmatter, re-expressed here rather
    than imported, because that module is inside this task's hard wall: a
    canon file must not become coupled to the Monad materializer even to
    reuse one empty-string check.

    Like Task 37's version of this class, it is NOT caught inside
    `_export_one_data_source()`: it propagates to `main()`, which reports the
    affected data source on stderr and marks the run failed (exit 1). A
    structurally broken page is a fact for a human to fix, not something to
    paper over by exporting the other 100-odd pages of that data source and
    reporting success.
    """


@dataclass(frozen=True, slots=True)
class CanonExportResult:
    """What one page produced.

    `target_path` is always set -- a result object only exists once the file
    has been written. `gmv_id` is set only when the name resolved, and
    `proposal` is set only when it did NOT: those two are mutually exclusive by
    construction, which is what makes "an unresolved page is still filed, and
    still proposed" observable from outside rather than asserted here.
    `entity_name` is `""` for a page Notion left untitled -- such a page is
    still filed, and is deliberately never proposed (see
    `export_notion_page_to_canon()`). `page_id` and `notion_kind` always
    describe the input, so a caller can report every page it saw."""

    entity_name: str
    page_id: str
    notion_kind: str
    outcome: str
    target_path: Path
    gmv_id: str | None = None
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
    *, source_notion_page_id: str, notion_kind: str, notion_title: str, body_text: str,
    now: str, gmv_id: str | None = None, entity_type: str | None = None,
    canonical_name: str | None = None,
) -> str:
    """Pure function: the canon file's exact text. Frontmatter field order
    follows the real Monad (see the module docstring); `# NOTION TITLE` and
    `# NOTION PAGE` carry only what Notion itself said.

    `gmv_id`/`entity_type`/`canonical_name` are all-or-nothing: they are either
    all given (a page whose name resolved to a registry entity) or all left
    `None` (a page it did not), and a partial set is refused rather than
    rendered. `render_canon_markdown()` is the one place that decision can be
    made once, and a file carrying `gmv_id` without `canonical_name` -- or a
    `canonical_name` with no id to attach it to -- is precisely the "this
    pipeline knows who this is" claim the module docstring says this format
    must never make on partial evidence. The check is `all(...)`/`any(...)`
    over exactly these three parameters rather than a per-key truthiness test,
    so an empty string counts as "not supplied" instead of silently rendering
    `gmv_id: ''`."""
    supplied = (gmv_id, entity_type, canonical_name)
    if any(value is not None for value in supplied) and not all(
        str(value or "").strip() for value in supplied
    ):
        raise CanonExportError(
            "gmv_id, entity_type and canonical_name must be supplied together and "
            f"non-empty; got {supplied!r}."
        )

    # Insertion order IS the field order (sort_keys=False), and the three
    # optional keys are skipped rather than appended, so a resolved page's
    # frontmatter is a prefix-for-prefix superset of the real Monad's first
    # five keys -- asserted against the real 03_STATE/ombra/GMV-000001.md by
    # tests/test_gmv_notion_canon_export.py, not merely claimed here.
    frontmatter: dict[str, str] = {"schema": NOTION_CANON_SCHEMA_ID}
    for key, value in (("gmv_id", gmv_id), ("entity_type", entity_type),
                       ("canonical_name", canonical_name)):
        if value is not None:
            frontmatter[key] = str(value)
    frontmatter["status"] = CANON_STATUS
    frontmatter["source_notion_page_id"] = source_notion_page_id
    frontmatter["notion_kind"] = notion_kind
    frontmatter["notion_title"] = notion_title
    frontmatter["exported_at"] = now
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
    notion_kind: str, registry: dict | None = None,
) -> CanonExportResult:
    """Export one Notion page as one `<notion_page_id>.md` canon file. Always.

    `record` is one `adapter_notion._record()` output (the `--with-bodies`
    shape described in the module docstring); `entity_name` is passed
    explicitly rather than read from `record["titolo"]` because `_record()`
    substitutes `"(senza titolo) <id>"` for a missing title, and a placeholder
    must not be offered to entity resolution as a name -- the CLI reads the
    config's title property instead and passes `""` when it is empty. That same
    substitution is why `notion_title` is rendered from `entity_name` and not
    from `record["titolo"]`: this module has no path that can put the
    placeholder in a required frontmatter field.

    `notion_kind` is the raw `config.json` `entita` key for the data source
    this page came from (`artista`, `mostra`, ...). Required, and recorded
    verbatim: it is Notion's own label, NOT a mapping onto the governed
    `entity_type` vocabulary, which stays a registry-only assertion.

    **Resolution failure does not skip the file.** An `entity_name` that
    resolves gets `gmv_id`/`entity_type`/`canonical_name` in the frontmatter;
    one that does not gets a file with those three keys absent plus a real
    `EntityIdentityProposal` handed back for the caller to queue. Proposed,
    never minted; filed, never gated.

    A page Notion left untitled (`entity_name` empty/whitespace) is still
    filed, with `notion_title: ''`, but is deliberately NEVER proposed:
    queueing a blank `raw_name` would put a non-name in the one human review
    queue. (`propose_entity_identity()` keeps blank names queueable on purpose
    for the crawler's own extractor, whose empty `subject_raw` is a real bug
    signal; a Notion page that simply has no title is not that signal, it is
    just untitled.) Zero of the 442 real pages are in this state, so the
    behaviour is a contract, not an observed split.

    The file name is the page's own id and nothing else -- no Notion string
    and no registry string ever reaches the path beyond the id itself, which
    `_SAFE_PAGE_ID` restricts to a file-name-safe token.

    Never imports or calls the Monad/atom modules (see the module docstring's
    hard-wall section).
    """
    page_id = str(record.get("id") or "").strip()
    if not page_id or not _SAFE_PAGE_ID.fullmatch(page_id):
        raise CanonExportError(
            f"page id {page_id!r} cannot be used as a canon file name. Notion page ids "
            "are UUIDs; an empty or path-bearing id means the page cannot be filed "
            "under its own identity, which is the only naming this module uses."
        )
    kind = (notion_kind or "").strip()
    if not kind:
        raise CanonExportError(
            "notion_kind is a required frontmatter field and was blank; pass the raw "
            "config.json 'entita' key for the data source this page came from."
        )
    if registry is None:
        registry = _load_entity_registry()
    name = (entity_name or "").strip()

    # Enrichment, in one pass: resolve first, and propose only on failure --
    # the same two reused resolver functions
    # `gmv_crawler_orchestrator.process_document()` uses, called in the order
    # that keeps one lookup per question: `propose_entity_identity()` returns
    # None for exactly the names that resolve and a proposal for every name
    # that does not, so asking it first would mean calling
    # `resolve_entity_gmv_id()` twice to recover the id it declines to carry
    # (`EntityIdentityProposal` deliberately has no `gmv_id` field). The
    # difference from Task 37 is that neither branch returns early: both fall
    # through to the same write.
    gmv_id = resolve_entity_gmv_id(name, registry) if name else None
    proposal: EntityIdentityProposal | None = None
    entry: dict | None = None
    if name:
        if gmv_id is None:
            proposal = propose_entity_identity(
                name, registry,
                source_id=f"notion:page/{page_id}",
                evidence_excerpt=name,
            )
        else:
            entry = _registry_entry_for(registry, gmv_id)
            empty = _registry_entry_fields_not_empty(entry)
            if empty:
                raise CanonExportError(
                    f"registry entry for {gmv_id} has empty {', '.join(empty)}: a canon "
                    "file's frontmatter has no other gate for it. Fix the registry by hand."
                )

    target_path = target_dir / f"{page_id}.md"
    atomic_write_text(target_path, render_canon_markdown(
        source_notion_page_id=page_id,
        notion_kind=kind,
        notion_title=name,
        body_text=str(record.get("corpo") or ""),
        now=now,
        gmv_id=None if entry is None else str(entry["gmv_id"]),
        entity_type=None if entry is None else str(entry["entity_type"]),
        canonical_name=None if entry is None else str(entry["canonical_name"]),
    ))
    return CanonExportResult(
        entity_name=name, page_id=page_id, notion_kind=kind, outcome=OUTCOME_WRITTEN,
        target_path=target_path, gmv_id=gmv_id, proposal=proposal,
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

    `entity_spec_key` is the `config.json` `entita` key itself and is passed
    straight through as `notion_kind`: it is Notion's own label for the
    collection, carried verbatim and never mapped onto the governed vocabulary.
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
            now=now, notion_kind=entity_spec_key, registry=registry,
        ))
    return results


def build_parser() -> argparse.ArgumentParser:
    """The CLI's argument parser, built in one place so `main()` stays about
    doing the run and a test can read the real defaults off the real parser
    object instead of re-deriving them from the source text. In particular
    `--proposal-queue`'s default being the SHARED human queue is part of this
    module's contract (see `main()`), so it is made inspectable rather than
    merely asserted in a docstring."""
    parser = argparse.ArgumentParser(
        description="Esporta TUTTE le pagine Notion Area35 in 03_STATE/area35_canon/<notion_page_id>.md (sola lettura su Notion)."
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Read every configured Notion data source and file every page.

    `--entities` narrows the run the same way `notion_extract.py` narrows it
    (comma-separated keys of `config.json`'s `entita`), so a single-entity
    live check does not cost six full database walks.

    **The registry is not consulted as a gate anywhere in this function.**
    `--proposal-queue` defaults to the SHARED queue the crawler nightly run and
    the review tool already append to
    (`01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl`), so a
    plain run both archives every page AND grows the human review queue with
    every name the registry does not know yet -- which is what eventually lets
    a later export enrich more pages. Pointing `--proposal-queue` elsewhere
    remains available (that is how a test or a dry run keeps the live queue
    untouched) but is not what a normal run does.

    Exit codes: 0 every requested data source was read and the identity queue
    was appended to, whether or not any name resolved (an unresolvable name is
    not a failure, it is the expected state for 436 of 442 real pages);
    2 unusable arguments/credentials/config; 1 at least one data source could
    not be read at all, or the proposal queue could not be appended to, both
    reported on stderr rather than hidden behind the "continue with the rest"
    behavior.
    """
    args = build_parser().parse_args(argv)

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
    untitled = 0
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
        written.extend(results)
        untitled += sum(1 for result in results if not result.entity_name)
        # Every page of every data source is filed either way, so the only
        # thing a result can still carry is the unresolved-identity proposal;
        # collecting them here and appending once at the end is what makes the
        # queue a SIDE EFFECT of a complete export rather than a step that
        # could stop it.
        proposals.extend(r.proposal for r in results if r.proposal is not None)
        print(f"  {key:12} {len(results)} pagine")

    # Last, and separately guarded: queueing is a SIDE EFFECT of the export,
    # never a step in it. Every file is already on disk by this point, so a
    # queue that cannot be appended to must not throw away the run's real
    # product -- but it must not exit 0 either, or a scheduled caller would
    # read a success over a run whose identity half silently did not happen.
    queued = 0
    queue_failed = False
    queue_path = Path(args.proposal_queue).expanduser()
    try:
        queued = append_entity_identity_proposals(proposals, queue_path, now=args.now)
    except OSError as exc:
        queue_failed = True
        print(
            f"[errore] coda proposte non scritta in {queue_path}: {exc}. "
            f"{len(written)} schede canon sono gia' state scritte; riesegui solo la coda.",
            file=sys.stderr,
        )
    enriched = sum(1 for result in written if result.gmv_id)
    print(
        f"\n{len(written)} schede canon scritte in {target_dir} "
        f"({enriched} con gmv_id dal registro, {len(written) - enriched} senza); "
        f"{queued} proposte in coda; {untitled} pagine senza titolo (non proposte)."
    )
    # Only the enriched minority is listed: with every page filed, printing all
    # of them would bury the one fact a reader of this output cannot get from
    # the directory itself, which is which pages the registry already knows.
    for result in written:
        if result.gmv_id:
            print(f"  {result.gmv_id} <- {result.entity_name} ({result.page_id})")
    if failed:
        print(f"[errore] {len(failed)} data source non lette: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 1 if queue_failed else 0


if __name__ == "__main__":
    sys.exit(main())
