# OpenCode Task 16 — generalize BUILD ATOMS to string-range ATTRIBUTE predicates (dimensions, medium, creation_year)

**Status: DRAFT TASK — not yet executed. Direct follow-up to the ontology registry edit made
directly in this session (not by OpenCode): `00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json` now
declares 3 new CANDIDATE ATTRIBUTE predicates, domain `["WORK"]`: `dimensions` (range
`["string"]`), `medium` (range `["string"]`), `creation_year` (range `["integer"]`).**

## Why this task exists

The user's real goal: reconstruct a complete artwork record (title, year, dimensions, materials)
from linked facts, so a future query ("what work did Bucchi make in 2013 for the Rome show") can
be answered from atoms that share a SUBJECT. That reframing rejected an earlier, wrong instinct
(filtering "noise" out of entity-identity proposals) — the real gap was that the ontology had *no
vocabulary at all* for a work's year/dimensions/materials as literal facts. That gap is now closed
at the registry level. This task closes it at the code level: today, adding `creation_year` broke
`10_API/gmv_crawler_atom_builder.py`'s own import-time guard on purpose (verified live — running
the test suite now raises `RuntimeError: gmv_crawler_atom_builder's ATTRIBUTE/integer predicate
set is stale: the ontology registry now declares ['creation_year', 'edition_number',
'edition_size'], expected {'edition_size', 'edition_number'}`), and there is currently no code path
at all for `dimensions`/`medium` (string-range ATTRIBUTE predicates have never existed before).

## What this task is NOT

1. **Not** the raw-text-mapping triage. Real crawler rejection-queue data shows raw predicate text
   for these facts is often messy/compound (e.g. `"olio su tela, 175 x 200 cm"` as a single blob
   mixing medium AND dimensions, not two clean predicate+object pairs) — unlike the clean
   single-token cases already mapped for RELATION predicates (`"a cura di"` -> `curated_by`).
   Deciding how to split/clean that real text into separate propositions is a distinct, slower
   editorial task, deferred on purpose. This task only makes the ATTRIBUTE atom-building path
   *capable* of handling a well-formed `dimensions`/`medium`/`creation_year` proposition once one
   exists — it does not attempt to produce one from messy real text.
2. **Not** WORK-subject identity resolution (giving a recurring artwork a stable `gmv_id` so its
   atoms link across documents). That is a separate future task. This task's proof of "linking"
   is narrower and already true today without any new identity mechanism: `build_atom()` already
   passes `proposition.subject_raw` through verbatim as the atom's `subject` (verified by reading
   the function — no entity resolution happens for ATTRIBUTE atoms, by original design). So three
   propositions about the same work that share the exact same `subject_raw` string already produce
   three atoms sharing the same `subject` — Step 5 below demonstrates exactly this, nothing more.
3. **Not** a registry edit. `GMV_ONTOLOGY_REGISTRY_v0.1.json` is already correct; do not touch it.

## Hard constraints

1. **Do not touch `00_CONFIG/GMV_ONTOLOGY_REGISTRY_v0.1.json`** — already edited and correct.
2. **Do not touch `00_CONFIG/crawler_predicate_text_mapping.json`** — out of scope (see above).
3. **Do not add entity resolution to `gmv_crawler_atom_builder.py`.** Its entire reason for
   existing (per its own module docstring) is the subset of predicates that need none. Adding
   `dimensions`/`medium` must not change that boundary — `subject` stays `proposition.subject_raw`
   verbatim, exactly as it already is for `edition_size`/`edition_number`.
4. **`edition_size`/`edition_number`'s existing behavior must not change** — same fixed literals,
   same `atom_id` scheme, same rejection reason codes, same test outcomes for those two predicates.
   This task only widens what the module accepts; every existing test in
   `tests/test_gmv_crawler_atom_builder.py` for the two integer predicates must still pass
   unmodified in its assertions (only the parts of the file that hardcode the old 2-predicate set
   need to change).
5. **No new `reason_code`.** The four documented in the module docstring
   (`UNKNOWN_PREDICATE`/`PREDICATE_NOT_YET_SUPPORTED`/`OBJECT_NOT_INTEGER`/`VALIDATION_FAILED`)
   stay exactly four. `OBJECT_NOT_INTEGER` keeps its name and continues to apply only to
   integer-range predicates (`edition_size`, `edition_number`, `creation_year`) — do not rename it
   to something generic; a string-range predicate (`dimensions`, `medium`) has no equivalent
   rejection in the common case (any non-empty string is valid, and `CandidateProposition.
  __post_init__` already guarantees `object_raw` is non-empty before `build_atom()` ever sees it).
   If you find a real edge case that needs rejecting for a string-range predicate, stop and
   disclose it in the report rather than inventing a fifth code.

## Real code to read before writing anything

- `10_API/gmv_crawler_atom_builder.py` lines 76-85 (the import-time guard) and the whole
  `build_atom()` function (~lines 128-214 at last read, line numbers may have drifted) — the exact
  logic to generalize.
- `tests/test_gmv_crawler_atom_builder.py` — full file. `test_module_attribute_predicate_set_
  matches_real_registry` (line ~50) hardcodes the 2-predicate assumption and must be updated
  first, or every other test will fail on collection (the import-time guard raises before any test
  body runs).
- `10_API/gmv_atom_validator.py::object_type_matches_predicate_range` (~line 266) — confirms
  `object_type` is checked against the predicate's registered `range` list directly (e.g.
  `"string" in ["string"]`), so `object_type="string"` for `dimensions`/`medium` and
  `object_type="integer"` for `creation_year` will validate cleanly with zero A-SCHEMA05 issues,
  exactly like the existing two predicates today.

## Steps

### Step 1 — generalize the import-time guard and predicate/object_type derivation

In `10_API/gmv_crawler_atom_builder.py`:
- Replace `_ATTRIBUTE_INTEGER_PREDICATE_IDS` (a bare frozenset of ids) with a mapping from
  predicate_id to its declared literal object_type, built from the registry, covering ATTRIBUTE
  predicates whose range is exactly `["integer"]` OR exactly `["string"]` (still excluding any
  ATTRIBUTE predicate with an entity-typed or `["ANY"]` range, if one is ever added — this module's
  whole reason to exist is "no entity resolution needed", so only literal-range ATTRIBUTE
  predicates belong here). Something like:
  ```python
  _ATTRIBUTE_LITERAL_PREDICATE_OBJECT_TYPES: dict[str, str] = {
      entry["predicate_id"]: entry["range"][0]
      for entry in _load_ontology_registry()["predicates"]
      if entry["predicate_class"] == "ATTRIBUTE" and entry.get("range") in (["integer"], ["string"])
  }
  ```
  Pick whatever name you judge clearest — the point is: no more hardcoded reliance on "integer"
  as the only possible object_type.
- Update the fail-loud guard's expected set to the 5 real predicate ids: `edition_size`,
  `edition_number`, `creation_year`, `dimensions`, `medium`. Keep the same fail-loud spirit (raise
  `RuntimeError` naming what changed) — this guard's whole purpose is to stop silently operating on
  an unanticipated predicate if the registry grows again; do not weaken it into a silent pass.
- In `build_atom()`, replace the `entry["predicate_class"] != "ATTRIBUTE"` /
  `object_value.isdigit()` logic so that:
  - Step 2 (predicate_class check) is unchanged.
  - A NEW check: if `entry["predicate_id"]` is not in the literal-predicate mapping from Step 1
    above (i.e. it's an ATTRIBUTE predicate this module still doesn't know how to build — there are
    none today after this registry, but the check must stay, for future-proofing exactly like the
    guard above) -> `PREDICATE_NOT_YET_SUPPORTED`, same as the existing RELATION case.
  - Object validation branches on the derived object_type: `"integer"` -> keep the existing
    `object_value.isdigit()` check, `OBJECT_NOT_INTEGER` on failure, `object_type="integer"` on
    success (byte-for-byte the same behavior as today for `edition_size`/`edition_number`, and the
    same for `creation_year`). `"string"` -> no additional check beyond what
    `CandidateProposition.__post_init__` already guarantees; `object_type="string"`.
  - Everything else in `build_atom()` (atom_id scheme, fixed literals, `validate_atom()` call,
    rejection wrapping) is unchanged.
- Update the module's own docstring: it currently says "the two registered ATTRIBUTE-class
  predicates whose declared range is the literal `["integer"]`" — this is no longer true after this
  task; update the description of scope to "ATTRIBUTE-class predicates whose declared range is a
  literal type (`integer` or `string`), never an entity type" or similar, keeping the rest of the
  docstring's reasoning (why this narrow slice is buildable, what's still out of scope) intact.

### Step 2 — tests

In `tests/test_gmv_crawler_atom_builder.py`:
- Fix `test_module_attribute_predicate_set_matches_real_registry` (or rename it if the new shape no
  longer fits that name — your call, but keep an equivalent independent-read cross-check against
  the real registry file, not a hardcoded duplicate list) to assert the new 5-predicate set and the
  module's new internal mapping/guard state, mirroring the existing test's own style (an
  independent `json.loads()` of the real registry file, not trusting the module's own computation).
- Add, mirroring `test_build_atom_edition_size_valid_all_fields_exact` /
  `test_build_atom_edition_number_valid_all_fields_exact` exactly in style (same helper
  `make_proposition()`, same assertion shape):
  - `test_build_atom_creation_year_valid_all_fields_exact` — predicate `"creation_year"`,
    object_raw e.g. `"2013"`, asserts `object_type == "integer"`, `object == "2013"`, passes
    `validate_atom()` with zero BLOCKER issues (mirror the existing pattern for that assertion too).
  - `test_build_atom_dimensions_valid_all_fields_exact` — predicate `"dimensions"`, object_raw
    e.g. `"150 x 100 cm"`, asserts `object_type == "string"`, `object == "150 x 100 cm"`, zero
    BLOCKER issues.
  - `test_build_atom_medium_valid_all_fields_exact` — predicate `"medium"`, object_raw e.g.
    `"olio su tela"`, asserts `object_type == "string"`, zero BLOCKER issues.
  - `test_build_atom_creation_year_non_integer_object_rejects` — mirror
    `test_build_atom_non_integer_object_rejects`'s existing style for the new integer predicate
    (e.g. object_raw `"circa 2013"` -> `OBJECT_NOT_INTEGER`).
  - A test demonstrating two atoms built from two propositions sharing the same `subject_raw` (one
    `creation_year`, one `dimensions`) end up with the same `atom.subject` value — this is the
    concrete "linking via shared SUBJECT" property the whole task exists to enable; make it
    explicit and named clearly, e.g.
    `test_two_attribute_atoms_sharing_subject_raw_share_the_same_atom_subject`.
- Do not delete or weaken any existing test for `edition_size`/`edition_number` — they must keep
  passing with identical assertions.

### Step 3 — verify

`.venv/bin/python -m pytest tests/ -q` and `.venv/bin/python -m ruff check .` — same bar as every
prior task in this series: only the one pre-existing, unrelated
`tests/security/test_runtime_git_policy.py::test_current_tracked_tree_passes_policy` failure
allowed, nothing new. In particular confirm the collection errors seen before this task (in
`tests/test_gmv_crawler_atom_builder.py`, `tests/test_gmv_crawler_orchestrator.py`,
`tests/test_gmv_crawler_rejection_queue.py`, `tests/test_gmv_crawler_relation_atom_builder.py`,
`tests/test_crawler_predicate_mapping_proposals_draft.py` — all caused by the same import-time
`RuntimeError`) are gone.

### Step 4 — live proof (not committed)

One-off script, discard or leave uncommitted after running, never touching real runtime state:
1. Build three `CandidateProposition` instances by hand, all with the exact same `subject_raw`
   (e.g. `"Senza Titolo (prova)"`), one each for `creation_year`/`dimensions`/`medium` with
   realistic values (`"2013"`, `"150 x 100 cm"`, `"olio su tela"`).
2. Call `build_atoms()` on all three; confirm all three build successfully (no rejections), and
   print each atom's `subject`, `predicate`, `object`, `object_type` — confirm all three share the
   same `subject` value verbatim.
3. This is the whole point of the task made concrete: paste this output in the report.

## What to report back

1. The Step 4 live-proof output verbatim (three atoms, same subject, three different
   predicate/object/object_type combinations).
2. Full `.venv/bin/python -m pytest tests/ -q` summary line, and `ruff check .` result — confirm
   the specific collection errors named in Step 3 are gone and nothing new broke.
3. The complete `git diff` / `git status --short` — every file changed, verbatim (should be exactly
   `10_API/gmv_crawler_atom_builder.py` and `tests/test_gmv_crawler_atom_builder.py`, nothing else).
   Do not commit anything yourself; that is a separate, explicit step for a human to do after
   review.
