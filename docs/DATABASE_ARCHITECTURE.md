# ABCT Database Architecture

## Current vs. Proposed Architecture

### BEFORE (Current - Insecure)
```
┌─────────────────────────────────────────────────┐
│ portfolio.db (2.1 MB)                           │
├─────────────────────────────────────────────────┤
│ ✅ wallets (has user_id)                        │
│ ❌ balances (NO user_id - via wallet_id only)  │
│ ❌ native_assets (NO user_id)                   │
│ ❌ cache (NO user_id - SHARED!)                 │
│ ✅ custom_tokens (has user_id)                  │
│ ✅ portfolio_snapshots (has user_id)            │
│ ⚠️  api_settings (has user_id - shouldn't)      │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ nft_images.db (36 KB) - SEPARATE DATABASE       │
├─────────────────────────────────────────────────┤
│ ❌ nft_images (NO user_id - CRITICAL BUG!)      │
│    All users share same image cache             │
└─────────────────────────────────────────────────┘

PROBLEM: User A can see User B's NFT images!
```

### AFTER (Proposed - Secure)
```
┌─────────────────────────────────────────────────┐
│ abct.db (consolidated)                          │
├─────────────────────────────────────────────────┤
│ USER-SPECIFIC TABLES (all have user_id)         │
│ ✅ wallets (user_id + timestamps)               │
│ ✅ balances (user_id + timestamps)              │
│ ✅ native_assets (user_id + timestamps)         │
│ ✅ nft_images (user_id + timestamps) ← FIXED!   │
│ ✅ custom_tokens (user_id + timestamps)         │
│ ✅ portfolio_snapshots (user_id + timestamps)   │
│ ✅ cache (user_id + key + timestamps) ← FIXED!  │
│ ✅ sessions (user_id + timestamps)              │
├─────────────────────────────────────────────────┤
│ SYSTEM-WIDE TABLES (no user_id)                 │
│ ✅ users (user registry)                         │
│ ✅ nft_floor_prices (shared market data)        │
│ ✅ token_metadata (shared token info)           │
│ ✅ api_settings (system config) ← CHANGED       │
│ ✅ security_settings (SSL config) ← CHANGED     │
└─────────────────────────────────────────────────┘

RESULT: Complete data isolation between users!
```

---

## Key Security Improvements

### 1. NFT Image Isolation (CRITICAL)
**Before**:
```sql
-- User 1 uploads NFT image
INSERT INTO nft_images (asset_id, image_data) VALUES ('asset123', <blob>);

-- User 2 can access it!
SELECT * FROM nft_images WHERE asset_id = 'asset123';  -- ❌ Returns User 1's image
```

**After**:
```sql
-- User 1 uploads NFT image
INSERT INTO nft_images (user_id, asset_id, image_data) VALUES (1, 'asset123', <blob>);

-- User 2 CANNOT access it
SELECT * FROM nft_images WHERE user_id = 2 AND asset_id = 'asset123';  -- ✅ Returns nothing
```

### 2. Cache Isolation (CRITICAL)
**Before**:
```sql
-- User 1 caches portfolio
INSERT INTO cache (key, value) VALUES ('nft_all_data', '{"nfts": [...]}');

-- User 2 gets User 1's cache! ❌
SELECT value FROM cache WHERE key = 'nft_all_data';  -- Returns User 1's NFTs
```

**After**:
```sql
-- User 1 caches portfolio
INSERT INTO cache (user_id, key, value) VALUES (1, 'nft_all_data', '{"nfts": [...]}');

-- User 2 gets their own cache ✅
SELECT value FROM cache WHERE user_id = 2 AND key = 'nft_all_data';  -- Returns nothing
```

### 3. Query Performance (Fast user_id Filtering)
**Before**:
```sql
-- Slow: Join through wallets to get user's assets
SELECT na.* FROM native_assets na
JOIN wallets w ON na.wallet_id = w.id
WHERE w.user_id = 1;  -- Requires join
```

**After**:
```sql
-- Fast: Direct user_id filter
SELECT * FROM native_assets WHERE user_id = 1;  -- Uses index
```

### 4. Cascade Deletes (Data Integrity)
**Before**:
```sql
-- Delete user → orphaned data remains
DELETE FROM users WHERE id = 1;
-- Orphaned: wallets, balances, nft_images, etc. ❌
```

**After**:
```sql
-- Delete user → all data automatically deleted
DELETE FROM users WHERE id = 1;
-- Cascades: wallets → balances → native_assets → nft_images ✅
```

---

## Data Flow Example: NFT Display

### BEFORE (Insecure)
```
User 1 Login
    ↓
GET /nfts/all/summary
    ↓
Backend: get_cache("nft_all_data")  ← NO user_id
    ↓
Returns: 304 NFTs (mixed from User 1, Demo, etc.) ❌
```

### AFTER (Secure)
```
User 1 Login (user_id=1)
    ↓
GET /nfts/all/summary
    ↓
Backend: get_cache("nft_all_data", user_id=1)  ← User-specific
    ↓
Returns: 0 NFTs (only User 1's data) ✅

Demo Login (user_id=10)
    ↓
GET /nfts/all/summary
    ↓
Backend: get_cache("nft_all_data", user_id=10)  ← User-specific
    ↓
Returns: 55 NFTs (only Demo's data) ✅
```

---

## Migration Impact Analysis

### What Changes
- ✅ Database schema (add columns, indexes)
- ✅ Cache storage (add user_id)
- ✅ Service layer (pass user_id everywhere)
- ✅ NFT image queries (filter by user_id)

### What Stays the Same
- ✅ API endpoints (same URLs)
- ✅ Frontend code (no changes needed)
- ✅ Authentication (same session system)
- ✅ User experience (transparent to users)

### What Gets Better
- ✅ Security (complete data isolation)
- ✅ Performance (better indexes, no joins)
- ✅ Audit trail (timestamps on everything)
- ✅ Data integrity (foreign key cascades)
- ✅ Simplicity (one database instead of two)

---

## Industry Best Practices Applied

### 1. Multi-Tenant Database Design
- **Pattern**: Shared database, isolated data
- **Implementation**: user_id on all user tables
- **Standard**: SaaS industry standard (Salesforce, Shopify, etc.)

### 2. Audit Trail
- **Pattern**: created_at, updated_at on all tables
- **Implementation**: Timestamps + triggers
- **Standard**: SOC 2, GDPR compliance requirement

### 3. Referential Integrity
- **Pattern**: Foreign keys with CASCADE
- **Implementation**: All relationships properly defined
- **Standard**: Database normalization (3NF)

### 4. Performance Optimization
- **Pattern**: Denormalization for reads
- **Implementation**: user_id on balances/native_assets (skip joins)
- **Trade-off**: Small storage increase for massive query speed

### 5. Security by Design
- **Pattern**: Row-Level Security (RLS)
- **Implementation**: user_id filtering on all queries
- **Standard**: OWASP Top 10 - Broken Access Control

---

## Comparison to Other Systems

### Similar to:
- **WordPress**: wp_posts has `post_author` (user_id)
- **Django**: Models have `ForeignKey(User)`
- **Rails**: `belongs_to :user` associations
- **Salesforce**: Record ownership with CreatedById

### Different from:
- **Separate databases per user**: Too complex, hard to manage
- **No isolation**: Security nightmare (our current state)
- **Application-level security only**: Can be bypassed

---

## FAQ

### Q: Why denormalize user_id on balances/native_assets?
**A**: Performance. Querying "get all user's assets" requires a join through wallets. With user_id directly on the table, it's a simple indexed lookup. Storage is cheap, query speed is expensive.

### Q: Why consolidate databases?
**A**: Atomic transactions, simpler backups, easier foreign keys, less complexity. No downside - SQLite handles it fine.

### Q: What if we want per-user API keys later?
**A**: Easy to add back. Create a `user_api_settings` table with (user_id, api_name, api_key). System-wide keys stay in `api_settings`.

### Q: Will this break existing backups?
**A**: No. Migration script handles old backups. New backups include user_id automatically.

### Q: How long does migration take?
**A**: 15-30 minutes downtime. Most time is data copying (2.1 MB is small).

### Q: Can we roll back?
**A**: Yes. Keep old databases for 7 days. Rollback is simple copy/paste.

---

## Performance Benchmarks (Expected)

### Query Speed Improvements
```
BEFORE:
SELECT assets for user: 15ms (join through wallets)
SELECT NFT images: 20ms (full table scan, no user_id filter)
SELECT cache: 5ms (no user_id, relies on key only)

AFTER:
SELECT assets for user: 2ms (direct user_id index)
SELECT NFT images: 3ms (user_id + asset_id compound index)
SELECT cache: 1ms (user_id + key compound index)

IMPROVEMENT: 3-7x faster queries
```

### Storage Impact
```
BEFORE: 2.1 MB portfolio.db + 36 KB nft_images.db = 2.136 MB

AFTER: ~2.3 MB (single database)
- user_id columns: +8 bytes per row
- Indexes: +~100 KB
- Overhead: +~50 KB

COST: +164 KB (~7% increase)
BENEFIT: Complete security + faster queries
VERDICT: Worth it! 🎯
```

---

## Visual Schema Relationships

```
users (id, username, password_hash, is_demo)
  ├─1:N─→ wallets (id, user_id, address, blockchain)
  │        ├─1:N─→ balances (id, wallet_id, user_id, amount)
  │        └─1:N─→ native_assets (id, wallet_id, user_id, asset_id)
  │
  ├─1:N─→ nft_images (id, user_id, asset_id, image_data)
  ├─1:N─→ custom_tokens (id, user_id, policy_id, quantity)
  ├─1:N─→ portfolio_snapshots (id, user_id, snapshot_date, total_value)
  ├─1:N─→ cache (id, user_id, key, value)
  └─1:N─→ sessions (token, user_id, expires_at)

SYSTEM-WIDE (no user_id):
  nft_floor_prices (policy_id, floor_price_ada)
  token_metadata (asset_id, ticker, name)
  api_settings (api_name, api_key)
  security_settings (ssl_mode, cert_path)
```

All relationships use `ON DELETE CASCADE` for data integrity.

---

**Conclusion**: This architecture follows industry best practices, provides complete security, improves performance, and sets ABCT up for future multi-tenant deployment.
