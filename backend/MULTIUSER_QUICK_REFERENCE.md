# Multi-User Database - Quick Reference Card

## 🚀 Quick Start

```python
from database import get_user_id_by_username, get_all_wallets

# Get user ID
user_id = await get_user_id_by_username("admin")  # Returns: 1

# Get user's data
wallets = await get_all_wallets(user_id=user_id)
```

## 📊 Tables with user_id

| Table | Records Migrated | Index |
|-------|-----------------|-------|
| wallets | 49 → admin | idx_wallets_user_id |
| portfolio_snapshots | 91 → admin | idx_portfolio_snapshots_user_id |
| custom_tokens | 0 → admin | idx_custom_tokens_user_id |
| api_settings | 0 → admin | idx_api_settings_user_id |
| security_settings | 1 → admin | idx_security_settings_user_id |

## 🔧 Common Functions

### Wallets
```python
# Save
await save_wallet(address, blockchain, label, user_id)

# Get all
wallets = await get_all_wallets(user_id)

# Get specific
wallet = await get_wallet_by_address(address, blockchain, user_id)
```

### Portfolio
```python
# Save snapshot
await save_portfolio_snapshot(snapshot_data, user_id)

# Get history
history = await get_portfolio_history(days=7, user_id)
```

### Custom Tokens
```python
# Add token
token_id = await add_custom_token(token_data, user_id)

# Get all
tokens = await get_all_custom_tokens(user_id)
```

### API Settings
```python
# Save
await save_api_setting(api_name, api_key, enabled, user_id)

# Get
setting = await get_api_setting(api_name, user_id)
```

## 👤 Admin User

```
Username: admin
Password: satoshi
User ID: 1
```

All existing data belongs to admin user.

## 🔒 User Context

### Option 1: Explicit (Recommended)
```python
user_id = await get_user_id_by_username(username)
data = await get_all_wallets(user_id=user_id)
```

### Option 2: Context
```python
set_current_user_id(user_id)
data = await get_all_wallets()  # Auto uses context
```

## 📦 Migration

```bash
python3 migrate_multiuser.py
```

Output:
```
✓ Users table created
✓ Admin user found (ID: 1)
✓ 5/5 tables migrated
✓ 141 total records migrated
```

## ✅ Status

**Database Layer:** ✅ Complete
**Router Layer:** ⏳ Next Phase

## 📚 Full Docs

- `MULTIUSER_MIGRATION_SUMMARY.md` - Technical details
- `MULTIUSER_DEVELOPER_GUIDE.md` - Usage examples
- `IMPLEMENTATION_SUMMARY.md` - Complete overview

---
**Version:** Multi-User v1.0 | **Date:** 2026-01-28
