#!/bin/bash
#
# Install Cardano NFT Floor Price Service on Unraid
#
# Usage:
#   1. Copy nft-price-service folder to Unraid (e.g., /mnt/user/appdata/nft-price-service-build)
#   2. SSH into Unraid
#   3. Run: bash /mnt/user/appdata/nft-price-service-build/unraid/install-unraid.sh
#   4. Enter your TapTools API key when prompted
#

set -e

echo "========================================"
echo "  Cardano NFT Floor Price Service - Unraid Install"
echo "========================================"
echo ""

# Configuration
CONTAINER_NAME="nft-floor-prices"
DATA_DIR="/mnt/user/appdata/nft-floor-prices"
BUILD_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"

# Check if running on Unraid
if [ ! -f /etc/unraid-version ]; then
    echo "Warning: This doesn't appear to be an Unraid system."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Get TapTools API key
if [ -z "$TAPTOOLS_API_KEY" ]; then
    read -p "Enter your TapTools API key: " TAPTOOLS_API_KEY
    if [ -z "$TAPTOOLS_API_KEY" ]; then
        echo "Error: TapTools API key is required"
        exit 1
    fi
fi

# Get port (check if default is in use)
DEFAULT_PORT=8080
if netstat -tuln 2>/dev/null | grep -q ":${DEFAULT_PORT} " || ss -tuln 2>/dev/null | grep -q ":${DEFAULT_PORT} "; then
    echo ""
    echo "Warning: Port $DEFAULT_PORT appears to be in use."
fi

echo ""
read -p "Enter port to use [${DEFAULT_PORT}]: " PORT
PORT="${PORT:-$DEFAULT_PORT}"

# Validate port is a number
if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
    echo "Error: Port must be a number"
    exit 1
fi

# Check if chosen port is available
if netstat -tuln 2>/dev/null | grep -q ":${PORT} " || ss -tuln 2>/dev/null | grep -q ":${PORT} "; then
    echo "Warning: Port $PORT appears to be in use by another service."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "Configuration:"
echo "  Container: $CONTAINER_NAME"
echo "  Data Dir:  $DATA_DIR"
echo "  Port:      $PORT"
echo "  Build Dir: $BUILD_DIR"
echo ""

# Create data directory
echo "Creating data directory..."
mkdir -p "$DATA_DIR"

# Stop existing container if running
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Stopping existing container..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
fi

# Build the image
echo "Building Docker image..."
cd "$BUILD_DIR"
docker build -t "$CONTAINER_NAME:latest" .

# Run the container
echo "Starting container..."
docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    -p "${PORT}:8080" \
    -v "${DATA_DIR}:/app/data" \
    -e "TAPTOOLS_API_KEY=${TAPTOOLS_API_KEY}" \
    -e "UPDATE_INTERVAL_MINUTES=15" \
    -e "CALLS_PER_UPDATE=1" \
    "$CONTAINER_NAME:latest"

# Wait for startup
echo "Waiting for service to start..."
sleep 5

# Verify
echo ""
echo "Checking health..."
if curl -s "http://localhost:${PORT}/health" | grep -q "healthy"; then
    echo "✓ Service is healthy!"
else
    echo "✗ Service may not be running correctly"
    echo "  Check logs: docker logs $CONTAINER_NAME"
fi

echo ""
echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo ""
echo "Service URL: http://$(hostname -I | awk '{print $1}'):${PORT}"
echo ""
echo "Useful commands:"
echo "  View status:  curl http://localhost:${PORT}/status"
echo "  View logs:    docker logs -f $CONTAINER_NAME"
echo "  Stop:         docker stop $CONTAINER_NAME"
echo "  Start:        docker start $CONTAINER_NAME"
echo "  Remove:       docker rm -f $CONTAINER_NAME"
echo ""
echo "To sync your ABCT NFT collections, run from your local machine:"
echo "  ./scripts/sync-from-abct.sh http://localhost:8000 http://UNRAID_IP:${PORT}"
echo ""
