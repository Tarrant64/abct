#!/bin/bash
#
# Deploy ABCT Dashboard on Unraid from GitHub
# Pulls latest code directly from repository
#
# Usage:
#   ./abct-docker/deploy-from-git.sh <unraid-ip> [port] [branch] [--fresh]
#
# Options:
#   --fresh    Force a full rebuild with no Docker layer cache
#              (use when requirements.txt or system dependencies change)
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "========================================"
echo "  ABCT Dashboard - Deploy from Git"
echo "========================================"
echo ""

# Configuration
CONTAINER_NAME="abct-dashboard"
REMOTE_PATH="/mnt/user/appdata/ABCT"
DATA_DIR="/mnt/user/appdata/abct-dashboard"
GIT_REPO="https://github.com/Tarrant64/abct.git"

# Parse arguments - separate --fresh flag from positional args
FRESH_BUILD=false
POSITIONAL_ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--fresh" ]; then
        FRESH_BUILD=true
    else
        POSITIONAL_ARGS+=("$arg")
    fi
done

# Get Unraid host
UNRAID_HOST="${POSITIONAL_ARGS[0]:-}"
if [ -z "$UNRAID_HOST" ]; then
    read -p "Unraid IP or hostname: " UNRAID_HOST
    if [ -z "$UNRAID_HOST" ]; then
        echo -e "${RED}Error: Unraid IP required${NC}"
        exit 1
    fi
fi

# Get port and branch from positional args
PORT="${POSITIONAL_ARGS[1]:-8081}"
BRANCH="${POSITIONAL_ARGS[2]:-main}"

SSH_USER="root"

echo -e "${YELLOW}Configuration:${NC}"
echo "  Git Repo:   $GIT_REPO"
echo "  Branch:     $BRANCH"
echo "  Unraid:     $SSH_USER@$UNRAID_HOST"
echo "  Port:       $PORT"
if [ "$FRESH_BUILD" = true ]; then
    echo -e "  Build:      ${RED}--fresh (no cache)${NC}"
else
    echo "  Build:      cached (use --fresh to force full rebuild)"
fi
echo ""

read -p "Proceed? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 0
fi

echo ""
read -p "Reset admin password to default? (y/N) " -n 1 -r
echo
RESET_PASSWORD="no"
if [[ $REPLY =~ ^[Yy]$ ]]; then
    RESET_PASSWORD="yes"
fi

# SSH connection multiplexing
SSH_CONTROL_PATH="/tmp/ssh-abct-git-%r@%h:%p"
SSH_OPTS="-o ControlMaster=auto -o ControlPath=$SSH_CONTROL_PATH -o ControlPersist=60"

echo ""
echo -e "${YELLOW}[1/4] Cloning repository on Unraid...${NC}"

DEPLOY_START=$(date +%s)
ssh $SSH_OPTS "${SSH_USER}@${UNRAID_HOST}" bash -s "$CONTAINER_NAME" "$REMOTE_PATH" "$DATA_DIR" "$PORT" "$GIT_REPO" "$BRANCH" "$RESET_PASSWORD" "$FRESH_BUILD" << 'ENDSSH'
    CONTAINER_NAME="$1"
    REMOTE_PATH="$2"
    DATA_DIR="$3"
    PORT="$4"
    GIT_REPO="$5"
    BRANCH="$6"
    RESET_PASSWORD="$7"
    FRESH_BUILD="$8"
    CONFIG_FILE="${DATA_DIR}/.env"

    set -e

    # Save API keys from running container
    if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
        echo "  Saving API keys..."
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
        NFT_SERVICE_URL=$(docker exec "$CONTAINER_NAME" printenv NFT_PRICE_SERVICE_URL 2>/dev/null || echo "")
        NFT_IMAGE_CACHE=$(docker exec "$CONTAINER_NAME" printenv NFT_IMAGE_CACHE_ENABLED 2>/dev/null || echo "false")
        REQUIRE_AUTH=$(docker exec "$CONTAINER_NAME" printenv ABCT_REQUIRE_AUTH 2>/dev/null || echo "false")
        ADMIN_USER=$(docker exec "$CONTAINER_NAME" printenv ABCT_ADMIN_USER 2>/dev/null || echo "")
        ADMIN_PASSWORD=$(docker exec "$CONTAINER_NAME" printenv ABCT_ADMIN_PASSWORD 2>/dev/null || echo "")

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
        echo "  ✓ API keys saved"
    fi

    # Remove old code directory
    if [ -d "$REMOTE_PATH" ]; then
        echo "  Removing old code..."
        rm -rf "$REMOTE_PATH"
    fi

    # Clone repository
    echo "  Cloning from Git..."
    git clone --depth 1 --branch "$BRANCH" "$GIT_REPO" "$REMOTE_PATH"
    echo "  ✓ Repository cloned"

    echo ""
    echo "[2/4] Stopping container..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
    echo "  ✓ Container stopped"

    # Clean up images
    docker image prune -f > /dev/null 2>&1 || true
    docker images "$CONTAINER_NAME" --format "{{.ID}}" | xargs -r docker rmi 2>/dev/null || true

    echo ""
    echo "[3/4] Building Docker image..."
    cd "$REMOTE_PATH"

    BUILD_START=$(date +%s)
    CACHE_FLAG=""
    if [ "$FRESH_BUILD" = "true" ]; then
        CACHE_FLAG="--no-cache"
        echo "  (fresh build - no layer cache)"
    else
        echo "  (cached build - reusing unchanged layers)"
    fi
    docker build $CACHE_FLAG --progress=plain -t "$CONTAINER_NAME:latest" -f abct-docker/Dockerfile . 2>&1 | {
        CURRENT_STEP=""
        STEP_START=$(date +%s)
        LAST_SUB_TIME=0

        while IFS= read -r line; do
            NOW=$(date +%s)

            # New build step started
            if echo "$line" | grep -qE "^#[0-9]+ \[[0-9]+/[0-9]+\]"; then
                # Print completion of previous step if it took >2s
                if [ -n "$CURRENT_STEP" ]; then
                    STEP_TIME=$((NOW - STEP_START))
                    if [ $STEP_TIME -gt 2 ]; then
                        printf "\r\033[K  \033[0;32m✓\033[0m %s done (%ds)\n" "$CURRENT_STEP" "$STEP_TIME"
                    fi
                fi

                STEP_INFO=$(echo "$line" | grep -oE "\[[0-9]+/[0-9]+\]" | head -1)
                CURRENT=$(echo "$STEP_INFO" | sed 's/\[//;s/\/.*//')
                TOTAL=$(echo "$STEP_INFO" | sed 's/.*\///;s/\]//')
                PERCENT=$((CURRENT * 100 / TOTAL))
                FILLED=$((PERCENT / 5))
                EMPTY=$((20 - FILLED))
                BAR=$(printf '%*s' "$FILLED" | tr ' ' '#')$(printf '%*s' "$EMPTY" | tr ' ' '-')
                DESC=$(echo "$line" | sed 's/^#[0-9]* \[[0-9]*\/[0-9]*\] //' | cut -c1-55)
                CURRENT_STEP="$STEP_INFO"
                STEP_START=$NOW
                LAST_SUB_TIME=0

                # Print on own line so SSH flushes immediately
                printf "  [%s] %3d%%  %s %s\n" "$BAR" "$PERCENT" "$STEP_INFO" "$DESC"

            # Sub-progress: apt-get operations (slow step)
            elif echo "$line" | grep -qiE "^#[0-9]+ [0-9.]+ (Setting up |Unpacking |Get:[0-9])"; then
                STEP_ELAPSED=$((NOW - STEP_START))
                if [ $((STEP_ELAPSED - LAST_SUB_TIME)) -ge 3 ]; then
                    LAST_SUB_TIME=$STEP_ELAPSED
                    SUB=$(echo "$line" | sed 's/^#[0-9]* [0-9.]* //' | cut -c1-55)
                    printf "\r\033[K       \033[2m↳ (%ds) %s\033[0m" "$STEP_ELAPSED" "$SUB"
                fi

            # Sub-progress: pip operations (slow step)
            elif echo "$line" | grep -qiE "^#[0-9]+ [0-9.]+ (Collecting |Downloading |Installing |Building wheel)"; then
                STEP_ELAPSED=$((NOW - STEP_START))
                if [ $((STEP_ELAPSED - LAST_SUB_TIME)) -ge 2 ]; then
                    LAST_SUB_TIME=$STEP_ELAPSED
                    SUB=$(echo "$line" | sed 's/^#[0-9]* [0-9.]* //' | cut -c1-55)
                    printf "\r\033[K       \033[2m↳ (%ds) %s\033[0m" "$STEP_ELAPSED" "$SUB"
                fi
            fi
        done

        # Final step completion
        if [ -n "$CURRENT_STEP" ]; then
            NOW=$(date +%s)
            STEP_TIME=$((NOW - STEP_START))
            if [ $STEP_TIME -gt 2 ]; then
                printf "\r\033[K  \033[0;32m✓\033[0m %s done (%ds)\n" "$CURRENT_STEP" "$STEP_TIME"
            else
                printf "\r\033[K\n"
            fi
        fi

        BUILD_TIME=$(( $(date +%s) - BUILD_START ))
        MINS=$((BUILD_TIME / 60))
        SECS=$((BUILD_TIME % 60))
        printf "  Build completed in %dm %ds\n" "$MINS" "$SECS"
    }

    echo "  ✓ Image built"

    echo ""
    echo "[4/4] Starting container..."

    # Load config
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
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

    sleep 5

    if curl -sf "http://localhost:${PORT}/health" > /dev/null 2>&1; then
        echo "  ✓ Service is healthy!"
    else
        echo "  ⚠ Service may still be starting"
    fi

    # Database schema is managed by database.py init_database() on startup.
    # No external migration scripts needed.

    echo ""
    echo "Verifying admin account..."
    if [ "$RESET_PASSWORD" = "yes" ]; then
        docker exec "$CONTAINER_NAME" python3 backend/check_auth.py --reset 2>&1 | grep -E "CREATED|RESET|OK|WARNING" || true
        echo "  ✓ Admin password reset (username: admin, password: satoshi)"
    else
        docker exec "$CONTAINER_NAME" python3 backend/check_auth.py 2>&1 | grep -E "CREATED|RESET|OK|WARNING" || true
        echo "  ✓ Admin account preserved (existing password kept)"
    fi

ENDSSH

SSH_EXIT_CODE=$?

# Get version
echo ""
DEPLOYED_VERSION=$(ssh $SSH_OPTS "${SSH_USER}@${UNRAID_HOST}" "docker exec $CONTAINER_NAME grep -o 'v[0-9.]*\s*(BUILD\s*[0-9]*)' /app/frontend/index.html 2>/dev/null | head -1" || echo "")

if [ $SSH_EXIT_CODE -eq 0 ]; then
    DEPLOY_TIME=$(( $(date +%s) - DEPLOY_START ))
    DEPLOY_MINS=$((DEPLOY_TIME / 60))
    DEPLOY_SECS=$((DEPLOY_TIME % 60))
    echo ""
    echo -e "${GREEN}========================================"
    echo "  Deployment from Git Complete!"
    echo "========================================${NC}"
    echo ""
    echo "Dashboard: http://${UNRAID_HOST}:${PORT}"
    if [ -n "$DEPLOYED_VERSION" ]; then
        echo "Version:   ${DEPLOYED_VERSION}"
    fi
    echo "Deploy:    ${DEPLOY_MINS}m ${DEPLOY_SECS}s"
    echo ""
else
    echo -e "${RED}Deployment failed.${NC}"
    exit 1
fi

# Clean up SSH connection
ssh -O exit -o ControlPath="$SSH_CONTROL_PATH" "${SSH_USER}@${UNRAID_HOST}" 2>/dev/null || true
