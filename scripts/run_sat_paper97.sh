#!/usr/bin/env bash
# Usage: bash scripts/run_sat_paper97.sh DATASET_DIR [CUTOFF_SECONDS] [REPEATS] [OUTPUT_CSV]
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
DATASET="${1:-benchmarks/paper_97}"
CUTOFF="${2:-3600}"
REPEATS="${3:-1}"
OUTPUT="${4:-experiments/sat_paper97_${CUTOFF}s_r${REPEATS}.csv}"
MANIFEST="${OUTPUT%.csv}.instances.json"

# Reject the 130-instance collection and incorrect published parameters.
# PAPER97_SOURCE records the URL/archive supplied with the original dataset.
"$PYTHON" scripts/prepare_paper97.py "$DATASET" \
  --source "${PAPER97_SOURCE:-}" --out "$MANIFEST"

# 97 instances x 3 methods x 2 encodings x REPEATS.
"$PYTHON" -u scripts/experiment_matrix.py \
  --manifest "$MANIFEST" \
  --methods multiple_sat incremental_sat binary_sat \
  --encodings pairwise staircase \
  --objective peak \
  --time-limit "$CUTOFF" \
  --repeat "$REPEATS" \
  --resume \
  --out "$OUTPUT"
