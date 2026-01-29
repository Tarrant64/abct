# Multi-User Database - Developer Guide

## Quick Start

The database layer now supports multiple users. All user-specific data is isolated by `user_id`.

## How to Use

### Option 1: Pass user_id explicitly (Recommended)

```python
from database import get_all_wallets, save_wallet, get_user_id_by_username

# In your router with auth
user_id = await get_user_id_by_username(username)

# Get user's wallets
wallets = await get_all_wallets(user_id=user_id)

# Save a wallet for user
await save_wallet(
    address="addr1...",
    blockchain="cardano",
    label="My Wallet",
    user_id=user_id
)
```

### Option 2: Use context (Alternative)

```python
from database import set_current_user_id, get_all_wallets

# Set user context (e.g., in auth middleware)
set_current_user_id(user_id)

# Functions automatically use context
wallets = await get_all_wallets()  # Uses current user
```

## Updated Function Signatures

### Wallets

```python
# Save/update wallet for user
await save_wallet(
    address: str,
    blockchain: str,
    label: str = None,
    user_id: int = None  # Optional, defaults to current user
)

# Get all wallets for user
wallets = await get_all_wallets(user_id: int = None)

# Get specific wallet for user
wallet = await get_wallet_by_address(
    address: str,
    blockchain: str = None,
    user_id: int = None
)
```

### Portfolio Snapshots

```python
# Save snapshot for user
await save_portfolio_snapshot(
    snapshot_data: dict,
    user_id: int = None
)

# Get history for user
history = await get_portfolio_history(
    days: int = 7,
    user_id: int = None
)
```

### Custom Tokens

```python
# Add token for user
token_id = await add_custom_token(
    token_data: dict,
    user_id: int = None
)

# Get user's tokens
tokens = await get_all_custom_tokens(user_id: int = None)

# Get specific token for user
token = await get_custom_token_by_id(
    token_id: int,
    user_id: int = None
)
```

### API Settings

```python
# Save API setting for user
await save_api_setting(
    api_name: str,
    api_key: str,
    enabled: bool = True,
    user_id: int = None
)

# Get user's API settings
settings = await get_all_api_settings(user_id: int = None)

# Get specific API setting
setting = await get_api_setting(
    api_name: str,
    user_id: int = None
)
```

### Security Settings

```python
# Save security settings for user
await save_security_settings(
    ssl_mode: str,
    cert_path: str = None,
    key_path: str = None,
    cert_type: str = None,
    cert_expires_at: str = None,
    user_id: int = None
)

# Get user's security settings
settings = await get_security_settings(user_id: int = None)
```

## Helper Functions

```python
from database import get_user_id_by_username, set_current_user_id, get_current_user_id

# Lookup user ID by username
user_id = await get_user_id_by_username("admin")
# Returns: 1

# Set current user context (for Option 2)
set_current_user_id(user_id)

# Get current user context
current_user = get_current_user_id()
```

## Router Integration Pattern

### Example: Wallets Router

```python
from fastapi import APIRouter, Depends, HTTPException
from database import get_all_wallets, save_wallet, get_user_id_by_username
from auth_utils import verify_session

router = APIRouter(prefix="/wallets", tags=["wallets"])

@router.get("/")
async def list_wallets(username: str = Depends(verify_session)):
    """Get all wallets for authenticated user."""
    # Get user ID from username
    user_id = await get_user_id_by_username(username)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not found")

    # Get user's wallets
    wallets = await get_all_wallets(user_id=user_id)

    return {"wallets": wallets}


@router.post("/")
async def add_wallet(
    address: str,
    blockchain: str,
    label: str = None,
    username: str = Depends(verify_session)
):
    """Add a wallet for authenticated user."""
    user_id = await get_user_id_by_username(username)

    if not user_id:
        raise HTTPException(status_code=401, detail="User not found")

    # Save wallet for user
    await save_wallet(
        address=address,
        blockchain=blockchain,
        label=label,
        user_id=user_id
    )

    return {"success": True}
```

## Backward Compatibility

During the transition period, all functions work without `user_id`:

```python
# Old code still works (returns all data)
wallets = await get_all_wallets()

# New code with user isolation
wallets = await get_all_wallets(user_id=1)
```

**Warning:** Once routers are updated to enforce user_id, the fallback behavior will be removed for security.

## Common Patterns

### Pattern 1: Auth Dependency

```python
from fastapi import Depends
from database import get_user_id_by_username

async def get_current_user_id_from_auth(
    username: str = Depends(verify_session)
) -> int:
    """Dependency to get user_id from authenticated session."""
    user_id = await get_user_id_by_username(username)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not found")
    return user_id

# Use in routers
@router.get("/wallets")
async def get_wallets(user_id: int = Depends(get_current_user_id_from_auth)):
    return await get_all_wallets(user_id=user_id)
```

### Pattern 2: Middleware Context

```python
# In middleware
from database import set_current_user_id, get_user_id_by_username

@app.middleware("http")
async def set_user_context(request: Request, call_next):
    # Get username from session/auth
    username = get_username_from_session(request)

    if username:
        user_id = await get_user_id_by_username(username)
        set_current_user_id(user_id)

    response = await call_next(request)

    # Clear context after request
    set_current_user_id(None)

    return response

# In routers (no need to pass user_id)
@router.get("/wallets")
async def get_wallets():
    return await get_all_wallets()  # Automatically uses context
```

## Testing

### Test with Different Users

```python
import pytest
from database import save_wallet, get_all_wallets, get_user_id_by_username

@pytest.mark.asyncio
async def test_user_isolation():
    # Get user IDs
    admin_id = await get_user_id_by_username("admin")
    demo_id = await get_user_id_by_username("demo")

    # Add wallet for admin
    await save_wallet("addr1_admin", "cardano", "Admin Wallet", admin_id)

    # Add wallet for demo
    await save_wallet("addr1_demo", "cardano", "Demo Wallet", demo_id)

    # Verify isolation
    admin_wallets = await get_all_wallets(user_id=admin_id)
    demo_wallets = await get_all_wallets(user_id=demo_id)

    assert len(admin_wallets) == 1
    assert len(demo_wallets) == 1
    assert admin_wallets[0]["address"] == "addr1_admin"
    assert demo_wallets[0]["address"] == "addr1_demo"
```

## Migration Notes

### Admin User
- **Username:** admin
- **User ID:** 1
- **Has access to:** All existing data (49 wallets, 91 snapshots)

### New Users
- Start with empty wallets, tokens, settings
- Completely isolated from other users
- Can be created via auth system

## Troubleshooting

### Issue: Functions return empty results

**Cause:** user_id not set or incorrect

**Solution:**
```python
# Check if user exists
user_id = await get_user_id_by_username("admin")
print(f"User ID: {user_id}")  # Should be 1

# Pass user_id explicitly
wallets = await get_all_wallets(user_id=user_id)
```

### Issue: "No such column: user_id"

**Cause:** Migration not run

**Solution:**
```bash
python3 migrate_multiuser.py
```

### Issue: Data not isolated between users

**Cause:** user_id = None in queries

**Solution:** Always pass user_id explicitly until routers are updated.

## Best Practices

1. **Always pass user_id explicitly** during transition period
2. **Use auth dependencies** to automatically inject user_id
3. **Validate user_id exists** before database operations
4. **Test user isolation** in integration tests
5. **Log user_id** in important operations for audit trail

## Database Schema Reference

### Tables with user_id

- `wallets` - User's wallet addresses
- `portfolio_snapshots` - User's portfolio history
- `custom_tokens` - User's custom token holdings
- `api_settings` - User's API configurations
- `security_settings` - User's security preferences

### Global Tables (no user_id)

- `users` - User accounts
- `cache` - API response cache
- `nft_floor_prices` - Global NFT price data
- `token_metadata` - Global token metadata
- `api_usage` - System-wide API usage
- `nft_scheduler_*` - NFT price update scheduler

## Performance Tips

1. All `user_id` columns are **indexed** for fast lookups
2. Queries automatically filter by user_id (no full table scans)
3. Foreign key constraints ensure data integrity
4. Use batch operations when possible

## Security

- ✅ Data isolated per user
- ✅ Foreign key constraints prevent orphaned data
- ✅ Backward compatibility for safe migration
- ✅ Indexed queries prevent performance issues
- ⚠️ Router layer must enforce authentication and user_id

---

**Status:** Database layer complete, ready for router integration
**Version:** Multi-User v1.0
**Last Updated:** 2026-01-28
