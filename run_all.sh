#!/bin/bash

echo " Starting TaxAI System..."

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start Mock ITR Server in background
echo "Starting Mock ITR Server (port 8002)..."
python3 itr.py > itr_server.log 2>&1 &
ITR_PID=$!
echo "ITR Server PID: $ITR_PID"

# Start Main Backend Server
echo "Starting Main Backend Server (port 8000)..."
python3 main.py

# Cleanup on exit
kill $ITR_PID
