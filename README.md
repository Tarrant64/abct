# A Better Crypto Tracker (ABCT)

Personal multi-chain portfolio tracker built Cardano-first.

![Version](https://img.shields.io/badge/version-1.12.3-brightgreen.svg)
![Build](https://img.shields.io/badge/build-1771184565-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-green.svg)
![FastAPI](https://img.shields.io/badge/fastapi-0.109-teal.svg)
![Chains](https://img.shields.io/badge/chains-26-brightgreen.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![Exchanges](https://img.shields.io/badge/exchanges-7-purple.svg)
![Themes](https://img.shields.io/badge/themes-5-purple.svg)

**Website**: [abettercryptotracker.com](https://abettercryptotracker.com)

## Why

Existing multi-chain wallets treat Cardano as an afterthought — basic balance tracking with no stake pool info, broken native assets, and zero governance integration. This project flips that: deep Cardano ecosystem support first, then proper multi-chain coverage.

## Features

### 26 Blockchains

**Cardano** (Primary) — Stake pool tracking, rewards, governance, native assets with metadata, DeFi protocol integration (Minswap, SundaeSwap, etc.), NFT collections with floor prices, stake key wallet grouping.

**API-Key Chains** — Ethereum, Solana, Polygon, Base, Algorand, Arbitrum, Avalanche, BNB Chain (via Etherscan/Alchemy/Helius APIs)

**Free Chains** (no API key required) — Bitcoin, Tron, XRP, Hedera, MultiversX, Sui, Aptos, Filecoin, Litecoin, Dogecoin, Zcash, Tezos, Stacks, VeChain, Cosmos, NEAR, ICP

### 7 Exchanges
Coinbase, Binance, Binance.US, OKX, Bitget, Gate.io, KuCoin — all read-only API integration.

### Portfolio & Analytics
- **Dashboard**: Dynamic blockchain cards, allocation donut chart, market heatmap, global market cap widget
- **Per-Wallet History**: Daily balance tracking per wallet/exchange/staking position with unified chart
- **Transaction Analytics**: Multi-chain transaction history with filtering, analytics, and portfolio vs. BTC relative strength
- **DePIN Tracking**: Iagon (Cardano) and Helium (Solana) infrastructure protocol monitoring
- **DeFi Monitoring**: Staking positions with APY and rewards across protocols
- **NFT Collection**: Browse NFTs with floor price valuations across Cardano, Ethereum, and Solana

### Infrastructure
- **Self-Hosted**: Your data stays on your machine — no telemetry, no external analytics
- **Docker Ready**: Single container deployment with multi-arch builds (amd64/arm64)
- **CI/CD**: Automated Docker Hub publishing and Docker Scout vulnerability scanning via GitHub Actions
- **V2 Data Architecture**: Per-source daily balances, materializer pipeline, off-chain collector
- **5 Themes**: Dark Mode, Light, Cypherpunk, Ocean Depths, Sunset Horizon
- **Privacy Mode**: Hide sensitive financial data and URLs with one click
- **Cloudflare Tunnel**: Built-in secure remote access (auto-restores across container rebuilds)
- **Encrypted API Keys**: All keys encrypted at rest in the database

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

> **Unraid users:** Use `abct-docker/deploy-from-git.sh` to pull from GitHub and rebuild (recommended).

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
TAPTOOLS_API_KEY=your_key_here       # NFT floor prices

# OPTIONAL: Additional blockchains
ETHERSCAN_API_KEY=your_key_here      # Ethereum/Arbitrum/Avalanche/BNB/Base
ALCHEMY_API_KEY=your_key_here        # Ethereum/Polygon/Base NFTs
HELIUS_API_KEY=your_key_here         # Solana

# OPTIONAL: Authentication
ABCT_REQUIRE_AUTH=false              # Set to false for localhost-only
```

Exchange API keys can be configured in the Settings page or via `.env` — see [Exchange Integration Guide](docs/docs/Exchange-Integration.md) for setup instructions.

All API keys should be **read-only**. Never grant withdrawal or trading permissions.

## Security

- **Read-Only Access**: Cannot move funds, only view balances
- **Local Database**: All data stored in local SQLite files
- **Encrypted API Keys**: API keys encrypted at rest
- **Optional Authentication**: Session-based auth with login page
- **HTTPS Support**: SSL/TLS with self-signed or custom certificates
- **DOMPurify**: Client-side XSS protection on all HTML rendering
- **Rate Limiting**: API endpoint protection against abuse
- **Secure Logging**: Audit trails with sensitive data redaction

See [SECURITY.md](SECURITY.md) for full details.

## What's New

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
- **[Exchange Integration](docs/docs/Exchange-Integration.md)** — Setup for 7 supported exchanges
- **[Backup & Restore](docs/BACKUP_RESTORE_GUIDE.md)** — Configuration management
- **[Security Guide](SECURITY.md)** — Security best practices
- **[API Providers](docs/API_PROVIDERS.md)** — API provider details and rate limits
- **[Password Reset](docs/guides/PASSWORD_RESET_GUIDE.md)** — Reset admin credentials
- **In-App Help** — Built-in Help & Guide page with setup walkthroughs

## License

MIT License — see [LICENSE](LICENSE) file for details.

## Acknowledgments

Built with [FastAPI](https://fastapi.tiangolo.com/), [Chart.js](https://www.chartjs.org/), [SQLite](https://www.sqlite.org/), [HTTPX](https://www.python-httpx.org/), and [DOMPurify](https://github.com/cure53/DOMPurify).

### Blockchain Data Providers

**Cardano**: [Blockfrost](https://blockfrost.io/), [TapTools](https://www.taptools.io/), [CExplorer](https://cexplorer.io/), [Koios](https://koios.rest/)
**Ethereum & EVM**: [Alchemy](https://www.alchemy.com/), [Etherscan](https://etherscan.io/), [Basescan](https://basescan.org/), [Polygonscan](https://polygonscan.com/)
**Solana**: [Helius](https://www.helius.dev/) · **Bitcoin**: [Blockstream](https://blockstream.info/) · **Algorand**: [Pera Wallet](https://developer.perawallet.app/), [Tatum](https://tatum.io/)
**Pricing**: [CoinGecko](https://www.coingecko.com/), [CoinMarketCap](https://coinmarketcap.com/), [DefiLlama](https://defillama.com/), [Coinbase](https://www.coinbase.com/)
**Logos**: [LogoKit](https://logokit.com/), [Logostream](https://logostream.dev)
**Exchanges**: [Coinbase CDP](https://www.coinbase.com/cloud), [Binance](https://www.binance.com/), [OKX](https://www.okx.com/), [Bitget](https://www.bitget.com/), [Gate.io](https://www.gate.io/), [KuCoin](https://www.kucoin.com/)
**Privacy**: [Midnight Network](https://midnight.network/) (NIGHT token support)

For detailed API information including rate limits and pricing, see [API Providers Guide](docs/API_PROVIDERS.md).

## Links

- **Website**: [abettercryptotracker.com](https://abettercryptotracker.com)
- **Repository**: [github.com/Tarrant64/abct](https://github.com/Tarrant64/abct)
- **Releases**: [github.com/Tarrant64/abct/releases](https://github.com/Tarrant64/abct/releases)
- **Issues**: [github.com/Tarrant64/abct/issues](https://github.com/Tarrant64/abct/issues)
- **Docker Hub**: [hub.docker.com/r/tarrant64/abct](https://hub.docker.com/r/tarrant64/abct)

---

**Current Version:** v1.12.3 (BUILD 1771184565)
**Last Updated:** February 15, 2026
