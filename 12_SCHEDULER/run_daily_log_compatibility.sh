#!/bin/bash

set -euo pipefail

GMV_COMPAT_SOURCE="$HOME/.gmv_scripts/genera_daily_log.sh" \
GMV_COMPAT_EXPECTED_SHA256="e1ef8e5f7aa51f61d20871e82ebf4f968073d65791e03743373421bae64c8e09" \
"$HOME/.gmv_core/10_API/gmv_compatibility.py" \
  daily_log -- "$HOME/.gmv_scripts/genera_daily_log.sh"
