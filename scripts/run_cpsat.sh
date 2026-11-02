#!/bin/bash
# =============================================================================
# Run CP-SAT solver on a single SALB3PM instance
# Usage: bash scripts/run_cpsat.sh <path_to_3pm_file>
# =============================================================================

set -e

INSTANCE="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOLVER_DIR="$SCRIPT_DIR/../solvers/CPSAT"

if [ -z "$INSTANCE" ]; then
    echo "Usage: bash scripts/run_cpsat.sh <path_to_3pm_file>"
    exit 1
fi

if [ ! -f "$INSTANCE" ]; then
    echo "Error: Instance file '$INSTANCE' not found."
    exit 1
fi

echo "========================================"
echo "Running CP-SAT on $(basename "$INSTANCE")"
echo "========================================"
python3 "$SOLVER_DIR/CPSAT.py" "$INSTANCE"
