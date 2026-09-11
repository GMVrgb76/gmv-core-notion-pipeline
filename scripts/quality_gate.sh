#!/bin/sh
set -eu

python -m pytest -q
python -m ruff check .
python -m pip check
python scripts/check_runtime_git_policy.py

git ls-files -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline

# Exclude Markdown's own hard-line-break convention (a non-blank line ending
# in exactly two spaces) -- that is meaningful trailing whitespace, not a
# mistake. A single trailing space, 3+, or a trailing tab still fails.
if git grep -nI -E '[[:blank:]]+$' | grep -v -E ':.*[^[:blank:]]  $'; then
    echo "tracked files contain trailing whitespace" >&2
    exit 1
fi

git diff --check
