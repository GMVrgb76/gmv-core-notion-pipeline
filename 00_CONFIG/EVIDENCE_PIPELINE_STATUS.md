# GMV Evidence Pipeline & Notion Publish — Status

## Scope and relationship to PROJECT_STATUS.md

This document tracks the **Dropbox archive → local LLM → Notion candidate →
Notion publish** pipeline (`10_API/gmv_evidence_pipeline.py`,
`gmv_notion_candidate.py`, `gmv_notion_multi_candidate.py`,
`gmv_notion_publish.py`, `notion_publish.py`, `gmv_review_server.py`, and
the `gmv evidence *` CLI subcommands).

`00_CONFIG/PROJECT_STATUS.md` states in its own Rule 1 that it is "the
single operational ledger for this project," and its Document Index notes
that documents outside the scope of the REBASE 001 / Post-REBASE 001 /
Core Integrity effort exist under `00_CONFIG/` without being indexed there.
This document is one of those: the evidence/Notion pipeline is a separate
workstream from Core Integrity (SQLite persistence boundary, Service
Registry, OID contract, etc.) and has never followed
`PROJECT_STATUS.md`'s ADR-driven Task Completion Protocol. This file exists
so the pipeline's own decisions are discoverable from `00_CONFIG/` without
either (a) being silently absent from any tracked document, or (b) being
folded into a ledger governed by a stricter protocol this track doesn't
follow. It does not supersede or duplicate `PROJECT_STATUS.md`.

Full reasoning for each decision below lives in the referenced commit/PR,
not here — this is a summary ledger, not the source of truth.

## Current state (as of 2026-09-10)

- The pipeline is live and has been run end-to-end against real archive
  data (Federico Garibaldi) through every stage: `scan` → `extract` →
  `analyze` (local Ollama, `gemma4:12b`) → `resolve` → `multi-candidate` →
  `review`. No live Notion write has been performed yet in this track —
  every real run so far has stopped at human review (`gate: REVIEW_REQUIRED`).
- `gmv_notion_candidate.py` (single-entity) and
  `gmv_notion_multi_candidate.py` (multi-entity fan-out: discovers
  mostra/persona/istituzione/opera mentioned in an artist's claims) both
  produce bundles publishable through the same, single
  `gmv_notion_publish.py::publish_bundle()` — no second publish code path
  exists.
- A local, stdlib-only review server (`gmv evidence review`) lists a run's
  bundles and lets a human preview/approve them without duplicating
  `publish_bundle`'s safety checks.

## Key architectural decisions

| Category | Decision | Reference |
|---|---|---|
| **Bundle format** | Multi-entity bundles converge on the same `NOTION_PATCH.json`/`NOTION_PAYLOAD.json` shape as single-entity bundles (real Notion property names resolved via `config.json`, `operation` CREATE/UPDATE, `keep`, `body_gate`) instead of `gmv_notion_publish.py` learning a second vocabulary. | PR #13 (`c82ee93`), 2026-09-09 |
| **Relation writes** | No relation-writer exists anywhere in this codebase. Every relation claim (single or multi-entity path) is unconditionally `CONFLICT`, never `ADD`/`UPDATE`/`RELATE` — Notion relation properties are full-list-replace and nothing here merges against an existing list yet. | PR #13 (`c82ee93`), 2026-09-09 |
| **Duplicate-page guard** | Before any `CREATE`, `gmv_notion_publish.py::publish_bundle()` performs a live, exact-title Notion query (`notion_publish.py::find_existing_page_id`) and refuses to publish if a page with that title already exists — closes a prior gap where nothing re-checked this at write time. | PR #13 (`c82ee93`), 2026-09-09 |
| **Silent-overwrite guard** | `gmv_notion_multi_candidate.py::build_entity_patch` compares a proposed field value against the entity's existing value before writing: `ADD` if empty, silently nothing if already equal, `CONFLICT` (never auto-applied) if a different value already exists. Deliberately **stricter** than `gmv_notion_candidate.py`'s single-entity path, which treats a differing property value as an auto-applied `UPDATE` — the multi-entity discovery path stays conservative until validated on more than one real artist. | PR #13 (`c82ee93`), 2026-09-09 |
| **Ambiguous-match guard** | `compare_entity` returning `AMBIGUOUS` (more than one existing Notion row with the same title) never falls through to `existing is None → CREATE`; `operation` stays undecided and the gate stays `REVIEW_REQUIRED`. | PR #13 (`c82ee93`), 2026-09-09 |
| **Body-text publication** | Multi-entity bundles always set `body_gate: "BODY_REVIEW_REQUIRED"` — the free-text body routing (`build_entity_body`) is a single fallback section, not the section-routed, semantically-checked logic `gmv_notion_candidate.py::attach_body_adapter` uses, so no multi-entity body text is ever auto-published. | PR #13 (`c82ee93`), 2026-09-09 |
| **Review interface** | First slice of the "GMV Human Interface" (architecture decided 2026-08-28, see the Notion page "Notion Page Extraction Candidate"): a local, stdlib-only web server, GUI as presentation layer only. Every action is a direct, unmodified call into `publish_bundle()` (`input_fn` answering "n" for preview, "y" for approval) — never a duplicated check sequence. Always a manually-started foreground process bound to `127.0.0.1`, never a LaunchAgent/scheduled service (no Service OID/Service Registry entry exists for it). | PR #13 (`c82ee93`), 2026-09-09 |
| **Review interface: bundle listing** | No cached manifest for a run's bundles — always a runtime scan of `run_dir/entities/*/` reading files the pipeline already writes (`entity.json`, `NOTION_PAYLOAD.json`, presence of `PUBLISHED.json`). A cache would need manual invalidation on every publish and become a second, parallel status vocabulary. | PR #13 (`c82ee93`), 2026-09-09 |
| **Review interface: content visibility** | The entity review page always shows the bundle's own `EVIDENCE.md` and `body.proposed_markdown` (read-only) above `publish_bundle`'s own screen text, because `publish_bundle` returns immediately with a one-line rejection whenever the gate isn't `READY_FOR_NOTION` — the common case right after a fresh `multi-candidate` run — without ever reaching the full review screen. | PR #14 (`93b928c`), 2026-09-10 |

## Timeline

| Date | Event | Commit/PR |
|---|---|---|
| 2026-09-01 | `gmv_notion_multi_candidate.py` created (multi-entity fan-out logic, `route_claim`/`discover_entities`) — dry-run only, never wired to publish. | `dcbfe6f` |
| 2026-09-09 | Multi-entity bundles wired into real Notion publish end-to-end: bundle-format convergence, `evidence multi-candidate`/`evidence review` CLI subcommands, duplicate-page guard, silent-overwrite guard. Verified via a real run against Federico Garibaldi's archive (7 entities discovered: 1 artista, 3 mostre, 1 persona, 2 istituzioni, all `REVIEW_REQUIRED`, none published). | PR #13, merge `bb0d4ad`; agent-memory reconciliation `dcf387a` |
| 2026-09-10 | Fixed review server showing only a one-line rejection instead of the bundle's actual evidence/proposed text for non-`READY_FOR_NOTION` bundles (found via the same real Federico Garibaldi run). | PR #14, merge `2fe8f12` |

## Known gaps (not yet built — do not assume otherwise)

- **No relation-writer.** Writing a Notion relation property safely requires merging against the existing list (`keep.relations`); nothing implements or tests this today. `check_staleness` only ever compares `keep.properties`.
- **`field_hints`/`relation_hints` in `00_CONFIG/notion_page_templates.json` are minimal.** Most real claims fall through to free-text body content rather than a structured property/relation — confirmed on the real Federico Garibaldi run (0 structured operations proposed across all 7 discovered entities).
- **Opera-entity discovery does not exist.** The semantic extraction stage doesn't isolate individual artworks as distinct claims/entities.
- **Web-retrieval pause/resume for pending relation targets is not wired in.**
- **Multi-entity discovery is validated on one real artist only** (Federico Garibaldi, and earlier Riccardo Paternò Castello for the single-entity path). Sponsor/istituzione routing is unit-test-only for the multi-entity path.
- **The review server MVP has no auth, no multi-user concurrency, and no inline editing** — approve/reject only, single local user, by design for this first iteration.
- **No live Notion write has been exercised yet through this track's own testing** — only dry-run bundles and the duplicate/staleness guard logic have been validated against real Notion reads; a real `apply_patch` (live write) has not been performed as part of this work.

## Where to look for more detail

- Commit messages and PR descriptions on `GMVrgb76/gmv-core-notion-pipeline` (PRs #13, #14) — the primary source of reasoning for each decision above.
- `10_API/gmv_notion_multi_candidate.py`'s own module docstring, which tracks its own known limitations independently of this file.
- `.claude/agent-memory/gmv-code-architect/MEMORY.md` — a Claude Code assistant's own working notes on this track's architecture; useful context but not a project source of truth, and not guaranteed current.
