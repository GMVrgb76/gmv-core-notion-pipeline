#!/bin/bash

set -euo pipefail

SOURCE="$HOME/.gmv_core/01_RUNTIME/legacy/market_engine_v2.py"

GMV_COMPAT_SOURCE="$SOURCE" \
GMV_COMPAT_EXPECTED_SHA256="dd06ec16723fff21a2474688092ae2843abe2800b8a9d2eeb7a28d966b2bdd65" \
"$HOME/.gmv_core/10_API/gmv_compatibility.py" \
  market_engine -- \
  python3 \
  "$SOURCE"
