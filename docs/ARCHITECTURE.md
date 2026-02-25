# ABCT Architecture (v1.15.2)

## System Overview

```
+-----------------------------------------------------------------------------------+
|                              ABCT System (v1.15.2)                                 |
|                         Multi-User Portfolio Tracker                              |
|                              BUILD 1771794638                                     |
|              53 Chains | 42 Exchanges | 80+ DeFi Protocols | P&L Engine           |
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
|  +------------------+  +------------------+  +------------------+                  |
|  |  Privacy API     |  |  Images API      |  |  Search API      |                  |
|  |  /privacy/*      |  |  /images/*       |  |  /search/*       |                  |
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
|  Blockchain Services (53 Chains):                                                |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  | Cardano  | | Bitcoin  | | Ethereum | | Solana   | | Polygon  | |   Base   |     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  | Algorand | |   BSC    | | Arbitrum | |Avalanche | |   Tron   | |   XRP    |     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  | Hedera   | |MultversX | |   Sui    | |  Aptos   | | Filecoin | | Litecoin |     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  | Dogecoin | |  Zcash   | |  Tezos   | |  Stacks  | | VeChain  | |  Cosmos  |     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  +----------+ +----------+ +----------+ +----------+                                 |
|  |   NEAR   | |   ICP    | |  Monero  | |  Secret  |                                 |
|  +----------+ +----------+ +----------+ +----------+                                 |
|  EVM Chains (all via generic evm_chain.py):                                        |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  | Optimism | | zkSync   | |  Linea   | |  Scroll  | | Fantom   | |  Cronos  |     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  +----------+ +----------+                                                          |
|  |  Gnosis  | |Moonbeam  |                                                          |
|  +----------+ +----------+                                                          |
|  Cosmos IBC Chains (v1.14.0+ — shared cosmos_chain.py via LCD REST API):            |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  | Osmosis  | | Celestia | |Injective | |  dYdX    | |   Sei    | |  Akash   |     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  Substrate Chains (v1.14.0+ — shared substrate_service.py via Subscan API):         |
|  +----------+ +----------+                                                          |
|  |Polkadot  | | Kusama   |                                                          |
|  +----------+ +----------+                                                          |
|  Major L1 Additions (v1.14.0+):                                                     |
|  +----------+ +----------+ +----------+                                             |
|  |   TON    | | Stellar  | |  Kaspa   |                                             |
|  +----------+ +----------+ +----------+                                             |
|  Additional Chains (v1.14.0+):                                                      |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  |  Kaia    | |  Ergo    | |  IOTA    | |  Waves   | |  Mina    | | Zilliqa  |     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  Note: BSC, Arbitrum, Avalanche, Optimism, zkSync, Linea, Scroll, Fantom,          |
|  Cronos, Gnosis, Moonbeam, and Kaia all use the generic evm_chain.py service       |
|  Cosmos IBC chains use cosmos_chain.py (config-driven, free LCD endpoints)         |
|  Polkadot/Kusama use substrate_service.py (Subscan API, optional key)              |
|  TON uses ton_service.py (TON Center API, optional key)                            |
|  Stellar uses stellar_service.py (Horizon API, free, no key required)              |
|  Tron uses tron.py with TronGrid API (free, no key required)                       |
|  XRP, Hedera, MultiversX, Sui, Aptos, and Filecoin use free public APIs (no key)   |
|  Litecoin and Dogecoin use BlockCypher API (free, no key required)                 |
|  Zcash uses Blockchair API (free, no key required)                                 |
|  Tezos uses TzKT API (free, no key required) - has tokens + NFTs                  |
|  Stacks uses Hiro API (free, no key required) - has tokens + NFTs                  |
|  VeChain uses VeBlocks/Thor API (free, no key required) - has VTHO token           |
|  Cosmos uses Cosmos LCD/PublicNode (free, no key required) - IBC tokens + staking  |
|  NEAR uses NEAR RPC + NearBlocks API (free, no key required) - tokens + NFTs       |
|  ICP uses Rosetta API (free, no key required) - balance only                       |
|  Monero uses monero.py - manual balance only (ring signatures make API             |
|    fetch impossible), user sets balance via POST /privacy/monero/set-balance       |
|  Secret Network uses secret_network.py - SecretSaturn LCD API (free, no key)       |
|  DeFi service includes Chainlink Staking (Ethereum contract reads via Alchemy)     |
|                                                                                    |
|  Exchange Services (42 Exchanges via BaseExchangeService + 5 auth mixins):        |
|  Original (7): Coinbase, Binance, Binance.US, OKX, Bitget, Gate.io, KuCoin        |
|  New (35): Bybit, MEXC, HTX, BingX (Binance-style HMAC-SHA256)                    |
|           Phemex, WOO X, AscendEX (OKX-style HMAC-SHA256 base64)                 |
|           Kraken, CoinSpot (Gate-style HMAC-SHA512)                               |
|           Gemini, Bitfinex, BTSE (Gemini-style HMAC-SHA384)                       |
|           Poloniex, Crypto.com, Bitstamp, Bitmart, Upbit, Pionex,                 |
|           Robinhood, Deribit, Backpack, CoinEx, LBank, ProBit, HitBTC,            |
|           Bitrue, WhiteBIT, Digifinex, CoinW, BitFlyer, Bitpanda,                 |
|           Bitvavo, Swyftx, Independent Reserve, XT.com                            |
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
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  | TronGrid | | XRPL RPC | |Hedera    | |MultversX | | Sui RPC  | |Aptos API |     |
|  |(Tron/Free)| |(XRP/Free)| |Mirror API| |  (Free)  | | (Free)   | | (Free)   |     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  | Glif RPC | |BlockCyph.| |Blockchair| | TzKT API | | Hiro API | |VeBlocks  |     |
|  |(FIL/Free)| |(LTC/DOGE)| |(ZEC/Free)| |(XTZ/Free)| |(STX/Free)| |(VET/Free)|     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  +----------+ +----------+ +----------+ +----------+                                 |
|  |Cosmos LCD| | NEAR RPC | |Rosetta   | |SecretSat.|                                 |
|  |(ATOM/Free)| |(NEAR/Free)| |(ICP/Free)| |(SCRT/Free)|                                 |
|  +----------+ +----------+ +----------+ +----------+                                 |
|  New APIs (v1.14.0):                                                              |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  |TON Center| | Horizon  | | Subscan  | |Cosmos LCD| | Public   | | Misc     |     |
|  |(TON/opt) | |(Stellar) | |(DOT/KSM) | |(IBC/Free)| | RPCs     | | APIs     |     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|                                                                                    |
|  Pricing:                                                                         |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|  |CoinGecko | |   CMC    | | Coinbase | |CoinPprika| |DefiLlama | | TapTools |     |
|  |(primary) | |(fallback)| |(fallback)| |(free/25k)| |(fallback)| |(ADA only)|     |
|  +----------+ +----------+ +----------+ +----------+ +----------+ +----------+     |
|                                                                                    |
|  Token Data:                                                                      |
|  +----------+ +----------+ +----------+ +----------+ +----------+                  |
|  |The Graph | |Logostream| |  NMKR    | | NFT CDN  | |Img Cache |                  |
|  |(Uniswap) | |(logos)   | |(minting) | |(images)  | |(local)   |                  |
|  +----------+ +----------+ +----------+ +----------+ +----------+                  |
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

Demo mode includes: 91 tokens across 26 blockchains, 76 NFTs across 7 collections, 1,500 transactions over 1 year of history, DeFi positions, and exchange balances.

## Pricing Fallback Chain

```
CoinGecko (primary, 60s cooldown on 429)
    ↓ fail
CoinMarketCap
    ↓ fail
Coinbase (spot prices)
    ↓ fail
CoinPaprika (free, no API key, 25k calls/month)
    ↓ fail
DefiLlama
    ↓ fail
TapTools (Cardano only)
    ↓ all fail
Stale cache backup
```

## Exchange Service Architecture

All 42 exchanges extend `BaseExchangeService` (`services/base_exchange.py`) with auth mixins:

| Auth Mixin | Algorithm | Exchanges |
|-----------|-----------|-----------|
| `BinanceStyleAuth` | HMAC-SHA256 query string | Bybit, MEXC, HTX, BingX, Bitrue, Pionex, XT, CoinW, Digifinex, LBank, ProBit, CoinEx, Bitmart, WhiteBIT, HitBTC |
| `OKXStyleAuth` | HMAC-SHA256 base64 header | Phemex, WOO X, AscendEX |
| `GateStyleAuth` | HMAC-SHA512 | Kraken, CoinSpot |
| `GeminiStyleAuth` | HMAC-SHA384 payload | Gemini, Bitfinex, BTSE |
| Custom | JWT, Ed25519, Bearer, OAuth2, Basic | Coinbase (Ed25519), Robinhood (OAuth2), Deribit (Bearer), Backpack (Ed25519), Poloniex, Crypto.com, Bitstamp, Upbit, Bitflyer, Bitpanda, Bitvavo, Swyftx, IndependentReserve |

`ExchangeRegistry` auto-wires new exchanges into `/exchanges/status`, `/exchanges/all`, and creates individual `GET /exchanges/{name}/balances` endpoints. Adding a new exchange requires only: create `{name}_service.py`, extend `BaseExchangeService`, register in the router.

## DeFi Protocol Detection

Protocol adapters implement `ProtocolAdapter` ABC (`services/defi_protocols/base_adapter.py`) with 5 detection methods:

| Method | Enum | Use Case | Example Protocols |
|--------|------|----------|-------------------|
| Token balance | `TOKEN_BALANCE` | Check ERC-20/SPL receipt tokens | stETH, rETH, mSOL, jitoSOL |
| Contract call | `CONTRACT_CALL` | Query smart contract state | Aave, Compound, Maker, Spark |
| UTXO scan | `UTXO_SCAN` | Scan UTXOs for protocol assets | Minswap, Liqwid, Indigo (Cardano) |
| NFT position | `NFT_POSITION` | NFT-based LP positions | Uniswap v3, Orca (concentrated) |
| Program account | `PROGRAM_ACCOUNT` | Solana program accounts | Marinade, Drift, MarginFi, Kamino |

`ProtocolRegistry` provides auto-discovery: adapters self-register at import time via `__init__.py` exports. Detection runs in parallel with per-adapter timeouts. Current coverage:

- **Cardano** (13): Minswap, SundaeSwap V3, WingRiders, Splash, Djed, FluidTokens, Lenfi, MuesliSwap, Liqwid, Indigo, Strike Finance, Surf Protocol, Iagon
- **EVM** (55+ protocols): Aave v3, Compound v3, Uniswap v3 LP, Curve, Balancer, EigenLayer, Maker/Spark, Morpho, GMX, Pendle, Stargate, Aerodrome, Velodrome, Radiant, Benqi, SushiSwap, Yearn v3, Beefy, Synthetix, Liquity, Camelot, Abracadabra, PancakeSwap v3, `token_balance_adapters.py` (liquid staking tokens: stETH, rETH, wstETH, cbETH, swETH, rswETH, ezETH), and more
- **Solana** (15): Marinade, Jito, Blazestake, Sanctum, Orca, Raydium, Lifinity, Meteora, Drift, MarginFi, Kamino, Jupiter Perps, Phoenix, Solend, Tulip

## P&L Analytics

`CostBasisEngine` (`services/cost_basis_engine.py`) tracks cost basis lots from exchange transactions and wallet history:

- **Ingestion**: Imports buy/sell/deposit/withdrawal transactions from `exchange_transactions` table into `cost_basis_lots`
- **Lot disposal**: FIFO (first in, first out), LIFO (last in, first out), or Average Cost matching
- **Realized gains**: Stored in `realized_gains` table with per-lot detail
- **Unrealized gains**: Computed on demand by comparing open lots against current prices
- **Summary table**: `asset_pnl_summary` materialized for fast portfolio performance queries

Endpoints: `GET /pnl/summary`, `GET /pnl/assets`, `POST /pnl/ingest`, `GET /pnl/method`

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

### External Services (40+ providers)
- **Cardano**: Blockfrost, CExplorer, TapTools, Koios, Maestro (fallback)
- **Bitcoin**: Blockstream
- **EVM (original)**: Etherscan, Alchemy, Polygonscan, Basescan, BscScan, Arbiscan, Snowscan
- **EVM (new chains)**: Optimism public RPC, zkSync RPC, Linea RPC, Scroll RPC, Fantom public RPC, Cronos RPC, Gnosis RPC, Moonbeam RPC — all via evm_chain.py
- **Solana**: Helius
- **Algorand**: Pera Wallet API, Tatum
- **Tron**: TronGrid (free, no API key required)
- **XRP**: XRPL JSON-RPC (free, no API key required)
- **Hedera**: Mirror Node REST API (free, no API key required)
- **MultiversX**: MultiversX API (free, no API key required)
- **Sui**: Sui JSON-RPC (free, no API key required)
- **Aptos**: Aptos REST API (free, no API key required)
- **Filecoin**: Glif RPC (free, no API key required)
- **Litecoin**: BlockCypher API (free, no API key required)
- **Dogecoin**: BlockCypher API (free, no API key required)
- **Zcash**: Blockchair API (free, no API key required)
- **Tezos**: TzKT API (free, no API key required)
- **Stacks**: Hiro API (free, no API key required)
- **VeChain**: VeBlocks/Thor API (free, no API key required)
- **Cosmos**: Cosmos LCD/PublicNode (free, no API key required)
- **NEAR**: NEAR RPC + NearBlocks API (free, no API key required)
- **ICP**: Rosetta API (free, no API key required)
- **TON**: TON Center API (optional API key for higher rate limits)
- **Stellar**: Horizon API (free, no API key required)
- **Polkadot/Kusama**: Subscan REST API (optional API key for higher rate limits)
- **Cosmos IBC** (Osmosis, Celestia, Injective, dYdX, Sei, Akash): Public LCD endpoints (free, no API key required)
- **Kaspa, Ergo, IOTA, Waves, Mina, Zilliqa, Kaia**: Public chain REST APIs (free, no API key required)
- **Monero**: Manual balance only (ring signatures make API fetch impossible)
- **Secret Network**: SecretSaturn LCD API (free, no API key required)
- **DeFi**: Chainlink Staking via Alchemy (Ethereum contract reads)
- **Privacy Detection**: Railgun contract interaction detection (ETH/Polygon/BSC/Arbitrum via Etherscan)
- **Pricing**: CoinGecko, CoinMarketCap, Coinbase, CoinPaprika, DefiLlama
- **Exchanges**: 42 exchanges via BaseExchangeService with 5 auth method families

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
│   ├── routers/                    # 30 API endpoint routers
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
│   │   ├── mobile.py               # Mobile API
│   │   ├── analytics.py            # Analytics endpoints
│   │   ├── intelligence.py         # Intelligence endpoints
│   │   ├── privacy.py              # Privacy & ZK endpoints
│   │   ├── images.py               # Token image cache
│   │   ├── search.py               # Search endpoints
│   │   └── pnl.py                  # P&L cost basis reporting
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
│   ├── services/                   # 100+ business logic services
│   │   ├── http_client.py          # Shared HTTP client pool
│   │   ├── api_key_manager.py      # Dynamic API key management
│   │   ├── pricing.py              # 5-source pricing fallback
│   │   ├── base_exchange.py        # BaseExchangeService + 5 auth mixins
│   │   ├── cost_basis_engine.py    # P&L: FIFO/LIFO/Average cost basis
│   │   ├── cardano.py              # Cardano blockchain
│   │   ├── bitcoin.py              # Bitcoin blockchain
│   │   ├── ethereum.py             # Ethereum blockchain
│   │   ├── solana.py               # Solana blockchain
│   │   ├── polygon.py              # Polygon blockchain
│   │   ├── base.py                 # Base blockchain
│   │   ├── algorand.py             # Algorand blockchain
│   │   ├── evm_chain.py           # Generic EVM (BSC, Arbitrum, Avalanche,
│   │   │                           #   Optimism, zkSync, Linea, Scroll,
│   │   │                           #   Fantom, Cronos, Gnosis, Moonbeam)
│   │   ├── tron.py                # Tron blockchain (TronGrid)
│   │   ├── xrp.py                 # XRP Ledger (XRPL JSON-RPC)
│   │   ├── hedera.py              # Hedera (Mirror Node REST API)
│   │   ├── multiversx.py          # MultiversX (MultiversX API)
│   │   ├── sui.py                 # Sui (Sui JSON-RPC)
│   │   ├── aptos.py               # Aptos (Aptos REST API)
│   │   ├── filecoin.py            # Filecoin (Glif RPC)
│   │   ├── litecoin.py            # Litecoin (BlockCypher API)
│   │   ├── dogecoin.py            # Dogecoin (BlockCypher API)
│   │   ├── zcash.py               # Zcash (Blockchair API)
│   │   ├── tezos.py               # Tezos (TzKT API)
│   │   ├── stacks.py              # Stacks (Hiro API)
│   │   ├── vechain.py             # VeChain (VeBlocks/Thor API)
│   │   ├── cosmos.py              # Cosmos (Cosmos LCD/PublicNode)
│   │   ├── cosmos_chain.py        # Cosmos IBC chains (config-driven LCD)
│   │   ├── near.py                # NEAR (NEAR RPC + NearBlocks API)
│   │   ├── icp.py                 # ICP (Rosetta API)
│   │   ├── ton_service.py         # TON (TON Center API)
│   │   ├── stellar_service.py     # Stellar (Horizon API)
│   │   ├── substrate_service.py   # Polkadot/Kusama (Subscan API)
│   │   ├── kaspa_service.py       # Kaspa (public REST API)
│   │   ├── ergo_service.py        # Ergo (public REST API)
│   │   ├── iota_service.py        # IOTA (public REST API)
│   │   ├── waves_service.py       # Waves (public REST API)
│   │   ├── mina_service.py        # Mina (public REST API)
│   │   ├── zilliqa_service.py     # Zilliqa (public REST API)
│   │   ├── monero.py              # Monero (manual balance only)
│   │   ├── secret_network.py     # Secret Network (SecretSaturn LCD)
│   │   ├── privacy_detector.py   # Railgun privacy contract detection
│   │   ├── coinpaprika.py        # CoinPaprika pricing fallback
│   │   ├── image_cache.py        # Token image caching service
│   │   ├── token_metadata_cache.py  # Token metadata cache (SQLite)
│   │   ├── helium.py              # Helium (DePIN tracking)
│   │   ├── charli3.py             # Charli3 oracle service
│   │   ├── tradfi_data.py         # TradFi data integration
│   │   ├── chain_analytics.py     # Chain analytics service
│   │   ├── offchain_collector.py  # Off-chain data collector
│   │   ├── nftcdn.py              # NFT CDN image service
│   │   ├── balance_history.py     # Balance history service
│   │   ├── api_health.py          # API health monitoring
│   │   ├── rate_limit_tracker.py  # Rate limit tracking
│   │   ├── known_addresses.py     # Known address labels
│   │   ├── defi_protocols/        # DeFi protocol adapters (100+ protocols)
│   │   │   ├── base_adapter.py    # ProtocolAdapter ABC + DetectionMethod enum
│   │   │   ├── registry.py        # ProtocolRegistry with auto-discovery
│   │   │   ├── cardano/           # 13 Cardano adapters (UTXO_SCAN method)
│   │   │   ├── evm/               # 55+ EVM protocols (TOKEN_BALANCE/CONTRACT_CALL/NFT_POSITION)
│   │   │   └── solana/            # 15 Solana adapters (PROGRAM_ACCOUNT method)
│   │   └── *_service.py           # 41 exchange service files (+ coinbase.py = 42)
│   └── middleware/                 # Security middleware
├── frontend/                      # HTML/CSS/JS (19 pages)
│   ├── index.html                 # Dashboard
│   ├── wallets.html               # Wallet management
│   ├── assets.html                # Asset breakdown
│   ├── transactions.html          # Transaction history
│   ├── nft-wall.html              # NFT gallery
│   ├── settings.html              # Consolidated settings
│   ├── system.html                # System management
│   ├── login.html                 # Login
│   ├── privacy.html               # Privacy & ZK features
│   ├── api-help.html              # API help documentation
│   ├── dashv2.html                # Dashboard V2
│   ├── data.html                  # Data management
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
