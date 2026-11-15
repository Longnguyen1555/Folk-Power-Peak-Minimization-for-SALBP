#!/usr/bin/env bash
# Edit configs/matrix_1993.json, or override options after the config path.
# Usage: PYTHON=python bash scripts/run_matrix.sh [CONFIG.json] [CLI overrides]
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
CONFIG="configs/matrix_1993.json"
if (( $# > 0 )) && [[ "$1" != --* ]]; then
  CONFIG="$1"
  shift
fi
"$PYTHON" -u scripts/experiment_matrix.py --config "$CONFIG" "$@"
