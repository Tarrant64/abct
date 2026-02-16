# A Better Crypto Tracker (ABCT)

Personal multi-chain portfolio tracker built Cardano-first.

![Version](https://img.shields.io/badge/version-1.9.0-brightgreen.svg)
![Build](https://img.shields.io/badge/build-1771009377-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-green.svg)
![FastAPI](https://img.shields.io/badge/fastapi-0.109-teal.svg)
![Chains](https://img.shields.io/badge/chains-11-brightgreen.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![Exchanges](https://img.shields.io/badge/exchanges-7-purple.svg)
![Themes](https://img.shields.io/badge/themes-5-purple.svg)

## Why

Existing multi-chain wallets treat Cardano as an afterthought — basic balance tracking with no stake pool info, broken native assets, and zero governance integration. This project flips that: deep Cardano ecosystem support first, then proper multi-chain coverage.

## Features
**Cardano** (Primary):
- Stake pool tracking, rewards, governance
- Native assets with metadata and decimals
- DeFi protocol integration (Minswap, SundaeSwap, etc.)
- NFT collections with floor prices
- Stake key wallet grouping

**Other Chains** (10):
Bitcoin, Ethereum, Solana, Polygon, Base, Algorand, Arbitrum, Avalanche, BNB Chain, Tron

**Tools**:
Privacy-focused (self-hosted), transaction analytics, custom tokens, portfolio history with per-wallet tracking

## Project
Personal side project built with AI assistance. Goal: Create a robust tracker that doesn't compromise on Cardano while supporting major chains.

**Current Build**: v1.9.0 (BUILD 1771009377)

## ⚠️ Important: Intended Use

**ABCT is designed for personal, self-hosted use on trusted local networks.**
**NOTE:** **THIS WILL HAVE PERIODIC BUGS AS I'M WORKING THROUGH THIS TO LEARN MORE ABOUT CONNECTING TO BLOCKCHAIN INFRASTRUCTURES VIA API, WHAT WORKS WEL, AND WHAT DOESN'T. **

This is a hobby project for tracking your personal cryptocurrency portfolio. It is:

- ✅ **Perfect for:** Home networks, personal NAS devices, local development
- ✅ **Designed for:** Single-user or family use on trusted networks
- ❌ **NOT designed for:** Public internet hosting or multi-tenant use
- ❌ **NOT recommended:** Exposing directly to the internet without VPN

### Security Considerations

- Default configuration assumes localhost/trusted network access
- Authentication is optional (can be disabled for local use)
- Built-in HTTPS/SSL support (self-signed or custom certificates)
- API keys encrypted at rest in database
- Read-only access to blockchain data (cannot move funds)

### Remote Access

If you need to access ABCT remotely:
- ✅ Use built-in Cloudflare Tunnel (configured in Settings — auto-restores across updates)
- ✅ Use a VPN (Tailscale, WireGuard, etc.)
- ✅ Use a reverse proxy with authentication (nginx + Basic Auth)
- ✅ Use SSH tunnel
- ❌ Don't expose port directly to internet

For more details, see [SECURITY.md](SECURITY.md)

## 🏗️ Architecture

For a detailed overview of the system architecture, authentication flow, and database structure, see [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## ✨ Features

### Portfolio Tracking
- **11 Blockchains**: Cardano, Bitcoin, Ethereum, Solana, Polygon, Base, Algorand, Arbitrum, Avalanche, BNB Chain, Tron
- **7 Exchanges**: Coinbase, Binance, Binance.US, OKX, Bitget, Gate.io, KuCoin
- **Per-Wallet History**: Daily balance tracking per wallet/exchange/staking position with unified chart
- **Dashboard**: Dynamic blockchain cards, allocation donut chart, market heatmap, portfolio breakdown
- **DeFi Monitoring**: Cardano staking positions with APY and rewards
- **NFT Collection**: Browse your NFTs with floor price valuations
- **Transaction History**: Complete transaction tracking across all blockchains with analytics
- **Privacy Mode**: Hide sensitive financial data and URLs with one click
- **Cloudflare Tunnel**: Built-in support for secure remote access (auto-restores across container rebuilds)

### Infrastructure
- **Self-Hosted**: Your data stays on your machine
- **Docker Ready**: Single container deployment with automated update scripts
- **V2 Data Architecture**: Per-source daily balances, materializer pipeline, off-chain collector
- **Optional HTTPS**: SSL/TLS encryption support
- **Secure Logging**: Audit trails with sensitive data redaction

## 📦 What's New

### v1.9.0 - V2 Architecture, Dashboard Overhaul & 11-Chain Support (February 2026)
- **V2 Data Architecture**: Complete rebuild of portfolio history around per-wallet granularity
  - New `wallet_sources` and `wallet_daily_balances` tables track each wallet, exchange, staking position, DeFi position, and NFT collection individually
  - Materializer pipeline converts raw data into unified daily balances with automatic gap-filling
  - Off-chain collector runs every 2 hours for exchange, staking, DeFi, NFT, and live on-chain values
  - Unified chart reads exclusively from V2 tables (all V1 legacy fallbacks removed)
  - Automatic V1 data migration on startup — existing balance history is preserved
  - Rebuild History button in Settings to clear and regenerate from source data
- **Dashboard Overhaul**: Complete visual redesign
  - Dynamic blockchain cards auto-populate based on your wallets
  - Interactive allocation donut chart with hover tooltips
  - Market heatmap (treemap) showing portfolio holdings with relative sizing
  - Global market cap widget
  - Redesigned portfolio card with top holdings, 7-day change, liquid/staked/NFT breakdown
- **4 New Blockchains** (7 → 11 chains): Arbitrum, Avalanche, BNB Chain (BSC), Tron
- **V1→V2 Engine Consolidation**: Unified price cache (CoinGecko bulk + DefiLlama fallback), unified collection pipeline, Data Collectors settings tab
- **Cloudflare Tunnel Persistence**: Token stored encrypted in DB; auto-restores tunnel on container rebuild
- **Mobile API**: All 11 chains, NFT image URLs, correct chart fields, graceful error handling
- **Privacy**: Sensitive URLs hidden from browser status bar in privacy mode
- **Deployment**: Removed redundant migration scripts; database.py handles all schema idempotently on startup

### v1.5.0 - V2 Ingestion Engine (February 2026)
- **V2 Ingestion Engine**: 6-stage pipeline (Expand → Index → Hydrate → Normalize → Enrich → Positions)
  - 14 registered data providers with priority-based scoring and automatic failover
  - Circuit breaker pattern, token bucket rate limiting, bulkhead concurrency control
  - Idempotent event dedup (safe to re-run backfills)
- **Backfill Orchestration**: Plan, execute, and monitor backfills via API
- **8 New Database Tables** for engine state, **11 New API Endpoints** for engine management
- **Performance**: Fixed 7s page load delay, improved Assets UX

### v1.0.1 - UI, Themes, & Multi-Chain Expansion (February 2026)
- **Algorand Support**: Pera Wallet API + Tatum fallback, native ALGO + ASA + NFTs
- **Transaction History**: Unified multi-chain view with analytics and chain filtering
- **Theme Redesign**: 5 themes (Dark Mode, Light, Cypherpunk 1, Ocean Depths, Sunset Horizon)
- **.env Import/Export**: Upload .env files to import API keys directly into database
- **Demo Mode**: 91 tokens, 76 NFTs, 1,500 transactions across all blockchains

### v1.0.0 - Production Ready Release (January 2026)
- **7 Exchange Integrations**: Coinbase, Binance, Binance.US, OKX, Bitget, Gate.io, KuCoin
- **Visual Enhancements**: Blockchain and token logos via LogoKit/Logostream
- **Manage Wallets**: Three-tab interface (Self-Custody, Exchanges, Manual Tokens)

### Earlier Releases
- **v0.13**: Asset breakdown charts, The Graph token pricing, NFT Wall improvements
- **v0.12**: Multi-user support, demo mode, multi-chain NFT wall
- **v0.10**: Backup/restore system, NFT background scheduler

See [CHANGELOG.md](CHANGELOG.md) for complete version history.

## 🔐 Default Login Credentials

ABCT includes a login page to protect your portfolio data. Use these credentials on first access:

- **Admin Account**:
  - Username: `admin`
  - Password: `satoshi`
  - Full access to add wallets and configure settings

- **Demo Account**:
  - Username: `demo`
  - Password: `demo`
  - Pre-loaded with ~$1M multi-chain portfolio:
    - 91 tokens across all 11 blockchains
    - 76 NFTs across 7 collections
    - 1,500 transactions over 1 year
    - DeFi positions, exchange balances, and staking
  - Try ABCT without connecting your wallets!

**⚠️ IMPORTANT**: Change the default admin password after first login! See [Password Reset Guide](docs/guides/PASSWORD_RESET_GUIDE.md) for instructions.

**Forgot your password?** See [Password Reset Guide](docs/guides/PASSWORD_RESET_GUIDE.md) for reset instructions.

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

> **Note for Unraid users:** Two deployment scripts are available:
> - `abct-docker/update-unraid.sh` — rsync local files to Unraid and rebuild
> - `abct-docker/deploy-from-git.sh` — pull latest from GitHub and rebuild (recommended)

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

- **Portfolio Card**: Total value with top holdings, 7-day change, and liquid/staked/NFT breakdown
- **Unified Chart**: Portfolio value over time (1W, 4W, 3M, All) from per-wallet daily balances
- **Allocation Donut**: Interactive chain allocation with hover tooltips
- **Market Heatmap**: Treemap of holdings with relative sizing
- **Blockchain Cards**: Auto-populated based on your tracked wallets

<img width="1231" height="699" alt="Screenshot 2026-01-29 at 9 11 28 PM" src="https://github.com/user-attachments/assets/b0ff3d54-48fa-47dd-af6b-b73033e5d60a" />
<img width="1206" height="762" alt="Screenshot 2026-01-29 at 9 12 54 PM" src="https://github.com/user-attachments/assets/93011fcd-56a9-421f-ad15-34bc14cc3814" />
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
| Etherscan | Optional | Ethereum support | [etherscan.io](https://etherscan.io/apis) |
| Coinbase | Optional | Exchange balances | [portal.cdp.coinbase.com](https://portal.cdp.coinbase.com) |
| Binance | Optional | Exchange balances | [binance.com/en/my/settings/api-management](https://www.binance.com/en/my/settings/api-management) |
| OKX | Optional | Exchange balances | [okx.com/account/my-api](https://www.okx.com/account/my-api) |

## 📁 Project Structure

```
ABCT/
├── backend/                    # Python FastAPI backend
│   ├── main.py                # Application entry point
│   ├── config.py              # Configuration management
│   ├── database.py            # SQLite database layer
│   ├── auth_utils.py          # Session auth utilities
│   ├── routers/               # API endpoint handlers (26 routers)
│   │   ├── auth.py            # Authentication (login/logout/password)
│   │   ├── portfolio.py       # Portfolio summary & history
│   │   ├── wallets.py         # Wallet CRUD operations
│   │   ├── prices.py          # Cryptocurrency prices
│   │   ├── defi.py            # Staking positions
│   │   ├── exchanges.py       # Exchange balances
│   │   ├── nfts.py            # NFT collection
│   │   ├── nft_scheduler.py   # NFT scheduler API
│   │   ├── transactions.py    # Transaction history & analytics
│   │   ├── balance_history.py # Balance history charts
│   │   ├── engine.py          # V2 Ingestion Engine API (v1.5.0+)
│   │   ├── backup.py          # Backup & restore
│   │   ├── cache.py           # Cache management
│   │   ├── custom_tokens.py   # Custom token management
│   │   ├── dashboard.py       # Dashboard data
│   │   ├── demo.py            # Demo mode management
│   │   ├── spam.py            # Spam token filtering
│   │   ├── nmkr.py            # NMKR NFT minting
│   │   ├── cloudflare.py      # Cloudflare tunnel management
│   │   ├── mobile.py          # Mobile API endpoints
│   │   ├── system.py          # System info & health
│   │   ├── settings.py        # Application settings
│   │   ├── security.py        # Security settings
│   │   └── logs.py            # Log viewer
│   ├── engine/                # V2 Ingestion Engine & Data Architecture
│   │   ├── models.py          # Pydantic models (ChainId, WorkUnit, CanonicalEvent)
│   │   ├── db.py              # 8 engine_* tables with CRUD
│   │   ├── orchestrator.py    # Backfill orchestration & pipeline coordination
│   │   ├── materializer.py    # Converts raw data → wallet_daily_balances
│   │   ├── expansion/         # Stage A: wallet → account subjects
│   │   │   ├── cardano_expander.py   # Stake key → payment addresses
│   │   │   ├── bitcoin_expander.py   # Address passthrough
│   │   │   ├── evm_expander.py       # Normalize to lowercase
│   │   │   └── solana_expander.py    # SPL token account enumeration
│   │   ├── indexing/          # Stage B: collect tx IDs (cheap)
│   │   │   ├── cardano_indexer.py    # Blockfrost pagination
│   │   │   ├── bitcoin_indexer.py    # Blockstream pagination
│   │   │   ├── evm_indexer.py        # Etherscan txlist+internal+token
│   │   │   ├── solana_indexer.py     # Helius getSignatures
│   │   │   └── coinstats_indexer.py  # CoinStats (NOT Cardano)
│   │   ├── hydration/         # Stage C: full tx detail (expensive)
│   │   │   ├── cardano_hydrator.py   # Blockfrost UTXOs
│   │   │   ├── bitcoin_hydrator.py   # Blockstream /tx/
│   │   │   ├── evm_hydrator.py       # Alchemy RPC
│   │   │   ├── solana_hydrator.py    # Helius enhanced tx
│   │   │   └── coinstats_hydrator.py # CoinStats (NOT Cardano)
│   │   ├── normalization/     # Stage D: raw tx → canonical events
│   │   │   ├── cardano_normalizer.py # UTxO in/out → events
│   │   │   ├── bitcoin_normalizer.py # vin/vout → events
│   │   │   ├── evm_normalizer.py     # logs → events
│   │   │   └── solana_normalizer.py  # instructions → events
│   │   ├── enrichment/        # Stage E: prices & metadata
│   │   │   ├── price_enricher.py         # Historical price lookup
│   │   │   ├── token_metadata_enricher.py # Token name/decimals
│   │   │   └── nft_metadata_enricher.py   # NFT metadata (stub)
│   │   ├── positions/         # Stage F: DeFi inference (stubs)
│   │   │   ├── cardano_defi.py  # Cardano DeFi positions
│   │   │   └── evm_defi.py     # EVM DeFi positions
│   │   ├── providers/         # Provider registry & scoring
│   │   │   ├── provider.py    # Provider dataclass
│   │   │   └── registry.py    # 14 providers with health-aware selection
│   │   └── scheduler/         # Rate limiting & circuit breaking
│   │       ├── scheduler.py       # Work unit scheduler
│   │       ├── token_bucket.py    # Per-provider rate limiter
│   │       └── circuit_breaker.py # Health tracking & auto-pause
│   ├── services/              # Business logic layer (50+ services)
│   │   ├── cardano.py         # Cardano blockchain
│   │   ├── bitcoin.py         # Bitcoin blockchain
│   │   ├── ethereum.py        # Ethereum blockchain
│   │   ├── solana.py          # Solana blockchain
│   │   ├── polygon.py         # Polygon blockchain
│   │   ├── base.py            # Base blockchain
│   │   ├── algorand.py        # Algorand blockchain
│   │   ├── etherscan.py       # Etherscan multi-chain API
│   │   ├── pricing.py         # Price aggregation (5-source fallback)
│   │   ├── defi.py            # DeFi/staking service
│   │   ├── balance_history.py # V1 balance history
│   │   ├── transaction_history.py  # Multi-chain transactions
│   │   ├── http_client.py     # Shared HTTP client pool (30+ named pools)
│   │   ├── api_key_manager.py # Dynamic API key management
│   │   ├── coinbase.py        # Coinbase exchange
│   │   ├── binance_service.py # Binance.com exchange
│   │   ├── binance_us_service.py # Binance.US exchange
│   │   ├── okx_service.py     # OKX exchange
│   │   ├── bitget_service.py  # Bitget exchange
│   │   ├── gate_service.py    # Gate.io exchange
│   │   ├── kucoin_service.py  # KuCoin exchange
│   │   ├── nft.py             # NFT service
│   │   ├── nft_scheduler.py   # NFT background scheduler
│   │   ├── nft_price_client.py # NFT price aggregation
│   │   ├── nft_image_service.py # NFT image caching
│   │   ├── ethereum_nft.py    # Ethereum NFT service
│   │   ├── solana_nft.py      # Solana NFT service
│   │   ├── algorand_nft.py    # Algorand NFT service
│   │   ├── offchain_collector.py  # V2: Periodic off-chain balance collection (2h)
│   │   ├── offchain_helpers.py   # Staking/DeFi/NFT/exchange value helpers
│   │   ├── snapshot.py        # Portfolio snapshots (V1, deprecated)
│   │   ├── logostream.py      # Token logo API
│   │   ├── logging_service.py # Structured logging
│   │   ├── taptools.py        # TapTools Cardano data
│   │   ├── moralis.py         # Moralis NFT service
│   │   ├── nmkr.py            # NMKR minting service
│   │   ├── nmkr_service.py    # NMKR business logic
│   │   ├── nftcdn.py          # NFT CDN service
│   │   ├── graph.py           # The Graph API (Uniswap pricing)
│   │   └── demo_*.py          # Demo mode services (wallets, NFTs, transactions, etc.)
│   └── middleware/            # Security middleware
│       ├── demo_mode.py       # Demo mode detection
│       └── size_limit.py      # Request size limiting
├── frontend/                  # HTML/CSS/JS frontend
│   ├── index.html             # Main dashboard
│   ├── wallets.html           # Wallet management
│   ├── assets.html            # Asset breakdown & details
│   ├── transactions.html      # Transaction history & analytics
│   ├── nft-wall.html          # NFT gallery
│   ├── nfts.html              # NFT collection management
│   ├── settings.html          # Consolidated settings (APIs, exchanges, security)
│   ├── system.html            # System management (logs, cache, services, backup)
│   ├── login.html             # Login page
│   ├── api-help.html          # API setup guide
│   ├── dashv2.html            # Dashboard V2 (experimental)
│   ├── static/demo-nfts/      # Demo NFT images
│   ├── css/styles.css         # Styling (5 themes, 7000+ lines)
│   └── js/
│       ├── app.js             # Main application logic
│       └── session-auth.js    # Authentication utilities
├── abct-docker/               # Docker deployment
│   ├── Dockerfile             # Container definition
│   ├── nginx.conf             # Reverse proxy config
│   ├── supervisord.conf       # Process manager
│   ├── deploy-from-git.sh     # Deploy from GitHub (recommended)
│   └── update-unraid.sh       # Deploy via rsync
├── data/                      # SQLite databases (auto-created)
│   ├── portfolio.db           # Main database (includes engine_* tables)
│   └── nft_images.db          # NFT image cache
├── docs/                      # Documentation
│   ├── ARCHITECTURE.md        # System architecture
│   ├── API_PROVIDERS.md       # API provider details
│   ├── DOCKER_DEPLOYMENT.md   # Docker setup guide
│   ├── BACKUP_RESTORE_GUIDE.md # Backup documentation
│   └── docs/Exchange-Integration.md  # Exchange setup guide
├── .env                       # API keys (you create this)
├── .env.example               # Example configuration
├── requirements.txt           # Python dependencies
├── deploy.sh                  # Guided deployment script
├── run.sh                     # Start server (local)
├── stop.sh                    # Stop server (local)
├── CHANGELOG.md               # Version history
└── README.md                  # This file
```

## 📡 API Endpoints

### Authentication
- `POST /auth/login` - Login with credentials
- `POST /auth/logout` - End session
- `POST /auth/change-password` - Change password

### Wallets
- `GET /wallets` - List all tracked wallets
- `POST /wallets` - Add a new wallet
- `DELETE /wallets/{id}` - Remove a wallet
- `POST /wallets/{id}/refresh` - Refresh wallet data

### Portfolio
- `GET /portfolio/summary` - Get portfolio overview
- `GET /portfolio/history?range=7d|4w|3m` - Historical values
- `GET /portfolio/unified-chart` - Unified chart from wallet_daily_balances (V2)
- `POST /portfolio/rebuild-history` - Clear and regenerate all portfolio history (V2)
- `GET /portfolio/health/v2` - V2 data architecture health check

### Dashboard
- `GET /dashboard/data` - Aggregated dashboard data

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

### Transactions
- `GET /transactions` - Transaction history with filtering
- `GET /transactions/analytics` - Transaction analytics data

### Balance History
- `GET /balance-history/data` - Balance history chart data
- `POST /balance-history/clear-cache` - Clear history cache

### NFT Background Scheduler
- `GET /nft-scheduler/status` - Scheduler status and statistics
- `POST /nft-scheduler/enable` - Enable background updates
- `POST /nft-scheduler/disable` - Disable background updates
- `POST /nft-scheduler/trigger` - Manually trigger update cycle

### Custom Tokens
- `GET /custom-tokens` - List custom tokens
- `POST /custom-tokens` - Add a custom token
- `DELETE /custom-tokens/{id}` - Remove a custom token

### Spam Filtering
- `GET /spam/filters` - List spam filters
- `POST /spam/filters` - Add spam filter

### Cache Management
- `GET /cache/stats` - Cache statistics
- `POST /cache/clear` - Clear cached data

### Backup & Restore
- `GET /backup/info` - Backup information and statistics
- `POST /backup/export` - Export configuration to JSON
- `POST /backup/preview` - Preview backup file (dry-run)
- `POST /backup/import` - Import configuration from backup
- `GET /backup/export-env` - Export API keys as .env file
- `POST /backup/import-env` - Import API keys from .env file

### System
- `GET /system/info` - System information and health
- `GET /system/logs` - View system logs

### V2 Ingestion Engine (v1.5.0+)
- `POST /engine/backfill` - Start a new backfill job
- `GET /engine/backfill/{id}/status` - Backfill progress and status
- `POST /engine/backfill/{id}/cancel` - Cancel a running backfill
- `GET /engine/backfills` - List all backfills
- `GET /engine/gaps` - Diagnose data gaps
- `GET /engine/snapshot` - Portfolio snapshot from canonical events
- `GET /engine/history/data` - Balance history (backward-compatible format)
- `GET /engine/providers` - List registered providers
- `GET /engine/providers/health` - Provider health and circuit breaker states
- `GET /engine/events` - Query canonical events
- `GET /engine/events/count` - Event counts by chain/type

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

### Exchange Integration

ABCT supports 7 major cryptocurrency exchanges. For detailed setup instructions, see [Exchange Integration Guide](docs/docs/Exchange-Integration.md).

**Supported Exchanges:**
- **Coinbase** (CDP API) - Place `cdp_api_key.json` file in project root
- **Binance.com** - Add `BINANCE_API_KEY` and `BINANCE_API_SECRET` to .env
- **Binance.US** - Add `BINANCE_US_API_KEY` and `BINANCE_US_API_SECRET` to .env
- **OKX** - Add `OKX_API_KEY`, `OKX_API_SECRET`, `OKX_API_PASSPHRASE` to .env
- **Bitget** - Add `BITGET_API_KEY`, `BITGET_API_SECRET`, `BITGET_API_PASSPHRASE` to .env
- **Gate.io** - Add `GATE_API_KEY` and `GATE_API_SECRET` to .env
- **KuCoin** - Add `KUCOIN_API_KEY`, `KUCOIN_API_SECRET`, `KUCOIN_API_PASSPHRASE` to .env

**Security Note:** Always create API keys with **read-only** permissions. Never grant withdrawal or trading permissions.

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
- **Optional Authentication**: Session-based auth with login page
- **HTTPS Support**: SSL/TLS encryption with self-signed or custom certificates
- **Cloudflare Tunnel**: Built-in secure remote access (auto-restores across container rebuilds)
- **Encrypted API Keys**: API keys encrypted at rest in database
- **Secure Logging**: Audit trails with sensitive data redaction
- **Input Validation**: Protection against malformed inputs and XSS
- **Rate Limiting**: API endpoint protection against abuse
- **CORS Hardening**: Restricted cross-origin access
- **DOMPurify**: Client-side XSS protection on all HTML rendering

**Note:** This application is designed for **self-hosted, localhost-only** use. The optional authentication feature allows running without credentials on trusted local installations, or with Basic Auth if you expose it on your network.

For detailed security information, see [SECURITY.md](SECURITY.md)

## 📖 Documentation

- **[Docker Deployment Guide](docs/DOCKER_DEPLOYMENT.md)** - Complete multi-platform Docker setup
- **[Exchange Integration Guide](docs/docs/Exchange-Integration.md)** - Setup for 7 supported exchanges (v1.0.0+)
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

#### Algorand Network
- [Pera Wallet](https://developer.perawallet.app/) - Algorand blockchain API (primary)
- [Tatum](https://tatum.io/) - Algorand blockchain data (fallback)

#### Pricing & Market Data
- [CoinGecko](https://www.coingecko.com/) - Cryptocurrency price aggregation and market data
- [CoinMarketCap](https://coinmarketcap.com/) - Alternative cryptocurrency price data
- [Coinbase](https://www.coinbase.com/) - Spot price data (public API)
- [DefiLlama](https://defillama.com/) - Universal price fallback for all chains

#### Visual Assets & Branding
- [LogoKit](https://logokit.com/) - Blockchain and cryptocurrency logos
- [Logostream](https://logostream.io/) - Token logo API for multi-chain assets

#### Exchange Integration
- [Coinbase CDP](https://www.coinbase.com/cloud) - Exchange API for portfolio balances (JWT authentication)
- [Binance](https://www.binance.com/) - Global cryptocurrency exchange API
- [Binance.US](https://www.binance.us/) - US-based exchange API
- [OKX](https://www.okx.com/) - Multi-asset exchange API
- [Bitget](https://www.bitget.com/) - Derivatives and spot trading exchange API
- [Gate.io](https://www.gate.io/) - Comprehensive exchange API
- [KuCoin](https://www.kucoin.com/) - Global cryptocurrency exchange API

### Privacy & Blockchain Innovation
- [Midnight Network](https://midnight.network/) - Privacy-focused Cardano partner chain (NIGHT token support)

### Blockchain Logos
- [Logostream](https://logostream.dev) Crypto Logos provided by Logostream

For detailed API information including rate limits and pricing, see [API Providers Guide](docs/API_PROVIDERS.md).

## 🔗 Links

- **Repository**: https://github.com/Tarrant64/abct
- **Releases**: https://github.com/Tarrant64/abct/releases
- **Issues**: https://github.com/Tarrant64/abct/issues
- **Latest Release**: [v1.9.0 - V2 Architecture & Dashboard Overhaul](https://github.com/Tarrant64/abct/releases/tag/v1.9.0)

---

**Current Version:** v1.9.0 (BUILD 1771009377)
**Last Updated:** February 13, 2026
