# OpenCode Task 23 — investigation only: quantify classify_entity_types() non-determinism

**Status: DRAFT TASK — approved plan, not yet executed.**
**Read-only investigation. No registry writes, no commits.**

## Why

The codebase documents ONE anecdote of `classify_entity_types()` returning different results for
the same real name across separate runs ("Le Stanze della Fotografia": INSTITUTION once,
EXHIBITION another time) — cited as justification for always treating MODEL_INFERENCE results as
`needs_verification=True`. That's one data point. This task gets a real rate, not another anecdote.

## Steps

1. Pick 5 real, previously-seen entity names that are NOT in `area35_known_artists.json` or
   `area35_known_institutions.json` (so they genuinely hit the model path, not the roster
   shortcut) — use 5 distinct real names from `01_RUNTIME/gmv_crawler/entity_identity_proposal_queue.jsonl`
   (excluding obvious non-entities like "Roma"/"ITALIA" — pick plausible real person/org/event
   names).
2. Call `classify_entity_types()` on each name **5 separate times**, `temperature=0, seed=42`
   EVERY time (same determinism settings the real pipeline uses) — 25 calls total.
3. For each of the 5 names, report whether all 5 calls agreed on `entity_type`, and if not, exactly
   which types appeared and how often.
4. Separately, repeat the same 5-calls-per-name experiment WITHOUT `temperature`/`seed` (Ollama's
   own defaults) for comparison — does forcing `temperature=0, seed=42` actually eliminate the
   flip, or only reduce it?

## Report back

A table: name | temp=0/seed=42 results (5 calls) | agreement rate | default-sampling results (5
calls) | agreement rate. Plus your honest verdict: is this a 5%-of-cases footnote or a real,
frequent reliability problem for THIS specific step of the pipeline?
