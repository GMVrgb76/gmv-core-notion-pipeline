# OpenCode Task 39 — extract real exhibition dates from Area35 `event` canon pages into gbrain's timeline

**Status: DRAFT TASK.**

## Why

[[project_gmv_notion_canon_gbrain_fix]] (today's prior work, 2026-10-05) fixed gbrain's generic
import so `03_STATE/area35_canon/*.md` pages get a real `type`/`title` instead of `concept`/"NOTION
TITLE". That made categorical questions ("list all persons") work. It did NOT make chronological
questions work ("what did Area35 show in 2016?") — exhibition dates live only as free Italian prose
inside each `type: event` page's body, not as a structured field gbrain can sort or filter on.

Tried `gbrain extract timeline --source db --type event --infer-dates` (gbrain's own built-in
heuristic): it correctly found all 95 real `event` pages but produced **zero** timeline entries —
the heuristic doesn't parse Italian month names or en-dash date ranges. This task is the real fix:
read the actual prose, extract the actual Area35-relevant date(s), write them into gbrain's
structured timeline via `gbrain timeline-add <slug> <date> <text>` (see `gbrain timeline --help`,
`gbrain timeline-add --help` for the exact real signature — confirm it, don't assume from this
brief).

## The real data is messier than one regex — read it before coding

I pulled several real `event` pages today and the date-bearing line is NOT one consistent pattern.
Real examples, verbatim, from real pages already in `03_STATE/area35_canon/`:

- `Date: 3 marzo – 7 aprile 2016` (page "In flore furoris", en-dash with spaces)
- `Date: 26 ottobre – 15 novembre 2016` (page "UNREST")
- `Date: 23 aprile–20 giugno 2022` (page "Purple Overthoughts — Federico Garibaldi", en-dash **no**
  spaces)
- `Periodo: 14 marzo – 14 maggio 2017` (page "AURUM. Ernesto Morales" — different label, "Periodo"
  not "Date")
- `Date Area35: 13 aprile – 6 maggio 2012` (page "In Itinere. Tra Arte e Design" — yet another label
  variant, used specifically because this page ALSO lists dates for two other venues the same
  exhibition toured to — see next point)
- Some pages have **multiple** date ranges for **different venues**, only one of which is the
  Area35 stage. "In Itinere" (above) lists, in a "Cronologia verificata del progetto" section:
  `13 aprile – 6 maggio 2012: tappa Area35 Art Gallery, Milano.` alongside a DIFFERENT range for
  "Institut Français Milano" and another for "Chiesa di San Francesco, Pordenone" — a naive
  first-date-match would as easily grab the wrong venue's dates as the right one.
- Some pages explicitly flag a secondary-source date as a **known discrepancy**, not canonical:
  "In Itinere" also says "Artribune... Riporta 13 aprile – 7 maggio 2012; la data finale è
  registrata come discrepanza rispetto al catalogo" — the parser must prefer the line the page
  itself marks canonical, not every date-shaped string in the body.
- Some pages have **no** precise date at all, only a year, and say so explicitly: page "12 Shoes —
  una per ogni ora del giorno" has `Anno: 2016` and no Date/Periodo line, with
  `STATO EDITORIALE\nDa verificare: date precise...` — this is a real, intentional gap in the
  source, not a parser failure. Do not invent a day/month for these.

**Do not design the parser from these 7 examples alone.** Read the real, current text of every one
of the ~95 real `type: event` pages in `03_STATE/area35_canon/` (query gbrain or grep the files
directly — confirm the real count first, don't trust "95" blindly) before writing extraction logic,
and catalogue the actual distinct date-line label variants and the actual distinct ambiguous-page
shapes you find. Report that catalogue before or alongside the implementation — it's the real
spec, this brief is only a starting sample.

## What to build

1. A script (pick the right location — `10_API/` matches the sibling exporter
   `gmv_notion_canon_export.py`; decide and say why) that:
   - Reads every real `type: event` page under `03_STATE/area35_canon/` (or queries gbrain for
     them — your call, justify it).
   - For each, extracts the canonical Area35 date range (start, and end if present) using the real
     label/format variants you catalogued. Year-only pages get a year-level result, explicitly
     marked as such (lower precision than a day-level date) — never fabricate a day or month gbrain
     can't actually tell you.
   - For pages with multiple venues' dates, picks the one explicitly tied to Area35 (several real
     pages literally label it "Date Area35:" or name "Area35 Art Gallery" directly in the same
     line/sentence — use that signal) and skips/flags the rest rather than guessing.
   - For pages where the text itself flags a date as a non-canonical discrepancy, exclude that one.
2. **Mandatory `--dry-run` mode that is the default** — print/write a report (one row per page:
   slug, title, extracted date(s) or "NONE — reason", confidence/precision level) without calling
   `gbrain timeline-add` or touching the live database. A human reviews this report before any real
   run.
3. The real write path (`--apply` or similar explicit flag) calls the real `gbrain timeline-add
   <slug> <date> <text>` CLI once per page with an extracted date. **Before assuming this needs
   `gbrain serve` stopped first**: check whether `timeline-add` is a CLI-only direct-PGLite command
   (like `gbrain extract`, `gbrain import` — needs serve stopped) or routes through the running
   HTTP server like `gbrain mcp grant` turned out to (today's session found real inconsistency here
   — some CLI subcommands go through the live server, some open the file directly and conflict with
   it; confirm empirically which this is, don't assume either way).
4. Pages where no reliable date can be extracted: do NOT call `timeline-add` for them. List them
   explicitly in the report as skipped, with the real reason (no date line found / only year / only
   non-canonical/ambiguous venue dates found).

## Constraints

- Do not touch `gmv_notion_canon_export.py` or re-run the Notion export — the canon files are
  already correct for this task, this is a read-only-on-the-canon-files, write-only-to-gbrain's-
  timeline operation.
- Do not touch the EIC-10 wall (no Monad/atom imports) — same discipline as the sibling exporter.
- `03_STATE/area35_canon/` is read-only input here; do not modify those files.
- gbrain's PGLite engine is single-writer — if the real write path needs `gbrain serve` stopped,
  say so explicitly in your report and stop/restart it yourself around the write step (mirror
  `~/.gmv_scripts/gbrain_morning_sync.sh`'s existing pattern: `pkill -f "gbrain serve --http"`,
  wait, run the write step, restart with `GBRAIN_ADMIN_BOOTSTRAP_TOKEN` read fresh from `~/.zshrc`).
  Never leave gbrain's server down when you're done — AnythingLLM and other live consumers depend
  on it being up.
- If, after reading the real 95 pages, the format turns out too inconsistent for a reliable general
  parser (more venue-ambiguity cases than clean ones, say), **say so plainly and report the real
  split** (how many pages parsed cleanly vs. how many are genuinely ambiguous/undated) rather than
  forcing a brittle heuristic that silently mis-assigns dates. A smaller number of correct timeline
  entries is better than a larger number with wrong-venue or fabricated dates.

## Report back

1. The real count of `type: event` pages found, and your catalogue of the actual distinct
   date-line label variants / ambiguous-page shapes across all of them (not just the 7 examples
   above).
2. Dry-run report: how many pages got a clean date extraction, how many got year-only, how many
   were skipped and why (grouped by reason).
3. Whether `gbrain timeline-add` needed `gbrain serve` stopped or worked live — state which, and how
   you confirmed it.
4. If you ran the real `--apply` step: confirmation `gbrain serve` is back up and reachable
   afterward (`curl http://localhost:3131/health` or equivalent), and a few real example timeline
   entries read back via `gbrain timeline <slug>` to prove it actually landed.
5. Exact diff / new file(s), `git status --short`.
