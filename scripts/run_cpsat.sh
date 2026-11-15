#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m salb3pm solve "${1:?Provide an instance.3pm}" --method cpsat "${@:2}"
