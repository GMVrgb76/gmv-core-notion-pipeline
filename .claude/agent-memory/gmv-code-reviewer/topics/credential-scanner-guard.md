# credential_assignment scanner: single-match guard was a false-negative regression

- **A "value is followed by `(`, so treat as a safe call and skip" guard on a
  security-scanner regex only checks the classification of the single
  leftmost match returned by `pattern.search(line)`, not the whole line.**
  `scripts/check_runtime_git_policy.py::scan_text` (fix for the
  `credential_assignment` false positive on `os.environ.get(...)` /
  `path.read_text(...)`) did `match = pattern.search(line); if ... == "(":
  continue` — once the first match on a line is classified as a safe call,
  the function moved to the next pattern kind and never re-scanned the rest of
  the line for that pattern. Reproduced empirically 2026-08-30: lines like
  `secret = load_secret(fallback="literal-secret-123")` (illustrative only,
  not a real secret — hardcoded default arg to a getter, a real, common leak
  pattern; gmv-policy-test-fixture) and `token = os.environ.get("X"); password = "abc12345"`
  (illustrative only, not a real secret; unrelated real literal later on the
  same line) went from correctly flagged (pre-fix, for the "wrong" reason —
  matching the accessor name) to silently `[]` (post-fix) — a genuine
  false-negative regression in a CI security gate, not just a leftover
  cosmetic false positive. The submitter's own first added regression test
  for this exact class passed only because its example put the real literal
  immediately after the *same* keyword the call-like guard consumed (so the
  leftmost match already captured the literal directly), not because the
  guard's mechanism handles multiple matches per line — a passing test with a
  docstring claiming to cover "a literal after a call-like prefix" does not
  mean it exercises the call-embeds-a-literal-as-its-own-argument case. When
  reviewing any fix to a per-line regex scanner that changes `search()`-based
  single-match logic from "always flag on match" to "conditionally skip based
  on classifying that one match", always test: (a) a real secret embedded as
  a default/fallback argument inside the very call being whitelisted, and (b)
  two independent occurrences of the same keyword on one line, one safe one
  not — diff before/after with `git stash` to confirm which direction
  changed, not just whether the new test file passes.

  **Round 2 (2026-08-30): case (b) fixed, case (a) NOT fixed — verified by
  direct execution, not by trusting "587 passed".** Switched to
  `pattern.finditer(line)`: every match on the line is now checked, and only
  the individual call-shaped match is skipped, not the whole line — case (b)
  (`token = os.environ.get("X"); password = "abc12345"`, gmv-policy-test-fixture)
  is genuinely caught now, confirmed by tracing the regex by hand and running it. But case (a) is
  untouched: `POLICY.scan_text('token = os.environ.get("API_TOKEN", '
  '"literal-hardcoded-fallback-9x7z")', 'x')` still returns `[]`, and this line
  IS caught by the pre-any-fix baseline (`git show HEAD:...` — plain
  `pattern.search`, no call-skip heuristic at all), so this is a demonstrated
  regression vs. the pre-fix baseline, not merely an unfixed pre-existing gap.
  The new regression test suite (2 new tests) only covers case (b); no test
  exercises a literal passed as a positional/kwarg argument inside the very
  call being whitelisted. **Lesson: when a submitter's own docstring/PR
  description lists two failure classes from a prior BLOCK, verify BOTH
  independently by execution before crediting the fix — a fix and its new
  tests can be 100% consistent with each other while only covering the
  narrower of the two classes, and a green, expanded test suite does not
  imply the untested class was addressed.**

  **Also found in round 2: self-referential doc content re-triggers the
  scanner, per-file, not just per-test-file.** The submitter added a
  `gmv-policy-test-fixture` marker/rewording to `tests/security/
  test_runtime_git_policy.py` (confirmed effective) but a *new memory file*
  written to document this very bug (`topics/credential-scanner-guard.md`,
  containing the illustrative `token = os.environ.get("X"); password =
  "abc12345"` line) did NOT get the same treatment. It only escaped detection
  because it was still `git`-untracked when checked (`audit_tracked_files`
  scans `git ls-files` output) — `scan_text()` on its raw content directly
  returns a real Finding at the literal's line. Any claim of "fixed the
  self-referential false-positive" must be checked file-by-file across
  everything the change adds, not just the one file the submitter mentions,
  and must account for untracked files that will start being scanned the
  moment they're `git add`ed.

  **Round 3 (2026-08-30): case (a) genuinely fixed, both prior blockers closed
  — but the fix method introduces a new, narrower false-positive class.**
  `_call_is_a_plain_lookup` now walks the matched call's parens (depth-counted,
  not quote-aware) and counts quoted-string arguments via `QUOTED_STRING =
  re.compile(r"""(['"])(?:(?!\1).)*\1""")`; a call is only whitelisted when it
  has <= 1 quoted argument. Verified by direct execution: the round-2 repro
  (`get("API_TOKEN", "literal-hardcoded-fallback-9x7z")`) is now correctly
  flagged, the two original real false positives (`adapter_notion.py:195`
  `token = os.environ.get("NOTION_TOKEN")`, `notion_extract.py:202` `token =
  token_path.read_text(encoding="utf-8").strip()`) remain correctly silent,
  and self-referential content is now clean *everywhere* in
  `.claude/agent-memory/gmv-code-reviewer/` (checked every topic file
  individually with `scan_text()` on raw content, not just the one file
  mentioned — this closes the exact gap round 2 itself flagged) — additionally
  confirmed by copying the whole worktree, running `git add -A` there, and
  running the real `scripts/check_runtime_git_policy.py` entry point (not just
  `scan_text()` in isolation): `POLICY|PASS|findings=0` once every new file is
  actually tracked, which is the condition round 2 warned had not been tested.

  **New gap found by direct execution (not hypothetical): the 2-quoted-args
  heuristic has no minimum-length floor on the second literal, unlike the
  primary `credential_assignment` regex's own `{8,}` threshold, so it flags
  calls where the "fallback" is structurally incapable of being a secret.**
  `token = self.config.get("key", "")`, `token = os.environ.get("API_TOKEN",
  "")`, and `authorization = request.headers.get("Authorization", "")` (a
  very common idiom: default-to-empty-string instead of `None`) all get
  flagged as `credential_assignment`, purely because they have 2 quoted
  arguments — the tool's own length-based secret heuristic used everywhere
  else is not applied to this nested check. Not currently present anywhere in
  this repo's tracked files (grepped; full audit run is still `PASS
  findings=0` today) so this is not an active regression, and it is a
  false-positive (safe direction for a security gate — consistent with
  "prefer rare false positives over false negatives on secrets"), so it did
  not block round 3. But it is a real, cheap-to-fix inconsistency: filtering
  `QUOTED_STRING.findall(arguments)` to only count matches with non-trivial
  content length (matching the outer regex's own `{8,}` bar) would close it
  without reopening case (a). **Lesson: when a fix for a scanner's
  false-negative narrows a whitelist by counting *some* property of the
  matched text (arg count, arg presence, etc.), check whether the tool
  already has an established heuristic for "how long/complex must a literal
  be to plausibly be a secret" elsewhere in the same file, and apply it
  consistently — a new nested check that ignores an existing threshold is a
  predictable source of a new, narrower false-positive class.**
