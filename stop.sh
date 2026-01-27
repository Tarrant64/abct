#!/bin/bash
#===============================================================================
# ABCT - A Better Crypto Tracker
# Stop Script
#===============================================================================
#
# Description:
#   This script gracefully stops the ABCT portfolio tracker server.
#   It finds the process running on port 8000 and terminates it.
#
# Usage:
#   ./stop.sh
#
# How it works:
#   1. Searches for process listening on port 8000 (using lsof)
#   2. Sends SIGTERM for graceful shutdown
#   3. If process doesn't stop, sends SIGKILL (force kill)
#   4. Falls back to searching for python main.py process
#
# Exit Codes:
#   0 - Success (server stopped or wasn't running)
#
#===============================================================================

# Change to script directory (project root)
cd "$(dirname "$0")"

echo "========================================"
echo "  Stopping ABCT Portfolio Tracker..."
echo "========================================"
echo ""

# Find process running on port 8000
PID=$(lsof -ti:8000 2>/dev/null)

if [ -n "$PID" ]; then
    echo "Found process $PID on port 8000"

    # Send graceful termination signal
    kill $PID
    sleep 1

    # Check if it's still running and force kill if needed
    if lsof -ti:8000 >/dev/null 2>&1; then
        echo "Process still running, force killing..."
        kill -9 $(lsof -ti:8000) 2>/dev/null
        sleep 1
    fi

    # Verify stopped
    if lsof -ti:8000 >/dev/null 2>&1; then
        echo "WARNING: Process may still be running."
    else
        echo "ABCT stopped successfully."
        # Clean up PID file if exists
        rm -f data/server.pid 2>/dev/null
    fi
else
    # Try to find by process name as fallback
    PID=$(pgrep -f "python.*main.py" 2>/dev/null | head -1)

    if [ -n "$PID" ]; then
        echo "Found python main.py process $PID"
        kill $PID
        sleep 1
        echo "ABCT stopped successfully."
        # Clean up PID file if exists
        rm -f data/server.pid 2>/dev/null
    else
        echo "No running ABCT process found."
        # Clean up stale PID file if exists
        rm -f data/server.pid 2>/dev/null
    fi
fi

echo ""
