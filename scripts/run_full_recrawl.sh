#!/bin/bash
echo "Starting full recrawl process..."

# 1. Ensure Model is present
echo "Ensuring valid LLM model (llama3)..."
ollama pull llama3

# 2. Run Recrawl
echo "Starting Recrawl Script..."
./venv/bin/python scripts/recrawl_db.py

echo "Recrawl process complete."
