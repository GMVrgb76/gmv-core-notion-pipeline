#!/bin/bash

set -euo pipefail

"$HOME/.gmv_core/10_API/gmv_compatibility.py" \
  daily_log -- "$HOME/.gmv_scripts/genera_daily_log.sh"
