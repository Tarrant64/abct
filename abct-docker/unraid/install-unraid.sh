#!/bin/bash
#
# Install ABCT Dashboard on Unraid
#
# Usage:
#   1. Copy entire ABCT folder to Unraid: /mnt/user/appdata/ABCT/
#   2. SSH into Unraid
#   3. Run: bash /mnt/user/appdata/ABCT/abct-docker/unraid/install-unraid.sh
#

set -e

echo "========================================"
echo "  ABCT Dashboard - Unraid Installer"
echo "========================================"
echo ""

# Configuration
CONTAINER_NAME="abct-dashboard"
DATA_DIR="/mnt/user/appdata/abct-dashboard"

# Detect paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$DOCKER_DIR")"

echo "Detected paths:"
echo "  Project: $PROJECT_DIR"
echo ""

# ===========================================
# STEP 1: Verify project structure
# ===========================================
echo "[1/6] Verifying project structure..."

MISSING=""
[ ! -d "$PROJECT_DIR/backend" ] && MISSING="$MISSING backend/"
[ ! -d "$PROJECT_DIR/frontend" ] && MISSING="$MISSING frontend/"
[ ! -d "$PROJECT_DIR/abct-docker" ] && MISSING="$MISSING abct-docker/"
[ ! -f "$PROJECT_DIR/backend/requirements.txt" ] && MISSING="$MISSING backend/requirements.txt"

if [ -n "$MISSING" ]; then
    echo "ERROR: Missing required files/folders:"
    for item in $MISSING; do
        echo "  - $item"
    done
    echo ""
    echo "Make sure you copied the entire ABCT folder to Unraid."
    exit 1
fi

echo "  ✓ Project structure verified"
echo ""

# ===========================================
# STEP 2: Clean up any existing containers
# ===========================================
echo "[2/6] Cleaning up existing containers..."

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "  Removing existing container: $CONTAINER_NAME"
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
    echo "  ✓ Removed"
else
    echo "  No existing container found"
fi
echo ""

# ===========================================
# STEP 3: Get configuration
# ===========================================
echo "[3/6] Configuration..."
echo ""

# Blockfrost API key
if [ -z "$BLOCKFROST_API_KEY" ]; then
    read -p "Blockfrost API key (required): " BLOCKFROST_API_KEY
    if [ -z "$BLOCKFROST_API_KEY" ]; then
        echo "ERROR: Blockfrost API key is required"
        exit 1
    fi
fi
echo "  ✓ Blockfrost configured"

# TapTools API key
if [ -z "$TAPTOOLS_API_KEY" ]; then
    read -p "TapTools API key (optional, press Enter to skip): " TAPTOOLS_API_KEY
fi
if [ -n "$TAPTOOLS_API_KEY" ]; then
    echo "  ✓ TapTools configured"
else
    echo "  - TapTools skipped (NFT features limited)"
fi

# Port selection
DEFAULT_PORT=8080
echo ""
if command -v ss &> /dev/null; then
    if ss -tuln | grep -q ":${DEFAULT_PORT} "; then
        echo "  Note: Port $DEFAULT_PORT appears to be in use"
    fi
elif command -v netstat &> /dev/null; then
    if netstat -tuln | grep -q ":${DEFAULT_PORT} "; then
        echo "  Note: Port $DEFAULT_PORT appears to be in use"
    fi
fi

read -p "Port to use [$DEFAULT_PORT]: " PORT
PORT="${PORT:-$DEFAULT_PORT}"

if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
    echo "ERROR: Port must be a number"
    exit 1
fi
echo "  ✓ Port: $PORT"
echo ""

# ===========================================
# STEP 4: Create data directory
# ===========================================
echo "[4/6] Creating data directory..."
mkdir -p "$DATA_DIR"
echo "  ✓ $DATA_DIR"
echo ""

# ===========================================
# STEP 5: Build Docker image
# ===========================================
echo "[5/6] Building Docker image..."
echo "  This may take 2-5 minutes..."
echo ""

cd "$PROJECT_DIR"
docker build -t "$CONTAINER_NAME:latest" -f abct-docker/Dockerfile .

echo ""
echo "  ✓ Image built successfully"
echo ""

# ===========================================
# STEP 6: Run container
# ===========================================
echo "[6/6] Starting container..."

docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    -p "${PORT}:80" \
    -v "${DATA_DIR}:/app/data" \
    -e "BLOCKFROST_API_KEY=${BLOCKFROST_API_KEY}" \
    -e "TAPTOOLS_API_KEY=${TAPTOOLS_API_KEY}" \
    -e "COINGECKO_API_KEY=${COINGECKO_API_KEY:-}" \
    -e "NFT_PRICE_SERVICE_URL=${NFT_PRICE_SERVICE_URL:-}" \
    "$CONTAINER_NAME:latest"

# Wait for startup
echo "  Waiting for service to start..."
sleep 8

# Health check
if curl -sf "http://localhost:${PORT}/health" > /dev/null 2>&1; then
    echo "  ✓ Service is healthy!"
else
    echo "  ⚠ Service may still be starting..."
    echo "    Check logs: docker logs $CONTAINER_NAME"
fi

# Get IP address
IP_ADDR=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "your-unraid-ip")

echo ""
echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo ""
echo "Dashboard URL: http://${IP_ADDR}:${PORT}"
echo ""
echo "Commands:"
echo "  Logs:    docker logs -f $CONTAINER_NAME"
echo "  Stop:    docker stop $CONTAINER_NAME"
echo "  Start:   docker start $CONTAINER_NAME"
echo "  Remove:  docker rm -f $CONTAINER_NAME"
echo ""
echo "To import existing database:"
echo "  docker cp portfolio.db ${CONTAINER_NAME}:/app/data/"
echo "  docker restart $CONTAINER_NAME"
echo ""
echo "For ABCT mobile app, use: http://${IP_ADDR}:${PORT}"
echo ""
