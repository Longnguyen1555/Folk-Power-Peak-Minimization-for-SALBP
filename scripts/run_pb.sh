#!/bin/bash
# =============================================================================
# Run PB-based encoders on a single SALB3PM instance
# This script generates OPB files that can be solved by PB solvers
# (RoundingSAT, Sat4j, etc.)
#
# Usage: bash scripts/run_pb.sh <path_to_3pm_file> <output_dir> [formulation]
#
# formulation options: enhanced (default), inaugural, both
# =============================================================================

set -e

INSTANCE="$1"
OUTPUT_DIR="$2"
FORMULATION="${3:-both}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOLVER_DIR="$SCRIPT_DIR/../solvers/PB_based"

if [ -z "$INSTANCE" ] || [ -z "$OUTPUT_DIR" ]; then
    echo "Usage: bash scripts/run_pb.sh <path_to_3pm_file> <output_dir> [formulation]"
    echo ""
    echo "Formulation options: enhanced, inaugural, both (default)"
    echo ""
    echo "This script generates OPB files. To solve them, use a PB solver:"
    echo "  roundingsat <output.opb>"
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
        echo "Generating OPB with Enhanced formulation..."
        python3 "$SOLVER_DIR/PBO-E.py" "$INSTANCE" "$OUTPUT_DIR/${BASENAME}_enhanced.opb"
        ;;
    inaugural|i)
        echo "Generating OPB with Inaugural formulation..."
        python3 "$SOLVER_DIR/PBO-I.py" "$INSTANCE" "$OUTPUT_DIR/${BASENAME}_inaugural.opb"
        ;;
    both)
        echo "Generating OPB with Enhanced formulation..."
        python3 "$SOLVER_DIR/PBO-E.py" "$INSTANCE" "$OUTPUT_DIR/${BASENAME}_enhanced.opb"
        echo ""
        echo "Generating OPB with Inaugural formulation..."
        python3 "$SOLVER_DIR/PBO-I.py" "$INSTANCE" "$OUTPUT_DIR/${BASENAME}_inaugural.opb"
        ;;
    *)
        echo "Unknown formulation: $FORMULATION"
        echo "Available: enhanced, inaugural, both"
        exit 1
        ;;
esac

echo ""
echo "OPB files generated in: $OUTPUT_DIR"
echo "To solve, use a PB solver, e.g.:"
echo "  roundingsat $OUTPUT_DIR/${BASENAME}_enhanced.opb"
