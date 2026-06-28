#!/bin/bash
# ABCT Dashboard - Deploy from Git
# Usage: ./deploy_from_git.sh [options]
#
# Environment variables (or set defaults below):
#   ABCT_STATIC_IP       - Static IP for container (default: 192.168.50.232)
#   ABCT_DOCKER_NETWORK  - Docker network name (default: br0)
#   ABCT_DATA_PATH       - Host path for persistent data (default: /mnt/user/appdata/abct-dashboard)
#   GIT_REPO             - GitHub repo URL (default: https://github.com/Tarrant64/abct.git)
#   GIT_BRANCH           - Branch to deploy (default: main)

set -e

# --- Configuration ---
ABCT_STATIC_IP="${ABCT_STATIC_IP:-192.168.50.232}"
ABCT_DOCKER_NETWORK="${ABCT_DOCKER_NETWORK:-br0}"
ABCT_DATA_PATH="${ABCT_DATA_PATH:-/mnt/user/appdata/abct-dashboard}"
GIT_REPO="${GIT_REPO:-https://github.com/Tarrant64/abct.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"

CLONE_DIR="/tmp/abct-deploy"
CONTAINER_NAME="abct-dashboard"

echo "================================================"
echo " ABCT Dashboard - Deploy from Git"
echo "================================================"
echo " Network : ${ABCT_DOCKER_NETWORK}"
echo " Static IP: ${ABCT_STATIC_IP}"
echo " Data path: ${ABCT_DATA_PATH}"
echo " Repo     : ${GIT_REPO} (${GIT_BRANCH})"
echo "================================================"

# Load env file if present
ENV_FILE="/mnt/user/appdata/ABCT/.env"
if [ -f "$ENV_FILE" ]; then
    echo "[1/7] Loading env from $ENV_FILE"
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "[1/7] No .env file at $ENV_FILE (continuing without)"
fi

# Clone / refresh source
echo "[2/7] Fetching latest code from Git..."
rm -rf "$CLONE_DIR"
git clone --depth=1 --branch "$GIT_BRANCH" "$GIT_REPO" "$CLONE_DIR"

# Ensure data directory exists
echo "[3/7] Ensuring data directory..."
mkdir -p "$ABCT_DATA_PATH"

# Build image
echo "[4/7] Building Docker image..."
cd "$CLONE_DIR"
docker build -t "${CONTAINER_NAME}:latest" -f abct-docker/Dockerfile .

# Stop and remove old container
echo "[5/7] Stopping old container (if running)..."
docker stop "$CONTAINER_NAME" 2>/dev/null && docker rm "$CONTAINER_NAME" 2>/dev/null || true

# Run new container
echo "[6/7] Starting container on ${ABCT_DOCKER_NETWORK} @ ${ABCT_STATIC_IP}..."
docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    --network "$ABCT_DOCKER_NETWORK" \
    --ip "$ABCT_STATIC_IP" \
    -v "${ABCT_DATA_PATH}:/app/data" \
    -e "BLOCKFROST_API_KEY=${BLOCKFROST_API_KEY:-}" \
    -e "COINGECKO_API_KEY=${COINGECKO_API_KEY:-}" \
    -e "NFT_PRICE_SERVICE_URL=${NFT_PRICE_SERVICE_URL:-}" \
    -e "DATABASE_PATH=/app/data/portfolio.db" \
    -e "ABCT_REQUIRE_AUTH=${ABCT_REQUIRE_AUTH:-true}" \
    -e "ABCT_ADMIN_USER=${ABCT_ADMIN_USER:-}" \
    -e "ABCT_ADMIN_PASSWORD=${ABCT_ADMIN_PASSWORD:-}" \
    --label "net.unraid.docker.icon=https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/png/crypto.png" \
    --label "net.unraid.docker.webui=http://[IP]:80/" \
    "${CONTAINER_NAME}:latest"

# Cleanup
echo "[7/7] Cleaning up build directory..."
rm -rf "$CLONE_DIR"

echo ""
echo "================================================"
echo " Deploy complete!"
echo " Container IP : ${ABCT_STATIC_IP}"
echo " Check status : docker ps | grep ${CONTAINER_NAME}"
echo " View logs    : docker logs -f ${CONTAINER_NAME}"
echo "================================================"
