#!/bin/sh
set -eu

python -m pytest -q
python -m ruff check .
python -m pip check
python scripts/check_runtime_git_policy.py

git ls-files -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline

if git grep -nI -E '[[:blank:]]+$'; then
    echo "tracked files contain trailing whitespace" >&2
    exit 1
fi

git diff --check
