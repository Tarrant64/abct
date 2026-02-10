# ABCT Architecture (v1.5.0)

## System Overview

```
+-----------------------------------------------------------------------------------+
|                              ABCT System (v1.5.0)                                  |
|                         Multi-User Portfolio Tracker                              |
|                              BUILD 1770726755                                     |
+-----------------------------------------------------------------------------------+

                                   +-----------------+
                                   |   Frontend UI   |
                                   | (HTML/CSS/JS)   |
                                   |   - Dashboard   |
                                   |   - Wallets     |
                                   |   - Assets      |
                                   |   - Transactions|
                                   |   - NFT Wall    |
                                   |   - Settings    |
                                   |   - System      |
                                   +--------+--------+
                                            |
                                            | HTTP/REST
                                            | Session Tokens
                                            v
+-----------------------------------------------------------------------------------+
|                              FastAPI Backend Server                                |
|                                   (main.py)                                        |
+-----------------------------------------------------------------------------------+
|                                                                                    |
|  +---------------------------+                                                    |
|  |   Authentication Layer    |                                                    |
|  |  - Session Management     |                                                    |
|  |  - Password Hashing       |                                                    |
|  |  - Demo Mode Detection    |                                                    |
|  +-----------+---------------+                                                    |
|              |                                                                    |
|              v                                                                    |
|  +------------------+  +------------------+  +------------------+                  |
|  |  Auth API        |  |  Portfolio API   |  |   Wallets API    |                  |
|  |  /auth/*         |  |  /portfolio/*    |  |   /wallets/*     |                  |
|  +------------------+  +------------------+  +------------------+                  |
|                                                                                    |
|  +------------------+  +------------------+  +------------------+                  |
|  |  Prices API      |  |   DeFi API       |  |  Exchanges API   |                  |
|  |  /prices/*       |  |   /defi/*        |  |  /exchanges/*    |                  |
|  +------------------+  +------------------+  +------------------+                  |
|                                                                                    |
|  +------------------+  +------------------+  +------------------+                  |
|  |   NFTs API       |  |  Transactions    |  | Balance History  |                  |
|  |   /nfts/*        |  |  /transactions/* |  | /balance-history |                  |
|  +------------------+  +------------------+  +------------------+                  |
|                                                                                    |
|  +------------------+  +------------------+  +------------------+                  |
|  |  Dashboard API   |  |   Backup API     |  |   Cache API      |                  |
|  |  /dashboard/*    |  |   /backup/*      |  |   /cache/*       |                  |
|  +------------------+  +------------------+  +------------------+                  |
|                                                                                    |
|  +------------------+  +------------------+  +------------------+                  |
|  | Custom Tokens    |  |   System API     |  |  Security API    |                  |
|  | /custom-tokens/* |  |   /system/*      |  |  /security/*     |                  |
|  +------------------+  +------------------+  +------------------+                  |
|                                                                                    |
|  +-----------------------------------------------------------------------+         |
|  |                  V2 Ingestion Engine (v1.5.0)                         |         |
|  |                  /engine/*  (11 endpoints)                            |         |
|  |  Backfill orchestration | Provider health | Event queries             |         |
|  +-----------------------------------------------------------------------+         |
|                                                                                    |
+-----------------------------------------------------------------------------------+
            |                     |                     |
            v                     v                     v
+-----------------------------------------------------------------------------------+
|                              Services Layer                                        |
+-----------------------------------------------------------------------------------+
|                                                                                    |
|  Blockchain Services (11 Chains):                                                |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  | Cardano  | | Bitcoin  | | Ethereum | | Solana   | | Polygon  | |   Base   |     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  +----------+ +----------+ +----------+ +----------+ +----------+                  |
|  | Algorand | |   BSC    | | Arbitrum | |Avalanche | |   Tron   |                  |
|  +----------+ +----------+ +----------+ +----------+ +----------+                  |
|  Note: BSC, Arbitrum, and Avalanche share the generic evm_chain.py service         |
|  Tron uses tron.py with TronGrid API (free, no key required)                       |
|                                                                                    |
|  Exchange Services:                                                               |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  | Coinbase | | Binance  | |Binance.US| |   OKX    | |  Bitget  | | Gate.io  |     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  +----------+                                                                      |
|  |  KuCoin  |                                                                      |
|  +----------+                                                                      |
|                                                                                    |
|  Core Services:                                                                   |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  | Pricing  | |   DeFi   | |   NFT    | | Snapshot | | Logging  | |HTTP Pool |     |
|  | (5 src)  | | Service  | | Service  | | Service  | | Service  | |(30 pools)|     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|                                                                                    |
|  V2 Engine Pipeline:                                                              |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  | Expand   | |  Index   | | Hydrate  | |Normalize | | Enrich   | |Positions |     |
|  |(4 chains)| |(5 adapt.)| |(5 adapt.)| |(4 chains)| |(3 types) | | (stubs)  |     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|                                                                                    |
|  Engine Infrastructure:                                                           |
|  +----------+ +----------+ +----------+ +----------+                               |
|  | Provider | | Token    | | Circuit  | | Work Unit|                               |
|  | Registry | | Bucket   | | Breaker  | | Scheduler|                               |
|  |(14 provs)| |(rate lim)| |(health)  | |(pipeline)|                               |
|  +----------+ +----------+ +----------+ +----------+                               |
|                                                                                    |
+-----------------------------------------------------------------------------------+
            |                     |                     |
            v                     v                     v
+-----------------------------------------------------------------------------------+
|                           External APIs                                            |
+-----------------------------------------------------------------------------------+
|                                                                                    |
|  Blockchain:                                                                      |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  |Blockfrost| |Blockstrm | |Etherscan | | Alchemy  | |  Helius  | | Pera API |     |
|  |(Cardano) | |(Bitcoin) | |(EVM)     | |(EVM 6ch) | |(Solana)  | |(Algorand)|     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  |CExplorer | | TapTools | | Moralis  | | BscScan  | | Arbiscan | | Snowscan |     |
|  |(Cardano) | |(Cardano) | |(NFTs)    | |(BSC)     | |(Arbitrum)| |(Avalanche)|    |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  +----------+                                                                      |
|  | TronGrid |                                                                      |
|  |(Tron/Free)|                                                                     |
|  +----------+                                                                      |
|                                                                                    |
|  Pricing:                                                                         |
|  +----------+ +----------+ +----------+ +----------+ +----------+                  |
|  |CoinGecko | |   CMC    | | Coinbase | |DefiLlama | | TapTools |                  |
|  |(primary) | |(fallback)| |(fallback)| |(fallback)| |(ADA only)|                  |
|  +----------+ +----------+ +----------+ +----------+ +----------+                  |
|                                                                                    |
|  Token Data:                                                                      |
|  +----------+ +----------+ +----------+ +----------+                               |
|  |The Graph | |Logostream| |  NMKR    | | NFT CDN  |                               |
|  |(Uniswap) | |(logos)   | |(minting) | |(images)  |                               |
|  +----------+ +----------+ +----------+ +----------+                               |
|                                                                                    |
+-----------------------------------------------------------------------------------+
            |
            v
+-----------------------------------------------------------------------------------+
|                              Database Layer                                        |
|                           (SQLite - portfolio.db)                                  |
+-----------------------------------------------------------------------------------+
|                                                                                    |
|  Authentication & Users:                                                          |
|  +------------------+  +------------------+  +------------------+                   |
|  |      users       |  |    sessions      |  |  password_reset  |                   |
|  +------------------+  +------------------+  +------------------+                   |
|                                                                                    |
|  Portfolio Data (User-Scoped):                                                    |
|  +------------------+  +------------------+  +------------------+                   |
|  |     wallets      |  |    balances      |  |  native_assets   |                   |
|  +------------------+  +------------------+  +------------------+                   |
|  +------------------+  +------------------+  +------------------+                   |
|  | portfolio_       |  | custom_tokens    |  |  api_settings    |                   |
|  | snapshots        |  +------------------+  +------------------+                   |
|  +------------------+  +------------------+                                         |
|                        | balance_history  |                                         |
|                        +------------------+                                         |
|                                                                                    |
|  V2 Engine Tables (v1.5.0):                                                       |
|  +------------------+  +------------------+  +------------------+                   |
|  | engine_          |  | engine_          |  | engine_          |                   |
|  | backfills        |  | account_subjects |  | tx_index         |                   |
|  +------------------+  +------------------+  +------------------+                   |
|  +------------------+  +------------------+  +------------------+                   |
|  | engine_          |  | engine_          |  | engine_          |                   |
|  | tx_raw           |  | events           |  | work_units       |                   |
|  +------------------+  +------------------+  +------------------+                   |
|  +------------------+  +------------------+                                         |
|  | engine_          |  | engine_          |                                         |
|  | provider_health  |  | price_history    |                                         |
|  +------------------+  +------------------+                                         |
|                                                                                    |
|  Shared Data:                                                                     |
|  +------------------+  +------------------+  +------------------+                   |
|  | nft_floor_       |  | token_metadata   |  |     cache        |                   |
|  | prices           |  |                  |  |                  |                   |
|  +------------------+  +------------------+  +------------------+                   |
|                                                                                    |
+-----------------------------------------------------------------------------------+
```

## V2 Ingestion Engine Architecture (v1.5.0)

The V2 engine is a 6-stage pipeline that replaces the V1 balance history system with provider-agnostic, resumable processing.

### Pipeline Stages

```
Wallet → [A] Expand → [B] Index → [C] Hydrate → [D] Normalize → [E] Enrich → [F] Positions
           │              │             │              │              │             │
           │              │             │              │              │             │
     Stake key →    Collect tx     Full tx        Raw tx →       Add prices    DeFi
     payment        IDs (cheap)    detail        canonical       & metadata    inference
     addresses                     (expensive)    events                       (stub)
```

Each stage produces work units stored in the database. If a provider fails mid-backfill, remaining work units are reassigned to another provider without restarting.

### Provider Registry

14 providers registered at startup with priority-based scoring:

```
Score = priority * health_factor * quota_factor * latency_factor
```

| Provider | Chains | Domains | Priority |
|----------|--------|---------|----------|
| blockfrost | Cardano | index, hydrate | 60 |
| cexplorer | Cardano | index | 30 |
| taptools | Cardano | enrich_metadata | 50 |
| blockstream | Bitcoin | index, hydrate | 60 |
| etherscan | Ethereum, Polygon, Base | index | 60 |
| alchemy | Ethereum, Polygon, Base | hydrate | 55 |
| public_rpc_evm | Ethereum, Polygon, Base | hydrate | 20 |
| helius | Solana | index, hydrate | 60 |
| public_rpc_solana | Solana | hydrate | 20 |
| **coinstats** | Bitcoin, ETH, SOL, Polygon, Base | index, hydrate | 40 |
| coingecko | ALL | enrich_price | 60 |
| cmc | ALL | enrich_price | 40 |
| defillama | ALL | enrich_price | 35 |

**CoinStats Cardano exclusion**: Enforced at three levels — registry (`excluded_chains`), indexer constructor, and hydrator constructor. CoinStats never receives Cardano work.

### Scheduler Components

**Token Bucket**: Per-provider rate limiter. `try_acquire()` is non-blocking; `wait_for_token()` blocks until a token is available. Each provider has its own bucket with configurable `rate` (tokens/sec) and `burst` (max tokens).

**Circuit Breaker**: Per-provider+chain+domain health tracking.
```
CLOSED (normal) → OPEN (5 consecutive failures) → HALF_OPEN (after 5 min) → CLOSED (1 success)
```
When a circuit is OPEN, the scheduler automatically falls back to the next available provider.

**Bulkheads**: `asyncio.Semaphore` per provider limiting concurrent requests (e.g., Blockfrost max 5 concurrent, TapTools max 1).

### Work Unit Lifecycle

```
pending → assigned → running → completed
                            └→ retry (if attempt < max_attempts)
                            └→ failed (if attempt >= max_attempts)
```

Work units are portable — any compatible provider can execute them. The scheduler picks providers based on health, rate limit availability, and priority score.

### Engine Database Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `engine_backfills` | Top-level backfill jobs | chains, domains, status, progress_pct |
| `engine_account_subjects` | Expanded accounts per wallet | chain, account_id, account_type |
| `engine_tx_index` | Transaction IDs per account | chain, account_id, tx_id, block_time |
| `engine_tx_raw` | Cached full transaction data | chain, tx_id, raw_data (JSON), provider |
| `engine_events` | Canonical ledger events | chain, tx_id, event_index, asset_id, amount, direction |
| `engine_work_units` | Portable job queue | backfill_id, chain, domain, status, assigned_provider |
| `engine_provider_health` | Provider health tracking | provider_name, chain, domain, consecutive_failures |
| `engine_price_history` | Cached historical prices | asset_id, date, price_usd, source |

### Idempotency

Events use composite unique keys to prevent duplicates on re-processing:
- **EVM**: `(chain, tx_hash, log_index, account_id, direction)`
- **UTXO** (Bitcoin/Cardano): `(chain, txid, vout/vin_index, account_id, direction)`
- **Solana**: `(chain, signature, instruction_index, account_id, direction)`

---

## Authentication Flow

```
+-------------+                                      +-------------+
|   Browser   |                                      |   Backend   |
+-------------+                                      +-------------+
      |                                                    |
      |  1. POST /auth/login                              |
      |    {username, password}                           |
      |-------------------------------------------------->|
      |                                                   |
      |                                    2. Verify      |
      |                                       bcrypt hash |
      |                                                   |
      |  3. Set-Cookie: session_token=...                 |
      |<--------------------------------------------------|
      |                                                   |
      |  4. GET /portfolio/summary                        |
      |    Cookie: session_token=...                      |
      |-------------------------------------------------->|
      |                                                   |
      |                               5. verify_session() |
      |                                  Check sessions   |
      |                                  table, get       |
      |                                  user_id          |
      |                                                   |
      |  6. Return user-scoped data                       |
      |<--------------------------------------------------|
      |                                                   |
```

## Demo Mode Architecture

```
+-------------+                                      +-------------+
| Demo User   |                                      |   Backend   |
+-------------+                                      +-------------+
      |                                                    |
      |  Login with demo/demo                             |
      |-------------------------------------------------->|
      |                                                   |
      |                              Check users.is_demo  |
      |                                                   |
      |  Set session with is_demo flag                    |
      |<--------------------------------------------------|
      |                                                   |
      |  API Request (e.g., /wallets)                     |
      |-------------------------------------------------->|
      |                                                   |
      |                       if is_demo_user(user_id):   |
      |                         return demo_wallet_       |
      |                         service.get_wallets()     |
      |                       else:                       |
      |                         call real APIs            |
      |                                                   |
      |  Mocked data (no real API calls)                  |
      |<--------------------------------------------------|
      |                                                   |
```

Demo mode includes: 91 tokens across 11 blockchains, 76 NFTs across 7 collections, 1,500 transactions over 1 year of history, DeFi positions, and exchange balances.

## Pricing Fallback Chain

```
CoinGecko (primary, 60s cooldown on 429)
    ↓ fail
CoinMarketCap
    ↓ fail
Coinbase (spot prices)
    ↓ fail
DefiLlama
    ↓ fail
TapTools (Cardano only)
    ↓ all fail
Stale cache backup
```

## HTTP Client Pool

Shared persistent `httpx.AsyncClient` instances via `get_client(name, timeout)`:
- 30+ named pools across 36+ files
- `fetch_with_retry()` for CoinGecko with exponential backoff
- `close_all()` called on app shutdown
- Connection reuse eliminates per-request TCP/TLS overhead

## Cache TTL Tiers

| Tier | TTL | Use Cases |
|------|-----|-----------|
| HOT | 300s (5 min) | Prices, exchange data, balances |
| WARM | 3600s (1 hr) | Analytics, charts, breakdowns |
| COLD | 86400s (24 hr) | NFT data, DeFi positions |
| PERSISTENT | 604800s (7 days) | Portfolio summary |

## Technology Stack

### Backend
- **FastAPI**: Modern Python web framework with async support
- **SQLite**: Embedded database with WAL mode for concurrent reads
- **aiosqlite**: Async database operations
- **httpx**: Shared async HTTP client pool (30+ named connections)
- **Pydantic**: Data validation and serialization
- **bcrypt**: Password hashing
- **GZip middleware**: Response compression (min 1000 bytes)

### Frontend
- **HTML5/CSS3**: Modern responsive design
- **Vanilla JavaScript**: No framework dependencies
- **Chart.js v4.4.1**: Portfolio charts and asset breakdowns
- **TradingView Lightweight Charts**: Price chart visualization
- **DOMPurify v3.0.8**: XSS protection on all dynamic HTML
- **5 Themes**: Dark Mode (default), Light, Cypherpunk 1, Ocean Depths, Sunset Horizon
- **Cache Busting**: Build version system (v=1770726755) for immediate updates

### External Services (19 providers)
- **Cardano**: Blockfrost, CExplorer, TapTools, Koios
- **Bitcoin**: Blockstream
- **EVM**: Etherscan, Alchemy, Polygonscan, Basescan, BscScan, Arbiscan, Snowscan
- **Solana**: Helius
- **Algorand**: Pera Wallet API, Tatum
- **Tron**: TronGrid (free, no API key required)
- **Pricing**: CoinGecko, CoinMarketCap, Coinbase, DefiLlama
- **Exchanges**: Coinbase CDP, Binance, Binance.US, OKX, Bitget, Gate.io, KuCoin

## Security Architecture

```
+-----------------------------------------------------------------------------------+
|                              Security Layers                                       |
+-----------------------------------------------------------------------------------+
|                                                                                    |
|  1. Authentication Layer                                                          |
|     - Session-based auth with secure tokens                                      |
|     - bcrypt password hashing                                                    |
|     - Session expiration (24 hours)                                              |
|     - Demo mode isolation                                                        |
|                                                                                    |
|  2. Input Validation                                                             |
|     - Pydantic models for all endpoints                                          |
|     - Address validation per blockchain                                          |
|     - Request size limiting middleware                                           |
|                                                                                    |
|  3. XSS Protection                                                               |
|     - DOMPurify sanitization on all innerHTML operations                         |
|     - CSP headers (if configured)                                                |
|                                                                                    |
|  4. Data Isolation                                                               |
|     - User ID verification on all data access                                    |
|     - SQL injection prevention via parameterized queries                         |
|                                                                                    |
|  5. API Security                                                                 |
|     - API keys stored per-user in database                                       |
|     - Rate limiting per API provider                                             |
|     - Read-only blockchain access (no transaction signing)                       |
|     - Circuit breakers prevent cascading failures (v1.5.0)                       |
|                                                                                    |
+-----------------------------------------------------------------------------------+
```

## Data Isolation

```
User A (user_id=1):
+------------------+
| wallets          |  WHERE user_id = 1
| balances         |  WHERE user_id = 1
| native_assets    |  WHERE user_id = 1
| engine_events    |  WHERE user_id = 1
| engine_backfills |  WHERE user_id = 1
+------------------+

Demo User (user_id=13, is_demo=1):
+------------------+
| wallets          |  WHERE user_id = 13
| balances         |  Mock data returned
| native_assets    |  Mock data returned
+------------------+
```

## SQLite Optimizations

- **WAL mode**: Enabled in `database.py` for concurrent reads during writes
- **Indexes**: `idx_wallets_user_blockchain` for fast wallet lookups
- **Expired cache cleanup**: Runs on startup
- **Engine table indexes**: Composite unique constraints on all engine tables for dedup
- **GZip middleware**: Compresses responses over 1000 bytes

## File Structure

```
ABCT/
├── backend/
│   ├── main.py                     # FastAPI application entry
│   ├── auth_utils.py               # Session authentication utilities
│   ├── database.py                 # Database operations + schema
│   ├── config.py                   # Configuration management
│   ├── routers/                    # 26 API endpoint routers
│   │   ├── auth.py                 # Authentication endpoints
│   │   ├── portfolio.py            # Portfolio endpoints
│   │   ├── wallets.py              # Wallet management
│   │   ├── prices.py               # Price data
│   │   ├── defi.py                 # DeFi/staking
│   │   ├── exchanges.py            # Exchange balances
│   │   ├── nfts.py                 # NFT endpoints
│   │   ├── nft_scheduler.py        # NFT background scheduler
│   │   ├── transactions.py         # Transaction history
│   │   ├── balance_history.py      # Balance history charts
│   │   ├── engine.py               # V2 Ingestion Engine (v1.5.0+)
│   │   ├── dashboard.py            # Dashboard aggregation
│   │   ├── backup.py               # Backup/restore
│   │   ├── cache.py                # Cache management
│   │   ├── custom_tokens.py        # Custom tokens
│   │   ├── spam.py                 # Spam token filtering
│   │   ├── system.py               # System health
│   │   ├── settings.py             # Application settings
│   │   ├── security.py             # Security settings
│   │   ├── logs.py                 # Log viewer
│   │   ├── demo.py                 # Demo mode
│   │   ├── nmkr.py                 # NMKR minting
│   │   ├── cloudflare.py           # Cloudflare tunnel
│   │   └── mobile.py               # Mobile API
│   ├── engine/                     # V2 Ingestion Engine (v1.5.0+)
│   │   ├── models.py               # ChainId, WorkUnit, CanonicalEvent
│   │   ├── db.py                   # 8 engine_* tables
│   │   ├── orchestrator.py         # Pipeline orchestration
│   │   ├── expansion/              # Stage A (4 chain expanders)
│   │   ├── indexing/               # Stage B (5 indexer adapters)
│   │   ├── hydration/              # Stage C (5 hydrator adapters)
│   │   ├── normalization/          # Stage D (4 chain normalizers)
│   │   ├── enrichment/             # Stage E (3 enrichers)
│   │   ├── positions/              # Stage F (2 stubs)
│   │   ├── providers/              # Registry + Provider dataclass
│   │   └── scheduler/              # Scheduler + TokenBucket + CircuitBreaker
│   ├── services/                   # 50+ business logic services
│   │   ├── http_client.py          # Shared HTTP client pool
│   │   ├── api_key_manager.py      # Dynamic API key management
│   │   ├── pricing.py              # 5-source pricing fallback
│   │   ├── cardano.py              # Cardano blockchain
│   │   ├── bitcoin.py              # Bitcoin blockchain
│   │   ├── ethereum.py             # Ethereum blockchain
│   │   ├── solana.py               # Solana blockchain
│   │   ├── polygon.py              # Polygon blockchain
│   │   ├── base.py                 # Base blockchain
│   │   ├── algorand.py             # Algorand blockchain
│   │   ├── evm_chain.py           # Generic EVM (BSC, Arbitrum, Avalanche)
│   │   ├── tron.py                # Tron blockchain (TronGrid)
│   │   └── ...                     # Exchange, NFT, demo services
│   └── middleware/                 # Security middleware
├── frontend/                      # HTML/CSS/JS (17 pages)
│   ├── index.html                 # Dashboard
│   ├── wallets.html               # Wallet management
│   ├── assets.html                # Asset breakdown
│   ├── transactions.html          # Transaction history
│   ├── nft-wall.html              # NFT gallery
│   ├── settings.html              # Consolidated settings
│   ├── system.html                # System management
│   ├── login.html                 # Login
│   └── css/styles.css             # 5 themes, 7000+ lines
├── data/
│   └── portfolio.db               # SQLite (includes engine_* tables)
└── docs/
    ├── ARCHITECTURE.md             # This file
    ├── API_PROVIDERS.md            # Provider details
    └── DOCKER_DEPLOYMENT.md        # Docker setup
```

## Deployment Options

### Local Development
```bash
./run.sh
# or
source venv/bin/activate && cd backend && uvicorn main:app --reload
```

### Production (Docker)
```bash
cd abct-docker && docker-compose up -d
```

### Guided Deployment
```bash
./deploy.sh   # Interactive deployment with version bumping
```

## Performance Considerations

- **Database**: SQLite with WAL mode for concurrent access
- **Caching**: Tiered TTLs (5 min to 7 days) based on data volatility
- **Async Operations**: All I/O operations are async (FastAPI + httpx + aiosqlite)
- **Connection Pooling**: 30+ named HTTP client pools with connection reuse
- **Rate Limiting**: Per-provider token buckets prevent API exhaustion
- **Circuit Breakers**: Auto-pause failing providers, prevent cascading failures
- **GZip Compression**: Response compression for payloads over 1000 bytes
- **Parallel Loading**: Frontend loads data concurrently with `Promise.all`
- **Lazy NFTs**: NFT images loaded on-demand, not at page load
