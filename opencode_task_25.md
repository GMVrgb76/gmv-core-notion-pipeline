# OpenCode Task 25 — investigation only: classify_entity_types() non-determinism, REAL batch shape this time

**Status: DRAFT TASK — approved plan, not yet executed.**
**Read-only investigation. No registry writes, no commits.**

## Why this supersedes Task 23's result

Task 23 tested `classify_entity_types()` one name per call, 5 names mostly single cities
(Singapore, New York, Pechino, Alessandria d'Egitto) — reported 100% stability both with and
without `temperature=0/seed=42`, including for "Le Stanze della Fotografia", the exact name the
codebase's own docstring documents as having flipped between INSTITUTION and EXHIBITION in real
use. That mismatch is the tell: **the real function never calls the model one name at a time** —
its own docstring states "Unmatched entities go to ONE `_classify_via_ollama()` call for the whole
sub-batch." A single-name prompt is a much easier, more stable case than a real multi-name batch
where the model has to stay consistent across many names at once. Task 23's test almost certainly
did not reproduce the real risk condition. This task fixes that specific gap — nothing else about
Task 23's work needs redoing.

## Steps

1. Build ONE real batch of `CandidateEntity` objects matching what Bucchi's actual document would
   produce for its unmatched (non-roster) names — reuse the real names already established in this
   session's prior work: `EMERGENZE FESTIVAL`, `XVI Biennale di Venezia di Architettura`, `Singapore
   (2012)`, `New York (2010)`, `Pechino`, `Alessandria d'Egitto (2008)`, `Buenos Aires (2005)`,
   `Baku (2004)`, `Amsterdam (2003)` (9 names — the exact shape of a real single-document batch
   call, not a synthetic one you assemble arbitrarily).
2. Call `classify_entity_types()` on this ONE batch (all 9 names together, one call) — repeat the
   **entire 9-name batch call** 5 separate times, `temperature=0, seed=42` every time (matching the
   real pipeline's actual settings, per `build_relation_atoms()`'s own docstring).
3. For each of the 9 names, report the `entity_type` returned in each of the 5 batch calls.
4. Repeat the same 5-repetitions-of-the-whole-batch experiment WITHOUT `temperature`/`seed`
   (Ollama defaults), for comparison.
5. If you have time: run one more batch of 5 repetitions mixing in 2-3 names from Task 23's
   additional spot checks that are NOT plain geography (`Le Stanze della Fotografia`, `Area35 Art
   Gallery`) alongside the 9 above, to see whether a real institution name embedded in a larger
   real batch behaves differently than it did alone in Task 23.

## Report back

Per-name, per-call results for all 5 repetitions (both modes), same table shape as Task 23 but for
the REAL batch condition. State plainly whether batching changes the agreement rate compared to
Task 23's single-name results, and whether "Le Stanze della Fotografia" (if you ran step 5) flips
inside a real multi-name batch even with `temperature=0/seed=42` forced.
