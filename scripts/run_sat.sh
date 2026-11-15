#!/usr/bin/env bash
# Usage: run_sat.sh instance.3pm [multiple_sat|incremental_sat|binary_sat|paper_cuts] [CLI options]
set -euo pipefail
cd "$(dirname "$0")/.."
instance="${1:?Provide an instance.3pm}"
method="${2:-incremental_sat}"
if (( $# >= 2 )); then shift 2; else shift; fi
python3 -m salb3pm solve "$instance" --method "$method" "$@"
