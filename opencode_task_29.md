# OpenCode Task 29 — pycountry for deterministic country-name filtering

**Status: DRAFT TASK — approved plan, not yet executed.**
**Approved with the user: add `pycountry` as a real dependency, use it for COUNTRY-level noise
only. City-level noise stays hand-curated in `00_CONFIG/area35_known_places.json`.**

## Why

Tonight's live re-run of the known-places filter (Task 27) found it works correctly for the 12
curated names, but the SAME single real document surfaced 13+ more bare geographic names the
hand-curated list doesn't cover — several of them countries (`ROMANIA`, `Bulgaria`, `Montenegro`,
and the already-curated `ITALIA`/`EGITTO`). Hand-curating every country name one document at a
time does not scale. `pycountry` (small, mature, no network calls, wraps ISO 3166) can cover every
real country name deterministically, same "deterministic-first" principle already used for
`is_generic_regulatory_reference()` in the real-estate pipeline.

## Steps

1. Add `pycountry` (pin to the latest stable version available at install time — check with
   `pip index versions pycountry` or just install latest and record the resolved version) to
   `requirements-dev.txt` — confirmed this session to be the repo's real, actually-used dependency
   file (`pyproject.toml` has deliberately empty `dependencies = []`, confirmed by its own ruff
   config comment "no installed package here"). Do not stop to ask which file to use — this is
   decided. Install it in `.venv` and confirm `python -c "import pycountry"` works.
2. In `10_API/gmv_crawler_entity_resolver.py`, add `_is_known_country(name: str) -> bool`:
   normalizes with the same `.strip().lower()`/`_forma()`-consistent approach already used by
   sibling functions, checks against `pycountry.countries` (iterate `.name`/`.official_name`/any
   `common_name` attribute it exposes — read `pycountry`'s real API, don't guess the attribute
   names) and `pycountry.historic_countries` (covers names like historical/former country forms, if
   relevant to real archive data — check whether it's needed before adding it, don't add unused
   surface). Deterministic, no network, same contract as `_load_known_places()`.
3. In `gmv_crawler_orchestrator.py::process_document()`, extend BOTH existing filter points from
   Task 26/27 (the `CandidateEntity` loop and the WORK-subject loop) to also skip when
   `_is_known_country(name)` is true, alongside the existing `known_places` check.
4. Clean up `00_CONFIG/area35_known_places.json`: remove any entry `pycountry` now correctly
   recognizes as a country (check `ITALIA`, `EGITTO` specifically — confirm `_is_known_country`
   catches both before removing them, do not remove on assumption). Leave every city entry
   untouched.
5. Tests: a test proving a real country name NOT in the old hand-curated list (e.g. `"Bulgaria"`,
   `"Montenegro"` — real names from tonight's live run) is now filtered via `_is_known_country()`
   alone; a test proving a real city name (still NOT a country) is unaffected by this new check and
   still relies on the hand-curated list. Follow the exact mocking convention already established
   in `tests/test_gmv_crawler_orchestrator.py` (`monkeypatch.setattr(orchestrator,
   "extract_candidates", ...)` — no real Ollama call, per the bug already found and fixed in this
   same file tonight).
6. Run `.venv/bin/python -m pytest tests/ -q` and `ruff check .` — confirm only the one
   pre-existing, unrelated failure.
7. Live re-run (real, not static — same lesson as Task 26/27): re-run `process_document()` on the
   real Bucchi document used throughout this session, with both filters (places + country) active.
   Report the real before/after proposal counts, and whether `ROMANIA`/`Bulgaria`/`Montenegro` (the
   three countries seen in tonight's run) are now correctly excluded.

## Report back

1. Which dependency file `pycountry` was added to, and confirmation it installs cleanly.
2. The exact `pycountry` attributes/API used (quote the real check, not a paraphrase).
3. Which entries were removed from `area35_known_places.json` and why (confirmed caught by the new
   country check).
4. Test results + live re-run numbers (step 7), real not estimated.
5. `git diff`/`git status --short` for everything changed.
