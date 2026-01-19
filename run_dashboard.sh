#!/bin/bash

# Kill any process running on port 8501
PID=$(lsof -ti :8501)
if [ ! -z "$PID" ]; then
  echo "Killing process on port 8501 (PID: $PID)..."
  kill -9 $PID
fi

# Run the dashboard
echo "Starting Property Scanner Dashboard..."
python3 -m src.interfaces.cli dashboard
