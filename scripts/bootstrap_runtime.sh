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
datahub_version="${DATAHUB_VERSION:-v1.6.0}"
venv_dir="${COVENANT_VENV:-.venv}"

if [[ ! -x "$venv_dir/bin/python" ]]; then
  "$python_bin" -m venv "$venv_dir"
fi

"$venv_dir/bin/python" -m pip install --disable-pip-version-check --editable '.[test]'
"$venv_dir/bin/datahub" docker quickstart --version "$datahub_version"
"$venv_dir/bin/datahub" docker check

echo "Covenant runtime ready: DataHub ${datahub_version} at ${DATAHUB_GMS_URL:-http://localhost:8080}"
