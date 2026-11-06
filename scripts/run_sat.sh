#!/bin/bash
# =============================================================================
# Run SAT-based solvers on a single SALB3PM instance
# Usage: bash scripts/run_sat.sh <path_to_3pm_file> [solver]
#
# solver options: cadical-str, cadical-bs-e, cadical-bs-i, cadical-su-e,
#                 cadical-su-i, maplesat-str, maplesat-bs-e, maplesat-bs-i,
#                 maplesat-su-e, maplesat-su-i
# If no solver is specified, all SAT-based solvers will be run.
# =============================================================================

set -e

INSTANCE="$1"
SOLVER="$2"
if [ "$#" -ge 2 ]; then shift 2; else shift 1; fi
EXTRA_ARGS=("$@")
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOLVER_DIR="$SCRIPT_DIR/../solvers/SAT_based"
TIMEOUT=7200  # seconds

if [ -z "$INSTANCE" ]; then
    echo "Usage: bash scripts/run_sat.sh <path_to_3pm_file> [solver]"
    echo ""
    echo "Available solvers:"
    echo "  cadical-str, cadical-bs-e, cadical-bs-i, cadical-su-e, cadical-su-i"
    echo "  maplesat-str, maplesat-bs-e, maplesat-bs-i, maplesat-su-e, maplesat-su-i"
    exit 1
fi

if [ ! -f "$INSTANCE" ]; then
    echo "Error: Instance file '$INSTANCE' not found."
    exit 1
fi

run_solver() {
    local solver_file="$1"
    local solver_name="$(basename "$solver_file" .py)"
    echo "========================================"
    echo "Running $solver_name on $(basename "$INSTANCE")"
    echo "========================================"
    timeout "$TIMEOUT" python3 "$solver_file" "$INSTANCE" "${EXTRA_ARGS[@]}" 2>&1 || echo "[$solver_name] Timeout or error."
    echo ""
}

if [ -z "$SOLVER" ]; then
    # Run all SAT-based solvers
    for f in "$SOLVER_DIR"/Cadical-*.py "$SOLVER_DIR"/Maplesat-*.py; do
        run_solver "$f"
    done
else
    # Map solver name to file
    case "$SOLVER" in
        cadical-str)    run_solver "$SOLVER_DIR/Cadical-STR.py" ;;
        cadical-bs-e)   run_solver "$SOLVER_DIR/Cadical-BS-E.py" ;;
        cadical-bs-i)   run_solver "$SOLVER_DIR/Cadical-BS-I.py" ;;
        cadical-su-e)   run_solver "$SOLVER_DIR/Cadical-SU-E.py" ;;
        cadical-su-i)   run_solver "$SOLVER_DIR/Cadical-SU-I.py" ;;
        maplesat-str)   run_solver "$SOLVER_DIR/Maplesat-STR.py" ;;
        maplesat-bs-e)  run_solver "$SOLVER_DIR/Maplesat-BS-E.py" ;;
        maplesat-bs-i)  run_solver "$SOLVER_DIR/Maplesat-BS-I.py" ;;
        maplesat-su-e)  run_solver "$SOLVER_DIR/Maplesat-SU-E.py" ;;
        maplesat-su-i)  run_solver "$SOLVER_DIR/Maplesat-SU-I.py" ;;
        multiple-sat)   run_solver "$SOLVER_DIR/MultipleSAT.py" ;;
        incremental-sat) run_solver "$SOLVER_DIR/IncrementalSAT.py" ;;
        binary-sat)     run_solver "$SOLVER_DIR/BinarySAT.py" ;;
        paper-cuts)     run_solver "$SOLVER_DIR/StaircasePaperCuts.py" ;;
        *)
            echo "Unknown solver: $SOLVER"
            echo "Available: cadical-str, cadical-bs-e, cadical-bs-i, cadical-su-e, cadical-su-i"
            echo "           maplesat-str, maplesat-bs-e, maplesat-bs-i, maplesat-su-e, maplesat-su-i"
            exit 1
            ;;
    esac
fi
