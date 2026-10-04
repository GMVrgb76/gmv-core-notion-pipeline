# OpenCode Task 22 — investigation only: Garibaldi's real predicate gap

**Status: DRAFT TASK — approved plan, not yet executed.**
**Read-only investigation. No registry writes, no new atoms, no commits.**

## Why

A live re-extraction of Federico Garibaldi's `2026_06_17_MUTUALART_BIOGRAPHY.md` (Task 18)
produced 0 atoms, while the same session's live extraction of Danilo Bucchi's document produced
2 (Task 20) — only because Bucchi's `"partecipa"` predicate happened to already be mapped. This
task answers: what predicates DID Garibaldi's document actually produce, and are any of them
genuinely missing from `00_CONFIG/crawler_predicate_text_mapping.json` for a defensible reason (not
just "nobody mapped it yet")?

## Steps

1. Re-run `extract_candidates()` on the same real document (Dropbox locator
   `/GMV_MASTER_SYSTEM/01_AREA35_MASTER/01_ARTISTS/GARIBALDI_Federico/00_MASTER/2026_06_17_MUTUALART_BIOGRAPHY.md`),
   `temperature=0, seed=42`, via `DropboxConnector` (not a local filesystem read — confirm you're
   using the real API, learned the hard way in Task 20/21).
2. List every distinct raw predicate text extracted, with one real example subject/object per
   predicate.
3. For each, check `00_CONFIG/crawler_predicate_text_mapping.json`: already mapped? If not, would
   it map cleanly onto an EXISTING governed predicate in `GMV_ONTOLOGY_REGISTRY_v0.1.json` (name
   the candidate predicate_id and check domain/range against the real subject/object types), or is
   it genuinely out of scope (e.g. the GARBLED_TEXT / CONSTRUCTION_SAFETY_DOCUMENT-shaped noise
   already seen in the real-estate pipeline)?
4. Do NOT edit `crawler_predicate_text_mapping.json` yourself — this is curation, a human decision
   (same discipline as `confirm_predicate_mapping()`). Just produce the candidate mapping table.

## Report back

A table: predicate text | example subject/object | already mapped? | your candidate predicate_id
(or "no clean fit, because X") | domain/range check pass/fail. Plus: your honest one-line verdict
on whether Garibaldi's zero-atom result is "just needs curation" or "this document genuinely has
no RELATION-shaped facts in the governed vocabulary yet."
