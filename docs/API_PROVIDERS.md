# API Providers

This document provides detailed information about all external APIs used by ABCT.

## Overview

ABCT integrates with **16 different API providers** across 5 blockchain networks to provide comprehensive portfolio tracking. This architecture provides redundancy, fallback options, and specialized functionality.

## Categories

- [Cardano Network APIs](#cardano-network-apis)
- [Ethereum & EVM Chain APIs](#ethereum--evm-chain-apis)
- [Solana Network APIs](#solana-network-apis)
- [Bitcoin Network APIs](#bitcoin-network-apis)
- [Pricing & Market Data APIs](#pricing--market-data-apis)
- [Exchange Integration APIs](#exchange-integration-apis)

---

## Cardano Network APIs

### Blockfrost
**Purpose:** Primary Cardano blockchain API
**Status:** Required
**What it provides:**
- Wallet balances (ADA and native assets)
- Transaction history
- Asset metadata
- Staking account information
- Pool delegation data
- DRep governance delegation
- Rewards history

**Rate Limits:**
- Free tier: 10 requests/sec, burst of 500 requests
- No documented daily limit

**Pricing:** Free tier available, paid plans from $9.99/month
**Sign Up:** https://blockfrost.io
**API Docs:** https://docs.blockfrost.io
**Environment Variable:** `BLOCKFROST_API_KEY`

---

### TapTools
**Purpose:** Cardano NFT floor prices and token analytics
**Status:** Optional (recommended for NFT collectors)
**What it provides:**
- NFT collection floor prices
- NFT listing data
- Token price data
- DeFi analytics
- Wallet portfolio positions

**Rate Limits:**
- Varies by subscription plan
- Free tier: ~100 calls/day
- ABCT includes automatic scheduler to respect limits

**Pricing:** Subscription required (~$10/month)
**Sign Up:** https://www.taptools.io/openapi/subscription
**API Docs:** https://openapi.taptools.io/
**Environment Variable:** `TAPTOOLS_API_KEY`

**Note:** ABCT v0.9.0+ includes NFT Background Scheduler that automatically collects floor prices throughout the day while respecting rate limits.

---

### CExplorer
**Purpose:** Cardano staking and DeFi data
**Status:** Recommended (for staking features)
**What it provides:**
- Detailed staking positions
- Pool performance metrics
- Rewards calculations
- DeFi protocol data
- Fallback for Blockfrost

**Rate Limits:**
- Not clearly documented
- Generous free tier

**Pricing:** Free tier available
**Sign Up:** https://cexplorer.io/api
**API Docs:** https://cexplorer.io/api
**Environment Variable:** `CEXPLORER_API_KEY`

---

### Koios
**Purpose:** Free Cardano metadata API (fallback)
**Status:** Optional (used automatically as fallback)
**What it provides:**
- NFT collection metadata
- Asset information
- Transaction data

**Rate Limits:**
- No API key required
- Rate limits apply but are generous

**Pricing:** Free
**Sign Up:** Not required
**API Docs:** https://api.koios.rest/
**Environment Variable:** None (no key required)

**Note:** Koios is used automatically as a fallback when other APIs are unavailable. No configuration needed.

---

## Ethereum & EVM Chain APIs

### Alchemy
**Purpose:** Multi-chain blockchain infrastructure
**Status:** Optional (required for Ethereum/Polygon/Base/Optimism)
**What it provides:**
- **Ethereum:** ETH balance, ERC-20 tokens, NFTs
- **Polygon:** MATIC balance, tokens, NFTs
- **Base:** ETH balance, tokens, NFTs
- **Optimism:** ETH balance, tokens

**Supported Networks:**
- Ethereum Mainnet
- Polygon (MATIC)
- Base
- Optimism
- Arbitrum

**Rate Limits:**
- Free tier: 30M compute units/month (~1.8M simple requests)
- ~60,000 requests/day (conservative estimate)

**Pricing:** Free tier available, paid plans from $49/month
**Sign Up:** https://www.alchemy.com/
**API Docs:** https://docs.alchemy.com/
**Environment Variable:** `ALCHEMY_API_KEY`

**Note:** One API key works across all supported chains.

---

### Etherscan
**Purpose:** Ethereum blockchain explorer API
**Status:** Optional (required for Ethereum)
**What it provides:**
- Transaction history
- Token transfers
- Contract verification status
- Gas prices

**Rate Limits:**
- Free tier: 3 calls/sec OR 100,000 calls/day
- Whichever limit is reached first

**Pricing:** Free tier available, paid plans from $99/month
**Sign Up:** https://etherscan.io/apis
**API Docs:** https://docs.etherscan.io/
**Environment Variable:** `ETHERSCAN_API_KEY`

---

### Basescan
**Purpose:** Base blockchain explorer API
**Status:** Optional (required for Base)
**What it provides:**
- Same functionality as Etherscan but for Base chain
- Transaction history
- Token transfers

**Rate Limits:**
- Same as Etherscan (3 calls/sec OR 100,000 calls/day)

**Pricing:** Free tier available
**Sign Up:** https://basescan.org/apis
**API Docs:** https://docs.basescan.org/
**Environment Variable:** `ETHERSCAN_API_KEY` (shared with Etherscan)

**Note:** Basescan uses the same API key as Etherscan.

---

### Polygonscan
**Purpose:** Polygon blockchain explorer API
**Status:** Optional (required for Polygon)
**What it provides:**
- Same functionality as Etherscan but for Polygon chain
- Transaction history
- Token transfers

**Rate Limits:**
- Same as Etherscan (3 calls/sec OR 100,000 calls/day)

**Pricing:** Free tier available
**Sign Up:** https://polygonscan.com/apis
**API Docs:** https://docs.polygonscan.com/
**Environment Variable:** `ETHERSCAN_API_KEY` (shared with Etherscan)

**Note:** Polygonscan uses the same API key as Etherscan and Basescan.

---

### The Graph (Uniswap Subgraphs)
**Purpose:** Decentralized token pricing via Uniswap liquidity pools
**Status:** Optional (recommended for Ethereum/Polygon/Base token pricing)
**What it provides:**
- **Ethereum:** ERC-20 token prices in ETH via Uniswap V2/V3 pools
- **Polygon:** Token prices in ETH equivalent
- **Base:** Token prices in ETH
- Native-token-denominated pricing (ETH per token)
- Total Value Locked (TVL) data
- Trading volume statistics
- Comprehensive token metadata

**Integration Details:**
- **Uniswap V3 Subgraph ID:** `5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV`
- **Uniswap V2 Subgraph ID:** `A3Np3RQbaBA6oKJgiwDJeo5T3zrYfGHPWFYayMwtNDum`
- GraphQL query endpoint via The Graph Gateway
- Batch queries: up to 100 tokens per request
- 5-minute price caching for performance
- Automatic USD conversion using ETH/USD price

**Rate Limits:**
- Free tier: **100,000 queries per 24 hours**
- Tracked automatically via `api_usage` table
- Monitored at `/api/status` endpoint

**Pricing:** Free tier with 100K queries/day, paid plans available
**Sign Up:** https://thegraph.com/studio/
**API Docs:** https://thegraph.com/docs/
**Environment Variable:** `GRAPH_API_KEY`

**Implementation:**
- Service: `backend/services/graph.py`
- Documentation: `docs/GRAPH_API_INTEGRATION.md`
- Methods: `get_token_price_eth()`, `get_multiple_token_prices()`, `get_token_data()`

**Note:** Provides more accurate DeFi pricing than centralized price APIs by querying actual liquidity pool data. Integrated in v0.13.0.

---

## Solana Network APIs

### Helius
**Purpose:** Solana blockchain API and RPC
**Status:** Optional (required for Solana)
**What it provides:**
- SOL balance
- SPL token balances
- NFT holdings
- Token metadata
- Transaction history

**Rate Limits:**
- Free tier: 1M credits/month
- 10 RPS (requests per second)
- ~33,000 credits/day

**Pricing:** Free tier available, paid plans from $49/month
**Sign Up:** https://www.helius.dev/
**API Docs:** https://docs.helius.dev/
**Environment Variable:** `HELIUS_API_KEY`

---

## Bitcoin Network APIs

### Blockstream
**Purpose:** Bitcoin blockchain data
**Status:** Optional (required for Bitcoin)
**What it provides:**
- BTC balance (confirmed and unconfirmed)
- UTXO data
- Transaction history
- xpub support (BIP44, BIP49, BIP84)

**Rate Limits:**
- No API key required
- Rate limits exist but are generous
- Consider being respectful with request frequency

**Pricing:** Free (no API key needed)
**Sign Up:** Not required
**API Docs:** https://github.com/Blockstream/esplora/blob/master/API.md
**Environment Variable:** None (no key required)

**Note:** Blockstream API is free and doesn't require authentication. ABCT includes built-in support for Bitcoin xpub address derivation.

---

## Pricing & Market Data APIs

### CoinGecko
**Purpose:** Primary cryptocurrency price aggregation
**Status:** Recommended (works without key, key increases limits)
**What it provides:**
- Real-time cryptocurrency prices (USD)
- 1-hour and 24-hour price changes
- Market cap data
- Historical price data
- Supports all major cryptocurrencies

**Rate Limits:**
- Demo API (no key): 30 calls/min, 10,000 calls/month (~333/day)
- Pro API: Higher limits

**Pricing:** Free Demo API, Pro from $129/month
**Sign Up:** https://www.coingecko.com/en/api
**API Docs:** https://docs.coingecko.com/
**Environment Variable:** `COINGECKO_API_KEY` (optional)

**Note:** CoinGecko is the primary price source for ABCT. Works without an API key, but having a key increases rate limits.

---

### CoinMarketCap
**Purpose:** Alternative cryptocurrency price data (fallback)
**Status:** Optional
**What it provides:**
- Cryptocurrency prices
- Market cap data
- Volume data
- 1-hour and 24-hour price changes

**Rate Limits:**
- Free tier: 10,000 calls/month (~333/day)
- Higher tiers available

**Pricing:** Free tier available, paid plans from $29/month
**Sign Up:** https://coinmarketcap.com/api/
**API Docs:** https://coinmarketcap.com/api/documentation/
**Environment Variable:** `CMC_API_KEY`

**Note:** Used as fallback when CoinGecko is unavailable or rate-limited.

---

### Coinbase (Public API)
**Purpose:** Spot price data for major cryptocurrencies
**Status:** Optional (automatic fallback)
**What it provides:**
- Real-time spot prices for major coins (BTC, ETH, ADA, SOL, MATIC)
- No price change or market cap data

**Rate Limits:**
- No API key required
- Rate limits apply but are generous

**Pricing:** Free
**Sign Up:** Not required for public API
**API Docs:** https://docs.cloud.coinbase.com/
**Environment Variable:** None (no key required for public API)

**Note:** Used as fallback for major cryptocurrencies when other price sources fail. Separate from Coinbase CDP exchange integration.

---

### DefiLlama
**Purpose:** Universal price fallback for all chains
**Status:** Optional (automatic fallback)
**What it provides:**
- Cryptocurrency prices across all chains
- Support for Cardano native tokens
- Support for EVM tokens
- No API key required

**Rate Limits:**
- No API key required
- Generous rate limits

**Pricing:** Free
**Sign Up:** Not required
**API Docs:** https://defillama.com/docs/api
**Environment Variable:** None (no key required)

**Note:** DefiLlama is used as a universal fallback for token pricing when other sources are unavailable. Particularly useful for Cardano native tokens.

---

## Exchange Integration APIs

### Coinbase CDP
**Purpose:** Exchange API for portfolio balances
**Status:** Optional (for Coinbase users)
**What it provides:**
- Portfolio balances across all Coinbase accounts
- USD balances
- Cryptocurrency holdings
- Open order data

**Authentication:**
- Uses JSON key file (not environment variable)
- JWT-based authentication with EC private key

**Rate Limits:**
- Varies by tier
- Free tier has reasonable limits for personal use

**Pricing:** Free for personal use
**Sign Up:** https://portal.cdp.coinbase.com/access/api
**API Docs:** https://docs.cdp.coinbase.com/
**Configuration:** Create `cdp_api_key.json` in project root

**Setup Instructions:**
1. Go to https://portal.cdp.coinbase.com/access/api
2. Create a new API key with "View" permissions
3. Download the JSON file
4. Save as `cdp_api_key.json` in ABCT project root

---

## API Redundancy & Fallback Strategy

ABCT implements intelligent fallback strategies to ensure reliability:

### Cardano Balances
1. **Primary:** Blockfrost
2. **Fallback:** CExplorer

### Cryptocurrency Prices
1. **Primary:** CoinGecko (all tokens)
2. **Fallback 1:** CoinMarketCap (if available)
3. **Fallback 2:** Coinbase Public API (major coins only)
4. **Fallback 3:** DefiLlama (universal)
5. **Cardano-specific:** TapTools (Cardano tokens)

### NFT Metadata
1. **Primary:** TapTools (Cardano) or Alchemy (EVM)
2. **Fallback 1:** Koios (Cardano)
3. **Fallback 2:** Blockfrost (Cardano)

### EVM Transactions
1. **Primary:** Alchemy
2. **Fallback:** Etherscan/Basescan/Polygonscan

---

## Required vs Optional APIs

### Required (Minimum Configuration)
- **Blockfrost** - Essential for Cardano wallet tracking

### Highly Recommended
- **CExplorer** - For Cardano staking features
- **CoinGecko** - For price data (works without key)

### Optional (Per Use Case)
- **TapTools** - If you collect Cardano NFTs
- **Alchemy** - If you use Ethereum/Polygon/Base
- **Etherscan** - If you use Ethereum/Polygon/Base
- **Helius** - If you use Solana
- **Coinbase CDP** - If you use Coinbase exchange
- **CoinMarketCap** - For backup price data

### Automatic (No Configuration)
- **Blockstream** - Bitcoin support (free, no key)
- **Koios** - Cardano metadata fallback (free, no key)
- **DefiLlama** - Price fallback (free, no key)
- **Coinbase Public API** - Price fallback (free, no key)

---

## API Cost Optimization

ABCT includes several features to minimize API costs:

### Caching
- **Database caching:** Persistent across restarts (30 days for NFTs)
- **In-memory caching:** Fast access (5 minutes for balances)
- **Price caching:** 5-minute refresh intervals

### Smart Scheduling
- **NFT Scheduler:** Spreads TapTools calls across 24 hours
- **Batch requests:** Combines multiple queries when possible
- **Rate limit tracking:** Prevents exceeding free tier limits

### Fallback Strategy
- Free APIs used first when available
- Paid APIs only called when necessary
- Graceful degradation if API unavailable

### API Usage Dashboard
- Monitor API call counts in Settings → API Utilization
- View rate limit status
- Track daily usage
- Set custom limits

---

## Getting API Keys

### Free Tier Priority
Most APIs offer generous free tiers:
1. **Blockfrost** - 10 req/sec, unlimited daily (free forever)
2. **CoinGecko** - 10,000 calls/month (free forever)
3. **Alchemy** - 30M compute units/month (free forever)
4. **Helius** - 1M credits/month (free forever)
5. **Etherscan** - 100,000 calls/day (free forever)

### Paid APIs
Only TapTools requires a subscription for NFT features:
- **TapTools** - $10/month (required for NFT floor prices)

### Sign-Up Process
1. Visit the provider's website (links in each section above)
2. Create account with email
3. Generate API key from dashboard
4. Add to ABCT's `.env` file
5. Test in ABCT Settings → APIs

---

## Privacy & Data Handling

### What APIs See
- **Public wallet addresses** - Needed to fetch blockchain data
- **No private keys** - ABCT is read-only, never has access to private keys
- **IP address** - Standard for any API request

### Data Retention
- **ABCT:** All data cached locally in SQLite database
- **API Providers:** Check individual privacy policies
- **No telemetry:** ABCT doesn't send usage data to any third party

### Best Practices
- Use dedicated API keys for ABCT
- Rotate API keys periodically
- Monitor API usage in Settings
- Review provider privacy policies
- Consider VPN for additional privacy

---

## API Status & Monitoring

### Check API Status
- **ABCT Dashboard:** Settings → APIs (shows all configured APIs)
- **API Utilization:** Settings → API Utilization (real-time usage stats)
- **Test Connection:** Each API has a "Test" button in Settings

### Common Issues

#### "API key not configured"
- Add the API key to `.env` file
- Restart ABCT after adding keys
- Check for typos in the key

#### "Rate limited"
- Check usage in API Utilization dashboard
- Wait for rate limit reset (shown in dashboard)
- Consider upgrading API tier
- Enable caching features

#### "API unavailable"
- Check provider status page
- Verify internet connection
- Try fallback APIs (automatic in most cases)
- Check API key expiration

---

## Support & Resources

### ABCT Documentation
- [README.md](README.md) - Main documentation
- [DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md) - Docker setup
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture

### API Provider Support
Each provider has their own support channels:
- Check API documentation links above
- Provider status pages
- Community Discord/Telegram
- Email support (paid tiers)

### ABCT Community
- **GitHub Issues:** https://github.com/Tarrant64/abct/issues
- **Discussions:** https://github.com/Tarrant64/abct/discussions

---

## Updates & Changes

This document is maintained alongside ABCT releases. Check [CHANGELOG.md](CHANGELOG.md) for API-related changes.

**Last Updated:** January 2026
**ABCT Version:** v0.10.0

---

## Quick Reference

| Provider | Blockchain | Required | Free Tier | Env Variable |
|----------|-----------|----------|-----------|--------------|
| Blockfrost | Cardano | Yes | Yes (generous) | `BLOCKFROST_API_KEY` |
| CExplorer | Cardano | No | Yes | `CEXPLORER_API_KEY` |
| TapTools | Cardano | No | Paid (~$10/mo) | `TAPTOOLS_API_KEY` |
| Koios | Cardano | No | Yes (no key) | None |
| Alchemy | EVM | No | Yes (30M CU/mo) | `ALCHEMY_API_KEY` |
| Etherscan | Ethereum | No | Yes (100k/day) | `ETHERSCAN_API_KEY` |
| Basescan | Base | No | Yes (100k/day) | `ETHERSCAN_API_KEY` |
| Polygonscan | Polygon | No | Yes (100k/day) | `ETHERSCAN_API_KEY` |
| Helius | Solana | No | Yes (1M cr/mo) | `HELIUS_API_KEY` |
| Blockstream | Bitcoin | No | Yes (no key) | None |
| CoinGecko | Prices | No | Yes (10k/mo) | `COINGECKO_API_KEY` |
| CoinMarketCap | Prices | No | Yes (10k/mo) | `CMC_API_KEY` |
| DefiLlama | Prices | No | Yes (no key) | None |
| Coinbase Public | Prices | No | Yes (no key) | None |
| Coinbase CDP | Exchange | No | Yes | `cdp_api_key.json` |
