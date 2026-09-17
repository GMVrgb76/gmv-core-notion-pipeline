#!/bin/bash
# Wrapper invoked by launchd (see com.gmv.crawler.nightly.plist): launchd's
# EnvironmentVariables key only accepts literal values, not a command
# substitution, so the Dropbox token (never committed, lives outside the
# repo at ~/.gmv_dropbox_token, chmod 600) is read here instead and
# exported just for this one process.
set -euo pipefail

REPO_ROOT="/Users/giacomomarcovalerio/.gmv_core/.claude/worktrees/bridge-cse_01EFSz2nNresRvPh9GbfwwzK"
TOKEN_FILE="/Users/giacomomarcovalerio/.gmv_dropbox_token"

if [ ! -f "$TOKEN_FILE" ]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ERROR: token file not found at $TOKEN_FILE" >&2
    exit 1
fi

export DROPBOX_ACCESS_TOKEN
DROPBOX_ACCESS_TOKEN="$(cat "$TOKEN_FILE")"

cd "$REPO_ROOT"
source .venv/bin/activate
exec python3 automation/gmv_crawler_nightly_run.py
