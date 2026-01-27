#!/bin/bash
set -e

echo "========================================"
echo "  ABCT Dashboard - Starting..."
echo "========================================"

# Check required environment variables
if [ -z "$BLOCKFROST_API_KEY" ]; then
    echo "WARNING: BLOCKFROST_API_KEY not set - Cardano features will not work"
fi

if [ -z "$TAPTOOLS_API_KEY" ]; then
    echo "WARNING: TAPTOOLS_API_KEY not set - NFT and some token features will not work"
fi

# Show configuration
echo ""
echo "Configuration:"
echo "  Database: ${DATABASE_PATH:-/app/data/portfolio.db}"
echo "  Blockfrost: ${BLOCKFROST_API_KEY:+configured}${BLOCKFROST_API_KEY:-NOT SET}"
echo "  TapTools: ${TAPTOOLS_API_KEY:+configured}${TAPTOOLS_API_KEY:-NOT SET}"
echo "  CoinGecko: ${COINGECKO_API_KEY:+configured}${COINGECKO_API_KEY:-using free tier}"
echo "  NFT Service: ${NFT_PRICE_SERVICE_URL:-not configured}"
echo ""

# Ensure data directory exists and has correct permissions
mkdir -p /app/data
chmod 755 /app/data

# Update frontend API base URL to use relative path (for nginx proxy)
# This ensures the frontend calls /api/* which nginx proxies to backend
if [ -f /app/frontend/js/app.js ]; then
    # Check if already using relative URL
    if grep -q "const API_BASE = 'http://127.0.0.1:8000'" /app/frontend/js/app.js; then
        echo "Updating frontend API URL to use relative path..."
        sed -i "s|const API_BASE = 'http://127.0.0.1:8000'|const API_BASE = ''|g" /app/frontend/js/app.js
    fi
fi

# Remove default nginx site if exists
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default 2>/dev/null || true

echo "Starting services..."
echo "========================================"

# Start supervisor (manages nginx + uvicorn)
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
