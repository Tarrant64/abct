# Demo Mode Quick Start Guide

## For Developers

### How to Add Demo Support to a New Endpoint

```python
# 1. Import required utilities
from database import get_username_by_user_id
from middleware.demo_mode import is_demo_user
from services.demo_your_service import demo_your_service

# 2. Add demo check at start of endpoint
@router.get("/your-endpoint")
async def your_endpoint(user_id: int = Depends(verify_session)):
    # Check if demo user
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        # Return demo data
        return await demo_your_service.get_demo_data()

    # Normal mode - return real data
    return await real_service.get_real_data()
```

## Demo Services Available

### 1. Demo NFT Service
```python
from services.demo_nft_service import demo_nft_service

# Get all demo NFTs (55 anime images)
nfts = await demo_nft_service.get_all_nfts()

# Get NFT summary
summary = await demo_nft_service.get_nft_summary()
```

### 2. Demo DeFi Service
```python
from services.demo_defi_service import demo_defi_service

# Get DeFi summary (anime-themed protocols)
summary = await demo_defi_service.get_defi_summary()

# Get staking positions
staking = await demo_defi_service.get_all_staking_positions()

# Get lending positions
lending = await demo_defi_service.get_all_lending_positions()

# Get liquidity positions
liquidity = await demo_defi_service.get_all_liquidity_positions()

# Get farming positions
farming = await demo_defi_service.get_all_farming_positions()
```

### 3. Demo Exchange Service
```python
from services.demo_exchange_service import demo_exchange_service

# Get exchange balances (Coinbase)
portfolio = await demo_exchange_service.get_portfolio_balances()

# Get spot price
price = await demo_exchange_service.get_spot_price("BTC-USD")

# Get open orders (always returns empty list)
orders = await demo_exchange_service.get_open_orders()
```

### 4. Demo Wallet Service
```python
from services.demo_wallet_service import demo_wallet_service

# Get all wallets
wallets = await demo_wallet_service.get_all_wallets()

# Get wallet balance
balance = await demo_wallet_service.get_wallet_balance(address, blockchain)

# Get total balance in USD
total = await demo_wallet_service.get_total_balance_usd()
```

### 5. Demo Price Service
```python
from services.demo_price_service import demo_price_service

# Get single price
price = await demo_price_service.get_price("ADA")

# Get multiple prices
prices = await demo_price_service.get_prices(["BTC", "ETH", "ADA"])

# Get price with 24h change
data = await demo_price_service.get_price_with_change("ADA")
```

## Testing Demo Mode

### Run Test Suite
```bash
cd /Users/chriscata/Documents/Claude-Projects/ABCT/backend
python3 test_demo_implementation.py
```

### Manual Testing
1. Start the server: `python3 main.py`
2. Navigate to login page
3. Login with `demo` / `demo`
4. Verify all sections show fake data

## Demo User Information

- **User ID**: 10
- **Username**: demo
- **Password**: demo
- **Database Flag**: `is_demo = 1`

## Anime-Themed Content

### DeFi Protocols
- Senpai Swap (DEX)
- Kawaii Lending (Lending)
- Otaku Vault (Yield)
- Manga Money Market (Staking)

### NFT Collections
- Clay Nation (15 images)
- Ape Society (8 images)
- Bored Ape Yacht Club (12 images)
- Solana Monkey Business (20 images)

## Important Notes

1. **Always check for demo user at the START of the endpoint**
2. **Return early with demo data if demo user**
3. **Never make real API calls for demo user**
4. **Use anime-themed names for demo protocols**
5. **All NFT images must use `/static/demo-nfts/` path**

## Common Patterns

### Pattern 1: Simple Endpoint
```python
@router.get("/data")
async def get_data(user_id: int = Depends(verify_session)):
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        return await demo_service.get_data()
    return await real_service.get_data()
```

### Pattern 2: With Caching
```python
@router.get("/data")
async def get_data(user_id: int = Depends(verify_session)):
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        # Demo data doesn't need caching
        return await demo_service.get_data()

    # Normal mode with cache
    cache_key = f"data_{user_id}"
    cached = await get_cache(cache_key)
    if cached:
        return cached

    data = await real_service.get_data()
    await set_cache(cache_key, data, TTL)
    return data
```

### Pattern 3: With Parameters
```python
@router.get("/data/{address}")
async def get_data(address: str, user_id: int = Depends(verify_session)):
    username = await get_username_by_user_id(user_id)
    if username and await is_demo_user(username):
        # Ignore address parameter, return demo data
        return await demo_service.get_data()

    return await real_service.get_data(address)
```

## Troubleshooting

### Demo data not showing
1. Check user is logged in as `demo` / `demo`
2. Verify `is_demo = 1` in users table
3. Check router has demo mode check
4. Verify demo service is imported

### Images not loading
1. Check image path starts with `/static/demo-nfts/`
2. Verify images exist in `frontend/demo-nfts/`
3. Check static files are mounted in `main.py`

### Wrong data showing
1. Verify demo check is BEFORE real API calls
2. Check demo service returns correct data structure
3. Ensure demo flag in response for debugging

## Quick Command Reference

```bash
# Run demo test
python3 backend/test_demo_implementation.py

# Check demo user exists
sqlite3 data/portfolio.db "SELECT * FROM users WHERE username='demo'"

# Verify demo images
ls -l frontend/demo-nfts/ | wc -l

# Start server
cd backend && python3 main.py
```

## Need Help?

See full documentation:
- `/Users/chriscata/Documents/Claude-Projects/ABCT/DEMO_IMPLEMENTATION_COMPLETE.md`
- `/Users/chriscata/Documents/Claude-Projects/ABCT/backend/DEMO_MODE_GUIDE.md`
