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

python_bin="${COVENANT_PYTHON:-python3.11}"
venv_dir="${COVENANT_VENV:-.venv}"
api_host="${COVENANT_API_HOST:-127.0.0.1}"
api_port="${COVENANT_API_PORT:-8000}"

"$python_bin" scripts/preflight_port.py "$api_host" "$api_port"

./scripts/bootstrap_runtime.sh

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

"$venv_dir/bin/python" scripts/ensure_fixture.py
"$venv_dir/bin/python" scripts/seed_registry.py

echo "Covenant API: http://${api_host}:${api_port}/docs"
echo "React UI is started separately from frontend/ and binds to this API."
exec "$venv_dir/bin/uvicorn" src.api.app:app --host "$api_host" --port "$api_port"
