# Demo Mode API Mocking System

## Overview

The Demo Mode system prevents real API calls for demo accounts and returns realistic fake data instead. This is useful for:
- Public demonstrations without exposing real portfolio data
- Testing the frontend without API keys
- Onboarding new users with example data
- Development and testing

## Demo Account Credentials

**Username:** `demo`
**Password:** `demo`

The demo user is automatically created during application startup.

## Architecture

### Core Components

1. **`middleware/demo_mode.py`** - Core demo mode detection and utilities
2. **`services/demo_wallet_service.py`** - Mock wallet balances and data
3. **`services/demo_defi_service.py`** - Mock DeFi positions, staking, lending
4. **`services/demo_nft_service.py`** - Mock NFT collections and floor prices
5. **`services/demo_price_service.py`** - Mock cryptocurrency prices

### Database Changes

- Added `is_demo` column to `users` table
- Demo flag stored in session data during login
- No real data is associated with demo accounts

## How to Use Demo Mode in Routers

### Basic Pattern

```python
from fastapi import APIRouter, Depends
from middleware.demo_mode import is_demo_user
from services.demo_wallet_service import demo_wallet_service
from auth_utils import verify_session

router = APIRouter()

@router.get("/wallets")
async def get_wallets(username: str = Depends(verify_session)):
    # Check if demo user
    if await is_demo_user(username):
        # Return fake data - NO real API calls
        return await demo_wallet_service.get_all_wallets()

    # Normal flow for real users
    return await real_wallet_service.get_all_wallets()
```

### Example: Wallets Router

```python
@router.get("")
async def list_wallets(username: str = Depends(verify_session)):
    """List all tracked wallets."""

    # Demo mode check
    if await is_demo_user(username):
        demo_wallets = await demo_wallet_service.get_all_wallets()
        return {
            "wallets": demo_wallets,
            "total": len(demo_wallets),
            "demo_mode": True
        }

    # Real user flow
    wallets = await get_all_wallets()
    # ... process real wallet data
    return {"wallets": wallets, "total": len(wallets)}
```

### Example: NFT Router

```python
@router.get("/nfts")
async def get_nfts(username: str = Depends(verify_session)):
    """Get all NFTs."""

    # Demo mode - return fake NFTs
    if await is_demo_user(username):
        return await demo_nft_service.get_all_nfts()

    # Real mode - fetch from blockchain
    return await nft_service.get_all_nfts()
```

### Example: Price Router

```python
@router.get("/prices/{symbol}")
async def get_price(symbol: str, username: str = Depends(verify_session)):
    """Get cryptocurrency price."""

    # Demo mode - return fake price
    if await is_demo_user(username):
        return await demo_price_service.get_price(symbol)

    # Real mode - fetch from CoinGecko/CMC
    return await pricing_service.get_price(symbol)
```

## Demo Services API Reference

### DemoWalletService

```python
from services.demo_wallet_service import demo_wallet_service

# Get all demo wallets
wallets = await demo_wallet_service.get_all_wallets()

# Get wallet balance
balance = await demo_wallet_service.get_wallet_balance(address, blockchain)

# Get wallet tokens
tokens = await demo_wallet_service.get_wallet_tokens(address, blockchain)

# Get total balance USD
total = await demo_wallet_service.get_total_balance_usd()
```

**Demo Wallets Include:**
- Cardano: 42,500 ADA (~$44,625)
- Bitcoin: 0.25 BTC (~$24,500)
- Ethereum: 5.75 ETH (~$20,125)
- Solana: 125.50 SOL (~$22,590)
- Polygon: 500.25 POL (~$450)
- Base: 2.50 ETH (~$8,750)

### DemoDeFiService

```python
from services.demo_defi_service import demo_defi_service

# Get staking positions
staking = await demo_defi_service.get_all_staking_positions()

# Get lending positions
lending = await demo_defi_service.get_all_lending_positions()

# Get liquidity positions
liquidity = await demo_defi_service.get_all_liquidity_positions()

# Get farming positions
farming = await demo_defi_service.get_all_farming_positions()

# Get overall DeFi summary
summary = await demo_defi_service.get_defi_summary()

# Get rewards history
history = await demo_defi_service.get_rewards_history(days=30)
```

**Demo DeFi Positions Include:**
- Cardano Staking: 35,000 ADA (4.5% APY)
- Ethereum Staking: 32 ETH (3.8% APY)
- Indigo CDP: 25,000 ADA collateral
- Liqwid Supply: 10,000 ADA (3.2% APY)
- Minswap LP: ADA/MIN pool ($5,250 value)
- SundaeSwap Farming: ADA/SUNDAE (15.8% APY)

### DemoNFTService

```python
from services.demo_nft_service import demo_nft_service

# Get all NFTs
nfts = await demo_nft_service.get_all_nfts()

# Get NFT summary
summary = await demo_nft_service.get_nft_summary()

# Get collection floor price
floor = await demo_nft_service.get_collection_floor_price(policy_id)

# Get NFT details
details = await demo_nft_service.get_nft_details(asset_id)

# Get collection stats
stats = await demo_nft_service.get_collection_stats(policy_id)
```

**Demo NFT Collections Include:**
- Demo Apes: 3 NFTs, 125.50 ADA floor
- Cardano Planets: 2 NFTs, 85 ADA floor
- Clay Nation: 1 NFT, 250 ADA floor
- Demo Dinos: 4 NFTs, 42.50 ADA floor

### DemoPriceService

```python
from services.demo_price_service import demo_price_service

# Get single price
price = await demo_price_service.get_price("ADA")

# Get multiple prices
prices = await demo_price_service.get_prices(["ADA", "BTC", "ETH"])

# Get price with 24h change
data = await demo_price_service.get_price_with_change("ADA")

# Get price history
history = await demo_price_service.get_price_history("ADA", days=30)

# Get market data
market = await demo_price_service.get_market_data("ADA")

# Get trending tokens
trending = await demo_price_service.get_trending_tokens(limit=10)
```

**Demo Prices Include:**
- ADA: $1.05
- BTC: $98,000
- ETH: $3,500
- SOL: $180
- And 20+ other tokens with realistic prices

## Frontend Integration

### Check Demo Mode Status

```javascript
// Check if current user is in demo mode
const response = await fetch('/api/auth/demo-status', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});

const { is_demo } = await response.json();

if (is_demo) {
  // Show "DEMO MODE" banner
  showDemoBanner();
}
```

### Display Demo Mode Banner

```javascript
function showDemoBanner() {
  const banner = document.createElement('div');
  banner.className = 'demo-mode-banner';
  banner.innerHTML = `
    <strong>DEMO MODE</strong> -
    All data is fake. No real API calls are being made.
    <a href="/login">Login</a> with your account to see real data.
  `;
  document.body.prepend(banner);
}
```

### CSS for Demo Banner

```css
.demo-mode-banner {
  background: linear-gradient(90deg, #ff6b6b, #ff8e53);
  color: white;
  padding: 12px 20px;
  text-align: center;
  font-weight: 500;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  position: sticky;
  top: 0;
  z-index: 9999;
}

.demo-mode-banner a {
  color: white;
  text-decoration: underline;
  margin-left: 10px;
}
```

## Router Update Checklist

When adding demo mode support to a router:

1. ✅ Import required utilities:
   ```python
   from middleware.demo_mode import is_demo_user
   from services.demo_*_service import demo_*_service
   from auth_utils import verify_session
   ```

2. ✅ Add `username` parameter to endpoints:
   ```python
   async def endpoint(username: str = Depends(verify_session)):
   ```

3. ✅ Add demo mode check at start of function:
   ```python
   if await is_demo_user(username):
       return await demo_service.get_fake_data()
   ```

4. ✅ Ensure NO real API calls in demo mode:
   - No Blockfrost calls
   - No TapTools calls
   - No CoinGecko calls
   - No blockchain RPC calls

5. ✅ Return realistic fake data:
   - Use demo service methods
   - Include `demo_mode: True` flag in response

## Routers to Update

### Priority 1 (Core Data)
- ✅ `/wallets` - Use `demo_wallet_service`
- 🔲 `/nfts` - Use `demo_nft_service`
- 🔲 `/prices` - Use `demo_price_service`
- 🔲 `/defi` - Use `demo_defi_service`
- 🔲 `/portfolio` - Aggregate demo services

### Priority 2 (Features)
- 🔲 `/exchanges` - Return empty or mock exchange data
- 🔲 `/custom_tokens` - Return demo tokens
- 🔲 `/settings` - Allow viewing but prevent changes

### Skip (Admin Only)
- `/auth` - Already handles demo user
- `/backup` - Admin only, no demo mode needed
- `/security` - Admin only, no demo mode needed
- `/logs` - Admin only, no demo mode needed

## Testing Demo Mode

### Test Demo Login

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "demo"}'
```

### Test Demo Status

```bash
curl http://localhost:8000/api/auth/demo-status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Test Demo Wallets

```bash
curl http://localhost:8000/api/wallets \
  -H "Authorization: Bearer YOUR_DEMO_TOKEN"
```

## Security Considerations

1. **No Real Data Access**: Demo users NEVER access real wallet data
2. **No API Keys**: Demo mode never uses real API keys
3. **No Database Writes**: Demo users should not modify real data
4. **Session Isolation**: Demo sessions are separate from real user sessions
5. **Rate Limiting**: Demo requests still count toward rate limits (but make no real API calls)

## Troubleshooting

### Demo User Not Created

Check logs during startup:
```
INFO: Demo user created successfully (username: demo, password: demo)
```

If not created, run:
```python
from middleware.demo_mode import create_demo_user
await create_demo_user()
```

### Real API Calls Still Happening

Ensure demo check is BEFORE any service calls:
```python
# ❌ WRONG - API call happens before check
wallets = await get_all_wallets()
if await is_demo_user(username):
    return demo_wallets

# ✅ CORRECT - Check first
if await is_demo_user(username):
    return await demo_wallet_service.get_all_wallets()
wallets = await get_all_wallets()
```

### Demo Data Not Showing

1. Verify demo user is logged in:
   ```bash
   curl http://localhost:8000/api/auth/demo-status -H "Authorization: Bearer TOKEN"
   ```

2. Check `is_demo` flag in session:
   ```python
   session_data = active_sessions.get(token)
   print(session_data.get('is_demo'))  # Should be True
   ```

3. Ensure router imports demo service:
   ```python
   from services.demo_wallet_service import demo_wallet_service
   ```

## Future Enhancements

- [ ] Add more demo NFT collections
- [ ] Generate random price variations in real-time
- [ ] Add demo transaction history
- [ ] Mock exchange balances (Coinbase, Kraken, etc.)
- [ ] Add demo DeFi protocol integrations
- [ ] Configurable demo portfolio values
- [ ] Multiple demo user profiles (conservative, aggressive, etc.)

## Summary

The Demo Mode system provides a complete mocking layer for the ABCT application, allowing demo users to explore all features without:
- Making real API calls
- Requiring API keys
- Accessing blockchain networks
- Exposing real portfolio data

All demo services return realistic, pre-defined fake data that looks and feels like real data, providing an excellent onboarding and demonstration experience.
