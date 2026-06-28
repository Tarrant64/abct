# ABCT Dashboard - Docker Container

A containerized version of the ABCT (A Better Crypto Tracker) portfolio dashboard. Deploy to any Docker host for 24/7 access from anywhere.

## Quick Start

### 1. Configure Environment

```bash
cd abct-docker
cp .env.example .env
```

Edit `.env` and add your API keys:
```
BLOCKFROST_API_KEY=your_key_here
ABCT_PORT=8080
```

### 2. Build and Run

```bash
docker-compose up -d
```

### 3. Access Dashboard

Open `http://your-server-ip:8080` in your browser.

---

## Deployment Options

### Local Docker

```bash
# Build and start
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Unraid

**Option A: Using the install script**

```bash
# Copy files to Unraid
scp -r . root@unraid:/mnt/user/appdata/abct-docker/

# SSH and run
ssh root@unraid
cd /mnt/user/appdata/abct-docker
bash unraid/install-unraid.sh
```

**Option B: Manual via Unraid UI**

1. Go to **Docker** → **Add Container**
2. Build image first:
   ```bash
   cd /mnt/user/appdata/abct-docker
   docker build -t abct-dashboard -f Dockerfile ..
   ```
3. Configure container:
   - Name: `abct-dashboard`
   - Repository: `abct-dashboard:latest`
   - Port: `8080` → `80`
   - Path: `/app/data` → `/mnt/user/appdata/abct-dashboard/data`
   - Variables: `BLOCKFROST_API_KEY`

### Remote Server (VPS)

```bash
# Clone repo
git clone <repo-url>
cd ABCT/abct-docker

# Configure
cp .env.example .env
nano .env  # Add your API keys

# Build and run
docker-compose up -d --build

# (Optional) Set up reverse proxy with SSL
# Use nginx-proxy or Traefik for HTTPS
```

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BLOCKFROST_API_KEY` | Yes | Cardano blockchain access |
| `ABCT_PORT` | No | Host port (default: 8080) |
| `COINGECKO_API_KEY` | No | Better rate limits for prices |
| `NFT_PRICE_SERVICE_URL` | No | External NFT price service |

### Data Persistence

The SQLite database is stored in a Docker volume (`abct-data`). To backup:

```bash
# Copy database out
docker cp abct-dashboard:/app/data/portfolio.db ./backup.db

# Or use volume backup
docker run --rm -v abct-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/abct-backup.tar.gz /data
```

### Importing Existing Data

If you have an existing `portfolio.db` from local development:

```bash
# Copy into container
docker cp portfolio.db abct-dashboard:/app/data/portfolio.db

# Restart to pick up changes
docker-compose restart
```

---

## API Endpoints

The container exposes the full ABCT API:

| Endpoint | Description |
|----------|-------------|
| `/` | Dashboard UI |
| `/health` | Health check |
| `/wallets` | Wallet management |
| `/portfolio/summary` | Portfolio overview |
| `/defi/summary` | DeFi positions |
| `/nfts` | NFT holdings |
| `/prices` | Token prices |

All API endpoints are also available with `/api/` prefix (e.g., `/api/wallets`).

---

## Connecting Mobile App

Once deployed, your iOS app can connect to this dashboard:

1. Note your server's IP address or domain
2. In the ABCT mobile app, enter: `http://your-server:8080`
3. The app will load the dashboard in a WebView

For external access (outside your network):
- Set up port forwarding on your router, OR
- Use a reverse proxy with HTTPS (recommended)
- Consider a VPN for secure access

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs

# Common issues:
# - Missing API keys in .env
# - Port already in use (change ABCT_PORT)
# - Docker not running
```

### Can't access dashboard

```bash
# Verify container is running
docker ps | grep abct

# Check health
curl http://localhost:8080/health

# Check nginx logs
docker exec abct-dashboard cat /var/log/nginx/error.log
```

### Database issues

```bash
# Check database exists
docker exec abct-dashboard ls -la /app/data/

# Reset database (will lose all data!)
docker-compose down -v
docker-compose up -d
```

### API errors

```bash
# Check backend logs
docker exec abct-dashboard cat /var/log/supervisor/supervisord.log

# Test API directly
docker exec abct-dashboard curl http://127.0.0.1:8000/health
```

---

## Security Considerations

1. **API Keys**: Never commit `.env` file to git
2. **HTTPS**: Use a reverse proxy (nginx, Traefik) for SSL in production
3. **Firewall**: Limit access to trusted IPs if possible
4. **Updates**: Rebuild container periodically to get updates

---

## Architecture

```
┌─────────────────────────────────────────┐
│           Docker Container              │
│                                         │
│   ┌─────────────┐    ┌──────────────┐  │
│   │   Nginx     │    │   FastAPI    │  │
│   │   (port 80) │───▶│  (port 8000) │  │
│   │             │    │              │  │
│   │  Frontend   │    │   Backend    │  │
│   │  (static)   │    │   + SQLite   │  │
│   └─────────────┘    └──────────────┘  │
│         │                    │         │
└─────────│────────────────────│─────────┘
          │                    │
          ▼                    ▼
    Port 8080            /app/data/
    (exposed)           (volume mount)
```
