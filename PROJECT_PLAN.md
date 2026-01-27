# ABCT - Crypto Portfolio Tracker
## Project Plan

---

## Overview
A locally-hosted web application to track cryptocurrency portfolios across multiple blockchains (Cardano, Bitcoin, Ethereum) with native asset support, pricing data, and eventual exchange integration.

---

## Tech Stack (Recommended)

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Backend | Python + FastAPI | Simple, async support, easy API integration |
| Frontend | HTML/CSS/JavaScript (vanilla or lightweight framework) | Keeps it simple for local use |
| Database | SQLite | No external dependencies, file-based, perfect for local hosting |
| Package Manager | pip + requirements.txt | Standard Python tooling |

---

## Phase 1: Wallet Listing & Balance Retrieval

### Objective
Read wallet addresses from a text file, identify the blockchain, and fetch balances + native assets.

### Tasks

#### 1.1 Project Setup
- [ ] Initialize project structure
- [ ] Set up Python virtual environment
- [ ] Create FastAPI backend skeleton
- [ ] Create basic HTML frontend

#### 1.2 Wallet File Parser
- [ ] Define `wallets.txt` format (e.g., `blockchain:address` or auto-detect)
- [ ] Build parser to read and validate addresses
- [ ] Implement address format detection:
  - Cardano: starts with `addr1` (mainnet) or `addr_test1` (testnet)
  - Bitcoin: starts with `1`, `3`, or `bc1`
  - Ethereum: starts with `0x` (40 hex chars)

#### 1.3 Blockchain API Integration
- [ ] **Cardano** - Blockfrost API (free: 50k requests/day)
  - Fetch ADA balance
  - Fetch native assets (tokens, NFTs)
- [ ] **Bitcoin** - Blockstream API (free, no key required)
  - Fetch BTC balance
  - Fetch UTXOs
- [ ] **Ethereum** - Etherscan API (free: 5 calls/sec)
  - Fetch ETH balance
  - Fetch ERC-20 token balances

#### 1.4 Data Models & Storage
- [ ] Design SQLite schema for wallets, balances, assets
- [ ] Implement caching to reduce API calls
- [ ] Store last refresh timestamp

#### 1.5 Basic API Endpoints
- [ ] `GET /wallets` - List all tracked wallets
- [ ] `GET /wallets/{id}/balance` - Get balance for specific wallet
- [ ] `POST /wallets/refresh` - Refresh all balances
- [ ] `GET /portfolio/summary` - Aggregate portfolio view

### APIs & Keys Required
| Blockchain | API | Key Required | Free Tier |
|------------|-----|--------------|-----------|
| Cardano | Blockfrost | Yes (free signup) | 50k req/day |
| Bitcoin | Blockstream | No | Unlimited |
| Ethereum | Etherscan | Yes (free signup) | 5 req/sec |

---

## Phase 2: Pricing Integration

### Objective
Pull real-time and historical pricing data from free sources.

### Tasks

#### 2.1 Price Data Sources
- [ ] **CoinGecko API** (primary - free, no key for basic)
  - Current prices
  - Historical data
  - Market data
- [ ] **CoinMarketCap API** (backup - free tier: 10k calls/month)
  - Alternative pricing source

#### 2.2 Price Mapping
- [ ] Map native assets to CoinGecko IDs
- [ ] Handle unknown/unlisted tokens gracefully
- [ ] Implement fallback pricing logic

#### 2.3 Portfolio Valuation
- [ ] Calculate total portfolio value in USD
- [ ] Calculate individual wallet values
- [ ] Track value changes over time

#### 2.4 Price Caching
- [ ] Cache prices to reduce API calls
- [ ] Configurable refresh interval
- [ ] Store historical snapshots

### New Endpoints
- [ ] `GET /prices` - Current prices for tracked assets
- [ ] `GET /portfolio/value` - Total portfolio value
- [ ] `GET /portfolio/history` - Historical portfolio value

---

## Phase 3: UI/UX Enhancement

### Objective
Create a polished, user-friendly interface.

### Tasks

#### 3.1 Dashboard Design
- [ ] Portfolio overview with total value
- [ ] Breakdown by blockchain
- [ ] Breakdown by asset type
- [ ] 24h/7d/30d change indicators

#### 3.2 Wallet Views
- [ ] Individual wallet detail pages
- [ ] Asset list with thumbnails (for NFTs)
- [ ] Transaction history (if feasible)

#### 3.3 Charts & Visualization
- [ ] Portfolio value over time (line chart)
- [ ] Asset allocation (pie chart)
- [ ] Use Chart.js or similar lightweight library

#### 3.4 Settings & Configuration
- [ ] Add/remove wallets via UI
- [ ] Configure refresh intervals
- [ ] API key management
- [ ] Theme selection (light/dark)

#### 3.5 Responsive Design
- [ ] Mobile-friendly layout
- [ ] Clean, minimal aesthetic

---

## Phase 4: Exchange Integration

### Objective
Connect to cryptocurrency exchanges to pull additional portfolio data.

### Tasks

#### 4.1 Exchange Selection
Potential exchanges with free API access:
- [ ] **Coinbase** - OAuth or API key
- [ ] **Kraken** - API key
- [ ] **Binance** - API key (read-only)

#### 4.2 Exchange API Integration
- [ ] Implement read-only API connections
- [ ] Fetch balances from exchanges
- [ ] Fetch transaction/trade history
- [ ] Map exchange assets to portfolio

#### 4.3 Unified Portfolio View
- [ ] Combine on-chain + exchange holdings
- [ ] Avoid double-counting (deposits/withdrawals)
- [ ] Show source attribution (wallet vs exchange)

#### 4.4 Security Considerations
- [ ] Store API keys securely (encrypted)
- [ ] Read-only API permissions only
- [ ] Local-only storage (never transmit keys)

---

## Phase 5: NFT Display & Valuation

### Objective
Display NFT holdings with images, metadata, and estimated floor prices.

### Tasks

#### 5.1 NFT Detection & Metadata
- [ ] Identify NFT assets vs fungible tokens (quantity = 1, policy patterns)
- [ ] Fetch NFT metadata from on-chain or IPFS
- [ ] Parse CIP-25/CIP-68 metadata standards
- [ ] Handle image URLs (IPFS, HTTP, on-chain)

#### 5.2 NFT Image Display
- [ ] Create NFT gallery view
- [ ] Lazy load images for performance
- [ ] Support multiple formats (PNG, JPG, GIF, SVG)
- [ ] Handle IPFS gateway conversion (ipfs:// to https gateway)
- [ ] Fallback placeholder for missing images

#### 5.3 NFT Valuation & Floor Prices
- [ ] **jpg.store API** - Cardano NFT marketplace data
- [ ] **OpenSea API** - Ethereum NFT data (if ETH added)
- [ ] Fetch collection floor prices
- [ ] Calculate estimated NFT portfolio value
- [ ] Track floor price changes over time

#### 5.4 Collection Grouping
- [ ] Group NFTs by collection/policy ID
- [ ] Display collection name and statistics
- [ ] Show number owned vs total supply
- [ ] Collection-level valuation

#### 5.5 NFT Detail View
- [ ] Individual NFT detail page
- [ ] Full metadata display (traits, rarity)
- [ ] Links to marketplace listings
- [ ] Transaction history for NFT

### APIs & Resources
| Service | Purpose | Notes |
|---------|---------|-------|
| jpg.store | Cardano NFT floor prices | Free API available |
| IPFS Gateways | NFT image retrieval | cloudflare-ipfs.com, ipfs.io |
| Blockfrost | NFT metadata | Already integrated |
| OpenSea | Ethereum NFTs | API key required |

---

## Project Structure (Proposed)

```
ABCT/
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Configuration & API keys
│   ├── database.py          # SQLite connection & models
│   ├── routers/
│   │   ├── wallets.py       # Wallet endpoints
│   │   ├── prices.py        # Price endpoints
│   │   └── portfolio.py     # Portfolio endpoints
│   ├── services/
│   │   ├── cardano.py       # Blockfrost integration
│   │   ├── bitcoin.py       # Blockstream integration
│   │   ├── ethereum.py      # Etherscan integration
│   │   └── pricing.py       # CoinGecko integration
│   └── utils/
│       └── address.py       # Address detection & validation
├── frontend/
│   ├── index.html           # Main dashboard
│   ├── css/
│   │   └── styles.css
│   └── js/
│       └── app.js
├── data/
│   ├── wallets.txt          # Wallet addresses (user config)
│   └── portfolio.db         # SQLite database
├── requirements.txt
├── .env.example             # API key template
└── README.md
```

---

## Wallet File Format (wallets.txt)

```
# Format: One address per line
# Blockchain is auto-detected, or prefix with chain:
#
# Examples:
addr1qxy...                    # Cardano (auto-detected)
bc1qar0srrr...                 # Bitcoin (auto-detected)
0x742d35Cc6634C0532925a3b844Bc9e7595f...  # Ethereum (auto-detected)
cardano:addr1qxy...            # Explicit chain prefix
bitcoin:1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
ethereum:0x742d35Cc6634C0532925a3b844Bc9e7595f...
```

---

## Getting Started (Prerequisites)

1. **Python 3.9+** installed
2. **API Keys** (free signup required):
   - Blockfrost: https://blockfrost.io/
   - Etherscan: https://etherscan.io/apis
3. **wallets.txt** with your addresses

---

## Execution Order

We will execute in this order:
1. **Phase 1** - Core functionality (wallets + balances) ✅ COMPLETE
   - Cardano & Bitcoin wallet tracking
   - Native asset display
   - DeFi token identification
   - Staking position tracking (Indigo, Strike, Liqwid)
   - External explorer links
   - Editable wallet names
   - Collapsible sections
2. **Phase 2** - Add pricing
3. **Phase 3** - Polish UI
4. **Phase 4** - Exchange integration
5. **Phase 5** - NFT display & valuation

Ready to continue with Phase 2 when you are.
