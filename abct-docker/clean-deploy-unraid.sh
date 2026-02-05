#!/bin/bash
#
# Clean Deploy ABCT Dashboard on Unraid
# Creates a fresh instance with new database
#
# Usage:
#   ./abct-docker/clean-deploy-unraid.sh <unraid-ip> [port]
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "========================================"
echo "  ABCT Dashboard - Clean Deploy"
echo "========================================"
echo ""
echo -e "${RED}WARNING: This will create a FRESH deployment${NC}"
echo "  - New empty database"
echo "  - No existing wallets or settings"
echo "  - Preserves API keys if you choose"
echo ""

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Configuration
CONTAINER_NAME="abct-dashboard"
REMOTE_PATH="/mnt/user/appdata/ABCT"
DATA_DIR="/mnt/user/appdata/abct-dashboard"

# Get Unraid host
UNRAID_HOST="${1:-}"
if [ -z "$UNRAID_HOST" ]; then
    read -p "Unraid IP or hostname: " UNRAID_HOST
    if [ -z "$UNRAID_HOST" ]; then
        echo -e "${RED}Error: Unraid IP or hostname is required${NC}"
        exit 1
    fi
fi

# Get port
PORT="${2:-}"
if [ -z "$PORT" ]; then
    read -p "Dashboard port [8081]: " PORT
    PORT="${PORT:-8081}"
fi

SSH_USER="root"

echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  Unraid:     $SSH_USER@$UNRAID_HOST"
echo "  Port:       $PORT"
echo "  Data Dir:   $DATA_DIR"
echo ""

# Ask about API keys
echo -e "${YELLOW}API Key Options:${NC}"
echo "  1) Preserve existing API keys"
echo "  2) Start with no API keys (configure after)"
echo ""
read -p "Choice [1]: " API_CHOICE
API_CHOICE="${API_CHOICE:-1}"

echo ""
read -p "Proceed with CLEAN deployment? (type 'yes' to confirm): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Cancelled."
    exit 0
fi

# SSH connection multiplexing
SSH_CONTROL_PATH="/tmp/ssh-abct-clean-%r@%h:%p"
SSH_OPTS="-o ControlMaster=auto -o ControlPath=$SSH_CONTROL_PATH -o ControlPersist=60"

echo ""
echo -e "${YELLOW}[1/5] Syncing files to Unraid...${NC}"

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

# Run deployment on Unraid
ssh $SSH_OPTS "${SSH_USER}@${UNRAID_HOST}" bash -s "$CONTAINER_NAME" "$REMOTE_PATH" "$DATA_DIR" "$PORT" "$API_CHOICE" << 'ENDSSH'
    CONTAINER_NAME="$1"
    REMOTE_PATH="$2"
    DATA_DIR="$3"
    PORT="$4"
    API_CHOICE="$5"
    CONFIG_FILE="${DATA_DIR}/.env"
    BACKUP_DIR="${DATA_DIR}_backup_$(date +%Y%m%d_%H%M%S)"

    set -e

    echo "[2/5] Backing up existing data (if any)..."

    # Save API keys if option 1
    if [ "$API_CHOICE" = "1" ] && docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
        echo "  Extracting API keys from running container..."
        BLOCKFROST_KEY=$(docker exec "$CONTAINER_NAME" printenv BLOCKFROST_API_KEY 2>/dev/null || echo "")
        TAPTOOLS_KEY=$(docker exec "$CONTAINER_NAME" printenv TAPTOOLS_API_KEY 2>/dev/null || echo "")
        CEXPLORER_KEY=$(docker exec "$CONTAINER_NAME" printenv CEXPLORER_API_KEY 2>/dev/null || echo "")
        MAESTRO_KEY=$(docker exec "$CONTAINER_NAME" printenv MAESTRO_API_KEY 2>/dev/null || echo "")
        ALCHEMY_KEY=$(docker exec "$CONTAINER_NAME" printenv ALCHEMY_API_KEY 2>/dev/null || echo "")
        ETHERSCAN_KEY=$(docker exec "$CONTAINER_NAME" printenv ETHERSCAN_API_KEY 2>/dev/null || echo "")
        BEACONCHAIN_KEY=$(docker exec "$CONTAINER_NAME" printenv BEACONCHAIN_API_KEY 2>/dev/null || echo "")
        HELIUS_KEY=$(docker exec "$CONTAINER_NAME" printenv HELIUS_API_KEY 2>/dev/null || echo "")
        COINGECKO_KEY=$(docker exec "$CONTAINER_NAME" printenv COINGECKO_API_KEY 2>/dev/null || echo "")
        CMC_KEY=$(docker exec "$CONTAINER_NAME" printenv CMC_API_KEY 2>/dev/null || echo "")
        echo "  ✓ API keys saved"
    fi

    # Backup existing data directory
    if [ -d "$DATA_DIR" ]; then
        echo "  Creating backup: $BACKUP_DIR"
        cp -r "$DATA_DIR" "$BACKUP_DIR"
        echo "  ✓ Backup created (old database preserved)"
    fi

    # Stop and remove container
    echo "  Stopping container..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
    echo "  ✓ Container stopped"

    # Remove old data directory (fresh start!)
    echo "  Removing old data directory..."
    rm -rf "$DATA_DIR"
    echo "  ✓ Old data removed"

    # Create fresh data directory
    mkdir -p "$DATA_DIR"
    chmod 755 "$DATA_DIR"
    echo "  ✓ Fresh data directory created"

    # Write config file with API keys (if preserved)
    if [ "$API_CHOICE" = "1" ]; then
        echo "  Writing API keys to config..."
        cat > "$CONFIG_FILE" << EOF
# Cardano APIs
BLOCKFROST_API_KEY=${BLOCKFROST_KEY:-}
TAPTOOLS_API_KEY=${TAPTOOLS_KEY:-}
CEXPLORER_API_KEY=${CEXPLORER_KEY:-}
MAESTRO_API_KEY=${MAESTRO_KEY:-}
# EVM APIs
ALCHEMY_API_KEY=${ALCHEMY_KEY:-}
ETHERSCAN_API_KEY=${ETHERSCAN_KEY:-}
BEACONCHAIN_API_KEY=${BEACONCHAIN_KEY:-}
# Solana APIs
HELIUS_API_KEY=${HELIUS_KEY:-}
# Pricing APIs
COINGECKO_API_KEY=${COINGECKO_KEY:-}
CMC_API_KEY=${CMC_KEY:-}
# Optional services
NFT_PRICE_SERVICE_URL=
NFT_IMAGE_CACHE_ENABLED=false
# Authentication
ABCT_REQUIRE_AUTH=false
ABCT_ADMIN_USER=
ABCT_ADMIN_PASSWORD=
EOF
        chmod 600 "$CONFIG_FILE"
        echo "  ✓ Config file created"
    fi

    # Clean up old images
    echo "  Cleaning up old Docker images..."
    docker image prune -f > /dev/null 2>&1 || true
    docker images "$CONTAINER_NAME" --format "{{.ID}} {{.Tag}}" | grep -v latest | awk '{print $1}' | xargs -r docker rmi 2>/dev/null || true
    echo "  ✓ Cleanup complete"

    echo ""
    echo "[3/5] Building Docker image..."
    cd "$REMOTE_PATH"

    docker build --progress=plain -t "$CONTAINER_NAME:latest" -f abct-docker/Dockerfile . 2>&1 | {
        while IFS= read -r line; do
            if echo "$line" | grep -qE "^#[0-9]+ \[[0-9]+/[0-9]+\]"; then
                STEP_INFO=$(echo "$line" | grep -oE "\[[0-9]+/[0-9]+\]" | head -1)
                CURRENT=$(echo "$STEP_INFO" | sed 's/\[//;s/\/.*//')
                TOTAL=$(echo "$STEP_INFO" | sed 's/.*\///;s/\]//')
                PERCENT=$((CURRENT * 100 / TOTAL))
                FILLED=$((PERCENT / 5))
                EMPTY=$((20 - FILLED))
                BAR=$(printf '%*s' "$FILLED" | tr ' ' '#')$(printf '%*s' "$EMPTY" | tr ' ' '-')
                DESC=$(echo "$line" | sed 's/^#[0-9]* \[[0-9]*\/[0-9]*\] //' | cut -c1-50)
                printf "\r  \033[K[%s] %3d%%  Step %s - %s" "$BAR" "$PERCENT" "$STEP_INFO" "$DESC"
            fi
        done
        echo ""
    }

    if [ $? -ne 0 ]; then
        echo "  ✗ Build failed!"
        exit 1
    fi

    echo "  ✓ Image built"

    echo ""
    echo "[4/5] Starting container..."

    # Load API keys from config
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
        echo "  ✓ Loaded config"
    fi

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
        -e "BEACONCHAIN_API_KEY=${BEACONCHAIN_KEY:-}" \
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
        echo "  ⚠ Service may still be starting"
    fi

    echo ""
    echo "[5/5] Initializing database..."

    # Database will auto-initialize on first request
    # But we can trigger it by hitting the health endpoint
    docker exec "$CONTAINER_NAME" python3 -c "from backend.database import init_db; init_db()" 2>&1 || true

    echo "  ✓ Database initialized"

ENDSSH

SSH_EXIT_CODE=$?

# Get deployed version
echo ""
echo -e "${YELLOW}Extracting version information...${NC}"
DEPLOYED_VERSION=$(ssh $SSH_OPTS "${SSH_USER}@${UNRAID_HOST}" "docker exec $CONTAINER_NAME grep -o 'v[0-9.]*\s*(BUILD\s*[0-9]*)' /app/frontend/index.html 2>/dev/null | head -1" || echo "")

if [ $SSH_EXIT_CODE -eq 0 ]; then
    echo ""
    echo -e "${GREEN}========================================"
    echo "  Clean Deployment Complete!"
    echo "========================================${NC}"
    echo ""
    echo "Dashboard: http://${UNRAID_HOST}:${PORT}"
    if [ -n "$DEPLOYED_VERSION" ]; then
        echo "Version:   ${DEPLOYED_VERSION}"
    fi
    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo "  1. Create a new user account"
    echo "  2. Configure API keys (if not preserved)"
    echo "  3. Add your wallets"
    echo ""
    echo -e "${YELLOW}Old Data Backup:${NC}"
    echo "  Your old database is backed up on unRAID at:"
    OLD_BACKUP=$(ssh $SSH_OPTS "${SSH_USER}@${UNRAID_HOST}" "ls -dt ${DATA_DIR}_backup_* 2>/dev/null | head -1" || echo "")
    if [ -n "$OLD_BACKUP" ]; then
        echo "  ${OLD_BACKUP}"
    fi
    echo ""
else
    echo ""
    echo -e "${RED}Deployment failed. Check the output above.${NC}"
    exit 1
fi

# Clean up SSH connection
ssh -O exit -o ControlPath="$SSH_CONTROL_PATH" "${SSH_USER}@${UNRAID_HOST}" 2>/dev/null || true
