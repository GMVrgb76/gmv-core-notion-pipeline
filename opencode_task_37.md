# OpenCode Task 37 — export Notion Area35 pages into `03_STATE/area35_canon/`, parallel to the Monad folder

**Status: DRAFT TASK — approved design, not yet executed.**

## Why

Area35's Notion pages are synthesized from the same Dropbox archive the crawler/Monad pipeline reads,
plus independent web cross-checking — the user treats this as the gallery's current operational
"canon", but it has NOT passed the Monad pipeline's own fact-by-fact EIC-09 verification. The
directing Claude session + the `gmv-code-architect` agent (consulted 2026-10-05) designed where this
should live without writing any code; this task builds it.

**Recommended destination, already decided**: `03_STATE/area35_canon/`, parallel to the existing
`03_STATE/ombra/` (the Monad folder) — same "never Git" governance class, confirmed inherited
automatically from the parent `03_STATE/` entry in `00_CONFIG/SOURCE_RUNTIME_BOUNDARIES.md` and
`.gitignore:23` (a literal `/03_STATE/` pattern covering the whole tree, not just `ombra/`). No new
governance file or `.gitignore` line is needed.

**Keying, already decided**: one file per entity, named `<gmv_id>.md` (e.g. `GMV-000001.md`) — the
SAME `gmv_id` the Monad for that entity uses, from `00_CONFIG/gmv_entity_registry.json`. This is
deliberate: it lets a human or GBrain later compare "what the Monad has verified" against "what
Notion's canon says" for the exact same entity. **Never a separate keying scheme.**

**Frontmatter, already decided** (confirm the real Monad shape in `03_STATE/ombra/GMV-000001.md`
before finalizing field names/order — mirror its conventions, don't invent a divergent style):
```yaml
schema: GMV_NOTION_CANON_SNAPSHOT_V1   # never GMV_KNOWLEDGE_MONAD_V1 -- this is not a Monad
gmv_id: GMV-000001
canonical_name: Federico Garibaldi
entity_type: ARTIST
status: canon_unaudited                # new value, used nowhere else -- this task defines it
source_notion_page_id: <page_id>
exported_at: <ISO timestamp>
```

## Hard constraints

1. **Reuse the existing read-only Notion tooling — do not write a new Notion client.**
   `adapter_notion.py` (repo root) already does authenticated, read-only Notion API calls
   (`credentials.py` resolves `NOTION_TOKEN`) and supports `--with-bodies` to fetch page text (bios/
   critical texts), producing `rows.json`. `notion_extract.py` is the other existing reader. Read
   both in full before designing anything new; your new code should call into or adapt these, not
   duplicate their HTTP/auth logic.
2. **Credentials may not be available in this worktree — verify first, do not fabricate.**
   Confirmed before this brief was written: no `config.json` exists here, `NOTION_TOKEN` is not set
   in this shell's environment, and `credentials.py`'s file-fallback path was not checked for a real
   file. Check whether a real token/config exists anywhere reachable (another worktree, a documented
   credentials file, env on a different shell) before concluding live proof is possible. If nothing
   real is found, say so plainly in your report and stop at the fixture-tested stage — do not invent
   a fake token or skip verification silently.
3. **Entity resolution must reuse the crawler's existing discipline, never invent a new one.** A
   Notion page for an entity not yet in `00_CONFIG/gmv_entity_registry.json` must go through the same
   path the crawler uses today (`gmv_crawler_entity_resolver.py` / `resolve_entity_gmv_id()` /
   `gmv_crawler_entity_proposal_queue.py`) — proposed, never auto-minted, never auto-written as a new
   canon file until a human confirms the entity. Read these modules before designing the new one's
   entity-matching step.
4. **Hard wall against the Monad pipeline — this task must not touch it.** Do not modify anything
   under `03_STATE/ombra/`, `gmv_monad_materializer.py`, `gmv_crawler_atom_builder.py`,
   `gmv_crawler_relation_atom_builder.py`, or any atom-STATUS logic. Per **EIC-10**
   (`00_CONFIG/EPISTEMIC_INGESTION_RULES_v0.2.json`): "Derived GMV Masters are assertions, not
   primary evidence... cannot alone upgrade uncertain claims to VALID" — this new canon content must
   never be wired as an input to anything that sets or changes an atom's STATUS. If you find any
   existing code path that could let this happen, flag it, do not silently guard it yourself without
   asking first (Group B judgment call).
5. **Do not touch GBrain or anything that imports into it.** Pushing `03_STATE/area35_canon/` into
   GBrain is a separate, already-decided-elsewhere step (a daily launchd job handles a different
   folder today; extending it to this one is the directing session's call, not yours here).
6. **New module location**: put it alongside the existing Notion tooling rather than inside
   `10_API/` unless you find a real precedent showing `10_API/` is the right home for Notion-reading
   code specifically (check how `gmv_notion_candidate.py` etc. are organized vs. `adapter_notion.py`
   — they may belong to two different layers; ground the choice in what you find, don't guess).

## Steps

1. Read in full: `adapter_notion.py`, `notion_extract.py`, `credentials.py`, one real Monad file
   (`03_STATE/ombra/GMV-000001.md`), `10_API/gmv_monad_materializer.py` (for its real file-writing
   pattern — atomic write, etc. — mirror it, don't reinvent), `00_CONFIG/gmv_entity_registry.json`,
   and the entity-resolution/proposal-queue functions named in constraint 3.
2. Check real credential availability per constraint 2. Report exactly what you found (present,
   partial, or absent) before writing any code that assumes one way or the other.
3. Design and build one new function (name and exact module location per constraint 6) that takes a
   single Notion page's data (shape matching what `adapter_notion.py --with-bodies` actually
   produces — confirm the real shape, don't assume) and writes one `03_STATE/area35_canon/<gmv_id>.md`
   file with the frontmatter above plus the page's real body text, using the existing entity-
   resolution discipline for `gmv_id` (constraint 3) and the existing atomic-write pattern
   (constraint 1's Monad materializer precedent).
4. Tests: realistic fixtures covering (a) a known entity already in the registry — correct file,
   correct path, correct frontmatter; (b) an unrecognized entity — goes to the proposal queue, NO
   canon file written; (c) confirm nothing here ever calls or imports anything from the Monad/atom
   modules named in constraint 4 (an explicit test asserting this, e.g. via `monkeypatch` raising if
   a forbidden function is called, same convention as prior tasks' orchestrator tests).
5. Live proof: ONLY if step 2 found real, usable credentials — run the real export against one real
   Notion page for an entity already in the registry (prefer Garibaldi/GMV-000001 or Bucchi/
   GMV-000002, both already confirmed real entities) and report the real file produced. If
   credentials are not available, state this plainly as the reason live proof was not done — this is
   an acceptable, expected outcome, not a failure to hide.
6. Run `.venv/bin/python -m pytest tests/ -q` / `ruff check .` — report the result. Current known
   baseline (confirm it's still the same, don't assume): 1 pre-existing failure
   (`test_runtime_git_policy.py`, `personal_absolute_path` findings, unrelated to this task) — note
   if your changes add or remove any findings from that same scanner (`scripts/check_runtime_git_policy.py`),
   same discipline as Task 35's audit caught for a prior commit.

## Report back

1. Real credential-availability finding (step 2) — present/partial/absent, and where you checked.
2. The new module's real path and function signature, and why that location (constraint 6).
3. How entity resolution was wired (step 3) — real code reused, not reinvented.
4. Test results, including the explicit non-interference test (step 4c).
5. Live proof result, or the explicit reason it was not possible (step 5).
6. Test/ruff results and baseline comparison (step 6), exact diff, `git status --short`.
