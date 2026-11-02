#!/bin/bash
# =============================================================================
# Run MaxSAT-based encoders on a single SALB3PM instance
# This script generates WCNF files that can be solved by MaxSAT solvers
# (MaxHS, RC2, WMaxCDCL, Pacose, etc.)
#
# Usage: bash scripts/run_maxsat.sh <path_to_3pm_file> <output_dir> [formulation]
#
# formulation options: enhanced (default), inaugural, both
# =============================================================================

set -e

INSTANCE="$1"
OUTPUT_DIR="$2"
FORMULATION="${3:-both}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOLVER_DIR="$SCRIPT_DIR/../solvers/MaxSAT_based"

if [ -z "$INSTANCE" ] || [ -z "$OUTPUT_DIR" ]; then
    echo "Usage: bash scripts/run_maxsat.sh <path_to_3pm_file> <output_dir> [formulation]"
    echo ""
    echo "Formulation options: enhanced, inaugural, both (default)"
    echo ""
    echo "This script generates WCNF files. To solve them, use a MaxSAT solver:"
    echo "  maxhs <output.wcnf>"
    echo "  python3 -m pysat.examples.rc2 <output.wcnf>"
    exit 1
fi

if [ ! -f "$INSTANCE" ]; then
    echo "Error: Instance file '$INSTANCE' not found."
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
BASENAME="$(basename "$INSTANCE" .3pm)"

case "$FORMULATION" in
    enhanced|e)
        echo "Generating WCNF with Enhanced formulation..."
        python3 "$SOLVER_DIR/MSAT-E.py" "$INSTANCE" "$OUTPUT_DIR/${BASENAME}_enhanced.wcnf"
        ;;
    inaugural|i)
        echo "Generating WCNF with Inaugural formulation..."
        python3 "$SOLVER_DIR/MSAT-I.py" "$INSTANCE" "$OUTPUT_DIR/${BASENAME}_inaugural.wcnf"
        ;;
    both)
        echo "Generating WCNF with Enhanced formulation..."
        python3 "$SOLVER_DIR/MSAT-E.py" "$INSTANCE" "$OUTPUT_DIR/${BASENAME}_enhanced.wcnf"
        echo ""
        echo "Generating WCNF with Inaugural formulation..."
        python3 "$SOLVER_DIR/MSAT-I.py" "$INSTANCE" "$OUTPUT_DIR/${BASENAME}_inaugural.wcnf"
        ;;
    *)
        echo "Unknown formulation: $FORMULATION"
        echo "Available: enhanced, inaugural, both"
        exit 1
        ;;
esac

echo ""
echo "WCNF files generated in: $OUTPUT_DIR"
echo "To solve, use a MaxSAT solver, e.g.:"
echo "  maxhs $OUTPUT_DIR/${BASENAME}_enhanced.wcnf"
