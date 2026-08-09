# A Better Crypto Tracker (ABCT)

Personal multi-chain portfolio tracker built Cardano-first.

![Version](https://img.shields.io/badge/version-1.16.3-brightgreen.svg)
![Build](https://img.shields.io/badge/build-1786304190-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-green.svg)
![FastAPI](https://img.shields.io/badge/fastapi-0.133-teal.svg)
![Chains](https://img.shields.io/badge/chains-53-brightgreen.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![Exchanges](https://img.shields.io/badge/exchanges-42-purple.svg)
![DeFi](https://img.shields.io/badge/defi_protocols-80%2B-orange.svg)
![Themes](https://img.shields.io/badge/themes-8-purple.svg)

**Website**: [abettercryptotracker.com](https://abettercryptotracker.com)

## Why

Existing multi-chain wallets treat Cardano as an afterthought — basic balance tracking with no stake pool info, broken native assets, and zero governance integration. This project flips that: deep Cardano ecosystem support first, then proper multi-chain coverage.

## Features

### 53 Blockchains

**Cardano** (Primary) — Stake pool tracking, rewards, governance, native assets with metadata, DeFi protocol integration (Minswap, SundaeSwap, Liqwid, Indigo, etc.), NFT collections with floor prices, stake key wallet grouping.

**API-Key Chains** — Ethereum, Solana, Polygon, Base, Algorand, Arbitrum, Avalanche, BNB Chain (via Etherscan/Alchemy/Helius APIs)

**EVM Chains** — Optimism, zkSync Era, Linea, Scroll, Fantom, Cronos, Gnosis, Moonbeam (all via generic EVM service)

**Generic EVM Support** — Any EVM-compatible chain can be tracked. The `evm_chain.py` service is config-driven: add a new entry with the chain's RPC URL, chain ID, and explorer base URL and it works without additional code.

**Cosmos IBC Chains** (v1.14.0) — Osmosis, Celestia, Injective, dYdX, Sei, Akash (shared LCD pattern via `cosmos_chain.py`)

**Substrate Chains** (v1.14.0) — Polkadot, Kusama (via Subscan REST API, optional key)

**Major L1 Additions** (v1.14.0) — TON (TON Center API), Stellar (Horizon API), Kaspa

**Additional Chains** (v1.14.0) — Kaia (formerly Klaytn), Ergo, IOTA, Waves, Mina, Zilliqa

**Privacy Chains** (v1.15.0) — Monero (manual balance only, ring signatures prevent API fetch), Secret Network (SecretSaturn LCD API)

**Free Chains** (no API key required) — Bitcoin, Tron, XRP, Hedera, MultiversX, Sui, Aptos, Filecoin, Litecoin, Dogecoin, Zcash, Tezos, Stacks, VeChain, Cosmos (ATOM), NEAR, ICP, Secret Network, and all Cosmos IBC chains above

### 42 Exchange Integrations
Read-only API integration across 42 exchanges using 5 auth method families:
- **Original**: Coinbase, Binance, Binance.US, OKX, Bitget, Gate.io, KuCoin
- **New**: Bybit, MEXC, Kraken, Gemini, Bitfinex, HTX, BingX, Phemex, WOO X, AscendEX, Poloniex, Crypto.com, Bitstamp, Bitmart, and 21 more

### 80+ DeFi Protocol Detection
Protocol adapters detect positions automatically — no manual tracking needed:
- **Cardano** (13): Minswap, SundaeSwap V3, WingRiders, Splash, Djed, FluidTokens, Lenfi, MuesliSwap, Liqwid, Indigo, Strike Finance, Surf Protocol, Iagon
- **EVM** (55+): Aave v3, Compound v3, Uniswap v3 LP, Curve, Balancer, EigenLayer, Maker/Spark, Morpho, GMX, Pendle, Stargate, Aerodrome, Velodrome, Radiant, Benqi, SushiSwap, Yearn v3, Beefy, Synthetix, Liquity, Camelot, Abracadabra, PancakeSwap v3, and more
- **Solana** (15): Marinade, Jito, Orca, Raydium, Drift, MarginFi, Kamino, Jupiter Perps, Blazestake, and more

### Portfolio & Analytics
- **Dashboard**: Dynamic blockchain cards, allocation donut chart, market heatmap, global market cap widget, unified All Assets table with zero-balance toggle
- **P&L Analytics**: Cost basis tracking with FIFO/LIFO/Average methods — per-asset and portfolio-wide realized and unrealized P&L, dedicated P&L tab on Assets page with self-custody wallet transaction ingestion
- **Per-Wallet History**: Daily balance tracking per wallet/exchange/staking position with unified chart
- **Transaction Analytics**: Multi-chain transaction history with full paginated fetching, filtering, analytics, and portfolio vs. BTC relative strength
- **Security / Privacy**: Token approval monitoring, address poisoning scanner, Cardano Shield threat feed, spam token detection, Railgun contract detection, Zcash shielded pool stats, per-wallet privacy scoring, Monero and Secret Network support
- **DePIN Tracking**: Iagon (Cardano) and Helium (Solana) infrastructure protocol monitoring
- **DeFi Monitoring**: Auto-detected staking positions with APY and rewards across 80+ protocols
- **NFT Collection**: Browse NFTs with floor price valuations across Cardano, Ethereum, and Solana, mobile-optimized scroll pagination
- **Global Search**: Search across wallets, DeFi positions, staking, governance, and exchange results
- **Per-Asset Charts**: Detailed token modal with per-asset price charting and enriched metadata

### Infrastructure
- **Self-Hosted**: Your data stays on your machine — no telemetry, no external analytics
- **Docker Ready**: Single container deployment with multi-arch builds (amd64/arm64)
- **CI/CD**: Automated Docker Hub publishing and Docker Scout vulnerability scanning via GitHub Actions
- **V2 Data Architecture**: Per-source daily balances, materializer pipeline, off-chain collector with engine backfill UI
- **Blockfrost RYO**: Optional self-hosted Blockfrost node integration with automatic external fallback
- **DB Sync Direct Access**: Optional PostgreSQL connection to Cardano DB Sync via `pg_cardano`
- **Multi-Provider EVM**: Alchemy + Ankr EVM indexers for multi-provider fallback on Ethereum data
- **Stale-While-Revalidate UX**: Cached dashboard data displayed instantly, refreshed in background to eliminate load flicker
- **Chart Designer**: Customizable portfolio chart styling in Settings
- **Wallet Auto-Detect**: Automatic blockchain detection when adding wallet addresses
- **8 Themes**: Dark Mode, Light, Cypherpunk, Ocean Depths, Sunset Horizon, Cypher, Cypher 2, Cypher 3
- **V2 Frontend**: Professional parallel dashboard at `/next/` with collapsible sidebar navigation, portfolio hero with interactive chart, sortable assets table, and dedicated pages for all features
- **Privacy Mode**: Hide sensitive financial data and URLs with one click
- **Cloudflare Tunnel**: Built-in secure remote access (auto-restores across container rebuilds)
- **Encrypted API Keys**: All keys encrypted at rest in the database

## Mobile App

A native mobile client lives in [`mobile/`](mobile/) — a Flutter app for **iOS** with an **Apple Watch** companion (watch face complications for token prices and portfolio total). It connects to your self-hosted ABCT backend through Cloudflare Tunnel + Access with TLS certificate pinning and encrypted-at-rest connection profiles. **Android** support is planned from the same codebase.

See [`mobile/README.md`](mobile/README.md) for setup, code-signing configuration, and build instructions.

## Important: Intended Use

**ABCT is designed for personal, self-hosted use on trusted local networks.**

This is a hobby project for tracking your personal cryptocurrency portfolio. It is:

- **Perfect for:** Home networks, personal NAS devices, local development
- **Designed for:** Single-user or family use on trusted networks
- **NOT designed for:** Public internet hosting or multi-tenant use
- **NOT recommended:** Exposing directly to the internet without VPN

**Note:** This project will have periodic bugs as I'm working through connecting to blockchain infrastructures via API, learning what works and what doesn't.

### Remote Access
- Use built-in Cloudflare Tunnel (configured in Settings — auto-restores across updates)
- Use a VPN (Tailscale, WireGuard, etc.)
- Use a reverse proxy with authentication (nginx + Basic Auth)
- Don't expose port directly to internet

For more details, see [SECURITY.md](SECURITY.md).

## Default Login Credentials

- **Admin**: `admin` / `satoshi` — Full access to add wallets and configure settings
- **Demo**: `demo` / `demo` — Pre-loaded with ~$1M multi-chain portfolio (91 tokens, 76 NFTs, 1,500 transactions)

**Change the default admin password after first login!** See [Password Reset Guide](docs/guides/PASSWORD_RESET_GUIDE.md).

## Quick Start

ABCT works on any Docker-capable system including Linux servers, NAS devices (TrueNAS, Synology, Unraid), and desktop environments.

### Docker (Recommended)

```bash
git clone https://github.com/Tarrant64/abct.git
cd abct
cp .env.example .env
nano .env  # Add your API keys

cd abct-docker
docker-compose up -d
# Access at http://localhost:8080
```

For platform-specific instructions (TrueNAS, Synology, Portainer, etc.), see [Docker Deployment Guide](docs/DOCKER_DEPLOYMENT.md).

> **Unraid users:** Use `abct-docker/deploy_from_git.sh` to pull from GitHub and rebuild (recommended).

### Local Development

```bash
git clone https://github.com/Tarrant64/abct.git
cd abct
cp .env.example .env
nano .env  # Add your Blockfrost API key at minimum
./run.sh
# Open http://127.0.0.1:8000
```

## Configuration

### Essential Environment Variables (.env)

```bash
# REQUIRED: Cardano
BLOCKFROST_API_KEY=mainnetXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# RECOMMENDED: Enhanced Cardano features
CEXPLORER_API_KEY=your_key_here      # Staking positions and rewards

# OPTIONAL: Additional blockchains
BLOCKSCOUT_API_KEY=proapi_your_key   # Free Etherscan-compatible EVM transaction API
ETHERSCAN_API_KEY=your_key_here      # EVM transaction API fallback
ALCHEMY_API_KEY=your_key_here        # Ethereum/Polygon/Base NFTs
HELIUS_API_KEY=your_key_here         # Solana

# OPTIONAL: Self-hosted Cardano infrastructure
BLOCKFROST_RYO_URL=http://your-node:3000  # Self-hosted Blockfrost (auto-fallback to hosted)
PG_CARDANO_DSN=postgresql://...           # Direct DB Sync access

# OPTIONAL: Authentication
ABCT_REQUIRE_AUTH=false              # Set to false for localhost-only
```

Exchange API keys can be configured in the Settings page or via `.env` — see [Exchange Integration Guide](docs/Exchange-Integration.md) for setup instructions. All 42 exchanges use read-only API keys.

All API keys should be **read-only**. Never grant withdrawal or trading permissions.

## Security

- **Read-Only Access**: Cannot move funds, only view balances
- **Local Database**: All data stored in local SQLite files
- **Encrypted API Keys**: API keys encrypted at rest
- **Optional Authentication**: Session-based auth with login page, authenticated pricing endpoints
- **HTTPS Support**: SSL/TLS with self-signed or custom certificates
- **DOMPurify + setSafeHTML**: Client-side XSS protection on all HTML rendering including cached data
- **Sanitized API Responses**: Error messages scrubbed of internal details
- **Token Approval Monitoring**: Track and review EVM token approvals
- **Address Poisoning Detection**: Scanner for address poisoning attack patterns
- **Cardano Shield**: Threat feed integration with CF Token Registry scanner
- **Spam Token Detection**: Inline detection and filtering of spam/scam tokens
- **Rate Limiting**: API endpoint protection against abuse
- **Secure Logging**: Audit trails with sensitive data redaction

See [SECURITY.md](SECURITY.md) for full details.

## What's New

### V2 Frontend — Professional Dashboard Redesign (March 2026)
- **Parallel V2 UI**: Accessible at `/next/` — V1 remains fully intact at existing URLs
- **Sidebar Navigation**: Collapsible left sidebar with icon + text labels across 3 sections (Portfolio, Analytics, System)
- **Dashboard**: Portfolio hero with total value, 24h change, interactive Chart.js history chart with range selector (1W/1M/3M/6M/1Y/ALL), 6 stat cards, sortable assets table with sparklines
- **12 Dedicated Pages**: Dashboard, Assets (tabbed: Wallets/Exchanges/DeFi/Custom Tokens/P&L), NFTs (grid gallery with chain filters), DeFi & Staking, Exchanges, Analytics, Transactions, P&L, Security, Wallets, Settings (8 tabs), Help & Guide
- **8 Theme Support**: All themes work across V2 — Dark Mode (default), Light, Cypherpunk, Ocean Depths, Sunset Horizon, Cypher, Cypher 2, Cypher 3
- **Same Backend**: Zero backend changes — V2 consumes the same API endpoints as V1
- **Professional Polish**: Loading skeletons, smooth transitions, privacy mode toggle, toast notifications, responsive design, DOMPurify XSS protection

### v1.15.x — 53 Chains, Security/Privacy, P&L Engine, Infrastructure (Feb–Mar 2026)
- **Security / Privacy Tab**: Renamed and expanded from Privacy & ZK — now includes token approval monitoring, address poisoning scanner, Cardano Shield threat feed with CF Token Registry scanner, inline spam token detection, plus original privacy analysis and Zcash shielded pool stats
- **P&L Engine Overhaul**: Self-custody wallet transaction ingestion, async background computation, progress tracking, SQLite optimization, and dedicated P&L tab on the Assets page
- **Portfolio Data Pipeline Refactor**: Separated quantities from prices for more accurate portfolio valuation
- **Blockfrost RYO Integration**: Self-hosted Blockfrost node support with conditional rate limits and automatic external fallback
- **DB Sync Direct Access**: Optional `pg_cardano` PostgreSQL connection for direct Cardano DB Sync queries
- **Engine Backfill UI**: New backfill controls in Settings > Data Collectors with force-full option
- **Stale-While-Revalidate UX**: Cached dashboard/sidebar data displayed instantly, background refresh eliminates page load flicker
- **Chart Designer**: Full-width preview with 3-column controls grid, added to Settings
- **Wallet Auto-Detect**: Automatic blockchain detection when adding new wallet addresses
- **Global Search**: Search across wallets, DeFi, staking, governance, and exchange results with standardized header
- **All Assets Table**: Unified view of all holdings on dashboard with zero-balance/dust token toggles
- **Per-Asset Charting**: Enriched token detail modal with per-asset price charts
- **Multi-Provider EVM Fallback**: Alchemy + Ankr indexers added alongside Etherscan (migrated from deprecated V1 to V2 API)
- **CoinGecko Resilience**: Multi-source pricing redundancy with CoinPaprika fallback
- **Mobile API Improvements**: Wallet breakdown endpoint, refresh params, sparkline data, image URLs for watchOS, proper staking/NFT/exchange totals
- **Full Transaction History**: Paginated fetchers for complete historical transaction data across chains
- **Privacy Chains**: Monero (XMR, manual balance) and Secret Network (SCRT, SecretSaturn LCD API)
- **CoinPaprika Pricing**: Free pricing fallback (25k calls/month, no API key) between Coinbase and DefiLlama
- **Token Caching**: Local image cache (eliminates CoinGecko CDN dependency) and SQLite metadata cache for supply, rank, ATH/ATL
- **Security Hardening**: Sanitized error messages in API responses, innerHTML sanitization with setSafeHTML, authenticated `/prices/*` endpoints

### v1.14.0 — 51 Chains, Cosmos IBC, 80+ DeFi Protocols (February 2026)
- **Chain Depth Expansion**: 34 → 51 chains across 5 new categories
- **Cosmos IBC Support**: Osmosis, Celestia, Injective, dYdX, Sei, Akash — all via shared `cosmos_chain.py` LCD pattern
- **Substrate Chains**: Polkadot and Kusama via Subscan REST API (optional API key for higher rate limits)
- **Major L1 Additions**: TON (TON Center API), Stellar (Horizon API), Kaspa
- **Additional Chains**: Kaia (formerly Klaytn), Ergo, IOTA, Waves, Mina, Zilliqa
- **EVM Chain Fixes**: 8 previously wired-but-broken EVM chains now fully working (Optimism, zkSync Era, Linea, Scroll, Fantom, Cronos, Gnosis, Moonbeam)
- **Generic EVM Framework**: `evm_chain.py` is now fully config-driven; any EVM-compatible chain works without new code
- **Cardano DeFi Expansion**: 5 → 13 protocols (added Minswap, SundaeSwap V3, WingRiders, Splash, Djed, FluidTokens, Lenfi, MuesliSwap)
- **EVM DeFi Expansion**: ~30 → 55+ protocols (Pendle, Stargate, Aerodrome, Velodrome, Radiant, Benqi, SushiSwap, Yearn v3, Beefy, Synthetix, Liquity, Camelot, Abracadabra, PancakeSwap v3, and more)

### v1.13.0 — 42 Exchanges, 34 Chains, 100+ DeFi Protocols & P&L (February 2026)
- **Exchange Expansion**: 35 new exchange integrations (42 total) — Bybit, MEXC, Kraken, Gemini, Bitfinex, HTX, BingX, Phemex, WOO X, AscendEX, Poloniex, Crypto.com, Bitstamp, Bitmart, and 21 more
- **Exchange Architecture**: `BaseExchangeService` with 5 auth method mixins; Exchange Registry auto-wires new exchanges into `/exchanges/status`, `/exchanges/all`, and individual endpoints
- **EVM Chain Expansion**: 8 new EVM chains (Optimism, zkSync Era, Linea, Scroll, Fantom, Cronos, Gnosis, Moonbeam) — 34 total chains
- **DeFi Protocol Support**: 100+ DeFi protocols across Cardano (5), EVM (30+), and Solana (15) via `ProtocolAdapter` framework with auto-discovery
- **P&L Analytics**: Full cost basis tracking with FIFO/LIFO/Average methods; per-asset and portfolio-wide realized and unrealized P&L; dedicated P&L page
- **DeFi Router**: New `/defi/protocols` endpoints for position detection, protocol listing, and analytics

### v1.12.x — 26 Chains, DePIN, Analytics & CI/CD (February 2026)
- **15 New Blockchains** (11 → 26): XRP, Hedera, MultiversX, Sui, Aptos, Filecoin, Litecoin, Dogecoin, Zcash, Tezos, Stacks, VeChain, Cosmos, NEAR, ICP
- **DePIN Tracking**: Iagon (Cardano) staking and Helium (Solana) hotspot rewards
- **Transaction Analytics Overhaul**: Portfolio vs. BTC relative strength, top movers, CoinMarketCap fallback
- **CI/CD Pipeline**: Automated Docker Hub publishing with multi-arch builds, Docker Scout vulnerability scanning on PRs and weekly schedule
- **In-App Help & Guide**: Comprehensive self-serve documentation with chain setup guides, API key tiers, and FAQ

### v1.9.0 — V2 Architecture & Dashboard Overhaul (February 2026)
- **V2 Data Architecture**: Per-wallet daily balances, materializer pipeline, off-chain collector (2h interval)
- **Dashboard Redesign**: Dynamic blockchain cards, allocation donut chart, market heatmap, portfolio card with liquid/staked/NFT breakdown
- **4 New Blockchains** (7 → 11): Arbitrum, Avalanche, BNB Chain, Tron
- **Cloudflare Tunnel Persistence**: Token stored encrypted in DB; auto-restores on container rebuild

See [CHANGELOG.md](CHANGELOG.md) for complete version history.

## Documentation

- **[Architecture](docs/ARCHITECTURE.md)** — System design overview
- **[Docker Deployment](docs/DOCKER_DEPLOYMENT.md)** — Complete multi-platform Docker setup
- **[Exchange Integration](docs/Exchange-Integration.md)** — Setup for 42 supported exchanges
- **[Backup & Restore](docs/BACKUP_RESTORE_GUIDE.md)** — Configuration management
- **[Security Guide](SECURITY.md)** — Security best practices
- **[API Providers](docs/API_PROVIDERS.md)** — API provider details and rate limits
- **[Password Reset](docs/guides/PASSWORD_RESET_GUIDE.md)** — Reset admin credentials
- **In-App Help** — Built-in Help & Guide page with setup walkthroughs
- **V2 Frontend** — Access at `/next/` for the redesigned sidebar-navigation dashboard

### V2 Navigation Structure

| Section | Pages |
|---------|-------|
| **Portfolio** | Dashboard, Assets, NFTs, DeFi & Staking, Exchanges |
| **Analytics** | Analytics, Transactions, P&L, Security |
| **System** | Wallets, Settings, Help |

V2 files live under `frontend/v2/` with shared CSS (`css/v2.css`), core JS (`js/v2-app.js`), and sidebar shell (`js/v2-shell.js`). Backend serves V2 at `/next/` via `main.py` routes — no new API endpoints required.

## License

MIT License — see [LICENSE](LICENSE) file for details.

## Acknowledgments

Built with [FastAPI](https://fastapi.tiangolo.com/), [Chart.js](https://www.chartjs.org/), [SQLite](https://www.sqlite.org/), [HTTPX](https://www.python-httpx.org/), and [DOMPurify](https://github.com/cure53/DOMPurify).

### Blockchain Data Providers

**Cardano**: [Blockfrost](https://blockfrost.io/), [CExplorer](https://cexplorer.io/), [Koios](https://koios.rest/), [Charli3](https://charli3.io/)
**Ethereum & EVM**: [Alchemy](https://www.alchemy.com/), [Ankr](https://www.ankr.com/), [Etherscan](https://etherscan.io/), [Basescan](https://basescan.org/), [Polygonscan](https://polygonscan.com/)
**Solana**: [Helius](https://www.helius.dev/) · **Bitcoin**: [Blockstream](https://blockstream.info/) · **Algorand**: [Pera Wallet](https://developer.perawallet.app/), [Tatum](https://tatum.io/)
**TON**: [TON Center](https://toncenter.com/) · **Stellar**: [Horizon API](https://horizon.stellar.org/) · **Substrate**: [Subscan](https://subscan.io/)
**Cosmos IBC**: Public LCD nodes (Osmosis, Celestia, Injective, dYdX, Sei, Akash)
**Pricing**: [CoinGecko](https://www.coingecko.com/), [CoinMarketCap](https://coinmarketcap.com/), [Coinbase](https://www.coinbase.com/), [CoinPaprika](https://coinpaprika.com/), [DefiLlama](https://defillama.com/)
**Logos**: [LogoKit](https://logokit.com/), [Logostream](https://logostream.dev)
**Exchanges** (42 total): [Coinbase](https://www.coinbase.com/cloud), [Binance](https://www.binance.com/), [Bybit](https://www.bybit.com/), [MEXC](https://www.mexc.com/), [Kraken](https://www.kraken.com/), [Gemini](https://www.gemini.com/), [OKX](https://www.okx.com/), [Bitget](https://www.bitget.com/), [Gate.io](https://www.gate.io/), [KuCoin](https://www.kucoin.com/), [Bitfinex](https://www.bitfinex.com/), [HTX](https://www.htx.com/), and 30 more
**Privacy**: [Midnight Network](https://midnight.network/) (NIGHT token support)

For detailed API information including rate limits and pricing, see [API Providers Guide](docs/API_PROVIDERS.md).

## Links

- **Website**: [abettercryptotracker.com](https://abettercryptotracker.com)
- **Repository**: [github.com/Tarrant64/abct](https://github.com/Tarrant64/abct)
- **Releases**: [github.com/Tarrant64/abct/releases](https://github.com/Tarrant64/abct/releases)
- **Issues**: [github.com/Tarrant64/abct/issues](https://github.com/Tarrant64/abct/issues)
- **Docker Hub**: [hub.docker.com/r/tarrant64/abct](https://hub.docker.com/r/tarrant64/abct)

---

**Current Version:** v1.16.3 (BUILD 1786304190)
**Last Updated:** August 5, 2026
