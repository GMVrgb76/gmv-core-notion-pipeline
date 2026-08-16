#!/bin/sh
set -eu

BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CONFIG="$BASE/config.json"
ROWS="$BASE/rows.json"
REPORT="$BASE/report"
EXTRACT=0
TOKEN_FILE="${AREA35_NOTION_TOKEN_FILE:-$HOME/.config/area35-qa/notion_token}"
LIMIT=""
ENTITIES=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --extract) EXTRACT=1 ;;
    --token-file) shift; TOKEN_FILE=$1 ;;
    --limit) shift; LIMIT=$1 ;;
    --entities) shift; ENTITIES=$1 ;;
    --rows) shift; ROWS=$1 ;;
    --out) shift; REPORT=$1 ;;
    -h|--help)
      echo "Uso: $0 [--extract] [--token-file FILE] [--limit N] [--entities e1,e2] [--rows FILE] [--out DIR]"
      exit 0 ;;
    *) echo "Argomento non riconosciuto: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ "$EXTRACT" -eq 1 ]; then
  EXTRA="--token-file $TOKEN_FILE"
  [ -n "$LIMIT" ] && EXTRA="$EXTRA --limit $LIMIT"
  [ -n "$ENTITIES" ] && EXTRA="$EXTRA --entities $ENTITIES"
  # shellcheck disable=SC2086
  python3 "$BASE/notion_extract.py" --config "$CONFIG" --out "$ROWS" $EXTRA
fi

python3 "$BASE/area35_validator.py" --config "$CONFIG" --rows "$ROWS" --out "$REPORT"
