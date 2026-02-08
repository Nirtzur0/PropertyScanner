#!/bin/bash

# Prefer the project's venv if present so this works without requiring an
# activated shell environment.
PYTHON_BIN="python3"
if [ -x "./venv/bin/python" ]; then
  PYTHON_BIN="./venv/bin/python"
elif [ -x "./.venv/bin/python" ]; then
  PYTHON_BIN="./.venv/bin/python"
fi

# Kill any process running on port 8501
PID=$(lsof -ti :8501)
if [ ! -z "$PID" ]; then
  echo "Killing process on port 8501 (PID: $PID)..."
  kill -9 $PID
fi

# Run the dashboard
echo "Starting Property Scanner Dashboard..."
"$PYTHON_BIN" -m src.interfaces.cli dashboard
