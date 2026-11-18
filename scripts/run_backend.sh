#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ! -f "$ROOT/.env" ]]; then
  echo 'Missing .env. Run: python scripts/bootstrap.py' >&2
  exit 1
fi
set -a
source "$ROOT/.env"
set +a
cd "$ROOT/backend"
exec uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
