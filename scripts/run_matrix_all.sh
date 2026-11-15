#!/usr/bin/env bash
# All solver families; edit configs/matrix_all_1993.json or supply CLI overrides.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
CONFIG="configs/matrix_all_1993.json"
if (( $# > 0 )) && [[ "$1" != --* ]]; then
  CONFIG="$1"
  shift
fi
"$PYTHON" -u scripts/experiment_matrix.py --config "$CONFIG" "$@"
