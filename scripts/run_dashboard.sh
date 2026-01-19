#!/bin/bash

# Configuration
PORT=8501
APP_PATH="src/interfaces/dashboard/app.py"

# Function to check if port is in use
check_port() {
    lsof -i :$1 > /dev/null
    return $?
}

# Ensure we are in the project root
if [ ! -f "$APP_PATH" ]; then
    echo "Error: Could not find application at $APP_PATH"
    echo "Please run this script from the project root."
    exit 1
fi

# Activate virtualenv if present
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Check for existing process on the port
if check_port $PORT; then
    echo "Port $PORT is currently in use."
    PID=$(lsof -ti :$PORT)
    echo "Killing process $PID..."
    kill -9 $PID
    sleep 1
fi

echo "Starting Property Scanner Dashboard on port $PORT..."
python -m streamlit run "$APP_PATH" --server.port $PORT --server.fileWatcherType none
