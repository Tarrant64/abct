# Cardano NFT Floor Price Service

A standalone microservice that continuously collects Cardano NFT floor prices from TapTools and exposes them via REST API. Designed to run 24/7 on a server to work around TapTools API rate limits (100 calls/day).

## Why This Service?

TapTools has a strict rate limit of **100 API calls per day**. When tracking 300+ NFTs across many collections, this limit is quickly exhausted. This service:

- **Spreads API calls over 24 hours** (~4 calls/hour = 96/day)
- **Prioritizes high-value collections**
- **Stores all prices in SQLite** for instant retrieval
- **Exposes REST API** for ABCT (or any client) to query
- **Runs independently** on a server, separate from your local machine

## Quick Start

### 1. Set your TapTools API key

Create a `.env` file:

```bash
TAPTOOLS_API_KEY=your_api_key_here
```

Or export it:

```bash
export TAPTOOLS_API_KEY=your_api_key_here
```

### 2. Deploy with Docker Compose

```bash
# Build and start
docker-compose up -d

# Check logs
docker-compose logs -f

# Stop
docker-compose down
```

### 3. Verify it's running

```bash
curl http://localhost:8080/health
# {"status":"healthy","service":"nft-floor-price-service","database":"connected"}

curl http://localhost:8080/status
# Shows service stats, API calls today, collections tracked
```

## API Endpoints

### Health & Status

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/status` | GET | Service statistics |

### Collections

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/collections` | GET | List all tracked collections |
| `/collections/{policy_id}` | GET | Get collection details |
| `/collections/{policy_id}/history` | GET | Price history |
| `/collections/register` | POST | Register a collection to track |
| `/collections/register-batch` | POST | Register multiple collections |
| `/collections/{policy_id}` | DELETE | Remove collection |

### Floor Prices (for ABCT integration)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/floor/{policy_id}` | GET | Get floor price for one collection |
| `/floors?policy_ids=a,b,c` | GET | Get floor prices for multiple collections |

### Sync Control

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/sync/trigger` | POST | Manually trigger a price update |

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `TAPTOOLS_API_KEY` | (required) | Your TapTools API key |
| `UPDATE_INTERVAL_MINUTES` | `15` | Minutes between update cycles |
| `CALLS_PER_UPDATE` | `1` | API calls per update cycle |
| `DATABASE_PATH` | `/app/data/nft_prices.db` | SQLite database path |

### Rate Limit Strategy

With default settings (15 min interval, 1 call/update):
- **4 API calls per hour**
- **96 API calls per day** (under 100 limit)
- Each collection updated every ~6 hours (with 24 collections)

To track more collections, consider:
- Longer intervals (30 min = 48 calls/day)
- Or prioritize high-value collections

## Integrating with ABCT

### Option 1: Direct API Calls

Configure ABCT to fetch floor prices from this service instead of TapTools:

```python
# In ABCT's nft.py
NFT_PRICE_SERVICE_URL = "http://your-server:8080"

async def get_floor_price(policy_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{NFT_PRICE_SERVICE_URL}/floor/{policy_id}")
        data = response.json()
        return data.get("floor_price")
```

### Option 2: Batch Registration

Register all your NFT collections:

```bash
curl -X POST "http://localhost:8080/collections/register-batch" \
  -H "Content-Type: application/json" \
  -d '[
    {"policy_id": "abc123...", "name": "Cool Cats", "priority": 10},
    {"policy_id": "def456...", "name": "Rare NFTs", "priority": 5}
  ]'
```

### Option 3: Sync ABCT's NFT database

Export ABCT's tracked collections and register them here:

```bash
# From ABCT, get all NFT policy IDs
curl http://localhost:8000/nfts | jq '.nfts[].policy_id' | sort -u > policies.txt

# Register each one
while read policy; do
  curl -X POST "http://your-server:8080/collections/register?policy_id=$policy"
done < policies.txt
```

## Data Persistence

The SQLite database is stored in a Docker volume (`nft-data`). To backup:

```bash
# Copy database out of container
docker cp nft-floor-prices:/app/data/nft_prices.db ./backup.db

# Or mount a host directory instead of volume
volumes:
  - ./data:/app/data
```

## Deploying to Unraid

### Quick Install (Recommended)

1. Copy the `nft-price-service` folder to your Unraid server:
   ```bash
   scp -r nft-price-service root@unraid:/mnt/user/appdata/nft-price-service-build
   ```

2. SSH into Unraid and run the installer:
   ```bash
   ssh root@unraid
   bash /mnt/user/appdata/nft-price-service-build/unraid/install-unraid.sh
   ```

3. Enter your TapTools API key when prompted

4. Done! Access at `http://unraid-ip:8080/status`

### Manual Install via Unraid UI

1. Go to **Docker** → **Add Container**
2. Use these settings:

| Setting | Value |
|---------|-------|
| Name | `nft-floor-prices` |
| Repository | Build locally first (see below) |
| Port | `8080` → `8080` |
| Path | `/app/data` → `/mnt/user/appdata/nft-floor-prices` |
| Variable: `TAPTOOLS_API_KEY` | Your API key |
| Variable: `UPDATE_INTERVAL_MINUTES` | `15` |

3. Build the image first via SSH:
   ```bash
   cd /mnt/user/appdata/nft-price-service-build
   docker build -t nft-floor-prices .
   ```

### Using the XML Template

Copy `unraid/nft-floor-prices.xml` to `/boot/config/plugins/dockerMan/templates-user/` on your Unraid server, then find it in the Docker UI under "Add Container".

---

## Deploying to a Server

### Using Docker (recommended)

```bash
# On your server
git clone <repo>
cd nft-price-service

# Create .env with your API key
echo "TAPTOOLS_API_KEY=your_key" > .env

# Start
docker-compose up -d
```

### Using systemd (without Docker)

```bash
# Install dependencies
pip install -r requirements.txt

# Create systemd service
sudo cat > /etc/systemd/system/nft-price-service.service << EOF
[Unit]
Description=NFT Floor Price Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/nft-price-service
Environment=TAPTOOLS_API_KEY=your_key
ExecStart=/usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable nft-price-service
sudo systemctl start nft-price-service
```

## Monitoring

Check service status:

```bash
curl http://localhost:8080/status
```

Response includes:
- `api_calls_today`: Calls made today
- `api_calls_remaining`: Calls left before rate limit
- `collections_tracked`: Number of collections
- `last_update`: When prices were last fetched
- `rate_limited_until`: If rate limited, when it resets
