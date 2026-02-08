# A Better Crypto Tracker (ABCT)

Personal multi-chain portfolio tracker built Cardano-first.

![Version](https://img.shields.io/badge/version-1.5.0-brightgreen.svg)
![Build](https://img.shields.io/badge/build-1770563676-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-green.svg)
![FastAPI](https://img.shields.io/badge/fastapi-0.109-teal.svg)
![Security](https://img.shields.io/badge/security-hardened-green.svg)
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

**Other Chains**:
Bitcoin, Ethereum, Solana, Polygon, Base

**Tools**:
Privacy-focused (self-hosted), transaction analytics, custom tokens, portfolio snapshots

## Project
Personal side project built with AI assistance. Goal: Create a robust tracker that doesn't compromise on Cardano while supporting major chains. Community contributions welcome.

**Current Build**: v1.5.0 (BUILD 1770563676)

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

## 🏗️ Architecture

For a detailed overview of the system architecture, authentication flow, and database structure, see [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## ✨ Features

### Portfolio Tracking
- **Multi-Blockchain Support**: Track wallets on Cardano, Bitcoin, Ethereum, Solana, Polygon, Base, and Algorand (7 chains)
- **Multi-Exchange Integration**: Connect to 7 major exchanges (Coinbase, Binance, Binance.US, OKX, Bitget, Gate.io, KuCoin)
- **DeFi Monitoring**: View Cardano staking positions with APY and rewards
- **NFT Collection**: Browse your NFTs with floor price valuations
- **Transaction History**: Complete transaction tracking across all blockchains with analytics
- **Portfolio History**: Interactive charts showing value over time (7d, 4w, 3m)
- **Privacy Mode**: Hide sensitive financial data with one click

### Infrastructure
- **Self-Hosted**: Your data stays on your machine
- **Docker Ready**: Single container deployment
- **Optional HTTPS**: SSL/TLS encryption support
- **Secure Logging**: Audit trails with sensitive data redaction

## 📦 What's New

### v1.5.0 - V2 Ingestion Engine (February 2026)
- **V2 Ingestion Engine**: Complete rebuild of the data pipeline architecture
  - 6-stage pipeline: Expand → Index → Hydrate → Normalize → Enrich → Positions
  - Provider-agnostic work units — if one API rate-limits, work reassigns to another
  - 14 registered data providers across all chains
  - Circuit breaker pattern with automatic recovery (CLOSED → OPEN → HALF_OPEN)
  - Token bucket rate limiting per provider
  - Bulkhead concurrency control via asyncio.Semaphore
  - Idempotent event dedup (safe to re-run backfills)
- **Multi-Chain Coverage**: Full pipeline support for Cardano, Bitcoin, Ethereum, Solana, Polygon, Base
  - Chain-specific expanders, indexers, hydrators, and normalizers
  - CoinStats integration for non-Cardano chains (Bitcoin, Ethereum, Solana, Polygon, Base)
  - CoinStats Cardano exclusion enforced at registry, indexer, and hydrator levels
- **Provider Registry**: Priority-based scoring with health/quota/latency factors
  - Automatic failover when providers go down
  - Per-provider health tracking persisted to database
  - Circuit breakers with 5-failure threshold and 5-minute recovery
- **Backfill Orchestration**: Plan, execute, and monitor backfills via API
  - `POST /engine/backfill` — start a new backfill job
  - `GET /engine/backfill/{id}/status` — real-time progress
  - Background execution with domain pipeline ordering
- **8 New Database Tables**: `engine_backfills`, `engine_account_subjects`, `engine_tx_index`, `engine_tx_raw`, `engine_events`, `engine_work_units`, `engine_provider_health`, `engine_price_history`
- **11 New API Endpoints**: Backfill management, provider health, event queries, portfolio snapshots
- **Balance History Improvements**: Anchor to current on-chain balance, nginx proxy passthrough
- **Performance**: Fixed 7s page load delay from NFT image config, improved Assets UX

### v1.0.1 - UI, Themes, & Multi-Chain Expansion (February 2026) ✨
- **🔑 .env Import/Export Fix**: Complete API key migration workflow
  - Fixed .env export crash (missing `Path` import)
  - New .env import: upload a `.env` file to import API keys directly into the database
  - Supports all 17 API services including exchange key+secret+passphrase grouping
  - File upload UI with drag-and-drop on the Backup & Restore page
- **📈 Portfolio History Improvements**: Better snapshot frequency and backfill
  - Snapshot interval reduced from 4 hours to 2 hours for more granular history
  - Auto-generate 30 days of historical data for new users on startup
  - "Generate 30-Day History" button on dashboard when no data exists
  - Added Solana (SOL) to historical price tracking
- **🔗 Algorand Support**: Full blockchain integration for Algorand network
  - Pera Wallet API integration (primary source)
  - Tatum API fallback support
  - Native ALGO tracking and ASA (Algorand Standard Assets)
  - ARC-3 and ARC-69 NFT support
  - Transaction history integration
- **📊 Transaction History System**: Complete multi-chain transaction tracking
  - Unified transaction view across all 7 blockchains
  - Transaction analytics with visual charts
  - 1,500+ demo transactions for testing
  - Chain filtering and search capabilities
- **🖼️ Enhanced Demo Mode**: Massive expansion of sample data
  - 91 tokens across all blockchains
  - 76 NFTs across 7 collections
  - 1,500 transactions over 1 year of history
  - More realistic portfolio simulation
- **🎨 Complete Theme Redesign**: Reimagined theme system with enhanced visual polish
  - Renamed "Default" theme to "Dark Mode" for clarity
  - **New Light Theme**: Clean, modern white theme with refined UI elements
  - Removed "Green Terminal" theme
  - 5 professionally designed themes: Dark Mode, Light, Cypherpunk 1, Ocean Depths, Sunset Horizon
- **💎 Light Theme Polish**: Comprehensive styling for modern aesthetics
  - Rounded corners throughout (10-24px range for visual hierarchy)
  - Layered shadow effects for depth and elevation
  - Proper contrast and readability
  - White backgrounds with subtle gray accents (#e5e7eb borders)
  - Professional button and input styling
- **✨ Dark Mode Enhancements**: Improved visibility and polish
  - Glowing green borders on headers and sections (rgba(0, 210, 106, 0.4))
  - Enhanced shadow effects for better depth perception
  - Improved contrast for better readability
  - Consistent rounded corners matching light theme
- **🎯 UI Refinements**: Better spacing and visual hierarchy
  - Header and section headers now use rounded, padded containers
  - Improved text indentation (16-24px padding)
  - Portfolio card with enhanced shadows and borders
  - Chart containers with proper background styling per theme
  - Consistent waffle menu integration across all pages
- **🎭 Theme Selector Relocation**: Moved from header to waffle menu dropdown
  - More intuitive navigation structure
  - Cleaner header design
  - Theme selection with all navigation in one place
- **🔧 Cache Busting**: Build version system for immediate CSS/JS updates
  - Version 1770166262
  - No more browser cache issues after updates

### v1.0.0 - Production Ready Release (January 2026) 🎉
- **🌐 Seven Exchange Integrations**: Full API support for Binance, OKX, KuCoin, Bitget, Gate.io + existing Coinbase
  - Automatic portfolio aggregation across all exchanges
  - Read-only API keys for maximum security
  - 5-minute smart caching to respect rate limits
  - Individual exchange status monitoring
  - Easy environment variable configuration
- **🎨 Visual Enhancements**: LogoKit integration for blockchain and token logos
  - Blockchain logos on all summary cards
  - Token logos in wallet and exchange asset lists
  - Exchange-specific branding throughout UI
  - Improved pie chart colors for cypherpunk theme
- **🗂️ Manage Wallets Interface**: Redesigned asset management
  - Three-tab interface: Self-Custody | Exchanges | Manual Tokens
  - Exchange configuration status dashboard
  - Setup guide with direct links to API management
  - Better organization of different asset types
- **📚 Comprehensive Documentation**: Complete exchange integration guide
  - Step-by-step setup for each exchange
  - Security best practices and troubleshooting
  - API rate limit documentation

### v0.13.1 - Complete Portfolio History
- **📈 Complete Portfolio History**: 90-day historical snapshots with all components
  - Backfill script generates realistic historical price variations
  - Includes native coins, tracked tokens, NFTs, and exchange balances
  - Daily snapshots with auto-refresh every 4 hours
  - Chart now shows complete portfolio value (not just native coins)
  - All components properly tracked: wallets + tokens + NFTs + exchanges

### v0.13.0 - Asset Breakdown & Token Pricing 🎉
- **📊 Blockchain Asset Breakdown**: Interactive drill-down charts
  - Click any blockchain card to see asset composition
  - Doughnut charts showing native coin + tokens + NFTs
  - Sortable legend with percentages and USD values
  - Works across all 6 supported blockchains
- **🔗 The Graph API Integration**: Ethereum-based token pricing
  - Uniswap V2/V3 subgraph integration for accurate pricing
  - ETH-denominated prices for Ethereum, Polygon, Base tokens
  - 100K queries/day with automatic usage tracking
  - 5-minute price caching for performance
- **🌐 Multi-Chain Native Pricing**: Universal token pricing system
  - Cardano: ADA-denominated via TapTools
  - Ethereum/Base/Polygon: ETH-denominated via The Graph
  - Solana: SOL-equivalent calculated from USD
  - Automatic USD conversion with native token display
- **🖼️ Enhanced NFT Wall**: Major performance improvements
  - Fixed NFT collection expansion (DOMPurify compatibility)
  - Prominent gradient cache button with live status
  - Real-time background scheduler indicator
  - Batch progress showing: cached/failed/skipped counts
  - "Remaining" stat showing uncached images
  - Auto-disables when all images cached
- **🐛 Bug Fixes**:
  - Fixed NFT expansion on dashboard (event delegation)
  - Improved cache progress visibility and clarity
  - Better batch caching status messages
  - Enhanced background work visibility

### v0.12.0 - Multi-User & Enhanced Visualization
- **👥 Multi-User Support**: Full multi-user architecture with user isolation
  - Separate portfolios for different users
  - Session-based authentication with secure tokens
  - Per-user wallet, NFT, and DeFi data isolation
  - Password change functionality built-in
- **🎨 Demo Mode**: Try ABCT without connecting wallets
  - Pre-loaded with extensive realistic demo data
  - 91 tokens across all 7 supported blockchains
  - 76 NFTs across 7 collections (Cardano, Ethereum, Solana, Polygon, Base, Algorand)
  - 1,500 transactions spanning 1 year of history
  - Demo DeFi positions and exchange balances
  - Multi-chain NFT wall with blockchain filtering
  - Login with username: `demo` / password: `demo`
- **🖼️ Multi-Chain NFT Wall**: Enhanced NFT visualization
  - Support for Cardano, Ethereum, Solana NFTs
  - Filter by blockchain with live chain tabs
  - Colorful SVG placeholders for demo mode
  - Privacy mode to blur sensitive data
- **🐛 Bug Fixes**:
  - Fixed Cardano stake key collapse/expand functionality
  - Fixed demo NFT wall authentication
  - Improved multi-user database schema
  - Enhanced session token handling

### v0.10.0 - Backup & Restore Release
- **🔄 Complete Backup System**: Export/import all your configuration data
  - Migration ready for moving to new servers
  - Selective export options
  - Import modes: Merge (safe) or Replace (full restore)
  - Security warnings for sensitive data in backups
- **⏰ NFT Background Scheduler**: Automatic 24/7 NFT floor price updates
  - Smart rate limiting (95 calls/day)
  - State persistence and priority queue

### v0.9.0 - NFT Scheduler Integration
- **Single Container**: NFT price service integrated into main app
- **Background Updates**: Automatic 24/7 NFT floor price collection
- **Smart Rate Limiting**: Respects TapTools 95 calls/day limit
- **State Persistence**: Resumes exactly where it left off after restart
- **UI Controls**: Enable/disable from Services page

See [CHANGELOG.md](CHANGELOG.md) for complete version history.

## 🔐 Default Login Credentials

ABCT includes a login page to protect your portfolio data. Use these credentials on first access:

- **Admin Account**:
  - Username: `admin`
  - Password: `satoshi`
  - Full access to add wallets and configure settings

- **Demo Account** (New in v0.12.0):
  - Username: `demo`
  - Password: `demo`
  - Pre-loaded with extensive sample data:
    - 91 tokens across all 7 blockchains
    - 76 NFTs across 7 collections
    - 1,500 transactions over 1 year
    - DeFi positions and exchange balances
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
- 
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
│   ├── engine/                # V2 Ingestion Engine (v1.5.0+)
│   │   ├── models.py          # Pydantic models (ChainId, WorkUnit, CanonicalEvent)
│   │   ├── db.py              # 8 engine_* tables with CRUD
│   │   ├── orchestrator.py    # Backfill orchestration & pipeline coordination
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
│   │   ├── snapshot.py        # Portfolio snapshots
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
│   └── update-unraid.sh       # Deployment script
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
- `POST /portfolio/snapshot` - Create manual snapshot

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
- **Optional Authentication**: HTTP Basic Auth for network-exposed deployments (v0.10.0+)
- **HTTPS Support**: SSL/TLS encryption with self-signed or custom certificates (v0.8.0+)
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
- **Latest Release**: [v1.5.0 - V2 Ingestion Engine](https://github.com/Tarrant64/abct/releases/tag/v1.5.0)

---

**Current Version:** v1.5.0 (BUILD 1770563676)
**Last Updated:** February 8, 2026
**Release Date:** February 8, 2026
