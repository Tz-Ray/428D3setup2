#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
umask 077
export PYTHONDONTWRITEBYTECODE=1
if [[ ! -x frontend/node_modules/.bin/vite ]]; then
  npm ci --prefix frontend --prefer-offline --no-fund --no-audit
fi
npm --prefix frontend run build:d3
echo 'D3 sandbox http://127.0.0.1:8000/'
exec ../.venv/bin/python -m uvicorn d3.web:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers
