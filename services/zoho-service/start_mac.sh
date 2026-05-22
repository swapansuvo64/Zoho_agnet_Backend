#!/bin/bash
cd "$(dirname "$0")"
echo "Starting Zoho Agent Zoho Service on macOS..."
if [ ! -f "venv/bin/python" ]; then
    echo "Virtual environment 'venv' not found or python is missing."
    echo "Please make sure the venv is created."
    exit 1
fi

echo "Checking for existing process on port 8003..."
PID=$(lsof -t -i:8003)
if [ ! -z "$PID" ]; then
    echo "Found process $PID on port 8003. Killing it to start fresh..."
    kill -9 $PID 2>/dev/null || true
fi

echo "Starting FastAPI server on port 8003..."
./venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8003 --reload
