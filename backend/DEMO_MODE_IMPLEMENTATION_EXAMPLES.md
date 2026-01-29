# Demo Mode Implementation Examples

Quick reference for implementing demo mode in ABCT routers.

## Example 1: Wallets Router (COMPLETED)

```python
from fastapi import APIRouter, Depends
from middleware.demo_mode import is_demo_user
from services.demo_wallet_service import demo_wallet_service
from auth_utils import verify_session

router = APIRouter(prefix="/wallets", tags=["wallets"])

@router.get("")
async def list_wallets(username: str = Depends(verify_session)):
    """List all tracked wallets with their current balances."""

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
    # ... existing logic
    return {"wallets": wallets, "total": len(wallets)}
```

## Example 2: NFTs Router (TODO)

```python
from fastapi import APIRouter, Depends
from middleware.demo_mode import is_demo_user
from services.demo_nft_service import demo_nft_service
from auth_utils import verify_session

router = APIRouter(prefix="/nfts", tags=["nfts"])

@router.get("")
async def get_all_nfts(
    force_refresh: bool = False,
    username: str = Depends(verify_session)
):
    """Get all NFTs across all wallets."""

    # Demo mode - return fake NFTs
    if await is_demo_user(username):
        nfts = await demo_nft_service.get_all_nfts()
        ada_price = await demo_price_service.get_price('ADA')

        return {
            'nfts': nfts,
            'total_count': len(nfts),
            'total_value_usd': sum(n.get('price_usd', 0) for n in nfts),
            'ada_price': ada_price,
            'demo_mode': True
        }

    # Real user flow
    all_nfts = await nft_service.get_all_nfts(force_refresh=force_refresh)
    # ... existing logic
    return {...}


@router.get("/summary")
async def get_nft_summary(username: str = Depends(verify_session)):
    """Get a summary of all NFTs grouped by collection."""

    # Demo mode
    if await is_demo_user(username):
        return await demo_nft_service.get_nft_summary()

    # Real user flow
    summary = await nft_service.get_nft_summary()
    # ... existing logic
    return summary
```

## Example 3: Prices Router (TODO)

```python
from fastapi import APIRouter, Depends
from middleware.demo_mode import is_demo_user
from services.demo_price_service import demo_price_service
from auth_utils import verify_session

router = APIRouter(prefix="/prices", tags=["prices"])

@router.get("/{symbol}")
async def get_price(symbol: str, username: str = Depends(verify_session)):
    """Get current price for a cryptocurrency."""

    # Demo mode
    if await is_demo_user(username):
        price_data = await demo_price_service.get_price_with_change(symbol)
        return {
            **price_data,
            "demo_mode": True
        }

    # Real user flow
    price = await pricing_service.get_price(symbol)
    # ... existing logic
    return {"price": price, "symbol": symbol}


@router.get("/history/{symbol}")
async def get_price_history(
    symbol: str,
    days: int = 30,
    username: str = Depends(verify_session)
):
    """Get historical price data."""

    # Demo mode
    if await is_demo_user(username):
        history = await demo_price_service.get_price_history(symbol, days)
        return {
            "symbol": symbol,
            "history": history,
            "demo_mode": True
        }

    # Real user flow
    # ... existing logic
    return {...}
```

## Example 4: DeFi Router (TODO)

```python
from fastapi import APIRouter, Depends
from middleware.demo_mode import is_demo_user
from services.demo_defi_service import demo_defi_service
from auth_utils import verify_session

router = APIRouter(prefix="/defi", tags=["defi"])

@router.get("/staking")
async def get_staking_positions(username: str = Depends(verify_session)):
    """Get all staking positions."""

    # Demo mode
    if await is_demo_user(username):
        positions = await demo_defi_service.get_all_staking_positions()
        summary = await demo_defi_service.get_staking_summary()
        return {
            "positions": positions,
            "summary": summary,
            "demo_mode": True
        }

    # Real user flow
    # ... existing logic
    return {...}


@router.get("/summary")
async def get_defi_summary(username: str = Depends(verify_session)):
    """Get overall DeFi portfolio summary."""

    # Demo mode
    if await is_demo_user(username):
        return await demo_defi_service.get_defi_summary()

    # Real user flow
    # ... existing logic
    return {...}
```

## Example 5: Portfolio Router (TODO)

```python
from fastapi import APIRouter, Depends
from middleware.demo_mode import is_demo_user
from services.demo_wallet_service import demo_wallet_service
from services.demo_defi_service import demo_defi_service
from services.demo_nft_service import demo_nft_service
from auth_utils import verify_session

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

@router.get("/summary")
async def get_portfolio_summary(username: str = Depends(verify_session)):
    """Get complete portfolio summary."""

    # Demo mode - aggregate all demo services
    if await is_demo_user(username):
        wallet_total = await demo_wallet_service.get_total_balance_usd()
        defi_summary = await demo_defi_service.get_defi_summary()
        nft_summary = await demo_nft_service.get_nft_summary()

        total_value = (
            wallet_total['total_usd'] +
            defi_summary['total_defi_value_usd'] +
            nft_summary['total_value_usd']
        )

        return {
            "total_value_usd": total_value,
            "wallets_value_usd": wallet_total['total_usd'],
            "defi_value_usd": defi_summary['total_defi_value_usd'],
            "nft_value_usd": nft_summary['total_value_usd'],
            "breakdown": {
                **wallet_total['breakdown'],
                "defi": defi_summary['total_defi_value_usd'],
                "nfts": nft_summary['total_value_usd']
            },
            "demo_mode": True
        }

    # Real user flow
    # ... existing logic
    return {...}
```

## Example 6: Exchanges Router (TODO)

For exchanges, we can either return empty data or mock some exchange balances:

```python
from fastapi import APIRouter, Depends
from middleware.demo_mode import is_demo_user
from auth_utils import verify_session

router = APIRouter(prefix="/exchanges", tags=["exchanges"])

@router.get("")
async def get_exchanges(username: str = Depends(verify_session)):
    """Get all connected exchanges."""

    # Demo mode - return empty or mock exchanges
    if await is_demo_user(username):
        return {
            "exchanges": [
                {
                    "name": "Coinbase",
                    "connected": True,
                    "total_value_usd": 5000.00,
                    "balances": [
                        {"asset": "BTC", "amount": "0.05", "value_usd": 4900.00},
                        {"asset": "ETH", "amount": "0.025", "value_usd": 87.50},
                    ]
                }
            ],
            "total_value_usd": 5000.00,
            "demo_mode": True
        }

    # Real user flow
    # ... existing logic
    return {...}
```

## Pattern Template

Use this template when adding demo mode to any router:

```python
# 1. Add imports
from middleware.demo_mode import is_demo_user
from services.demo_*_service import demo_*_service  # Replace with actual service
from auth_utils import verify_session

# 2. Add username parameter
@router.get("/endpoint")
async def endpoint_name(
    # ... other parameters ...
    username: str = Depends(verify_session)
):
    """Endpoint description."""

    # 3. Add demo mode check FIRST (before any real API calls)
    if await is_demo_user(username):
        # Return fake data using demo service
        demo_data = await demo_*_service.get_*()
        return {
            **demo_data,
            "demo_mode": True  # Always include this flag
        }

    # 4. Real user flow continues as normal
    # ... existing logic ...
    return {...}
```

## Common Mistakes to Avoid

### ❌ WRONG - API Call Before Check

```python
# This makes a real API call even for demo users!
wallets = await get_all_wallets()  # ❌ API CALL HAPPENS HERE

if await is_demo_user(username):
    return demo_wallets

return wallets
```

### ✅ CORRECT - Check First

```python
# Check demo mode BEFORE any API calls
if await is_demo_user(username):  # ✅ CHECK FIRST
    return await demo_wallet_service.get_all_wallets()

# Real API calls only happen if not demo
wallets = await get_all_wallets()
return wallets
```

### ❌ WRONG - Missing username Parameter

```python
@router.get("/data")
async def get_data():  # ❌ No username parameter
    # Can't check demo mode without username!
    return await service.get_data()
```

### ✅ CORRECT - Include username

```python
@router.get("/data")
async def get_data(username: str = Depends(verify_session)):  # ✅ Has username
    if await is_demo_user(username):
        return await demo_service.get_data()
    return await service.get_data()
```

### ❌ WRONG - Forgetting demo_mode Flag

```python
if await is_demo_user(username):
    return {"data": demo_data}  # ❌ Frontend won't know it's demo data
```

### ✅ CORRECT - Include Flag

```python
if await is_demo_user(username):
    return {
        "data": demo_data,
        "demo_mode": True  # ✅ Frontend can detect demo mode
    }
```

## Testing Checklist

After implementing demo mode in a router:

- [ ] Demo user can access endpoint without errors
- [ ] No real API calls are made (check logs)
- [ ] Response includes `"demo_mode": true` flag
- [ ] Demo data is realistic and complete
- [ ] Real users still work normally
- [ ] No database writes from demo users
- [ ] API keys are not used for demo requests

## Quick Test Script

```bash
#!/bin/bash

# Test demo login
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "demo"}' \
  | jq -r '.token')

echo "Demo token: $TOKEN"

# Test demo status
curl -s http://localhost:8000/api/auth/demo-status \
  -H "Authorization: Bearer $TOKEN" \
  | jq

# Test demo wallets
curl -s http://localhost:8000/api/wallets \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.demo_mode'  # Should print: true

# Test demo NFTs (once implemented)
curl -s http://localhost:8000/api/nfts \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.demo_mode'  # Should print: true
```

## Summary

Implementing demo mode is straightforward:

1. Import demo utilities and services
2. Add `username: str = Depends(verify_session)` parameter
3. Check `await is_demo_user(username)` FIRST
4. Return demo service data with `demo_mode: True` flag
5. Real user logic continues as normal

The demo user will see realistic fake data while making ZERO real API calls.
