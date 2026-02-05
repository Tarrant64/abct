#!/bin/bash
#
# Update ABCT Dashboard on Unraid
# Run this from your Mac after making changes to sync and rebuild
#
# Usage:
#   ./abct-docker/update-unraid.sh <unraid-ip>
#   ./abct-docker/update-unraid.sh <unraid-ip> 8081
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "========================================"
echo "  ABCT Dashboard - Update Unraid"
echo "========================================"
echo ""

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Configuration
CONTAINER_NAME="abct-dashboard"
REMOTE_PATH="/mnt/user/appdata/ABCT"
DATA_DIR="/mnt/user/appdata/abct-dashboard"

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
    read -p "Dashboard port [8081]: " PORT
    PORT="${PORT:-8081}"
fi

# SSH user (usually root for Unraid)
SSH_USER="root"

echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  Project:    $PROJECT_DIR"
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
# SSH Connection Multiplexing Setup
# ===========================================
# This allows all SSH/rsync operations to reuse a single connection
# Reduces password prompts from 3 to 1
# The first SSH/rsync command will prompt for password and create the master connection
# All subsequent commands will reuse it automatically
SSH_CONTROL_PATH="/tmp/ssh-abct-update-%r@%h:%p"
SSH_OPTS="-o ControlMaster=auto -o ControlPath=$SSH_CONTROL_PATH -o ControlPersist=60"

echo -e "${YELLOW}Note: You'll be prompted for password once. Subsequent operations will reuse the connection.${NC}"
echo ""

# ===========================================
# STEP 1: Sync files to Unraid
# ===========================================
echo -e "${YELLOW}[1/4] Syncing files to Unraid...${NC}"

# Use rsync for efficient sync (only changed files)
# Reuses the SSH master connection (no password prompt)
rsync -avz --progress \
    -e "ssh $SSH_OPTS" \
    --exclude '.git' \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    --exclude 'data/*.db' \
    --exclude '.env' \
    "$PROJECT_DIR/" "${SSH_USER}@${UNRAID_HOST}:${REMOTE_PATH}/"

echo -e "${GREEN}  ✓ Files synced${NC}"
echo ""

# ===========================================
# STEP 2-4: Run commands on Unraid via SSH
# ===========================================
echo -e "${YELLOW}[2/4] Connecting to Unraid and rebuilding...${NC}"
echo ""

# Run commands on Unraid (output streams in real-time)
# Reuses the SSH master connection (no password prompt)
ssh $SSH_OPTS "${SSH_USER}@${UNRAID_HOST}" bash -s "$CONTAINER_NAME" "$REMOTE_PATH" "$DATA_DIR" "$PORT" << 'ENDSSH'
    CONTAINER_NAME="$1"
    REMOTE_PATH="$2"
    DATA_DIR="$3"
    PORT="$4"
    CONFIG_FILE="${DATA_DIR}/.env"

    set -e

    echo "[2/4] Stopping existing container..."

    # Extract API keys from running container before stopping
    if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
        echo "  Saving API keys from running container..."
        # Cardano APIs
        BLOCKFROST_KEY=$(docker exec "$CONTAINER_NAME" printenv BLOCKFROST_API_KEY 2>/dev/null || echo "")
        TAPTOOLS_KEY=$(docker exec "$CONTAINER_NAME" printenv TAPTOOLS_API_KEY 2>/dev/null || echo "")
        CEXPLORER_KEY=$(docker exec "$CONTAINER_NAME" printenv CEXPLORER_API_KEY 2>/dev/null || echo "")
        MAESTRO_KEY=$(docker exec "$CONTAINER_NAME" printenv MAESTRO_API_KEY 2>/dev/null || echo "")
        # EVM APIs
        ALCHEMY_KEY=$(docker exec "$CONTAINER_NAME" printenv ALCHEMY_API_KEY 2>/dev/null || echo "")
        ETHERSCAN_KEY=$(docker exec "$CONTAINER_NAME" printenv ETHERSCAN_API_KEY 2>/dev/null || echo "")
        BEACONCHAIN_KEY=$(docker exec "$CONTAINER_NAME" printenv BEACONCHAIN_API_KEY 2>/dev/null || echo "")
        # Solana APIs
        HELIUS_KEY=$(docker exec "$CONTAINER_NAME" printenv HELIUS_API_KEY 2>/dev/null || echo "")
        # Pricing APIs
        COINGECKO_KEY=$(docker exec "$CONTAINER_NAME" printenv COINGECKO_API_KEY 2>/dev/null || echo "")
        CMC_KEY=$(docker exec "$CONTAINER_NAME" printenv CMC_API_KEY 2>/dev/null || echo "")
        # Optional services
        NFT_SERVICE_URL=$(docker exec "$CONTAINER_NAME" printenv NFT_PRICE_SERVICE_URL 2>/dev/null || echo "")
        NFT_IMAGE_CACHE=$(docker exec "$CONTAINER_NAME" printenv NFT_IMAGE_CACHE_ENABLED 2>/dev/null || echo "false")
        # Authentication settings
        REQUIRE_AUTH=$(docker exec "$CONTAINER_NAME" printenv ABCT_REQUIRE_AUTH 2>/dev/null || echo "false")
        ADMIN_USER=$(docker exec "$CONTAINER_NAME" printenv ABCT_ADMIN_USER 2>/dev/null || echo "")
        ADMIN_PASSWORD=$(docker exec "$CONTAINER_NAME" printenv ABCT_ADMIN_PASSWORD 2>/dev/null || echo "")

        # Save to config file for future rebuilds
        mkdir -p "$DATA_DIR"
        cat > "$CONFIG_FILE" << EOF
# Cardano APIs
BLOCKFROST_API_KEY=$BLOCKFROST_KEY
TAPTOOLS_API_KEY=$TAPTOOLS_KEY
CEXPLORER_API_KEY=$CEXPLORER_KEY
MAESTRO_API_KEY=$MAESTRO_KEY
# EVM APIs
ALCHEMY_API_KEY=$ALCHEMY_KEY
ETHERSCAN_API_KEY=$ETHERSCAN_KEY
BEACONCHAIN_API_KEY=$BEACONCHAIN_KEY
# Solana APIs
HELIUS_API_KEY=$HELIUS_KEY
# Pricing APIs
COINGECKO_API_KEY=$COINGECKO_KEY
CMC_API_KEY=$CMC_KEY
# Optional services
NFT_PRICE_SERVICE_URL=$NFT_SERVICE_URL
NFT_IMAGE_CACHE_ENABLED=$NFT_IMAGE_CACHE
# Authentication
ABCT_REQUIRE_AUTH=$REQUIRE_AUTH
ABCT_ADMIN_USER=$ADMIN_USER
ABCT_ADMIN_PASSWORD=$ADMIN_PASSWORD
EOF
        chmod 600 "$CONFIG_FILE"
        echo "  ✓ API keys saved to $CONFIG_FILE"
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

    # Build with progress tracking (shows: [################----] 88% Step [15/17] - FROM docker.io/...)
    echo ""
    (docker build --progress=plain -t "$CONTAINER_NAME:latest" -f abct-docker/Dockerfile . 2>&1; echo "BUILD_EXIT:$?" >&2) | {
        while IFS= read -r line; do
            # Extract step numbers (e.g., "#1 [1/17]" or "#22 [17/17]")
            if echo "$line" | grep -qE "^#[0-9]+ \[[0-9]+/[0-9]+\]"; then
                # Extract current/total steps
                STEP_INFO=$(echo "$line" | grep -oE "\[[0-9]+/[0-9]+\]" | head -1)
                CURRENT=$(echo "$STEP_INFO" | sed 's/\[//;s/\/.*//')
                TOTAL=$(echo "$STEP_INFO" | sed 's/.*\///;s/\]//')

                # Calculate percentage
                PERCENT=$((CURRENT * 100 / TOTAL))

                # Create progress bar (20 characters wide)
                FILLED=$((PERCENT / 5))
                EMPTY=$((20 - FILLED))
                BAR=$(printf '%*s' "$FILLED" | tr ' ' '#')$(printf '%*s' "$EMPTY" | tr ' ' '-')

                # Extract step description (everything after the step number) - truncate to 50 chars
                DESC=$(echo "$line" | sed 's/^#[0-9]* \[[0-9]*\/[0-9]*\] //' | cut -c1-50)

                # Print progress on one line (overwrite previous)
                printf "\r  \033[K[%s] %3d%%  Step %s - %s" "$BAR" "$PERCENT" "$STEP_INFO" "$DESC"
            fi
        done
        echo ""
    }

    # Check if build succeeded
    if [ $? -ne 0 ]; then
        echo ""
        echo "  ✗ Build failed!"
        exit 1
    fi

    echo ""
    echo "  ✓ Image built"

    echo ""
    echo "[4/4] Starting container..."

    # Load API keys from config file
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
        echo "  Loaded API keys from config"
    fi

    # Ensure we have keys
    if [ -z "$BLOCKFROST_API_KEY" ]; then
        echo "  WARNING: No Blockfrost API key found!"
    fi

    # Get host IP for WebUI label
    HOST_IP=$(hostname -I | awk '{print $1}')

    docker run -d \
        --name "$CONTAINER_NAME" \
        --restart unless-stopped \
        -p "${PORT}:80" \
        -v "${DATA_DIR}:/app/data" \
        -e "BLOCKFROST_API_KEY=${BLOCKFROST_API_KEY:-}" \
        -e "TAPTOOLS_API_KEY=${TAPTOOLS_API_KEY:-}" \
        -e "CEXPLORER_API_KEY=${CEXPLORER_API_KEY:-}" \
        -e "MAESTRO_API_KEY=${MAESTRO_API_KEY:-}" \
        -e "ALCHEMY_API_KEY=${ALCHEMY_API_KEY:-}" \
        -e "ETHERSCAN_API_KEY=${ETHERSCAN_API_KEY:-}" \
        -e "BEACONCHAIN_API_KEY=${BEACONCHAIN_API_KEY:-}" \
        -e "HELIUS_API_KEY=${HELIUS_API_KEY:-}" \
        -e "COINGECKO_API_KEY=${COINGECKO_API_KEY:-}" \
        -e "CMC_API_KEY=${CMC_API_KEY:-}" \
        -e "NFT_PRICE_SERVICE_URL=${NFT_PRICE_SERVICE_URL:-}" \
        -e "NFT_IMAGE_CACHE_ENABLED=${NFT_IMAGE_CACHE_ENABLED:-false}" \
        -e "ABCT_REQUIRE_AUTH=${ABCT_REQUIRE_AUTH:-false}" \
        -e "ABCT_ADMIN_USER=${ABCT_ADMIN_USER:-}" \
        -e "ABCT_ADMIN_PASSWORD=${ABCT_ADMIN_PASSWORD:-}" \
        --label "net.unraid.docker.webui=http://[IP]:${PORT}/" \
        --label "net.unraid.docker.icon=https://raw.githubusercontent.com/walkxcode/dashboard-icons/main/png/crypto.png" \
        "$CONTAINER_NAME:latest"

    echo "  Waiting for startup..."
    sleep 5

    if curl -sf "http://localhost:${PORT}/health" > /dev/null 2>&1; then
        echo "  ✓ Service is healthy!"
    else
        echo "  ⚠ Service may still be starting. Check: docker logs $CONTAINER_NAME"
    fi

    echo ""
    echo "Running database migrations..."

    # Run comprehensive SQL migration script (applies all .sql migrations)
    echo "  Applying SQL migrations..."
    if docker exec "$CONTAINER_NAME" python3 /app/backend/run_migrations.py 2>&1; then
        echo "  ✓ SQL migrations applied"
    else
        echo "  ⚠ SQL migration may have failed"
    fi

    # Run Python migrations (safe to run multiple times)
    echo "  Applying Python migrations..."
    docker exec "$CONTAINER_NAME" python3 /app/backend/migrations/add_snapshot_quantities.py 2>&1 || true

    # Run legacy schema fixes (safe to run multiple times)
    echo "  Running schema fixes..."
    if docker exec "$CONTAINER_NAME" python3 /app/backend/fix_api_settings_schema.py 2>&1; then
        echo "  ✓ Schema fixes applied"
    else
        echo "  ⚠ Schema fix may have failed"
    fi

    echo "  ✓ Database migrations complete"

    echo ""
    echo "Verifying admin account..."
    docker exec "$CONTAINER_NAME" python3 backend/check_auth.py 2>&1 | grep -E "✅|❌|Resetting" || true
    echo "  ✓ Admin account verified"

ENDSSH

# Get result (check if SSH command succeeded)
SSH_EXIT_CODE=$?

# Extract version information from deployed container (separate quick SSH call)
# Reuses the SSH master connection (no password prompt)
echo ""
echo -e "${YELLOW}Extracting version information...${NC}"
DEPLOYED_VERSION=$(ssh $SSH_OPTS "${SSH_USER}@${UNRAID_HOST}" "docker exec $CONTAINER_NAME grep -o 'v[0-9.]*\s*(BUILD\s*[0-9]*)' /app/frontend/index.html 2>/dev/null | head -1" || echo "")

if [ $SSH_EXIT_CODE -eq 0 ]; then
    echo ""
    echo -e "${GREEN}========================================"
    echo "  Update Complete!"
    echo "========================================${NC}"
    echo ""
    echo "Dashboard: http://${UNRAID_HOST}:${PORT}"

    # Display version if extracted
    if [ -n "$DEPLOYED_VERSION" ]; then
        echo "Version:   ${DEPLOYED_VERSION}"
    fi
    echo ""
else
    echo ""
    echo -e "${RED}Update failed. Check the output above for errors.${NC}"
    exit 1
fi

# Clean up SSH master connection if it exists
ssh -O exit -o ControlPath="$SSH_CONTROL_PATH" "${SSH_USER}@${UNRAID_HOST}" 2>/dev/null || true
