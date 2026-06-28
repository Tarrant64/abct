#!/bin/bash
set -e

echo "========================================"
echo "  ABCT Dashboard - Starting..."
echo "========================================"

# Check required environment variables
if [ -z "$BLOCKFROST_API_KEY" ]; then
    echo "WARNING: BLOCKFROST_API_KEY not set - Cardano features will not work"
fi

# Show configuration
echo ""
echo "Configuration:"
echo "  Database: ${DATABASE_PATH:-/app/data/portfolio.db}"
echo "  Blockfrost: ${BLOCKFROST_API_KEY:+configured}${BLOCKFROST_API_KEY:-NOT SET}"
echo "  CoinGecko: ${COINGECKO_API_KEY:+configured}${COINGECKO_API_KEY:-using free tier}"
echo "  NFT Service: ${NFT_PRICE_SERVICE_URL:-not configured}"

# SSL Configuration
SSL_ENABLED="${ABCT_SSL_ENABLED:-false}"
echo "  SSL Enabled: $SSL_ENABLED"

# Ensure data directory exists and has correct permissions
mkdir -p /app/data
chmod 755 /app/data

# Ensure certs directory exists
mkdir -p /app/certs

# Configure SSL if enabled
if [ "$SSL_ENABLED" = "true" ]; then
    echo ""
    echo "SSL/HTTPS Configuration:"

    # Check for certificates - if not found, auto-generate self-signed
    if [ ! -f "/app/certs/server.crt" ] || [ ! -f "/app/certs/server.key" ]; then
        echo "  Certificates not found - generating self-signed certificate..."

        # Generate self-signed certificate using openssl
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout /app/certs/server.key \
            -out /app/certs/server.crt \
            -subj "/C=US/ST=Local/L=Development/O=ABCT/CN=localhost" \
            -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:::1" \
            2>/dev/null

        # Set restrictive permissions on private key
        chmod 600 /app/certs/server.key
        chmod 644 /app/certs/server.crt

        echo "  Self-signed certificate generated successfully!"
        echo "  Valid for: 365 days"
        echo "  Hostnames: localhost, 127.0.0.1"
    else
        echo "  Certificates: Found (using existing)"
    fi

    # Use SSL nginx configuration
    echo "  Enabling HTTPS nginx configuration..."
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
    ln -sf /etc/nginx/sites-available/ssl /etc/nginx/sites-enabled/default

    echo ""
    echo "  HTTPS enabled on port 443"
    echo "  HTTP requests will redirect to HTTPS"
    echo ""
    echo "  NOTE: Self-signed certificates show browser warnings."
    echo "  This is normal - click through to proceed:"
    echo "    Chrome: 'Advanced' > 'Proceed to localhost (unsafe)'"
    echo "    Firefox: 'Advanced' > 'Accept the Risk and Continue'"
    echo "    Safari: 'Show Details' > 'visit this website'"
else
    # Use standard nginx config (HTTP only)
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
    ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default
fi

echo ""

# Update frontend API base URL to use relative path (for nginx proxy)
if [ -f /app/frontend/js/app.js ]; then
    if grep -q "const API_BASE = 'http://127.0.0.1:8000'" /app/frontend/js/app.js; then
        echo "Updating frontend API URL to use relative path..."
        sed -i "s|const API_BASE = 'http://127.0.0.1:8000'|const API_BASE = ''|g" /app/frontend/js/app.js
    fi
fi

echo "Starting services..."
echo "========================================"

# Start supervisor (manages nginx + uvicorn)
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
