#!/usr/bin/env bash
# Binary paper export only. Usage: run_pb.sh instance.3pm output_dir
set -euo pipefail
cd "$(dirname "$0")/.."
instance="${1:?Provide an instance.3pm}"
out="${2:?Provide an output directory}"
name="$(basename "$instance" .3pm)"
python3 -m salb3pm export "$instance" "$out/${name}_binary.opb" --formulation paper
