#!/bin/bash
set -euo pipefail

# Prefer the project's venv if present so this works without requiring an
# activated shell environment.
PYTHON_BIN="python3"
if [ -x "./venv/bin/python" ]; then
  PYTHON_BIN="./venv/bin/python"
elif [ -x "./.venv/bin/python" ]; then
  PYTHON_BIN="./.venv/bin/python"
fi

HOST="${PROPERTY_SCANNER_HOST:-127.0.0.1}"
PORT="${PROPERTY_SCANNER_PORT:-8001}"

echo "Starting Property Scanner local API on http://${HOST}:${PORT}"
echo "Open the React workbench at http://${HOST}:${PORT}/workbench"
echo "Use 'python3 -m src.interfaces.cli legacy-dashboard --skip-preflight' only if you explicitly need the deprecated Streamlit surface."
exec "$PYTHON_BIN" -m src.interfaces.cli api --host "$HOST" --port "$PORT" "$@"
