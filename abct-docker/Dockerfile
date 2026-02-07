# ABCT Dashboard - Docker Container (Multi-Stage Build)
# Combines FastAPI backend + static frontend with Nginx reverse proxy
#
# Stage 1: Builder - compiles Python packages that need gcc/build-essential
# Stage 2: Runtime - slim image with only runtime dependencies

# ============================================
# STAGE 1: BUILDER
# ============================================
FROM python:3.11-slim AS builder

# Install build dependencies for compiling Python packages
# gcc/build-essential: bip_utils, cryptography
# libjpeg-dev/zlib1g-dev/libpng-dev: Pillow
# libffi-dev: cffi (cryptography dependency)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages into a virtual env so we can copy them cleanly
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# ============================================
# STAGE 2: RUNTIME
# ============================================
FROM python:3.11-slim

# Docker metadata labels (OCI standard + unRAID compatibility)
LABEL org.opencontainers.image.title="ABCT - A Better Crypto Tracker"
LABEL org.opencontainers.image.description="Multi-chain cryptocurrency portfolio tracker supporting Cardano, Ethereum, Bitcoin, Solana, Polygon, and Base"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.vendor="ABCT Project"
LABEL org.opencontainers.image.authors="Chris Catalano"
LABEL org.opencontainers.image.url="https://github.com/Tarrant64/abct"
LABEL org.opencontainers.image.source="https://github.com/Tarrant64/abct"
LABEL org.opencontainers.image.documentation="https://github.com/Tarrant64/abct/blob/main/README.md"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.base.name="python:3.11-slim"
# Icon for unRAID and other container managers (1024x1024 PNG)
LABEL org.opencontainers.image.icon="https://raw.githubusercontent.com/Tarrant64/abct/main/frontend/static/apple-touch-icon.png"

# Install runtime-only system dependencies (no gcc/build-essential)
# nginx + supervisor: process management
# curl: health checks
# openssl: auto-generating self-signed SSL certificates
# libjpeg62/zlib1g/libpng16: Pillow runtime libs (not -dev headers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    curl \
    openssl \
    libjpeg62-turbo \
    zlib1g \
    libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-compiled Python packages from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

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

# Create data, certs, and log directories
RUN mkdir -p /app/data /app/certs /var/log/supervisor /var/log/nginx

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
    CMD curl -f http://localhost/health || exit 1

# Run supervisor (manages nginx + uvicorn)
CMD ["/app/entrypoint.sh"]
