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

"$venv_dir/bin/python" scripts/reset_fixture.py
"$venv_dir/bin/python" scripts/run_impact_analysis.py
"$venv_dir/bin/python" scripts/apply_writeback.py --synthetic-override
"$venv_dir/bin/pytest" -q
"$venv_dir/bin/python" scripts/verify_smoke_test.py
