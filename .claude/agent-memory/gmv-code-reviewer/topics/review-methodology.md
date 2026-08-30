# Review methodology notes (independent of any one bug)

- When a review previously issued BLOCK with an empirically demonstrated
  repro (not just a theoretical concern), on re-review always re-run the same
  repro against the fixed code rather than trusting the diff/description —
  e.g. both `.doc`-extraction blockers (BOM survival through `.strip()`, and
  stale `-0.1.json` cache shadowing the new extractor) were independently
  reproduced and confirmed fixed, not just asserted by the submitter's test
  suite.

- Before judging a claimed test-suite result (e.g. "497 passed, 1 pre-existing
  unrelated failure"), actually create a throwaway venv and run the suite
  yourself if `pytest` isn't already on PATH — in this repo it usually isn't
  (`requirements-dev.txt` pins it, but the base interpreter doesn't have it
  installed). Do not accept the submitter's reported numbers without
  independent reproduction when it's cheap to do (`python3 -m venv /tmp/x &&
  /tmp/x/bin/pip install -q pytest ... && /tmp/x/bin/python -m pytest`).
