# ABCT Dashboard - Docker Container
# Combines FastAPI backend + static frontend with Nginx reverse proxy

FROM python:3.11-slim

# Install system dependencies (including Pillow requirements for image processing)
# gcc and build-essential needed for bip_utils (Bitcoin xpub support)
# openssl needed for auto-generating self-signed SSL certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    curl \
    openssl \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy backend requirements and install
COPY backend/requirements.txt /app/backend/
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy backend code
COPY backend/ /app/backend/

# Copy frontend code
COPY frontend/ /app/frontend/

# Copy nginx configuration
# Remove default config and install ours
RUN rm -f /etc/nginx/sites-enabled/default /etc/nginx/conf.d/default.conf
COPY abct-docker/nginx.conf /etc/nginx/sites-available/default
COPY abct-docker/nginx-ssl.conf /etc/nginx/sites-available/ssl
RUN ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default

# Copy supervisor configuration
COPY abct-docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy entrypoint script
COPY abct-docker/scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create data directory for SQLite
RUN mkdir -p /app/data

# Create certs directory for SSL certificates
RUN mkdir -p /app/certs

# Create log directories
RUN mkdir -p /var/log/supervisor /var/log/nginx

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV DATABASE_PATH=/app/data/portfolio.db
ENV NFT_IMAGE_DB_PATH=/app/data/nft_images.db
# Cardano APIs
ENV BLOCKFROST_API_KEY=""
ENV TAPTOOLS_API_KEY=""
ENV CEXPLORER_API_KEY=""
ENV MAESTRO_API_KEY=""
# EVM APIs
ENV ALCHEMY_API_KEY=""
ENV ETHERSCAN_API_KEY=""
ENV BEACONCHAIN_API_KEY=""
# Solana APIs
ENV HELIUS_API_KEY=""
# Pricing APIs
ENV COINGECKO_API_KEY=""
ENV CMC_API_KEY=""
# Optional services
ENV NFT_PRICE_SERVICE_URL=""
ENV NFT_IMAGE_CACHE_ENABLED="false"
# SSL configuration
ENV ABCT_SSL_ENABLED="false"

# Expose ports (80 for HTTP, 443 for HTTPS)
EXPOSE 80 443

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/api/health || exit 1

# Run supervisor (manages nginx + uvicorn)
CMD ["/app/entrypoint.sh"]
