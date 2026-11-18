#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if (( $# )); then
  echo "Usage: ./start.sh" >&2
  exit 2
fi
exec ./start-d3.sh
