# ABCT - A Better Crypto Tracker

A self-hosted cryptocurrency portfolio tracker that aggregates data from multiple blockchains, exchanges, and DeFi protocols.

![Version](https://img.shields.io/badge/version-0.10.0-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-green.svg)
![FastAPI](https://img.shields.io/badge/fastapi-0.109-teal.svg)
![Security](https://img.shields.io/badge/security-hardened-green.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)

## ⚠️ Important: Intended Use

**ABCT is designed for personal, self-hosted use on trusted local networks.**

This is a hobby project for tracking your personal cryptocurrency portfolio. It is:

- ✅ **Perfect for:** Home networks, personal NAS devices, local development
- ✅ **Designed for:** Single-user or family use on trusted networks
- ❌ **NOT designed for:** Public internet hosting or multi-tenant use
- ❌ **NOT recommended:** Exposing directly to the internet without VPN

### Security Considerations

- Default configuration assumes localhost/trusted network access
- Authentication is optional (can be disabled for local use)
- No built-in HTTPS/SSL (can be added via reverse proxy if needed)
- API keys stored in environment variables
- Read-only access to blockchain data (cannot move funds)

### Remote Access

If you need to access ABCT remotely:
- ✅ Use a VPN (Tailscale, WireGuard, etc.)
- ✅ Use a reverse proxy with authentication (nginx + Basic Auth)
- ✅ Use SSH tunnel
- ❌ Don't expose port directly to internet

For more details, see [SECURITY.md](SECURITY.md)

## ✨ Features

### Portfolio Tracking
- **Multi-Blockchain Support**: Track wallets on Cardano, Bitcoin, Ethereum, Solana, Polygon, and Base
- **Exchange Integration**: Connect to Coinbase for centralized holdings
- **DeFi Monitoring**: View Cardano staking positions with APY and rewards
- **NFT Collection**: Browse your NFTs with floor price valuations
- **Portfolio History**: Interactive charts showing value over time (7d, 4w, 3m)
- **Privacy Mode**: Hide sensitive financial data with one click

### New in v0.10.0 🎉
- **🔄 Backup & Restore**: Export/import your entire configuration with one click
  - Migrate to new servers easily
  - Disaster recovery ready
  - Selective data export (choose what to include)
  - Preview before import
- **⏰ NFT Background Scheduler**: Automatic 24/7 NFT floor price updates
  - Smart rate limiting (95 calls/day)
  - State persistence (resumes after restart)
  - Priority queue system
  - Integrated into main app (no separate container needed!)

### Infrastructure
- **Self-Hosted**: Your data stays on your machine
- **Docker Ready**: Single container deployment
- **Optional HTTPS**: SSL/TLS encryption support
- **Secure Logging**: Audit trails with sensitive data redaction

## 🚀 Quick Start

ABCT works on any Docker-capable system including Linux servers, NAS devices (TrueNAS, Synology, Unraid), and desktop environments.

> **Note:** ABCT is designed for local network use. See [security considerations](#️-important-intended-use) above before exposing to external networks.

### Option 1: Docker Deployment (Recommended)

```bash
# Clone the repository
git clone https://github.com/Tarrant64/abct.git
cd abct

# Create environment file
cp .env.example .env
nano .env  # Add your API keys

# Build and run with Docker Compose
cd abct-docker
docker-compose up -d

# Access at http://localhost:8080
```

**For detailed platform-specific instructions** (TrueNAS, Synology, Portainer, etc.), see [Docker Deployment Guide](docs/DOCKER_DEPLOYMENT.md).

> **Security Note:** The default Docker configuration binds to all network interfaces. For added security on trusted networks, consider restricting port binding to localhost only (`127.0.0.1:8080:80`) or implementing authentication and HTTPS. See [SECURITY.md](SECURITY.md) for guidance.

> **Note for Unraid users:** A convenience deployment script is available at `abct-docker/update-unraid.sh` for automated deployment and updates on Unraid servers.

### Option 2: Local Development

```bash
# Clone the repository
git clone https://github.com/Tarrant64/abct.git
cd abct

# Copy and configure environment
cp .env.example .env
nano .env  # Add your Blockfrost API key at minimum

# Run the application
./run.sh

# Open in browser
open http://127.0.0.1:8000
```

The `run.sh` script will:
- Create a Python virtual environment
- Install dependencies
- Start the FastAPI backend
- Display the server URL

## Screenshots

The dashboard provides a comprehensive view of your crypto portfolio:

- **Portfolio Summary**: Total value across all blockchains
- **Value History Chart**: Track portfolio performance over 7 days, 4 weeks, or 3 months
- **Staking Positions**: View delegated ADA, earned rewards, and pool APY
- **Exchange Holdings**: See balances from connected exchanges
- **NFT Gallery**: Browse collections with floor price estimates

<img width="2440" height="1612" alt="image" src="https://github.com/user-attachments/assets/36b98266-97c3-404c-9b0d-6e2d925ae5df" />
<img width="2996" height="1650" alt="image" src="https://github.com/user-attachments/assets/073a6537-e012-469c-b163-91090ec375c2" />


## Requirements

- Python 3.9 or higher
- 512MB RAM minimum
- API keys (see below)

## API Keys

| Service | Required | Purpose | Sign Up |
|---------|----------|---------|---------|
| Blockfrost | **Yes** | Cardano blockchain data | [blockfrost.io](https://blockfrost.io) |
| CExplorer | Recommended | Staking/rewards data | [cexplorer.io/api](https://cexplorer.io/api) |
| TapTools | Optional | NFT floor prices | [taptools.io](https://taptools.io/openapi/subscription) |
| Coinbase | Optional | Exchange integration | [portal.cdp.coinbase.com](https://portal.cdp.coinbase.com) |
| Etherscan | Optional | Ethereum support | [etherscan.io](https://etherscan.io/apis) |

## 📁 Project Structure

```
ABCT/
├── backend/                    # Python FastAPI backend
│   ├── main.py                # Application entry point
│   ├── config.py              # Configuration management
│   ├── database.py            # SQLite database layer
│   ├── routers/               # API endpoint handlers
│   │   ├── wallets.py         # Wallet CRUD operations
│   │   ├── portfolio.py       # Portfolio summary & history
│   │   ├── prices.py          # Cryptocurrency prices
│   │   ├── defi.py            # Staking positions
│   │   ├── exchanges.py       # Exchange balances
│   │   ├── nfts.py            # NFT collection
│   │   ├── nft_scheduler.py   # NFT scheduler API (v0.9.0+)
│   │   ├── backup.py          # Backup & restore API (v0.10.0+)
│   │   ├── security.py        # Security settings
│   │   └── settings.py        # Application settings
│   ├── services/              # Business logic layer
│   │   ├── cardano.py         # Cardano blockchain service
│   │   ├── bitcoin.py         # Bitcoin blockchain service
│   │   ├── ethereum.py        # Ethereum/EVM blockchain service
│   │   ├── pricing.py         # Price aggregation
│   │   ├── defi.py            # DeFi/staking service
│   │   ├── coinbase.py        # Coinbase exchange service
│   │   ├── nft.py             # NFT service
│   │   ├── nft_scheduler.py   # NFT background scheduler (v0.9.0+)
│   │   └── snapshot.py        # Portfolio snapshot service
│   ├── middleware/            # Security middleware
│   │   ├── auth.py            # Authentication
│   │   └── rate_limit.py      # Rate limiting
│   └── utils/                 # Utility functions
├── frontend/                  # HTML/CSS/JS frontend
│   ├── index.html             # Main dashboard
│   ├── wallets.html           # Wallet manager
│   ├── services.html          # Services monitor (NFT scheduler)
│   ├── backup.html            # Backup & restore (v0.10.0+)
│   ├── apis.html              # API key manager
│   ├── security.html          # Security settings
│   ├── nft-wall.html          # NFT gallery
│   ├── logs.html              # System logs
│   ├── css/styles.css         # Styling
│   └── js/app.js              # Client-side logic
├── abct-docker/               # Docker deployment
│   ├── Dockerfile             # Container definition
│   ├── nginx.conf             # Reverse proxy config
│   ├── supervisord.conf       # Process manager
│   └── update-unraid.sh       # Deployment script
├── data/                      # SQLite databases (auto-created)
│   ├── portfolio.db           # Main database
│   └── nft_images.db          # NFT image cache
├── docs/                      # Documentation
│   ├── ARCHITECTURE.md        # System architecture
│   ├── BACKUP_RESTORE_GUIDE.md # Backup documentation
│   └── ...
├── .env                       # API keys (you create this)
├── .env.example               # Example configuration
├── requirements.txt           # Python dependencies
├── run.sh                     # Start server (local)
├── stop.sh                    # Stop server (local)
├── CHANGELOG.md               # Version history
└── README.md                  # This file
```

## 📡 API Endpoints

### Wallets
- `GET /wallets` - List all tracked wallets
- `POST /wallets` - Add a new wallet
- `DELETE /wallets/{id}` - Remove a wallet
- `POST /wallets/{id}/refresh` - Refresh wallet data

### Portfolio
- `GET /portfolio/summary` - Get portfolio overview
- `GET /portfolio/history?range=7d|4w|3m` - Historical values
- `POST /portfolio/snapshot` - Create manual snapshot

### Prices
- `GET /prices` - Current cryptocurrency prices

### DeFi
- `GET /defi/staking` - Cardano staking positions

### Exchanges
- `GET /exchanges/balances` - Exchange holdings

### NFTs
- `GET /nfts` - NFT collection with values
- `GET /nfts/summary` - Collections grouped
- `GET /nfts/prices/status` - Price collection status
- `POST /nfts/prices/collect` - Trigger price collection

### NFT Background Scheduler (v0.9.0+)
- `GET /nft-scheduler/status` - Get scheduler status and statistics
- `POST /nft-scheduler/enable` - Enable background updates
- `POST /nft-scheduler/disable` - Disable background updates
- `POST /nft-scheduler/trigger` - Manually trigger update cycle
- `GET /nft-scheduler/collections` - List tracked NFT collections

### Backup & Restore (v0.10.0+)
- `GET /backup/info` - Get backup information and statistics
- `POST /backup/export` - Export configuration to JSON
- `POST /backup/preview` - Preview backup file (dry-run)
- `POST /backup/import` - Import configuration from backup

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# ============================================
# REQUIRED: Cardano Blockchain API
# ============================================
BLOCKFROST_API_KEY=mainnetXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# ============================================
# RECOMMENDED: Enhanced Features
# ============================================
CEXPLORER_API_KEY=your_key_here      # Staking positions and rewards
TAPTOOLS_API_KEY=your_key_here       # NFT floor prices

# ============================================
# OPTIONAL: Additional Blockchains
# ============================================
ETHERSCAN_API_KEY=your_key_here      # Ethereum support
ALCHEMY_API_KEY=your_key_here        # Ethereum/Polygon/Base NFTs
HELIUS_API_KEY=your_key_here         # Solana support

# ============================================
# NFT Background Scheduler (v0.9.0+)
# ============================================
NFT_SCHEDULER_ENABLED=false           # Enable automatic NFT price updates
NFT_UPDATE_INTERVAL_MINUTES=15        # Update every 15 minutes (default)
NFT_CALLS_PER_UPDATE=1                # Collections per cycle
NFT_MAX_DAILY_CALLS=95                # Daily API call limit

# ============================================
# Authentication (v0.10.0+)
# ============================================
ABCT_REQUIRE_AUTH=false               # Set to false for localhost-only
# ABCT_ADMIN_USER=admin               # Required if auth enabled
# ABCT_ADMIN_PASSWORD=secure_password # Required if auth enabled

# ============================================
# HTTPS/SSL (Optional)
# ============================================
# ABCT_SSL_MODE=http                  # Options: http | https-self-signed | https-custom
# ABCT_SSL_CERT=/path/to/cert.pem
# ABCT_SSL_KEY=/path/to/key.pem
```

### Coinbase Integration

1. Get API credentials from https://portal.cdp.coinbase.com/access/api
2. Create `cdp_api_key.json` in project root:
```json
{
    "name": "your-api-key-name",
    "privateKey": "-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----\n"
}
```

## Development

```bash
# Activate virtual environment
source venv/bin/activate

# Run with auto-reload
cd backend
uvicorn main:app --reload

# Run tests (if available)
pytest
```

## 🔒 Security

- **Local Only**: Server binds to 127.0.0.1 by default (localhost-only)
- **Read-Only Access**: Cannot move funds, only view balances and data
- **No Telemetry**: No data sent to external analytics or tracking
- **Local Database**: All data stored in local SQLite files
- **Optional Authentication**: HTTP Basic Auth for network-exposed deployments (v0.10.0+)
- **HTTPS Support**: SSL/TLS encryption with self-signed or custom certificates (v0.8.0+)
- **Secure Logging**: Audit trails with sensitive data redaction
- **Input Validation**: Protection against malformed inputs and XSS
- **Rate Limiting**: API endpoint protection against abuse
- **CORS Hardening**: Restricted cross-origin access
- **DOMPurify**: Client-side XSS protection on all HTML rendering

**Note:** This application is designed for **self-hosted, localhost-only** use. The optional authentication feature allows running without credentials on trusted local installations, or with Basic Auth if you expose it on your network.

For detailed security information, see [SECURITY.md](SECURITY.md)

## 📦 What's New

### v0.10.0 - Backup & Restore Release (January 2026)
- **Complete Backup System**: Export/import all your configuration data
- **Migration Ready**: Easily move to new servers
- **Selective Export**: Choose what data to include
- **Import Modes**: Merge (safe) or Replace (full restore)
- **Security Warnings**: Alerts for sensitive data in backups

### v0.9.0 - NFT Scheduler Integration (January 2026)
- **Single Container**: NFT price service integrated into main app
- **Background Updates**: Automatic 24/7 NFT floor price collection
- **Smart Rate Limiting**: Respects TapTools 95 calls/day limit
- **State Persistence**: Resumes exactly where it left off after restart
- **UI Controls**: Enable/disable from Services page

See [CHANGELOG.md](CHANGELOG.md) for complete version history.

## 📖 Documentation

- **[Docker Deployment Guide](docs/DOCKER_DEPLOYMENT.md)** - Complete multi-platform Docker setup
- **[Quick Start Guide](docs/)** - Get up and running
- **[Architecture](docs/ARCHITECTURE.md)** - System design overview
- **[Backup & Restore Guide](docs/BACKUP_RESTORE_GUIDE.md)** - Configuration management
- **[Security Guide](SECURITY.md)** - Security best practices
- **[API Documentation](#-api-endpoints)** - Complete endpoint reference

## 🔧 Troubleshooting

### Server won't start
```bash
# Check if port is in use
lsof -i :8000

# Kill existing process
./stop.sh
```

### Missing data
```bash
# Refresh all wallet data
# Click the refresh button in the UI, or:
curl -X POST http://127.0.0.1:8000/wallets/1/refresh
```

### Database reset
```bash
# Backup first!
cp data/portfolio.db data/portfolio.db.backup
rm data/portfolio.db
./run.sh  # Fresh database created
```

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

Built with amazing open-source tools and data from leading blockchain API providers:

### Backend Framework
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [APScheduler](https://apscheduler.readthedocs.io/) - Background task scheduling
- [SQLite](https://www.sqlite.org/) - Embedded database
- [HTTPX](https://www.python-httpx.org/) - Async HTTP client

### Frontend Libraries
- [Chart.js](https://www.chartjs.org/) - Interactive charting
- [DOMPurify](https://github.com/cure53/DOMPurify) - XSS sanitization

### Blockchain Data Providers

#### Cardano Network
- [Blockfrost](https://blockfrost.io/) - Primary Cardano blockchain API (addresses, transactions, assets, staking)
- [TapTools](https://www.taptools.io/) - Cardano NFT floor price data and token analytics
- [CExplorer](https://cexplorer.io/) - Cardano staking positions and DeFi data
- [Koios](https://koios.rest/) - Free Cardano API (metadata fallback)

#### Ethereum & EVM Chains
- [Alchemy](https://www.alchemy.com/) - Multi-chain infrastructure (Ethereum, Polygon, Base, Optimism)
- [Etherscan](https://etherscan.io/) - Ethereum blockchain explorer API
- [Basescan](https://basescan.org/) - Base blockchain explorer API
- [Polygonscan](https://polygonscan.com/) - Polygon blockchain explorer API

#### Solana Network
- [Helius](https://www.helius.dev/) - Solana blockchain API and RPC

#### Bitcoin Network
- [Blockstream](https://blockstream.info/) - Bitcoin blockchain data (free, no API key required)

#### Pricing & Market Data
- [CoinGecko](https://www.coingecko.com/) - Cryptocurrency price aggregation and market data
- [CoinMarketCap](https://coinmarketcap.com/) - Alternative cryptocurrency price data
- [Coinbase](https://www.coinbase.com/) - Spot price data (public API)
- [DefiLlama](https://defillama.com/) - Universal price fallback for all chains

#### Exchange Integration
- [Coinbase CDP](https://www.coinbase.com/cloud) - Exchange API for portfolio balances

### Privacy & Blockchain Innovation
- [Midnight Network](https://midnight.network/) - Privacy-focused Cardano partner chain (NIGHT token support)

For detailed API information including rate limits and pricing, see [API_PROVIDERS.md](API_PROVIDERS.md).

## 🔗 Links

- **Repository**: https://github.com/Tarrant64/abct
- **Releases**: https://github.com/Tarrant64/abct/releases
- **Issues**: https://github.com/Tarrant64/abct/issues
- **Latest Release**: [v0.10.0 - Backup & Restore](https://github.com/Tarrant64/abct/releases/tag/v0.10.0)

---

**Current Version:** v0.10.0 (BUILD 1769648168)
**Last Updated:** January 2026
