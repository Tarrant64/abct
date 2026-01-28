# Docker Deployment Guide for ABCT

A comprehensive guide to deploying ABCT (A Better Crypto Tracker) using Docker across multiple platforms including Docker Compose, TrueNAS Scale, Portainer, Synology NAS, and plain Docker.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start with Docker Compose](#quick-start-with-docker-compose)
4. [Platform-Specific Guides](#platform-specific-guides)
   - [Ubuntu/Debian Linux](#ubuntudebian-linux)
   - [TrueNAS Scale](#truenas-scale)
   - [Synology NAS](#synology-nas)
   - [Portainer](#portainer)
   - [Plain Docker](#plain-docker-without-compose)
5. [Configuration Reference](#configuration-reference)
6. [Volume Management](#volume-management)
7. [Networking](#networking)
8. [Maintenance](#maintenance)
9. [Troubleshooting](#troubleshooting)

---

## Overview

ABCT is packaged as a single Docker container that includes:
- **FastAPI Backend** - Python-based API server
- **Nginx Web Server** - Serves static frontend and reverse proxies API
- **Supervisor Process Manager** - Manages both services
- **SQLite Database** - Persistent data storage

**Key Features:**
- Single container deployment (no separate database container needed)
- Built-in web server (no external reverse proxy required)
- Optional HTTPS with self-signed or custom certificates
- Optional authentication for network-exposed deployments
- Automatic NFT price updates (when enabled)

### Platform Comparison

| Platform | Difficulty | Best For | Recommended Method |
|----------|------------|----------|-------------------|
| **Ubuntu/Debian** | Easy | Dedicated servers, VPS | Docker Compose |
| **TrueNAS Scale** | Medium | Home servers with ZFS | Docker Compose via SSH |
| **Synology NAS** | Easy | Home users, beginners | Container Manager UI |
| **Portainer** | Easy | Existing Portainer setups | Stack Deployment |
| **Plain Docker** | Medium | Minimal setups, automation | Single `docker run` |

**Quick Decision Guide:**
- **New to Docker?** → Start with [Synology NAS](#synology-nas) or [Portainer](#portainer)
- **Linux Server?** → Use [Docker Compose](#quick-start-with-docker-compose)
- **TrueNAS?** → Follow [TrueNAS Scale](#truenas-scale) guide
- **Advanced/Automation?** → See [Plain Docker](#plain-docker-without-compose)

---

## Prerequisites

Before deploying ABCT, ensure you have:

### Required:
- **Docker** (version 20.10 or higher)
- **512MB RAM minimum** (1GB+ recommended)
- **1GB disk space** for container + data
- **Blockfrost API key** - Get free at [blockfrost.io](https://blockfrost.io)

### Optional:
- **Docker Compose** (for compose-based deployments)
- Additional API keys for enhanced features:
  - **TapTools** - NFT floor prices ([taptools.io](https://www.taptools.io/openapi/subscription))
  - **CExplorer** - Staking rewards ([cexplorer.io/api](https://cexplorer.io/api))
  - **Etherscan** - Ethereum support ([etherscan.io/apis](https://etherscan.io/apis))
  - **Coinbase** - Exchange integration ([portal.cdp.coinbase.com](https://portal.cdp.coinbase.com))

---

## Quick Start with Docker Compose

The fastest way to get ABCT running on any Linux system.

### Step 1: Create Project Directory

```bash
mkdir -p ~/abct
cd ~/abct
```

### Step 2: Create docker-compose.yml

Create a file named `docker-compose.yml`:

```yaml
version: '3.8'

services:
  abct-dashboard:
    image: abct:latest
    build:
      context: .
      dockerfile: Dockerfile
    container_name: abct-dashboard
    restart: unless-stopped
    ports:
      - "8080:80"     # HTTP access
      # - "8443:443"  # HTTPS access (uncomment if using SSL)
    volumes:
      # Persistent data storage
      - abct-data:/app/data

      # Optional: Custom SSL certificates
      # - ./certs:/app/certs:ro

      # Optional: Coinbase API key file
      # - ./cdp_api_key.json:/app/cdp_api_key.json:ro

    environment:
      # ============================================
      # REQUIRED: Cardano Blockchain API
      # ============================================
      - BLOCKFROST_API_KEY=mainnetXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

      # ============================================
      # RECOMMENDED: Enhanced Features
      # ============================================
      - CEXPLORER_API_KEY=
      - TAPTOOLS_API_KEY=

      # ============================================
      # OPTIONAL: Additional Blockchains
      # ============================================
      - ETHERSCAN_API_KEY=
      - ALCHEMY_API_KEY=
      - HELIUS_API_KEY=

      # ============================================
      # NFT Background Scheduler (v0.9.0+)
      # ============================================
      - NFT_SCHEDULER_ENABLED=false
      - NFT_UPDATE_INTERVAL_MINUTES=15
      - NFT_CALLS_PER_UPDATE=1
      - NFT_MAX_DAILY_CALLS=95

      # ============================================
      # Authentication (v0.10.0+)
      # ============================================
      - ABCT_REQUIRE_AUTH=false
      # - ABCT_ADMIN_USER=admin
      # - ABCT_ADMIN_PASSWORD=your_secure_password

      # ============================================
      # HTTPS/SSL Configuration
      # ============================================
      - ABCT_SSL_MODE=http
      # - ABCT_SSL_CERT=/app/certs/cert.pem
      # - ABCT_SSL_KEY=/app/certs/key.pem

      # ============================================
      # Network Configuration
      # ============================================
      - BIND_HOST=0.0.0.0
      - BIND_PORT=8000

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  abct-data:
    driver: local
```

### Step 3: Build and Start

```bash
# If building from source (requires Dockerfile)
git clone https://github.com/Tarrant64/abct.git .
docker-compose up -d

# Or if using pre-built image
# docker-compose pull
# docker-compose up -d
```

### Step 4: Verify Deployment

```bash
# Check container status
docker-compose ps

# View logs
docker-compose logs -f

# Access the dashboard
open http://localhost:8080
```

### Common Docker Compose Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# Restart services
docker-compose restart

# View logs
docker-compose logs -f abct-dashboard

# Update to latest version
docker-compose pull
docker-compose up -d

# Backup data volume
docker run --rm -v abct_abct-data:/data -v $(pwd):/backup ubuntu tar czf /backup/abct-backup.tar.gz /data
```

---

## Platform-Specific Guides

### Ubuntu/Debian Linux

Complete installation on a fresh Ubuntu or Debian system.

#### Prerequisites Installation

```bash
# Update package list
sudo apt update

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group (optional, avoids needing sudo)
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo apt install docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

#### Deploy ABCT

```bash
# Create project directory
mkdir -p ~/abct && cd ~/abct

# Clone repository
git clone https://github.com/Tarrant64/abct.git .

# Create environment file
cp .env.example .env
nano .env  # Add your API keys

# Build and start
docker compose up -d

# Check status
docker compose ps
docker compose logs -f
```

#### Access Dashboard

```bash
# Local access
http://localhost:8080

# Network access (if BIND_HOST=0.0.0.0)
http://YOUR_SERVER_IP:8080
```

#### Auto-Start on Boot

Docker Compose with `restart: unless-stopped` automatically starts containers on boot. To enable Docker service:

```bash
sudo systemctl enable docker
```

---

### TrueNAS Scale

TrueNAS Scale has native Docker support and can run ABCT in multiple ways.

#### Method 1: Using TrueNAS Apps (Recommended)

**Note:** This method requires creating a custom TrueCharts app or waiting for ABCT to be added to the TrueNAS app catalog. Use Method 2 or 3 instead.

#### Method 2: Docker Compose via SSH

1. **Enable SSH on TrueNAS**
   - Navigate to **System Settings** → **Services**
   - Enable **SSH** service

2. **Connect via SSH**

```bash
ssh admin@truenas-ip
```

3. **Install Docker Compose** (if not present)

```bash
# TrueNAS Scale includes docker by default
# Install docker-compose if needed
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
```

4. **Create ABCT Directory on Pool**

```bash
# Navigate to your main pool (adjust path as needed)
cd /mnt/pool-name/docker
mkdir abct && cd abct
```

5. **Create docker-compose.yml** (use the example from Quick Start section above)

6. **Clone Repository or Download Files**

```bash
git clone https://github.com/Tarrant64/abct.git .
```

7. **Start Container**

```bash
docker-compose up -d
```

8. **Access Dashboard**
   - Open browser to `http://truenas-ip:8080`

#### Method 3: Custom App Deployment

1. **Navigate to Apps**
   - Go to **Apps** in TrueNAS Scale UI
   - Click **Discover Apps** → **Custom App**

2. **Configure Custom App**
   - **Application Name:** `abct-dashboard`
   - **Image Repository:** `ghcr.io/tarrant64/abct` (if available) or build locally
   - **Image Tag:** `latest`
   - **Container Port:** `80`
   - **Node Port:** `8080` (or your preferred port)

3. **Add Environment Variables**

Click **Add** for each variable:

| Variable | Value |
|----------|-------|
| `BLOCKFROST_API_KEY` | `your_blockfrost_key` |
| `TAPTOOLS_API_KEY` | `your_taptools_key` |
| `NFT_SCHEDULER_ENABLED` | `false` |
| `ABCT_REQUIRE_AUTH` | `false` |

4. **Configure Storage**
   - **Host Path Volume**
     - **Host Path:** `/mnt/pool-name/docker/abct/data`
     - **Mount Path:** `/app/data`

5. **Deploy**
   - Click **Save** and wait for deployment
   - Access at `http://truenas-ip:8080`

#### Storage Pool Configuration

For optimal performance on TrueNAS:

```yaml
volumes:
  abct-data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/pool-name/docker/abct/data
```

---

### Synology NAS

Deploy ABCT using Synology's Container Manager (formerly Docker).

#### Prerequisites

1. **Install Container Manager**
   - Open **Package Center**
   - Search for **Container Manager**
   - Click **Install**

2. **Create Shared Folder**
   - Open **Control Panel** → **Shared Folder**
   - Create new folder: `docker` (if it doesn't exist)
   - Create subfolder: `docker/abct`

#### Method 1: Container Manager UI

1. **Open Container Manager**
   - Navigate to **Container Manager** app

2. **Create Project**
   - Go to **Project** tab
   - Click **Create**
   - **Project Name:** `abct`
   - **Path:** `/docker/abct`
   - Click **Set Path**

3. **Create docker-compose.yml**
   - In the project settings, click **Source** tab
   - Click **Create docker-compose.yml**
   - Paste the docker-compose.yml content from the Quick Start section
   - Update `BLOCKFROST_API_KEY` with your actual key

4. **Build/Deploy**
   - Click **Build**
   - Wait for image to build/download
   - Container will start automatically

5. **Configure Port Forwarding** (if needed)
   - Go to **Container** tab
   - Select `abct-dashboard`
   - Click **Edit**
   - Under **Port Settings**, ensure port 80 → 8080 mapping exists

6. **Access Dashboard**
   - Open browser to `http://synology-ip:8080`

#### Method 2: Manual Container Setup

1. **Build/Download Image**
   - Go to **Image** tab
   - Click **Add** → **Add from URL**
   - Enter: `https://github.com/Tarrant64/abct.git` (if pre-built image available)

   OR build locally:
   - SSH into Synology
   - Navigate to `/volume1/docker/abct`
   - Run: `sudo docker build -t abct:latest .`

2. **Create Container**
   - Go to **Container** tab
   - Click **Create**
   - Select `abct:latest` image
   - **Container Name:** `abct-dashboard`
   - Click **Advanced Settings**

3. **Advanced Settings**

   **Port Settings:**
   | Local Port | Container Port | Type |
   |------------|----------------|------|
   | 8080 | 80 | TCP |

   **Volume Settings:**
   | File/Folder | Mount Path | Read/Write |
   |-------------|------------|------------|
   | `/docker/abct/data` | `/app/data` | Read/Write |

   **Environment Variables:**
   - Add each variable from the Quick Start section
   - Minimum required: `BLOCKFROST_API_KEY`

   **Network:**
   - Select **Bridge** network mode

4. **Auto-Restart**
   - Enable **Auto-restart** checkbox

5. **Apply and Start**
   - Click **Apply**
   - Container starts automatically
   - Access at `http://synology-ip:8080`

#### Synology-Specific Notes

- **Performance:** Use SSD storage pool if available for better database performance
- **Firewall:** Configure firewall rules in **Control Panel** → **Security** → **Firewall** to allow port 8080
- **Reverse Proxy:** Use built-in reverse proxy in **Control Panel** → **Login Portal** → **Advanced** → **Reverse Proxy** for HTTPS access
- **Task Scheduler:** Create scheduled task for automatic updates (see Maintenance section)

---

### Portainer

Deploy ABCT using Portainer's web interface.

#### Prerequisites

- Portainer installed and accessible
- Docker host connected to Portainer

#### Method 1: Stack Deployment (Recommended)

1. **Navigate to Stacks**
   - Click on your Docker environment
   - Go to **Stacks** in the left menu
   - Click **+ Add stack**

2. **Create Stack**
   - **Name:** `abct`
   - **Build method:** Select **Web editor**

3. **Paste docker-compose.yml**

Paste the following (simplified version):

```yaml
version: '3.8'

services:
  abct-dashboard:
    image: abct:latest
    container_name: abct-dashboard
    restart: unless-stopped
    ports:
      - "8080:80"
    volumes:
      - abct-data:/app/data
    environment:
      - BLOCKFROST_API_KEY=${BLOCKFROST_API_KEY}
      - TAPTOOLS_API_KEY=${TAPTOOLS_API_KEY}
      - CEXPLORER_API_KEY=${CEXPLORER_API_KEY}
      - NFT_SCHEDULER_ENABLED=${NFT_SCHEDULER_ENABLED:-false}
      - ABCT_REQUIRE_AUTH=${ABCT_REQUIRE_AUTH:-false}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  abct-data:
```

4. **Add Environment Variables**
   - Scroll down to **Environment variables**
   - Click **+ Add an environment variable**
   - Add each variable:

| Name | Value |
|------|-------|
| `BLOCKFROST_API_KEY` | `your_blockfrost_key` |
| `TAPTOOLS_API_KEY` | `your_taptools_key` |
| `NFT_SCHEDULER_ENABLED` | `false` |
| `ABCT_REQUIRE_AUTH` | `false` |

5. **Deploy Stack**
   - Click **Deploy the stack**
   - Wait for deployment to complete
   - Status will show "Running"

6. **Access Dashboard**
   - Click on the stack name
   - Click on container name to view details
   - Access at `http://docker-host-ip:8080`

#### Method 2: Manual Container Creation

1. **Navigate to Containers**
   - Go to **Containers** in the left menu
   - Click **+ Add container**

2. **Basic Configuration**
   - **Name:** `abct-dashboard`
   - **Image:** `abct:latest`

3. **Network Ports**
   - Click **publish a new network port**
   - **Host:** `8080`
   - **Container:** `80`
   - **Protocol:** `TCP`

4. **Volumes**
   - Click **map additional volume**
   - **Container:** `/app/data`
   - **Volume:** Create new volume named `abct-data`

5. **Environment Variables**
   - Scroll to **Env** tab
   - Click **+ add environment variable**
   - Add all required variables (minimum `BLOCKFROST_API_KEY`)

6. **Restart Policy**
   - Select **Unless stopped**

7. **Deploy**
   - Click **Deploy the container**
   - Access at `http://docker-host-ip:8080`

#### Managing ABCT in Portainer

**View Logs:**
1. Go to **Containers**
2. Click container name
3. Click **Logs** tab
4. Toggle **Auto-refresh** for live logs

**Update Container:**
1. Go to **Containers**
2. Select container checkbox
3. Click **Recreate**
4. Enable **Pull latest image**
5. Click **Recreate**

**Backup Volume:**
1. Go to **Volumes**
2. Select `abct-data`
3. Click **Export** (if available in your Portainer version)

OR use CLI:
```bash
docker run --rm -v abct_abct-data:/data -v $(pwd):/backup ubuntu tar czf /backup/abct-backup.tar.gz /data
```

---

### Plain Docker (Without Compose)

Run ABCT using a single `docker run` command.

#### Build Image (If Not Pre-Built)

```bash
# Clone repository
git clone https://github.com/Tarrant64/abct.git
cd abct

# Build image
docker build -t abct:latest -f abct-docker/Dockerfile .
```

#### Create Volume

```bash
# Create persistent volume for data
docker volume create abct-data
```

#### Run Container

**Basic HTTP Deployment:**

```bash
docker run -d \
  --name abct-dashboard \
  --restart unless-stopped \
  -p 8080:80 \
  -v abct-data:/app/data \
  -e BLOCKFROST_API_KEY="mainnetYOUR_API_KEY_HERE" \
  -e TAPTOOLS_API_KEY="" \
  -e CEXPLORER_API_KEY="" \
  -e NFT_SCHEDULER_ENABLED="false" \
  -e NFT_UPDATE_INTERVAL_MINUTES="15" \
  -e NFT_CALLS_PER_UPDATE="1" \
  -e NFT_MAX_DAILY_CALLS="95" \
  -e ABCT_REQUIRE_AUTH="false" \
  -e ABCT_SSL_MODE="http" \
  -e BIND_HOST="0.0.0.0" \
  -e BIND_PORT="8000" \
  abct:latest
```

**Advanced Deployment with All Options:**

```bash
docker run -d \
  --name abct-dashboard \
  --restart unless-stopped \
  -p 8080:80 \
  -p 8443:443 \
  -v abct-data:/app/data \
  -v $(pwd)/certs:/app/certs:ro \
  -v $(pwd)/cdp_api_key.json:/app/cdp_api_key.json:ro \
  -e BLOCKFROST_API_KEY="mainnetYOUR_API_KEY_HERE" \
  -e TAPTOOLS_API_KEY="your_taptools_key" \
  -e CEXPLORER_API_KEY="your_cexplorer_key" \
  -e ETHERSCAN_API_KEY="your_etherscan_key" \
  -e ALCHEMY_API_KEY="your_alchemy_key" \
  -e HELIUS_API_KEY="your_helius_key" \
  -e COINGECKO_API_KEY="" \
  -e NFT_SCHEDULER_ENABLED="true" \
  -e NFT_UPDATE_INTERVAL_MINUTES="15" \
  -e NFT_CALLS_PER_UPDATE="1" \
  -e NFT_MAX_DAILY_CALLS="95" \
  -e ABCT_REQUIRE_AUTH="true" \
  -e ABCT_ADMIN_USER="admin" \
  -e ABCT_ADMIN_PASSWORD="your_secure_password" \
  -e ABCT_SSL_MODE="https-custom" \
  -e ABCT_SSL_CERT="/app/certs/cert.pem" \
  -e ABCT_SSL_KEY="/app/certs/key.pem" \
  -e BIND_HOST="0.0.0.0" \
  -e BIND_PORT="8000" \
  -e NFT_IMAGE_CACHE_ENABLED="false" \
  --health-cmd="curl -f http://localhost/api/health || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  --health-start-period=15s \
  abct:latest
```

#### Container Management Commands

```bash
# View logs
docker logs -f abct-dashboard

# View real-time stats
docker stats abct-dashboard

# Stop container
docker stop abct-dashboard

# Start container
docker start abct-dashboard

# Restart container
docker restart abct-dashboard

# Remove container (keeps data volume)
docker rm -f abct-dashboard

# Access container shell (for debugging)
docker exec -it abct-dashboard /bin/bash

# View container details
docker inspect abct-dashboard
```

#### Network Modes

**Bridge Mode (Default):**
```bash
docker run -d --name abct-dashboard -p 8080:80 ...
```
Best for: Most deployments, provides isolation

**Host Mode:**
```bash
docker run -d --name abct-dashboard --network host -e BIND_PORT=8080 ...
```
Best for: Maximum performance, no port mapping overhead
Note: Use `http://localhost:8080` instead of mapping port 80

**Custom Network:**
```bash
# Create network
docker network create abct-network

# Run with custom network
docker run -d --name abct-dashboard --network abct-network -p 8080:80 ...
```
Best for: Multiple containers that need to communicate

---

## Configuration Reference

### Environment Variables

#### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `BLOCKFROST_API_KEY` | Cardano blockchain API key | `mainnetXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX` |

#### Recommended

| Variable | Description | Default |
|----------|-------------|---------|
| `TAPTOOLS_API_KEY` | NFT floor prices | (empty) |
| `CEXPLORER_API_KEY` | Staking/rewards data | (empty) |

#### Optional - Blockchain APIs

| Variable | Description | Default |
|----------|-------------|---------|
| `ETHERSCAN_API_KEY` | Ethereum support | (empty) |
| `ALCHEMY_API_KEY` | Ethereum/Polygon/Base | (empty) |
| `HELIUS_API_KEY` | Solana support | (empty) |
| `COINGECKO_API_KEY` | Pro pricing API | (empty) |

#### Optional - NFT Scheduler

| Variable | Description | Default |
|----------|-------------|---------|
| `NFT_SCHEDULER_ENABLED` | Enable automatic NFT updates | `false` |
| `NFT_UPDATE_INTERVAL_MINUTES` | Minutes between updates | `15` |
| `NFT_CALLS_PER_UPDATE` | Collections per cycle | `1` |
| `NFT_MAX_DAILY_CALLS` | Daily API call limit | `95` |

#### Optional - Security

| Variable | Description | Default |
|----------|-------------|---------|
| `ABCT_REQUIRE_AUTH` | Enable authentication | `false` |
| `ABCT_ADMIN_USER` | Admin username | (empty) |
| `ABCT_ADMIN_PASSWORD` | Admin password | (empty) |
| `ABCT_SSL_MODE` | SSL mode: `http`, `https-self-signed`, `https-custom` | `http` |
| `ABCT_SSL_CERT` | Path to SSL certificate | (empty) |
| `ABCT_SSL_KEY` | Path to SSL private key | (empty) |

#### Optional - Network

| Variable | Description | Default |
|----------|-------------|---------|
| `BIND_HOST` | Host to bind to (`127.0.0.1` or `0.0.0.0`) | `0.0.0.0` |
| `BIND_PORT` | Backend port | `8000` |

#### Optional - Advanced

| Variable | Description | Default |
|----------|-------------|---------|
| `NFT_IMAGE_CACHE_ENABLED` | Cache NFT images locally | `false` |
| `NFT_IMAGE_MAX_SIZE_MB` | Max image size to cache | `5` |
| `DATABASE_PATH` | SQLite database path | `/app/data/portfolio.db` |
| `NFT_IMAGE_DB_PATH` | NFT image cache DB path | `/app/data/nft_images.db` |

### SSL/HTTPS Configuration

#### Option 1: Self-Signed Certificate (Auto-Generated)

```yaml
environment:
  - ABCT_SSL_MODE=https-self-signed
ports:
  - "8443:443"
```

The container automatically generates a self-signed certificate. Browser will show security warning (this is normal).

#### Option 2: Custom Certificate

1. **Obtain SSL certificate** (from Let's Encrypt, etc.)

2. **Place files in host directory:**
```bash
mkdir certs
cp fullchain.pem certs/cert.pem
cp privkey.pem certs/key.pem
chmod 644 certs/cert.pem
chmod 600 certs/key.pem
```

3. **Mount and configure:**
```yaml
volumes:
  - ./certs:/app/certs:ro
environment:
  - ABCT_SSL_MODE=https-custom
  - ABCT_SSL_CERT=/app/certs/cert.pem
  - ABCT_SSL_KEY=/app/certs/key.pem
ports:
  - "8443:443"
```

4. **Access:** `https://your-server:8443`

### Authentication Configuration

#### Localhost-Only (No Auth Required)

```yaml
environment:
  - ABCT_REQUIRE_AUTH=false
```

Safe for local-only access (localhost, 127.0.0.1).

#### Network-Exposed (Auth Required)

```yaml
environment:
  - ABCT_REQUIRE_AUTH=true
  - ABCT_ADMIN_USER=admin
  - ABCT_ADMIN_PASSWORD=your_secure_password_here
  - BIND_HOST=0.0.0.0
```

**Important:** Always use authentication when exposing ABCT on your network. Combine with HTTPS for secure password transmission.

### Coinbase Integration

1. **Get API credentials:**
   - Go to https://portal.cdp.coinbase.com/access/api
   - Create API key with "View" permissions
   - Download JSON file

2. **Mount JSON file:**
```yaml
volumes:
  - ./cdp_api_key.json:/app/cdp_api_key.json:ro
```

3. **Verify:** The backend automatically detects the file and enables Coinbase integration.

---

## Volume Management

### Understanding Data Persistence

ABCT stores all data in `/app/data` inside the container:

- `portfolio.db` - Main SQLite database (wallets, snapshots, settings)
- `nft_images.db` - NFT image cache (optional)
- Log files and temporary data

**Volume mounting ensures data survives container recreation.**

### Volume Types

#### Docker Named Volumes (Recommended)

```yaml
volumes:
  abct-data:/app/data

volumes:
  abct-data:
    driver: local
```

**Pros:**
- Docker manages location
- Works across platforms
- Easy to backup with Docker commands
- Survives container deletion

**Cons:**
- Less visible in host filesystem
- Harder to access directly

**Location:**
- Linux: `/var/lib/docker/volumes/abct_abct-data/_data`
- Windows: `\\wsl$\docker-desktop-data\version-pack-data\community\docker\volumes\`

#### Bind Mounts

```yaml
volumes:
  - /host/path/to/abct-data:/app/data
```

**Pros:**
- Visible in host filesystem
- Easy to access/backup
- Can use specific storage location

**Cons:**
- Requires directory creation
- Path must exist before container start
- Permission issues on some systems

**Best for:** TrueNAS, Synology, manual backup setups

### Volume Backup Strategies

#### Method 1: Docker Volume Backup (Named Volumes)

```bash
# Backup volume to tar.gz
docker run --rm \
  -v abct_abct-data:/data \
  -v $(pwd):/backup \
  ubuntu tar czf /backup/abct-backup-$(date +%Y%m%d).tar.gz /data

# Restore volume from tar.gz
docker run --rm \
  -v abct_abct-data:/data \
  -v $(pwd):/backup \
  ubuntu tar xzf /backup/abct-backup-20260127.tar.gz -C /
```

#### Method 2: Application-Level Backup (v0.10.0+)

Use ABCT's built-in backup feature:

1. Open dashboard → **Backup & Restore** page
2. Click **Export Configuration**
3. Download JSON file (includes wallets, settings, API keys)
4. Store safely (encrypted if possible)

Restore:
1. Fresh ABCT installation
2. Go to **Backup & Restore** page
3. Upload JSON file
4. Review preview
5. Click **Import**

**Note:** Application backup doesn't include portfolio history. Combine with volume backup for complete restore.

#### Method 3: Direct File Backup (Bind Mounts)

```bash
# Backup
cp -r /host/path/to/abct-data /backups/abct-data-$(date +%Y%m%d)

# Or with rsync
rsync -av /host/path/to/abct-data/ /backups/abct-data/

# Restore
rsync -av /backups/abct-data/ /host/path/to/abct-data/
```

#### Automated Backup Script

Create `/usr/local/bin/abct-backup.sh`:

```bash
#!/bin/bash
# ABCT Automated Backup Script

BACKUP_DIR="/backups/abct"
VOLUME_NAME="abct_abct-data"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup Docker volume
docker run --rm \
  -v ${VOLUME_NAME}:/data \
  -v ${BACKUP_DIR}:/backup \
  ubuntu tar czf /backup/abct-${DATE}.tar.gz /data

# Keep only last 7 days of backups
find ${BACKUP_DIR} -name "abct-*.tar.gz" -mtime +7 -delete

echo "Backup completed: ${BACKUP_DIR}/abct-${DATE}.tar.gz"
```

Make executable and schedule:

```bash
chmod +x /usr/local/bin/abct-backup.sh

# Add to crontab (daily at 2 AM)
crontab -e
# Add line:
0 2 * * * /usr/local/bin/abct-backup.sh >> /var/log/abct-backup.log 2>&1
```

---

## Networking

### Port Configuration

| Port | Protocol | Purpose | Default Mapping |
|------|----------|---------|-----------------|
| 80 | HTTP | Web interface (unencrypted) | `8080:80` |
| 443 | HTTPS | Web interface (encrypted) | `8443:443` |

### Network Binding

#### Localhost Only (Secure)

```yaml
environment:
  - BIND_HOST=127.0.0.1
ports:
  - "127.0.0.1:8080:80"
```

Access: `http://localhost:8080` (only from host machine)

#### Network Accessible

```yaml
environment:
  - BIND_HOST=0.0.0.0
ports:
  - "8080:80"
```

Access: `http://any-network-ip:8080` (from any device on network)

**Security Note:** Always enable authentication when using `BIND_HOST=0.0.0.0`

### Reverse Proxy Configuration

#### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name crypto.example.com;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Traefik Reverse Proxy

```yaml
services:
  abct-dashboard:
    # ... other config ...
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.abct.rule=Host(`crypto.example.com`)"
      - "traefik.http.routers.abct.entrypoints=web"
      - "traefik.http.services.abct.loadbalancer.server.port=80"
```

#### Caddy Reverse Proxy

```
crypto.example.com {
    reverse_proxy localhost:8080
}
```

### Firewall Configuration

#### UFW (Ubuntu)

```bash
# Allow ABCT port
sudo ufw allow 8080/tcp

# Allow HTTPS (if using SSL)
sudo ufw allow 8443/tcp

# Enable firewall
sudo ufw enable
```

#### iptables

```bash
# Allow ABCT port
sudo iptables -A INPUT -p tcp --dport 8080 -j ACCEPT

# Save rules
sudo iptables-save > /etc/iptables/rules.v4
```

---

## Maintenance

### Updating ABCT

#### Docker Compose

```bash
cd ~/abct

# Pull latest changes
git pull

# Rebuild image
docker-compose build --no-cache

# Recreate containers
docker-compose up -d

# Verify
docker-compose logs -f
```

#### Plain Docker

```bash
# Stop and remove old container
docker stop abct-dashboard
docker rm abct-dashboard

# Rebuild image
docker build -t abct:latest -f abct-docker/Dockerfile .

# Start new container (use same docker run command)
docker run -d --name abct-dashboard ...
```

#### Portainer

1. Go to **Stacks** or **Containers**
2. Select ABCT
3. Click **Recreate**
4. Enable **Pull latest image**
5. Click **Recreate**

### Viewing Logs

#### Docker Compose

```bash
# All logs
docker-compose logs

# Follow logs (live)
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100

# Specific service
docker-compose logs abct-dashboard
```

#### Plain Docker

```bash
# All logs
docker logs abct-dashboard

# Follow logs (live)
docker logs -f abct-dashboard

# Last 100 lines
docker logs --tail=100 abct-dashboard

# With timestamps
docker logs -t abct-dashboard
```

#### Application Logs (Inside Container)

ABCT also has a web-based log viewer:

1. Open dashboard
2. Navigate to **Logs** page (hamburger menu → Logs)
3. View application logs with filtering and search

Or access via terminal:

```bash
# Access container
docker exec -it abct-dashboard /bin/bash

# View supervisor logs
tail -f /var/log/supervisor/supervisord.log
tail -f /var/log/supervisor/uvicorn-stdout.log
tail -f /var/log/supervisor/nginx-stdout.log

# View nginx logs
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

### Health Checks

ABCT includes built-in health checks:

```bash
# Check container health
docker inspect --format='{{.State.Health.Status}}' abct-dashboard

# View health check logs
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' abct-dashboard
```

Health check endpoint: `http://localhost:8080/api/health`

Response:
```json
{
  "status": "healthy",
  "version": "0.10.0",
  "uptime": 3600
}
```

### Database Maintenance

#### Vacuum Database (Reclaim Space)

```bash
# Enter container
docker exec -it abct-dashboard /bin/bash

# Vacuum main database
sqlite3 /app/data/portfolio.db "VACUUM;"

# Vacuum NFT cache
sqlite3 /app/data/nft_images.db "VACUUM;"

# Exit container
exit
```

#### Database Integrity Check

```bash
docker exec -it abct-dashboard sqlite3 /app/data/portfolio.db "PRAGMA integrity_check;"
```

Expected output: `ok`

### Resource Monitoring

```bash
# Container stats (CPU, memory, network, I/O)
docker stats abct-dashboard

# Container processes
docker top abct-dashboard

# Container disk usage
docker exec abct-dashboard du -sh /app/data
```

---

## Troubleshooting

### Container Won't Start

**Check logs:**
```bash
docker logs abct-dashboard
```

**Common issues:**

1. **Port already in use**
   ```bash
   # Check what's using port 8080
   sudo lsof -i :8080

   # Change port in docker-compose.yml or docker run
   ports:
     - "8081:80"  # Use 8081 instead
   ```

2. **Volume permission issues**
   ```bash
   # Fix volume permissions (bind mounts)
   sudo chown -R 1000:1000 /path/to/abct-data

   # Or use named volumes (Docker manages permissions)
   ```

3. **Missing API key**
   ```
   Error: BLOCKFROST_API_KEY environment variable not set
   ```

   Solution: Add `BLOCKFROST_API_KEY` to environment variables.

### Container Starts But Can't Access

**Check container is running:**
```bash
docker ps | grep abct
```

**Check port mapping:**
```bash
docker port abct-dashboard
```

**Test from container:**
```bash
docker exec abct-dashboard curl -f http://localhost/api/health
```

**Test from host:**
```bash
curl http://localhost:8080/api/health
```

**Check firewall:**
```bash
# UFW status
sudo ufw status

# Test if port is open
telnet localhost 8080
```

### Database Errors

**Database locked:**
```bash
# Stop container
docker stop abct-dashboard

# Remove .db-journal files
docker run --rm -v abct_abct-data:/data ubuntu rm -f /data/*.db-journal

# Start container
docker start abct-dashboard
```

**Corrupt database:**
```bash
# Backup current database
docker run --rm -v abct_abct-data:/data -v $(pwd):/backup ubuntu \
  cp /data/portfolio.db /backup/portfolio.db.corrupt

# Restore from backup
docker run --rm -v abct_abct-data:/data -v $(pwd):/backup ubuntu \
  cp /backup/abct-backup-20260127.tar.gz /tmp/ && \
  cd /tmp && tar xzf abct-backup-20260127.tar.gz && \
  cp data/portfolio.db /data/portfolio.db
```

### API Connection Errors

**Blockfrost API errors:**
```
Error: Invalid API key or network issue
```

Solutions:
1. Verify API key is correct (should start with `mainnet`)
2. Check network connectivity: `docker exec abct-dashboard curl -I https://cardano-mainnet.blockfrost.io/api/v0/`
3. Verify key at https://blockfrost.io/dashboard

**Rate limiting:**
```
Error: Rate limit exceeded
```

Solutions:
1. Wait for rate limit reset (check Blockfrost dashboard)
2. Upgrade to higher tier at Blockfrost
3. Reduce refresh frequency

### Performance Issues

**High CPU usage:**
```bash
# Check what's running
docker top abct-dashboard

# Check if NFT scheduler is updating
# Open dashboard → Services → NFT Scheduler status
```

Solution: Reduce NFT update frequency:
```yaml
environment:
  - NFT_UPDATE_INTERVAL_MINUTES=30  # Increase from 15 to 30
  - NFT_CALLS_PER_UPDATE=1          # Keep at 1 for slower systems
```

**High memory usage:**
```bash
# Check memory stats
docker stats abct-dashboard --no-stream
```

Solution: Limit container memory:
```yaml
services:
  abct-dashboard:
    # ... other config ...
    deploy:
      resources:
        limits:
          memory: 512M
```

**Slow database queries:**
```bash
# Vacuum database to optimize
docker exec abct-dashboard sqlite3 /app/data/portfolio.db "VACUUM;"

# Analyze database
docker exec abct-dashboard sqlite3 /app/data/portfolio.db "ANALYZE;"
```

### SSL/HTTPS Issues

**Self-signed certificate warning:**

This is normal for self-signed certificates. Solutions:
1. Click "Advanced" → "Proceed" (Chrome/Edge)
2. Use custom certificate from Let's Encrypt
3. Add exception in browser

**Custom certificate not loading:**
```bash
# Check certificate files exist
docker exec abct-dashboard ls -l /app/certs/

# Verify certificate format
docker exec abct-dashboard openssl x509 -in /app/certs/cert.pem -text -noout

# Check nginx configuration
docker exec abct-dashboard nginx -t
```

### Authentication Issues

**Can't login:**
1. Verify credentials in environment variables
2. Check if `ABCT_REQUIRE_AUTH=true`
3. Check logs: `docker logs abct-dashboard | grep auth`

**Forgot password:**
```bash
# Stop container
docker stop abct-dashboard

# Update environment variable
# Edit docker-compose.yml or recreate with new password

# Start container
docker start abct-dashboard
```

### Getting Help

If issues persist:

1. **Check logs thoroughly:**
   ```bash
   docker logs abct-dashboard > abct-logs.txt
   ```

2. **Collect system info:**
   ```bash
   docker version
   docker-compose version
   uname -a
   ```

3. **Check GitHub Issues:**
   https://github.com/Tarrant64/abct/issues

4. **Create new issue with:**
   - Docker version
   - Platform (Ubuntu, TrueNAS, Synology, etc.)
   - Deployment method (Compose, Portainer, plain Docker)
   - Relevant logs (redact API keys!)
   - Steps to reproduce

---

## Additional Resources

### Documentation Links

- **Main README:** [README.md](../README.md)
- **Architecture:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Backup Guide:** [BACKUP_RESTORE_GUIDE.md](BACKUP_RESTORE_GUIDE.md)
- **Security Guide:** [../SECURITY.md](../SECURITY.md)

### External Resources

- **Docker Documentation:** https://docs.docker.com/
- **Docker Compose:** https://docs.docker.com/compose/
- **Portainer:** https://docs.portainer.io/
- **TrueNAS Scale:** https://www.truenas.com/docs/scale/
- **Synology DSM:** https://www.synology.com/en-us/knowledgebase/DSM

### API Provider Documentation

- **Blockfrost:** https://docs.blockfrost.io/
- **TapTools:** https://www.taptools.io/openapi
- **CExplorer:** https://cexplorer.io/api-documentation
- **Coinbase:** https://docs.cdp.coinbase.com/

---

## Quick Reference

### Common Commands Cheat Sheet

```bash
# Docker Compose
docker-compose up -d              # Start services
docker-compose down               # Stop services
docker-compose restart            # Restart services
docker-compose logs -f            # Follow logs
docker-compose pull               # Update images
docker-compose build --no-cache   # Rebuild images

# Plain Docker
docker start abct-dashboard       # Start container
docker stop abct-dashboard        # Stop container
docker restart abct-dashboard     # Restart container
docker logs -f abct-dashboard     # Follow logs
docker exec -it abct-dashboard /bin/bash  # Shell access

# Maintenance
docker system prune              # Clean unused resources
docker volume ls                 # List volumes
docker inspect abct-dashboard    # Container details
docker stats abct-dashboard      # Resource usage
```

### Environment Variable Quick Copy

```bash
# Minimum required
BLOCKFROST_API_KEY=mainnetXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# Recommended
TAPTOOLS_API_KEY=your_key
CEXPLORER_API_KEY=your_key

# NFT Scheduler
NFT_SCHEDULER_ENABLED=false
NFT_UPDATE_INTERVAL_MINUTES=15
NFT_CALLS_PER_UPDATE=1
NFT_MAX_DAILY_CALLS=95

# Security
ABCT_REQUIRE_AUTH=false
ABCT_SSL_MODE=http

# Network
BIND_HOST=0.0.0.0
BIND_PORT=8000
```

---

**Document Version:** 1.0
**ABCT Version:** 0.10.0
**Last Updated:** January 2026
**Author:** ABCT Team

For questions or issues, please visit: https://github.com/Tarrant64/abct/issues
