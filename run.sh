#!/bin/bash
#===============================================================================
# ABCT - A Better Crypto Tracker
# Run Script for Local Development
#===============================================================================
#
# Description:
#   This script starts the ABCT portfolio tracker server for local development.
#   It handles virtual environment setup, dependency installation, and server launch.
#
# Prerequisites:
#   - Python 3.9 or higher installed
#   - pip (Python package manager)
#   - .env file configured with API keys (see .env.example)
#
# Usage:
#   ./run.sh                    # Run in background (HTTP mode, default)
#   ./run.sh -f                 # Run in foreground (see all logs)
#   ./run.sh --https            # Run with HTTPS (auto-generates self-signed cert)
#   ./run.sh --https -f         # Run HTTPS in foreground
#   ./run.sh --cert /path/cert.pem --key /path/key.pem  # Use custom certificate
#
# What this script does:
#   1. Creates Python virtual environment if it doesn't exist
#   2. Activates the virtual environment
#   3. Installs/updates dependencies from requirements.txt
#   4. Creates data directory for SQLite database
#   5. Optionally generates self-signed certificate for HTTPS
#   6. Starts the FastAPI server on http(s)://127.0.0.1:8000
#
# To stop the server:
#   - Press Ctrl+C in terminal, or
#   - Run ./stop.sh from another terminal
#
# Logs:
#   Server logs are output to the terminal in real-time
#
#===============================================================================

# Change to script directory (project root)
cd "$(dirname "$0")"

# Default values
BACKGROUND_MODE=true
HTTPS_MODE=false
CUSTOM_CERT=""
CUSTOM_KEY=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--foreground)
            BACKGROUND_MODE=false
            shift
            ;;
        --https)
            HTTPS_MODE=true
            shift
            ;;
        --cert)
            CUSTOM_CERT="$2"
            shift 2
            ;;
        --key)
            CUSTOM_KEY="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: ./run.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -f, --foreground    Run server in foreground (see logs)"
            echo "  --https             Enable HTTPS with self-signed certificate"
            echo "  --cert PATH         Path to custom SSL certificate file"
            echo "  --key PATH          Path to custom SSL private key file"
            echo "  -h, --help          Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./run.sh                              # HTTP mode, background (default)"
            echo "  ./run.sh --https                      # HTTPS with auto-generated cert"
            echo "  ./run.sh -f                           # HTTP in foreground (see logs)"
            echo "  ./run.sh --cert cert.pem --key key.pem  # Custom certificate"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo "========================================"
echo "  ABCT - A Better Crypto Tracker"
echo "========================================"
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required but not installed."
    echo "Please install Python 3.9 or higher and try again."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python version: $PYTHON_VERSION"

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment."
        exit 1
    fi
    echo "Virtual environment created successfully."
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies."
    exit 1
fi

# Create data directory if it doesn't exist
if [ ! -d "data" ]; then
    echo "Creating data directory..."
    mkdir -p data
fi

# Create certs directory if it doesn't exist
if [ ! -d "data/certs" ]; then
    mkdir -p data/certs
fi

# Create logs directory if it doesn't exist
if [ ! -d "logs" ]; then
    mkdir -p logs
fi

# Check for .env file
if [ ! -f ".env" ]; then
    echo ""
    echo "WARNING: No .env file found."
    echo "Copy .env.example to .env and add your API keys."
    echo ""
fi

# Handle SSL configuration
SSL_MODE="http"
SSL_CERT=""
SSL_KEY=""
SERVER_URL="http://127.0.0.1:8000"

# If custom cert/key provided, use those
if [ -n "$CUSTOM_CERT" ] && [ -n "$CUSTOM_KEY" ]; then
    if [ ! -f "$CUSTOM_CERT" ]; then
        echo "ERROR: Certificate file not found: $CUSTOM_CERT"
        exit 1
    fi
    if [ ! -f "$CUSTOM_KEY" ]; then
        echo "ERROR: Key file not found: $CUSTOM_KEY"
        exit 1
    fi
    SSL_MODE="https-custom"
    SSL_CERT="$CUSTOM_CERT"
    SSL_KEY="$CUSTOM_KEY"
    SERVER_URL="https://127.0.0.1:8000"
    echo "Using custom SSL certificate"
elif [ "$HTTPS_MODE" = true ]; then
    SSL_MODE="https-self-signed"
    SSL_CERT="data/certs/server.crt"
    SSL_KEY="data/certs/server.key"
    SERVER_URL="https://127.0.0.1:8000"

    # Generate self-signed certificate if it doesn't exist
    if [ ! -f "$SSL_CERT" ] || [ ! -f "$SSL_KEY" ]; then
        echo ""
        echo "Generating self-signed SSL certificate..."
        python3 -c "
import sys
sys.path.insert(0, 'backend')
from pathlib import Path
from services.ssl_service import get_ssl_service

certs_dir = Path('data/certs')
ssl_service = get_ssl_service(certs_dir)
cert_path, key_path = ssl_service.generate_self_signed_cert(
    hostname='localhost',
    valid_days=365
)
print(f'Certificate generated: {cert_path}')
print(f'Private key generated: {key_path}')
"
        if [ $? -ne 0 ]; then
            echo "ERROR: Failed to generate SSL certificate."
            exit 1
        fi
        echo "Certificate generated successfully."
    else
        echo "Using existing self-signed certificate"
    fi
fi

# Export environment variables for Python
export ABCT_SSL_MODE="$SSL_MODE"
export ABCT_SSL_CERT="$SSL_CERT"
export ABCT_SSL_KEY="$SSL_KEY"

# Run the application
echo ""
echo "========================================"
echo "  Starting ABCT Portfolio Tracker..."
echo "========================================"
echo ""
echo "Server URL: $SERVER_URL"

if [ "$SSL_MODE" != "http" ]; then
    echo "SSL Mode: $SSL_MODE"
    echo ""
    echo "NOTE: Self-signed certificates will show a browser warning."
    echo "This is normal for local development. To proceed:"
    echo "  - Chrome: Click 'Advanced' > 'Proceed to localhost (unsafe)'"
    echo "  - Firefox: Click 'Advanced' > 'Accept the Risk and Continue'"
    echo "  - Safari: Click 'Show Details' > 'visit this website'"
fi

echo ""

cd backend

if [ "$BACKGROUND_MODE" = true ]; then
    echo "Starting server in background mode..."
    nohup python main.py > ../logs/server.log 2>&1 &
    SERVER_PID=$!
    echo $SERVER_PID > ../data/server.pid

    # Wait for server to be ready
    echo "Waiting for server to start..."
    PROTOCOL="http"
    if [ "$SSL_MODE" != "http" ]; then
        PROTOCOL="https"
    fi

    for i in {1..30}; do
        if curl -sk "$PROTOCOL://127.0.0.1:8000/health" > /dev/null 2>&1; then
            echo ""
            echo "Server started successfully (PID: $SERVER_PID)"
            echo "URL: $SERVER_URL"
            echo "Logs: logs/server.log"
            echo "Stop: ./stop.sh"
            echo ""
            exit 0
        fi
        sleep 0.5
    done
    echo "Warning: Server may still be starting. Check logs/server.log"
else
    echo "Press Ctrl+C to stop the server"
    echo "(Running in foreground mode - use './run.sh' without -f to run in background)"
    echo ""
    python main.py
fi
