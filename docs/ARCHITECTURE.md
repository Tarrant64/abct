# ABCT Architecture Diagram

## System Overview

```
+-----------------------------------------------------------------------------------+
|                                    ABCT System                                     |
+-----------------------------------------------------------------------------------+

                                   +-----------------+
                                   |   Frontend UI   |
                                   |   (Browser)     |
                                   +--------+--------+
                                            |
                                            | HTTP/REST
                                            v
+-----------------------------------------------------------------------------------+
|                              FastAPI Backend Server                                |
|                                   (main.py)                                        |
+-----------------------------------------------------------------------------------+
|                                                                                    |
|  +------------------+  +------------------+  +------------------+                  |
|  |  Portfolio API   |  |   Wallets API    |  |   Prices API     |                  |
|  | /portfolio/*     |  |   /wallets/*     |  |   /prices/*      |                  |
|  +--------+---------+  +--------+---------+  +--------+---------+                  |
|           |                     |                     |                            |
|  +--------+---------+  +--------+---------+  +--------+---------+                  |
|  |    DeFi API      |  |  Exchanges API   |  |    NFTs API      |                  |
|  |    /defi/*       |  |  /exchanges/*    |  |    /nfts/*       |                  |
|  +--------+---------+  +--------+---------+  +--------+---------+                  |
|           |                     |                     |                            |
+-----------------------------------------------------------------------------------+
            |                     |                     |
            v                     v                     v
+-----------------------------------------------------------------------------------+
|                              Services Layer                                        |
+-----------------------------------------------------------------------------------+
|                                                                                    |
|  +---------------+  +---------------+  +---------------+  +---------------+        |
|  |   Cardano     |  |   Bitcoin     |  |   Ethereum    |  |   Pricing     |        |
|  |   Service     |  |   Service     |  |   Service     |  |   Service     |        |
|  +-------+-------+  +-------+-------+  +-------+-------+  +-------+-------+        |
|          |                  |                  |                  |                |
|  +-------+-------+  +-------+-------+  +-------+-------+  +-------+-------+        |
|  |    DeFi       |  |   Coinbase    |  |     NFT       |  |   Snapshot    |        |
|  |   Service     |  |   Service     |  |   Service     |  |   Service     |        |
|  +-------+-------+  +-------+-------+  +-------+-------+  +-------+-------+        |
|                                                                                    |
+-----------------------------------------------------------------------------------+
            |                     |                     |
            v                     v                     v
+-----------------------------------------------------------------------------------+
|                           External APIs                                            |
+-----------------------------------------------------------------------------------+
|                                                                                    |
|  +---------------+  +---------------+  +---------------+  +---------------+        |
|  |  Blockfrost   |  |  Blockstream  |  |   Etherscan   |  |  CoinGecko    |        |
|  |  (Cardano)    |  |  (Bitcoin)    |  |  (Ethereum)   |  |  (Prices)     |        |
|  +---------------+  +---------------+  +---------------+  +---------------+        |
|                                                                                    |
|  +---------------+  +---------------+  +---------------+  +---------------+        |
|  |   TapTools    |  |   Coinbase    |  |   CExplorer   |  |    Koios      |        |
|  |   (NFTs)      |  |  (Exchange)   |  |  (Staking)    |  |  (Cardano)    |        |
|  +---------------+  +---------------+  +---------------+  +---------------+        |
|                                                                                    |
+-----------------------------------------------------------------------------------+
            |
            v
+-----------------------------------------------------------------------------------+
|                              Database Layer                                        |
|                           (SQLite - portfolio.db)                                  |
+-----------------------------------------------------------------------------------+
|                                                                                    |
|  +------------------+  +------------------+  +------------------+                   |
|  |     wallets      |  |    balances      |  |  native_assets   |                   |
|  +------------------+  +------------------+  +------------------+                   |
|                                                                                    |
|  +------------------+  +------------------+  +------------------+                   |
|  | portfolio_       |  | nft_floor_       |  |     cache        |                   |
|  | snapshots        |  | prices           |  |                  |                   |
|  +------------------+  +------------------+  +------------------+                   |
|                                                                                    |
+-----------------------------------------------------------------------------------+
```

## Data Flow Diagram

```
+-------------+     +-------------+     +-------------+     +-------------+
|   User      |---->|  Frontend   |---->|   FastAPI   |---->|  Services   |
|  Browser    |     |  (HTML/JS)  |     |   Backend   |     |   Layer     |
+-------------+     +-------------+     +-------------+     +------+------+
                                                                   |
                    +----------------------------------------------+
                    |
                    v
        +-----------+-----------+
        |                       |
        v                       v
+---------------+       +---------------+
|   External    |       |    SQLite     |
|     APIs      |       |   Database    |
+---------------+       +---------------+
```

## Component Interactions

### Startup Sequence
```
1. main.py starts
2. Database initialized (init_db)
3. Background tasks launched:
   - Portfolio snapshot check/creation
   - NFT floor price collection
4. FastAPI server ready
5. Frontend served at /
```

### Portfolio Value Calculation
```
User Request: GET /portfolio/summary
       |
       v
+------------------+
| Portfolio Router |
+--------+---------+
         |
         v
+------------------+     +------------------+
| Get All Wallets  |---->| Cardano Service  |---> Blockfrost API
+------------------+     +------------------+
         |
         v
+------------------+     +------------------+
| Get Balances     |---->| Bitcoin Service  |---> Blockstream API
+------------------+     +------------------+
         |
         v
+------------------+     +------------------+
| Get Prices       |---->| Pricing Service  |---> CoinGecko API
+------------------+     +------------------+
         |
         v
+------------------+
| Calculate Totals |
+------------------+
         |
         v
    Response JSON
```

### NFT Price Collection Flow
```
Server Startup
      |
      v
+---------------------+
| Load from Database  |
+----------+----------+
           |
           v
+---------------------+
| Identify Missing    |
| Collections         |
+----------+----------+
           |
           v
+---------------------+     +------------------+
| Fetch from TapTools |---->| Rate Limited?    |
+----------+----------+     +--------+---------+
           |                         |
           |    Yes                  | No
           |<------------------------+
           |
           v
+---------------------+
| Save to Database    |
+---------------------+
```

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | HTML5, CSS3, JavaScript | User interface |
| Charts | Chart.js 4.4.1 | Portfolio history visualization |
| Backend | Python 3.11+, FastAPI | REST API server |
| Database | SQLite (aiosqlite) | Persistent data storage |
| HTTP Client | httpx | Async API requests |
| Server | Uvicorn | ASGI server |

## API Endpoints Summary

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve frontend |
| `/health` | GET | Health check |
| `/api/status` | GET | API configuration status |
| `/wallets` | GET/POST | List/add wallets |
| `/wallets/{id}` | GET/DELETE | Get/remove wallet |
| `/wallets/{id}/refresh` | POST | Refresh wallet data |
| `/portfolio/summary` | GET | Portfolio overview |
| `/portfolio/history` | GET | Historical values |
| `/portfolio/snapshot` | POST | Create snapshot |
| `/prices` | GET | Current prices |
| `/defi/staking` | GET | Staking positions |
| `/exchanges/balances` | GET | Exchange holdings |
| `/nfts` | GET | NFT collection |
| `/nfts/prices/status` | GET | Price collection status |
| `/nfts/prices/collect` | POST | Trigger price collection |
