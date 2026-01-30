# ABCT Architecture (v0.12.0)

## System Overview

```
+-----------------------------------------------------------------------------------+
|                              ABCT System (v0.12.0)                                 |
|                         Multi-User Portfolio Tracker                              |
+-----------------------------------------------------------------------------------+

                                   +-----------------+
                                   |   Frontend UI   |
                                   | (HTML/CSS/JS)   |
                                   |   - Dashboard   |
                                   |   - Wallets     |
                                   |   - NFT Wall    |
                                   |   - Settings    |
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
|  |  - Login         |  |  - Summary       |  |   - List/CRUD    |                  |
|  |  - Password      |  |  - Assets        |  |   - Discovery    |                  |
|  +--------+---------+  |  - Breakdown     |  |   - Assets       |                  |
|           |            +--------+---------+  +--------+---------+                  |
|           |                     |                     |                            |
|  +--------+---------+  +--------+---------+  +--------+---------+                  |
|  |   Prices API     |  |    DeFi API      |  |  Exchanges API   |                  |
|  |   /prices/*      |  |    /defi/*       |  |  /exchanges/*    |                  |
|  +--------+---------+  +--------+---------+  +--------+---------+                  |
|           |                     |                     |                            |
|  +--------+---------+  +--------+---------+  +--------+---------+                  |
|  |    NFTs API      |  |   Backup API     |  |   Security API   |                  |
|  |    /nfts/*       |  |   /backup/*      |  |   /security/*    |                  |
|  |  - Floor Prices  |  |  - Export/Import |  |  - API Keys      |                  |
|  |  - Collections   |  +------------------+  +------------------+                  |
|  +--------+---------+                                                              |
|           |                                                                        |
+-----------------------------------------------------------------------------------+
            |                     |                     |
            v                     v                     v
+-----------------------------------------------------------------------------------+
|                              Services Layer                                        |
+-----------------------------------------------------------------------------------+
|                                                                                    |
|  +---------------+  +---------------+  +---------------+  +---------------+        |
|  |   Cardano     |  |   Bitcoin     |  |   Ethereum    |  |   Solana      |        |
|  |   Service     |  |   Service     |  |   Service     |  |   Service     |        |
|  +-------+-------+  +-------+-------+  +-------+-------+  +-------+-------+        |
|          |                  |                  |                  |                |
|  +-------+-------+  +-------+-------+  +-------+-------+  +-------+-------+        |
|  |   Polygon     |  |     Base      |  |   Pricing     |  |     NFT       |        |
|  |   Service     |  |   Service     |  |   Service     |  |   Service     |        |
|  +-------+-------+  +-------+-------+  +-------+-------+  +-------+-------+        |
|          |                  |                  |                  |                |
|  +-------+-------+  +-------+-------+  +-------+-------+  +-------+-------+        |
|  |    DeFi       |  |   Coinbase    |  |   Snapshot    |  |   Logging     |        |
|  |   Service     |  |   Service     |  |   Service     |  |   Service     |        |
|  +-------+-------+  +-------+-------+  +-------+-------+  +-------+-------+        |
|          |                                                         |                |
|  +-------+-------+                                        +-------+-------+        |
|  |  Demo Wallet  |                                        | Demo Exchange |        |
|  |   Service     |  (Mocks API calls for demo users)     |   Service     |        |
|  +---------------+                                        +---------------+        |
|                                                                                    |
+-----------------------------------------------------------------------------------+
            |                     |                     |
            v                     v                     v
+-----------------------------------------------------------------------------------+
|                           External APIs                                            |
+-----------------------------------------------------------------------------------+
|                                                                                    |
|  +---------------+  +---------------+  +---------------+  +---------------+        |
|  |  Blockfrost   |  |  Blockstream  |  |   Etherscan   |  |    Alchemy    |        |
|  |  (Cardano)    |  |  (Bitcoin)    |  |  (Ethereum)   |  |  (Ethereum)   |        |
|  +---------------+  +---------------+  +---------------+  +---------------+        |
|                                                                                    |
|  +---------------+  +---------------+  +---------------+  +---------------+        |
|  |   Helius      |  |   QuickNode   |  |  Polygonscan  |  |   BaseScan    |        |
|  |  (Solana)     |  |  (Multi)      |  |  (Polygon)    |  |    (Base)     |        |
|  +---------------+  +---------------+  +---------------+  +---------------+        |
|                                                                                    |
|  +---------------+  +---------------+  +---------------+  +---------------+        |
|  |   TapTools    |  |   Coinbase    |  |   CExplorer   |  |    Koios      |        |
|  |   (NFTs)      |  |  (Exchange)   |  |  (Staking)    |  |  (Cardano)    |        |
|  +---------------+  +---------------+  +---------------+  +---------------+        |
|                                                                                    |
|  +---------------+  +---------------+                                              |
|  |  CoinGecko    |  |  CoinCap      |                                              |
|  |  (Prices)     |  |  (Prices)     |                                              |
|  +---------------+  +---------------+                                              |
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
|  | - id             |  | - token          |  | - user_id        |                   |
|  | - username       |  | - user_id        |  | - reset_code     |                   |
|  | - password_hash  |  | - expires_at     |  | - expires_at     |                   |
|  | - is_demo        |  | - is_demo        |  +------------------+                   |
|  +------------------+  +------------------+                                         |
|                                                                                    |
|  Portfolio Data (User-Scoped):                                                    |
|  +------------------+  +------------------+  +------------------+                   |
|  |     wallets      |  |    balances      |  |  native_assets   |                   |
|  | - user_id (FK)   |  | - user_id (FK)   |  | - user_id (FK)   |                   |
|  +------------------+  +------------------+  +------------------+                   |
|                                                                                    |
|  +------------------+  +------------------+  +------------------+                   |
|  | portfolio_       |  | custom_tokens    |  |  api_settings    |                   |
|  | snapshots        |  | - user_id (FK)   |  | - user_id (FK)   |                   |
|  | - user_id (FK)   |  +------------------+  +------------------+                   |
|  +------------------+                                                              |
|                                                                                    |
|  Shared Data:                                                                     |
|  +------------------+  +------------------+  +------------------+                   |
|  | nft_floor_       |  | token_metadata   |  |     cache        |                   |
|  | prices           |  |                  |  |                  |                   |
|  +------------------+  +------------------+  +------------------+                   |
|                                                                                    |
+-----------------------------------------------------------------------------------+
```

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

## Data Isolation

```
User A (user_id=1):
+------------------+
| wallets          |  WHERE user_id = 1
| balances         |  WHERE user_id = 1
| native_assets    |  WHERE user_id = 1
| portfolio_       |  WHERE user_id = 1
| snapshots        |
+------------------+

User B (user_id=2):
+------------------+
| wallets          |  WHERE user_id = 2
| balances         |  WHERE user_id = 2
| native_assets    |  WHERE user_id = 2
| portfolio_       |  WHERE user_id = 2
| snapshots        |
+------------------+

Demo User (user_id=13, is_demo=1):
+------------------+
| wallets          |  WHERE user_id = 13
| balances         |  Mock data returned
| native_assets    |  Mock data returned
| portfolio_       |  WHERE user_id = 13
| snapshots        |
+------------------+
```

## Technology Stack

### Backend
- **FastAPI**: Modern Python web framework
- **SQLite**: Embedded database (with multi-user support)
- **aiosqlite**: Async database operations
- **bcrypt**: Password hashing
- **pydantic**: Data validation
- **httpx**: Async HTTP client for API calls

### Frontend
- **HTML5/CSS3**: Modern responsive design
- **Vanilla JavaScript**: No framework dependencies
- **Chart.js v4.4.1**: Portfolio charts and asset breakdowns
- **DOMPurify**: XSS protection
- **CSS Custom Properties**: Theme support

### External Services
- **Blockfrost**: Cardano blockchain data
- **Blockstream**: Bitcoin blockchain data
- **Etherscan/Alchemy**: Ethereum blockchain data
- **Helius/QuickNode**: Solana blockchain data
- **TapTools**: NFT floor prices
- **CoinGecko**: Cryptocurrency pricing

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
|                                                                                    |
+-----------------------------------------------------------------------------------+
```

## Key Features (v0.12.0)

### Multi-User Support
- User account system with authentication
- Session-based authentication with cookies
- Password management and reset functionality
- Per-user data isolation across all tables

### Demo Mode
- Fully functional demo account
- ~$1M portfolio with diverse assets
- 30 different tokens across 3 blockchains
- No real API calls required
- Anime-themed NFT placeholders

### Portfolio Tracking
- 6 blockchain networks supported
- Interactive asset breakdown charts
- Expandable wallet assets
- Historical data visualization
- Privacy mode for sensitive data

### NFT Management
- Multi-chain NFT display
- Floor price tracking
- Collection management
- Blockchain indicators

### Backup & Restore
- Complete configuration export
- Selective data inclusion
- Merge or replace import modes
- Version compatibility checking

## Deployment Options

### Local Development
```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Production (Docker)
```bash
docker-compose up -d
```

### Production (Systemd)
```bash
systemctl start abct
```

## File Structure

```
ABCT/
├── backend/
│   ├── main.py                     # FastAPI application entry
│   ├── auth_utils.py               # Authentication utilities
│   ├── database.py                 # Database operations
│   ├── config.py                   # Configuration management
│   ├── routers/                    # API endpoint routers
│   │   ├── auth.py                 # Authentication endpoints
│   │   ├── portfolio.py            # Portfolio endpoints
│   │   ├── wallets.py              # Wallet management
│   │   ├── nfts.py                 # NFT endpoints
│   │   └── backup.py               # Backup/restore
│   ├── services/                   # Business logic services
│   │   ├── cardano.py              # Cardano blockchain
│   │   ├── bitcoin.py              # Bitcoin blockchain
│   │   ├── ethereum.py             # Ethereum blockchain
│   │   ├── solana.py               # Solana blockchain
│   │   ├── pricing_service.py      # Price aggregation
│   │   ├── demo_wallet_service.py  # Demo mode wallets
│   │   └── demo_exchange_service.py # Demo mode exchange
│   ├── middleware/                 # FastAPI middleware
│   │   ├── demo_mode.py            # Demo mode detection
│   │   └── size_limit.py           # Request size limiting
│   └── scripts/
│       └── create_demo_account.py  # Demo account setup
├── frontend/
│   ├── index.html                  # Dashboard
│   ├── wallets.html                # Wallet management
│   ├── nft-wall.html               # NFT gallery
│   ├── login.html                  # Login page
│   ├── js/
│   │   ├── app.js                  # Main application logic
│   │   └── session-auth.js         # Authentication utilities
│   └── css/
│       └── styles.css              # Application styles
├── data/
│   └── portfolio.db                # SQLite database
└── docs/
    ├── ARCHITECTURE.md             # This file
    ├── CHANGELOG.md                # Version history
    └── README.md                   # Main documentation
```

## Migration Notes

### Upgrading from v0.10.0 to v0.12.0

The v0.12.0 release introduces a complete database restructure for multi-user support. If upgrading from v0.10.0 or earlier:

1. **Backup your data**: Export using the backup feature
2. **Run migration script**: Use `database_migration.py` to add user tables
3. **Create initial user**: Set up your first user account
4. **Restore data**: Import your backup file

See `backend/MULTIUSER_DEVELOPER_GUIDE.md` for detailed migration instructions.

## Performance Considerations

- **Database**: SQLite with WAL mode for concurrent access
- **Caching**: In-memory cache for API responses (60-second TTL)
- **Async Operations**: All I/O operations are async
- **Connection Pooling**: Reused HTTP connections for API calls
- **Rate Limiting**: Respects API provider limits

## Future Enhancements

- PostgreSQL support for larger deployments
- Real-time WebSocket updates
- Mobile app (React Native)
- Hardware wallet integration
- Tax reporting exports
- Advanced charting and analytics
