#!/bin/bash
#
# Update Cardano NFT Floor Price Service on Unraid
# Run this from your Mac after making changes to sync and rebuild
#
# Usage:
#   ./nft-price-service/update-unraid.sh <unraid-ip>
#   ./nft-price-service/update-unraid.sh <unraid-ip> 8082
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo ""
echo "========================================"
echo "  Cardano NFT Price Service - Update Unraid"
echo "========================================"
echo ""

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration
CONTAINER_NAME="nft-floor-prices"
REMOTE_PATH="/mnt/user/appdata/nft-price-service"
DATA_DIR="/mnt/user/appdata/nft-floor-prices"

# Get Unraid host (required)
UNRAID_HOST="${1:-}"
if [ -z "$UNRAID_HOST" ]; then
    read -p "Unraid IP or hostname: " UNRAID_HOST
    if [ -z "$UNRAID_HOST" ]; then
        echo -e "${RED}Error: Unraid IP or hostname is required${NC}"
        echo "Usage: $0 <unraid-ip> [port]"
        exit 1
    fi
fi

# Get port
PORT="${2:-}"
if [ -z "$PORT" ]; then
    read -p "Service port [8082]: " PORT
    PORT="${PORT:-8082}"
fi

# SSH user (usually root for Unraid)
SSH_USER="root"

echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  Source:     $SCRIPT_DIR"
echo "  Unraid:     $SSH_USER@$UNRAID_HOST"
echo "  Remote:     $REMOTE_PATH"
echo "  Port:       $PORT"
echo ""

# Confirm
read -p "Proceed with update? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""

# ===========================================
# STEP 1: Sync files to Unraid
# ===========================================
echo -e "${YELLOW}[1/4] Syncing files to Unraid...${NC}"

# Use rsync for efficient sync (only changed files)
rsync -avz --progress \
    --exclude '.git' \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    --exclude 'data/*.db' \
    --exclude '.env' \
    "$SCRIPT_DIR/" "${SSH_USER}@${UNRAID_HOST}:${REMOTE_PATH}/"

echo -e "${GREEN}  ✓ Files synced${NC}"
echo ""

# ===========================================
# STEP 2-4: Run commands on Unraid via SSH
# ===========================================
echo -e "${YELLOW}[2/4] Connecting to Unraid and rebuilding...${NC}"
echo ""

ssh "${SSH_USER}@${UNRAID_HOST}" bash -s "$CONTAINER_NAME" "$REMOTE_PATH" "$DATA_DIR" "$PORT" << 'ENDSSH'
    CONTAINER_NAME="$1"
    REMOTE_PATH="$2"
    DATA_DIR="$3"
    PORT="$4"
    CONFIG_FILE="${DATA_DIR}/.env"

    set -e

    echo "[2/4] Stopping existing container..."

    # Extract API key from running container before stopping
    if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
        echo "  Saving API key from running container..."
        TAPTOOLS_KEY=$(docker exec "$CONTAINER_NAME" printenv TAPTOOLS_API_KEY 2>/dev/null || echo "")

        # Save to config file for future rebuilds
        mkdir -p "$DATA_DIR"
        if [ -n "$TAPTOOLS_KEY" ]; then
            echo "TAPTOOLS_API_KEY=$TAPTOOLS_KEY" > "$CONFIG_FILE"
            chmod 600 "$CONFIG_FILE"
            echo "  ✓ API key saved to $CONFIG_FILE"
        fi
    fi

    # Stop and remove container
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
    echo "  ✓ Container stopped"

    # Clean up old/dangling images to prevent orphans
    echo "  Cleaning up old images..."
    docker image prune -f > /dev/null 2>&1 || true
    # Remove old versions of this specific image
    docker images "$CONTAINER_NAME" --format "{{.ID}} {{.Tag}}" | grep -v latest | awk '{print $1}' | xargs -r docker rmi 2>/dev/null || true
    echo "  ✓ Old images cleaned"

    echo ""
    echo "[3/4] Building Docker image..."
    cd "$REMOTE_PATH"
    docker build -t "$CONTAINER_NAME:latest" .
    echo ""
    echo "  ✓ Image built"

    echo ""
    echo "[4/4] Starting container..."

    # Load API key from config file
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
        echo "  Loaded API key from config"
    fi

    # Ensure we have key
    if [ -z "$TAPTOOLS_API_KEY" ]; then
        echo "  WARNING: No TapTools API key found!"
    fi

    docker run -d \
        --name "$CONTAINER_NAME" \
        --restart unless-stopped \
        -p "${PORT}:8080" \
        -v "${DATA_DIR}:/app/data" \
        -e "TAPTOOLS_API_KEY=${TAPTOOLS_API_KEY:-}" \
        -e "UPDATE_INTERVAL_MINUTES=15" \
        -e "CALLS_PER_UPDATE=1" \
        --label "net.unraid.docker.webui=http://[IP]:${PORT}/status" \
        --label "net.unraid.docker.icon=https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/png/nft.png" \
        "$CONTAINER_NAME:latest"

    echo "  Waiting for startup..."
    sleep 5

    if curl -sf "http://localhost:${PORT}/status" > /dev/null 2>&1; then
        echo "  ✓ Service is healthy!"
    else
        echo "  ⚠ Service may still be starting. Check: docker logs $CONTAINER_NAME"
    fi
ENDSSH

# Get result
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}========================================"
    echo "  Update Complete!"
    echo "========================================${NC}"
    echo ""
    echo -e "Status Page: ${CYAN}http://${UNRAID_HOST}:${PORT}/health${NC}"
    echo -e "API Status:  ${CYAN}http://${UNRAID_HOST}:${PORT}/status${NC}"
    echo ""
else
    echo ""
    echo -e "${RED}Update failed. Check the output above for errors.${NC}"
    exit 1
fi
