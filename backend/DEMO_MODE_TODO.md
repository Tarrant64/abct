# Demo Mode Integration TODO List

Quick checklist for integrating demo mode into remaining routers.

## ✅ Completed

- [x] **Core Infrastructure**
  - [x] `middleware/demo_mode.py` created
  - [x] `services/demo_wallet_service.py` created
  - [x] `services/demo_defi_service.py` created
  - [x] `services/demo_nft_service.py` created
  - [x] `services/demo_price_service.py` created
  - [x] Database schema updated (is_demo column)
  - [x] Auth system updated (demo user creation)
  - [x] Documentation created

- [x] **Wallets Router** (`routers/wallets.py`)
  - [x] Import demo utilities
  - [x] Add username parameter
  - [x] Add demo mode check
  - [x] Return demo wallet data

## 🔲 High Priority - Core Data Routers

### NFTs Router (`routers/nfts.py`)

**Endpoints to Update:**
- [ ] `GET /nfts` - get_all_nfts()
- [ ] `GET /nfts/summary` - get_nft_summary()
- [ ] `GET /nfts/{policy_id}` - get collection details
- [ ] `GET /nfts/floor-prices` - get floor prices

**Steps:**
1. [ ] Import demo utilities
   ```python
   from middleware.demo_mode import is_demo_user
   from services.demo_nft_service import demo_nft_service
   from services.demo_price_service import demo_price_service
   from auth_utils import verify_session
   ```

2. [ ] Add username parameter to each endpoint
   ```python
   async def endpoint(username: str = Depends(verify_session)):
   ```

3. [ ] Add demo checks
   ```python
   if await is_demo_user(username):
       return await demo_nft_service.get_all_nfts()
   ```

4. [ ] Test with demo user

**Estimated Time:** 20 minutes

---

### Prices Router (`routers/prices.py`)

**Endpoints to Update:**
- [ ] `GET /prices/{symbol}` - get single price
- [ ] `GET /prices` - get multiple prices
- [ ] `GET /prices/history/{symbol}` - get price history

**Steps:**
1. [ ] Import demo utilities
   ```python
   from middleware.demo_mode import is_demo_user
   from services.demo_price_service import demo_price_service
   from auth_utils import verify_session
   ```

2. [ ] Add username parameter to each endpoint

3. [ ] Add demo checks
   ```python
   if await is_demo_user(username):
       return await demo_price_service.get_price(symbol)
   ```

4. [ ] Test with demo user

**Estimated Time:** 15 minutes

---

### DeFi Router (`routers/defi.py`)

**Endpoints to Update:**
- [ ] `GET /defi/staking` - get staking positions
- [ ] `GET /defi/lending` - get lending positions
- [ ] `GET /defi/liquidity` - get LP positions
- [ ] `GET /defi/summary` - get DeFi summary

**Steps:**
1. [ ] Import demo utilities
   ```python
   from middleware.demo_mode import is_demo_user
   from services.demo_defi_service import demo_defi_service
   from auth_utils import verify_session
   ```

2. [ ] Add username parameter to each endpoint

3. [ ] Add demo checks
   ```python
   if await is_demo_user(username):
       return await demo_defi_service.get_all_staking_positions()
   ```

4. [ ] Test with demo user

**Estimated Time:** 20 minutes

---

### Portfolio Router (`routers/portfolio.py`)

**Endpoints to Update:**
- [ ] `GET /portfolio/summary` - get complete portfolio
- [ ] `GET /portfolio/history` - get historical data
- [ ] `GET /portfolio/breakdown` - get asset breakdown

**Steps:**
1. [ ] Import ALL demo services
   ```python
   from middleware.demo_mode import is_demo_user
   from services.demo_wallet_service import demo_wallet_service
   from services.demo_defi_service import demo_defi_service
   from services.demo_nft_service import demo_nft_service
   from services.demo_price_service import demo_price_service
   from auth_utils import verify_session
   ```

2. [ ] Add username parameter to each endpoint

3. [ ] Add demo checks with aggregation
   ```python
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
           "breakdown": {...},
           "demo_mode": True
       }
   ```

4. [ ] Test with demo user

**Estimated Time:** 30 minutes

---

## 🔲 Medium Priority - Feature Routers

### Exchanges Router (`routers/exchanges.py`)

**Endpoints to Update:**
- [ ] `GET /exchanges` - get connected exchanges
- [ ] `GET /exchanges/{exchange_id}` - get single exchange

**Steps:**
1. [ ] Import demo utilities

2. [ ] Add demo checks
   ```python
   if await is_demo_user(username):
       return {
           "exchanges": [
               {
                   "name": "Coinbase",
                   "connected": True,
                   "total_value_usd": 5000.00,
                   "balances": [...]
               }
           ],
           "demo_mode": True
       }
   ```

3. [ ] Test with demo user

**Estimated Time:** 15 minutes

---

### Custom Tokens Router (`routers/custom_tokens.py`)

**Endpoints to Update:**
- [ ] `GET /custom-tokens` - get all custom tokens
- [ ] `POST /custom-tokens` - skip for demo (read-only)

**Steps:**
1. [ ] Import demo utilities

2. [ ] Add demo checks
   ```python
   if await is_demo_user(username):
       # Return demo tokens or empty list
       return {"tokens": [], "demo_mode": True}
   ```

3. [ ] Block writes for demo users
   ```python
   @router.post("/custom-tokens")
   async def add_custom_token(username: str = Depends(verify_session)):
       if await is_demo_user(username):
           raise HTTPException(403, "Demo users cannot modify data")
   ```

4. [ ] Test with demo user

**Estimated Time:** 10 minutes

---

## 🔲 Low Priority - Settings & Admin

### Settings Router (`routers/settings.py`)

**Endpoints to Update:**
- [ ] `GET /settings/apis` - allow viewing
- [ ] `PUT /settings/apis/{api_id}` - block for demo users

**Steps:**
1. [ ] Allow viewing API settings
   ```python
   if await is_demo_user(username):
       # Return generic info, no real keys
       return {"apis": [...], "demo_mode": True}
   ```

2. [ ] Block modifications
   ```python
   @router.put("/settings/apis/{api_id}")
   async def update_api(username: str = Depends(verify_session)):
       if await is_demo_user(username):
           raise HTTPException(403, "Demo users cannot modify settings")
   ```

**Estimated Time:** 10 minutes

---

## 🎯 Total Estimated Time

- **High Priority:** ~85 minutes (1.5 hours)
- **Medium Priority:** ~25 minutes
- **Low Priority:** ~10 minutes
- **Testing & Debugging:** ~30 minutes

**Total:** ~2.5 hours to complete all routers

---

## ✅ Testing Checklist

After updating each router, verify:

### Functional Tests
- [ ] Demo user can access endpoint without errors
- [ ] Response includes `"demo_mode": true` flag
- [ ] Demo data is complete and realistic
- [ ] Real users still work normally
- [ ] No API calls appear in logs for demo requests

### Security Tests
- [ ] Demo user cannot modify real data (POST/PUT/DELETE)
- [ ] Demo user has no access to real portfolio data
- [ ] API keys are never used for demo requests
- [ ] Session isolation works (demo vs real users)

### Integration Tests
- [ ] Frontend displays "DEMO MODE" banner
- [ ] All demo endpoints return valid JSON
- [ ] No 500 errors for demo users
- [ ] Consistent demo data across all endpoints

---

## 🚀 Quick Start Script

Use this to test each router as you update it:

```bash
#!/bin/bash

# Get demo token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "demo"}' \
  | jq -r '.token')

echo "Testing with token: $TOKEN"

# Test wallets (completed)
echo "Testing /wallets..."
curl -s http://localhost:8000/api/wallets \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.demo_mode'

# Test NFTs (TODO)
echo "Testing /nfts..."
curl -s http://localhost:8000/api/nfts \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.demo_mode'

# Test prices (TODO)
echo "Testing /prices/ADA..."
curl -s http://localhost:8000/api/prices/ADA \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.demo_mode'

# Test DeFi (TODO)
echo "Testing /defi/summary..."
curl -s http://localhost:8000/api/defi/summary \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.demo_mode'

# Test portfolio (TODO)
echo "Testing /portfolio/summary..."
curl -s http://localhost:8000/api/portfolio/summary \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.demo_mode'

echo "All tests complete!"
```

Save as `test_demo_routers.sh` and run after each router update.

---

## 📋 Code Snippet Reference

### Standard Pattern

```python
# 1. Imports (add to top of file)
from middleware.demo_mode import is_demo_user
from services.demo_*_service import demo_*_service
from auth_utils import verify_session

# 2. Update endpoint signature
@router.get("/endpoint")
async def endpoint_name(
    # ... existing parameters ...
    username: str = Depends(verify_session)  # ADD THIS
):
    """Endpoint description."""

    # 3. Add demo check FIRST
    if await is_demo_user(username):
        demo_data = await demo_service.get_data()
        return {
            **demo_data,
            "demo_mode": True  # ALWAYS include
        }

    # 4. Existing logic continues
    # ... real user flow ...
```

### Blocking Writes

```python
@router.post("/endpoint")
async def create_something(username: str = Depends(verify_session)):
    # Block demo users from modifying data
    if await is_demo_user(username):
        raise HTTPException(
            status_code=403,
            detail="Demo users cannot modify data. Please create a real account."
        )

    # Real user can proceed
    # ...
```

---

## 📝 Progress Tracking

Update this as you complete routers:

```
High Priority:
[x] Wallets     - COMPLETED
[ ] NFTs        - In Progress / Not Started
[ ] Prices      - In Progress / Not Started
[ ] DeFi        - In Progress / Not Started
[ ] Portfolio   - In Progress / Not Started

Medium Priority:
[ ] Exchanges       - Not Started
[ ] Custom Tokens   - Not Started

Low Priority:
[ ] Settings    - Not Started

Testing:
[ ] All endpoints tested
[ ] Frontend integration complete
[ ] Documentation updated
```

---

## 🎉 Completion Criteria

Mark as complete when:
- [x] All demo services created
- [ ] All high-priority routers updated
- [ ] All endpoints return demo data for demo user
- [ ] Zero real API calls for demo accounts
- [ ] Frontend shows "DEMO MODE" banner
- [ ] All tests passing
- [ ] Documentation reviewed

**Current Status:** Core infrastructure complete, router integration in progress

**Next Step:** Update NFTs router with demo mode integration
