#!/bin/bash
# Wrapper invoked by launchd (see com.gmv.crawler.nightly.plist): launchd's
# EnvironmentVariables key only accepts literal values, not a command
# substitution, so secrets are read here instead and exported just for
# this one process.
#
# OAuth refresh flow (2026-09-18), replacing the static DROPBOX_ACCESS_TOKEN
# used until now: that token expired in ~4h, too short for a multi-hour
# crawl over the full 46-artist roster. ~/.gmv_dropbox_oauth.json (never
# committed, chmod 600) holds a refresh_token that does not expire plus
# the app_key/app_secret needed to redeem it -- gmv_dropbox_connector.py
# uses these to fetch a fresh access token automatically, including mid-run
# on a 401, with no human needed to paste a new token ever again.
set -euo pipefail

REPO_ROOT="/Users/giacomomarcovalerio/.gmv_core/.claude/worktrees/bridge-cse_01EFSz2nNresRvPh9GbfwwzK"
OAUTH_FILE="/Users/giacomomarcovalerio/.gmv_dropbox_oauth.json"

if [ ! -f "$OAUTH_FILE" ]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ERROR: OAuth credentials file not found at $OAUTH_FILE" >&2
    exit 1
fi

export DROPBOX_REFRESH_TOKEN
export DROPBOX_APP_KEY
export DROPBOX_APP_SECRET
DROPBOX_REFRESH_TOKEN="$(python3 -c "import json; print(json.load(open('$OAUTH_FILE'))['refresh_token'])")"
DROPBOX_APP_KEY="$(python3 -c "import json; print(json.load(open('$OAUTH_FILE'))['app_key'])")"
DROPBOX_APP_SECRET="$(python3 -c "import json; print(json.load(open('$OAUTH_FILE'))['app_secret'])")"

cd "$REPO_ROOT"
source .venv/bin/activate
exec python3 automation/gmv_crawler_nightly_run.py
