#!/bin/bash

set -euo pipefail

GMV_COMPAT_SOURCE="$HOME/.gmv_scripts/genera_morning_brief.sh" \
GMV_COMPAT_EXPECTED_SHA256="da605bab0a3aaaadcb8077174792a054aae5ff60529bd27ab557ad24d627e1e8" \
"$HOME/.gmv_core/10_API/gmv_compatibility.py" \
  morning_brief -- "$HOME/.gmv_scripts/genera_morning_brief.sh"
