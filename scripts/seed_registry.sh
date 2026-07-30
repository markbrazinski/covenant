#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
venv_dir="${COVENANT_VENV:-.venv}"
exec "$venv_dir/bin/python" scripts/seed_registry.py
