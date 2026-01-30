# ABCT Database Architecture & Migration Plan

**Date**: 2026-01-30
**Status**: PROPOSED - Awaiting Approval

---

## Executive Summary

Redesign ABCT's database architecture to enforce proper **multi-user data isolation**, add **audit timestamps**, consolidate separate databases, and follow **industry security best practices**.

### Current Problems
1. **NFT images shared across users** (no user_id in nft_images table)
2. **Cache data not user-isolated** (cache keys like `nft_all_data` shared)
3. **Split databases complicate queries** (portfolio.db + nft_images.db)
4. **Inconsistent timestamps** (some tables missing created_at/updated_at)
5. **Weak foreign key enforcement** (some relationships not defined)
6. **Missing indexes** (performance issues on user_id lookups)

### Solution Benefits
- ✅ **Security**: Complete data isolation between users
- ✅ **Performance**: Consolidated DB, better indexes
- ✅ **Audit Trail**: Full timestamp tracking
- ✅ **Integrity**: Proper foreign key constraints
- ✅ **Simplicity**: Single database, clearer schema
- ✅ **Scalability**: Ready for multi-tenant deployment

---

## Database Consolidation

### Current State
```
data/
├── portfolio.db      (2.1 MB - users, wallets, balances, cache)
├── nft_images.db     (36 KB - NFT image cache)
└── logs.db           (768 KB - system logs)
```

### Proposed State
```
data/
├── abct.db           (ALL application data - consolidated)
└── logs.db           (system logs - stays separate)
```

**Rationale**:
- **Consolidate** portfolio.db + nft_images.db → `abct.db`
- **Keep separate** logs.db (system-wide, not user-specific)
- Simpler backup/restore (one database)
- Atomic transactions across all user data
- Easier to enforce foreign key constraints

---

## Schema Design Principles

### 1. User Data Isolation
**Rule**: Every table with user-specific data MUST have `user_id INTEGER NOT NULL`

**User-Specific Tables**:
- ✅ wallets
- ✅ balances (NEW: add user_id for direct filtering)
- ✅ native_assets (NEW: add user_id for direct filtering)
- ✅ custom_tokens
- ✅ portfolio_snapshots
- ✅ portfolio_history
- ✅ nft_images (NEW: add user_id - CRITICAL)
- ✅ sessions
- ✅ cache (NEW: add user_id column)

**System-Wide Tables** (no user_id):
- users (user registry itself)
- nft_floor_prices (shared market data)
- nft_scheduler_* (system background jobs)
- api_rate_limits (system config)
- api_usage (system-wide tracking)
- token_metadata (shared token info)

**Hybrid Tables** (CHANGED - make system-wide):
- ❌ api_settings (REMOVE user_id - APIs are system-wide config)
- ❌ security_settings (REMOVE user_id - SSL is system-wide)

### 2. Audit Timestamps
**Rule**: ALL tables get `created_at` and `updated_at`

```sql
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
```

Trigger to auto-update `updated_at`:
```sql
CREATE TRIGGER update_{table}_timestamp
AFTER UPDATE ON {table}
FOR EACH ROW
BEGIN
    UPDATE {table} SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
```

### 3. Foreign Key Constraints
**Rule**: All relationships use proper FOREIGN KEY with CASCADE options

```sql
user_id INTEGER NOT NULL,
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
```

**Cascade Behavior**:
- `ON DELETE CASCADE`: Delete user → delete all their data
- `ON UPDATE CASCADE`: Update user.id → update all references

### 4. Indexes for Performance
**Rule**: Index all foreign keys and frequently queried columns

```sql
CREATE INDEX idx_{table}_user_id ON {table}(user_id);
CREATE INDEX idx_{table}_{column} ON {table}({column});
```

### 5. Unique Constraints
**Rule**: Prevent duplicate data per user

Example:
```sql
UNIQUE(user_id, address, blockchain)  -- One wallet per user per chain
```

---

## New Schema Design

### Core Tables

#### users
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_demo INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_active ON users(is_active);
```

#### wallets
```sql
CREATE TABLE wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    address TEXT NOT NULL,
    blockchain TEXT NOT NULL,
    label TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(user_id, address, blockchain),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_wallets_user_id ON wallets(user_id);
CREATE INDEX idx_wallets_blockchain ON wallets(blockchain);
CREATE INDEX idx_wallets_active ON wallets(user_id, is_active);
```

#### balances
```sql
CREATE TABLE balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,  -- NEW: denormalized for fast filtering
    amount TEXT NOT NULL,
    unit TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_balances_wallet_id ON balances(wallet_id);
CREATE INDEX idx_balances_user_id ON balances(user_id);
```

#### native_assets
```sql
CREATE TABLE native_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,  -- NEW: denormalized for fast filtering
    asset_id TEXT NOT NULL,
    policy_id TEXT,
    asset_name TEXT,
    quantity TEXT NOT NULL,
    decimals INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (wallet_id) REFERENCES wallets(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_native_assets_wallet_id ON native_assets(wallet_id);
CREATE INDEX idx_native_assets_user_id ON native_assets(user_id);
CREATE INDEX idx_native_assets_policy_id ON native_assets(policy_id);
CREATE INDEX idx_native_assets_asset_id ON native_assets(asset_id);
```

#### nft_images (MOVED from nft_images.db)
```sql
CREATE TABLE nft_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,  -- NEW: CRITICAL for data isolation
    asset_id TEXT NOT NULL,
    blockchain TEXT NOT NULL,
    image_url TEXT,
    image_data BLOB,
    image_format TEXT,
    image_size INTEGER,
    width INTEGER,
    height INTEGER,
    thumbnail_data BLOB,
    fetch_status TEXT DEFAULT 'pending',
    error_message TEXT,
    fetched_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(user_id, asset_id, blockchain),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_nft_images_user_id ON nft_images(user_id);
CREATE INDEX idx_nft_images_blockchain ON nft_images(blockchain);
CREATE INDEX idx_nft_images_status ON nft_images(fetch_status);
CREATE INDEX idx_nft_images_fetched ON nft_images(fetched_at);
```

#### cache (REDESIGNED for multi-user)
```sql
CREATE TABLE cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,  -- NULL for system-wide cache
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(user_id, key),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_cache_user_key ON cache(user_id, key);
CREATE INDEX idx_cache_expires ON cache(expires_at);
```

**Cache Key Strategy**:
- User-specific: `(user_id=1, key="portfolio_summary")`
- System-wide: `(user_id=NULL, key="ada_price")`

#### custom_tokens
```sql
CREATE TABLE custom_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    policy_id TEXT NOT NULL,
    asset_name TEXT,
    ticker TEXT,
    blockchain TEXT NOT NULL,
    quantity TEXT NOT NULL,
    decimals INTEGER DEFAULT 0,
    label TEXT,
    token_name TEXT,
    price_usd REAL,
    last_price_update TIMESTAMP,
    include_in_total INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(user_id, policy_id, asset_name),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_custom_tokens_user_id ON custom_tokens(user_id);
CREATE INDEX idx_custom_tokens_blockchain ON custom_tokens(blockchain);
```

#### portfolio_snapshots
```sql
CREATE TABLE portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    snapshot_date DATE NOT NULL,
    snapshot_time TIMESTAMP NOT NULL,
    total_value_usd REAL NOT NULL,
    ada_amount REAL DEFAULT 0,
    ada_price REAL DEFAULT 0,
    btc_amount REAL DEFAULT 0,
    btc_price REAL DEFAULT 0,
    eth_amount REAL DEFAULT 0,
    eth_price REAL DEFAULT 0,
    sol_amount REAL DEFAULT 0,
    sol_price REAL DEFAULT 0,
    staking_value_usd REAL DEFAULT 0,
    defi_value_usd REAL DEFAULT 0,
    exchange_value_usd REAL DEFAULT 0,
    nft_value_usd REAL DEFAULT 0,
    tracked_tokens_value_usd REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(user_id, snapshot_date),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_portfolio_snapshots_user_id ON portfolio_snapshots(user_id);
CREATE INDEX idx_portfolio_snapshots_date ON portfolio_snapshots(snapshot_date);
```

#### sessions
```sql
CREATE TABLE sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    is_demo INTEGER DEFAULT 0,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);
```

### System Tables (No user_id)

#### api_settings (CHANGED - system-wide)
```sql
CREATE TABLE api_settings (
    api_name TEXT PRIMARY KEY,
    api_key TEXT,
    enabled INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

#### security_settings (CHANGED - system-wide)
```sql
CREATE TABLE security_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    ssl_mode TEXT DEFAULT 'http',
    cert_path TEXT,
    key_path TEXT,
    cert_type TEXT,
    cert_expires_at TIMESTAMP,
    pending_mode TEXT,
    restart_required INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

#### nft_floor_prices
```sql
CREATE TABLE nft_floor_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id TEXT NOT NULL,
    collection_name TEXT,
    floor_price_ada REAL,
    listings INTEGER DEFAULT 0,
    supply INTEGER,
    verified INTEGER DEFAULT 0,
    source TEXT,
    fetched_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(policy_id, fetched_at)
);
CREATE INDEX idx_nft_floor_prices_policy ON nft_floor_prices(policy_id);
CREATE INDEX idx_nft_floor_prices_fetched ON nft_floor_prices(fetched_at);
```

#### token_metadata
```sql
CREATE TABLE token_metadata (
    asset_id TEXT PRIMARY KEY,
    policy_id TEXT,
    asset_name TEXT,
    ticker TEXT,
    name TEXT,
    decimals INTEGER DEFAULT 0,
    logo_url TEXT,
    track_for_pricing INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX idx_token_metadata_policy ON token_metadata(policy_id);
CREATE INDEX idx_token_metadata_ticker ON token_metadata(ticker);
```

---

## Migration Strategy

### Phase 1: Preparation (No Downtime)
1. **Backup current databases**
   ```bash
   cp data/portfolio.db data/portfolio.db.backup
   cp data/nft_images.db data/nft_images.db.backup
   ```

2. **Create migration script**: `backend/database_migration.py`
3. **Test migration on backup copy**

### Phase 2: Schema Migration
1. **Create new abct.db** with updated schema
2. **Migrate data** from old databases:
   - Copy users, sessions (no changes)
   - Copy wallets (add updated_at if missing)
   - Copy balances → ADD user_id from wallet.user_id
   - Copy native_assets → ADD user_id from wallet.user_id
   - Copy custom_tokens, portfolio_snapshots (already have user_id)
   - Copy nft_floor_prices, token_metadata (system tables)
   - Copy nft_images from nft_images.db → ADD user_id based on asset ownership
   - Migrate cache → Split into user-specific entries

3. **Create database triggers** for updated_at auto-update

### Phase 3: Service Updates
1. **Update database.py**:
   - Add user_id to all query functions
   - Update cache get/set to use (user_id, key)
   - Add helper: `get_user_wallets(user_id)`

2. **Update NFT service**:
   - Change cache key: `nft_all_data` → `nft_all_data_{user_id}`
   - Filter nft_images by user_id
   - Pass user_id to all queries

3. **Update all routers**:
   - Ensure user_id from `verify_session()` is passed to all DB queries

4. **Update backup/restore**:
   - Handle new schema
   - Preserve user_id on import

### Phase 4: Deployment
1. **Stop backend server**
2. **Run migration script**
3. **Rename databases**:
   ```bash
   mv data/portfolio.db data/portfolio.db.old
   mv data/nft_images.db data/nft_images.db.old
   mv data/abct.db data/portfolio.db  # Keep same path for compatibility
   ```
4. **Restart backend**
5. **Verify** all endpoints work correctly
6. **Delete old databases** after 7-day verification period

### Phase 5: Verification
- [ ] Admin login → sees only admin data
- [ ] Demo login → sees only demo data
- [ ] NFT images isolated per user
- [ ] Cache isolated per user
- [ ] Backup/restore preserves user_id
- [ ] All timestamps working
- [ ] Foreign key cascades work (delete user → delete all data)

---

## Code Changes Required

### 1. database.py
```python
# ADD user_id to all user-specific queries
async def get_all_wallets(user_id: int) -> List[dict]:
    query = "SELECT * FROM wallets WHERE user_id = ? ORDER BY created_at"
    # ... (already has this)

async def get_wallet_balance(wallet_id: int, user_id: int):
    # NEW: Verify wallet belongs to user
    query = "SELECT b.* FROM balances b JOIN wallets w ON b.wallet_id = w.id WHERE b.wallet_id = ? AND w.user_id = ?"
    # ...

async def get_cache(key: str, user_id: int = None):
    # NEW: User-specific or system-wide cache
    if user_id is not None:
        query = "SELECT value FROM cache WHERE user_id = ? AND key = ? AND expires_at > CURRENT_TIMESTAMP"
        row = await cursor.execute(query, (user_id, key))
    else:
        query = "SELECT value FROM cache WHERE user_id IS NULL AND key = ? AND expires_at > CURRENT_TIMESTAMP"
        row = await cursor.execute(query, (key,))
    # ...

async def set_cache(key: str, value: dict, ttl: int = 3600, user_id: int = None):
    # NEW: User-specific or system-wide cache
    expires_at = datetime.now() + timedelta(seconds=ttl)
    query = "INSERT OR REPLACE INTO cache (user_id, key, value, expires_at) VALUES (?, ?, ?, ?)"
    await cursor.execute(query, (user_id, key, json.dumps(value), expires_at))
    # ...
```

### 2. services/nft.py
```python
class NFTService:
    def __init__(self):
        self.nft_cache = {}  # Remove global cache
        # Cache is now per-user in database

    async def get_all_nfts(self, user_id: int, force_refresh: bool = False):
        cache_key = f"nft_all_data"  # Key without user_id
        cached = await get_cache(cache_key, user_id=user_id)  # Pass user_id
        # ...

    async def get_nft_image(self, asset_id: str, user_id: int):
        # NEW: Filter by user_id
        query = "SELECT * FROM nft_images WHERE asset_id = ? AND user_id = ?"
        # ...
```

### 3. routers/*.py
```python
# All routers already use Depends(verify_session) → user_id
# Just ensure user_id is passed to all database calls

@router.get("/summary")
async def get_portfolio_summary(user_id: int = Depends(verify_session)):
    cached = await get_cache("portfolio_summary", user_id=user_id)  # NEW
    # ...
```

---

## Security Checklist

- [x] **User isolation**: All user data has user_id
- [x] **Query filtering**: All queries filter by user_id
- [x] **Foreign keys**: CASCADE deletes protect orphans
- [x] **Unique constraints**: Prevent duplicate data per user
- [x] **Indexes**: Fast user_id lookups
- [x] **Audit trail**: created_at/updated_at on all tables
- [x] **Cache isolation**: User-specific cache entries
- [x] **NFT images**: Per-user image cache
- [x] **Session validation**: verify_session() required on all endpoints

---

## Testing Plan

### Unit Tests
```python
# tests/test_database_isolation.py
async def test_user_data_isolation():
    # Create two users
    user1_id = await create_user("user1", "pass1")
    user2_id = await create_user("user2", "pass2")

    # Add wallet for user1
    wallet1_id = await add_wallet(user1_id, "addr1", "cardano")

    # User2 should NOT see user1's wallet
    wallets = await get_all_wallets(user2_id)
    assert len(wallets) == 0

    # User1 should see their wallet
    wallets = await get_all_wallets(user1_id)
    assert len(wallets) == 1

async def test_nft_image_isolation():
    # User1 caches an NFT image
    await save_nft_image(user1_id, "asset123", blockchain="cardano", image_data=b"...")

    # User2 should NOT see user1's cached image
    image = await get_nft_image("asset123", user2_id)
    assert image is None

    # User1 should see their cached image
    image = await get_nft_image("asset123", user1_id)
    assert image is not None

async def test_cache_isolation():
    # User1 caches portfolio summary
    await set_cache("portfolio_summary", {"total": 1000}, user_id=user1_id)

    # User2 should NOT see user1's cache
    cached = await get_cache("portfolio_summary", user_id=user2_id)
    assert cached is None

    # User1 should see their cache
    cached = await get_cache("portfolio_summary", user_id=user1_id)
    assert cached["total"] == 1000
```

### Integration Tests
- Test login → API calls → verify only user's data returned
- Test demo account → verify 55 NFTs visible
- Test admin account → verify 0 NFTs (clean slate)
- Test backup/restore → verify user_id preserved

---

## Rollback Plan

If migration fails:
1. **Stop backend server**
2. **Restore backups**:
   ```bash
   rm data/portfolio.db
   rm data/nft_images.db
   cp data/portfolio.db.backup data/portfolio.db
   cp data/nft_images.db.backup data/nft_images.db
   ```
3. **Restart backend** with old code
4. **Investigate** migration script errors
5. **Fix and retry**

---

## Timeline Estimate

- **Phase 1** (Prep): 30 minutes
- **Phase 2** (Migration script): 2-3 hours
- **Phase 3** (Service updates): 3-4 hours
- **Phase 4** (Deployment): 15 minutes
- **Phase 5** (Testing): 1-2 hours

**Total**: ~6-10 hours of development work

---

## Next Steps

1. **Review this plan** - confirm approach is correct
2. **Approve migration** - green light to proceed
3. **Create migration script** - Python script to move data
4. **Test on backup** - verify migration works
5. **Schedule downtime** - pick a time window
6. **Execute migration** - run the plan
7. **Verify & monitor** - ensure everything works

---

## Questions for Review

1. **API settings**: Should these be per-user or system-wide? (Proposed: system-wide)
2. **Security settings**: Should SSL config be per-user or system-wide? (Proposed: system-wide)
3. **Database name**: Keep `portfolio.db` for compatibility or rename to `abct.db`?
4. **Old databases**: Keep backups for how long? (Proposed: 7 days)
5. **Downtime tolerance**: How long can the system be offline for migration? (Estimated: 15-30 min)

---

**Status**: ✅ Ready for review and approval
