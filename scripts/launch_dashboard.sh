#!/bin/bash
# scripts/launch_dashboard.sh

# Ensure we are in the project root
cd "$(dirname "$0")/.."

# Export PYTHONPATH to include the current directory (project root)
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Crash Prevention (macOS/PyTorch/HF)
export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS=1
export TOKENIZERS_PARALLELISM=false

# Auto-migrate DB on launch
echo "Ensuring DB schema is up to date..."
./venv/bin/python scripts/migrate_db.py

echo "Starting Streamlit Dashboard on port 8503..."
./venv/bin/streamlit run src/dashboard.py --server.port 8503 --server.headless true
