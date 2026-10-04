# OpenCode Task 28 — survey descriptive-practice predicates across multiple artists (no registration yet)

**Status: DRAFT TASK — approved plan, not yet executed.**
**This task only gathers and counts real evidence. It does NOT register a new predicate or edit
`GMV_ONTOLOGY_REGISTRY_v0.1.json`/`crawler_predicate_text_mapping.json` — that is Task 29, which
depends on this task's real output.**

## Why

Federico Garibaldi's biography (Task 22, this session) produced 9 extracted predicates, none
cleanly mapping to a governed RELATION predicate — `explores`, `combines`, `investigating`,
`earning`, `acquired`, `under the patronage of`, plus 3 "presented/held/presenting" variants whose
real subject/object shape does not match `located_at`'s domain/range (verified: subject was the
artist, not an exhibition; this was a real catch, not assumed). Biography/critical-text content is
documented as the single largest real document category across the whole archive (project memory,
~200+ documents). Before registering any new predicate, this project's own precedent (`dimensions`/
`medium`/`relocated_to` in `GMV_ONTOLOGY_REGISTRY_v0.1.json`) requires grounding in real, counted,
multi-case evidence — never a single document.

## Steps

1. Use these 6 real, named artists (already confirmed real entries in
   `00_CONFIG/area35_known_artists.json`, different from Garibaldi/Bucchi) — do not pick your own
   substitutes, and do not stop to ask which ones to use: **Alessio Schiavo, Jacques Toussaint,
   Giulia Dall'Olio, Manuel Bonfanti, Stefano Bonzano, Dennis Dawson**. For each, call
   `DropboxConnector.list("/GMV_MASTER_SYSTEM/01_AREA35_MASTER/01_ARTISTS/<SURNAME>_<Firstname>/")`
   (folder name is `SURNAME_Firstname`, e.g. `SCHIAVO_Alessio` — derive it yourself from the name,
   same convention as `BUCCHI_Danilo`/`GARIBALDI_Federico` already used this session) and pick the
   first file whose name contains (case-insensitive) `bio`, `cv`, `biograph`, or `curator` — if a
   given artist has NONE matching, skip that artist and continue with the rest; do not stop to ask
   what to do, just note the skip in your report with the real reason (e.g. "no bio-shaped filename
   found in that folder's listing"). You need AT LEAST 4 real documents to complete this task
   meaningfully — if fewer than 4 of the 6 yield one, report that honestly rather than improvising
   a 7th artist.
   Credentials: read `~/.gmv_dropbox_oauth.json` (fields `refresh_token`, `app_key`, `app_secret`)
   and pass them directly as `DropboxConnector(refresh_token=..., app_key=..., app_secret=...)` —
   same mechanism Task 18/20/21 already used successfully. Do NOT look for `DROPBOX_ACCESS_TOKEN`
   as an environment variable; that is a different, unused auth mode on this connector — do not
   stop to ask about credentials, this is the complete, correct answer.
2. For each, run `extract_candidates()` (`temperature=0, seed=42`), same as Task 22.
3. For every extracted predicate, check it against `00_CONFIG/crawler_predicate_text_mapping.json`'s
   existing mappings AND against `GMV_ONTOLOGY_REGISTRY_v0.1.json`'s governed RELATION predicates
   (domain/range check, not just name similarity — this is exactly where Garibaldi's `located_at`
   mis-mapping was caught, don't repeat it here in reverse by assuming a predicate is "close
   enough").
4. Collect every predicate that does NOT fit any existing RELATION predicate AND that describes the
   artist's own practice/approach/themes (not a location, not an event participation, not a
   biographical fact like birth year) — count real occurrences across the whole 5-6 document
   sample, with the real subject/object pair for each occurrence.
5. Separately flag predicates that don't fit a RELATION but are NOT practice-description either
   (e.g. "earning international recognition" might be this — an achievement/attribution, not a
   description of practice) — these are a different, separate future question, do not lump them
   into the practice-description count.

## Report back

1. A table: predicate text | real count across the sample | 2-3 real subject/object examples |
   artist(s) it came from.
2. Your own judgment on whether a SINGLE new ATTRIBUTE predicate (domain `["ARTIST"]` or
   `["PERSON","ARTIST"]`, free-text object, same shape as `dimensions`/`medium`) would genuinely
   cover the practice-description cases found, or whether the real data suggests something
   different (e.g. two distinct shapes, or not enough real repetition to justify registering
   anything yet — report that honestly if it's what the data shows).
3. The separate list from step 5 (achievement/attribution-shaped predicates), explicitly NOT
   folded into the practice-description recommendation.
4. Do not edit any registry/mapping file in this task. Report only.
