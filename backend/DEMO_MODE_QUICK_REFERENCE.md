# Demo Mode Quick Reference Card

## 🔑 Demo Credentials
```
Username: demo
Password: demo
```

## 📝 Quick Integration Pattern

```python
# 1. Add imports (top of file)
from middleware.demo_mode import is_demo_user
from services.demo_*_service import demo_*_service
from auth_utils import verify_session

# 2. Update endpoint
@router.get("/endpoint")
async def endpoint(username: str = Depends(verify_session)):

    # 3. Check demo mode FIRST
    if await is_demo_user(username):
        return await demo_service.get_data()

    # 4. Real user flow
    return await real_service.get_data()
```

## 🎯 Demo Services

| Service | Import | Example Usage |
|---------|--------|---------------|
| **Wallets** | `demo_wallet_service` | `await demo_wallet_service.get_all_wallets()` |
| **DeFi** | `demo_defi_service` | `await demo_defi_service.get_defi_summary()` |
| **NFTs** | `demo_nft_service` | `await demo_nft_service.get_all_nfts()` |
| **Prices** | `demo_price_service` | `await demo_price_service.get_price("ADA")` |

## 🧪 Quick Test

```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "demo"}'

# Save token, then test
curl http://localhost:8000/api/wallets \
  -H "Authorization: Bearer TOKEN"
```

## ✅ Checklist

Before deploying router changes:
- [ ] Import demo utilities
- [ ] Add `username` parameter
- [ ] Check `is_demo_user()` FIRST
- [ ] Return with `demo_mode: true`
- [ ] Test with demo user
- [ ] Verify no API calls in logs

## 📚 Documentation

- **Complete Guide:** `DEMO_MODE_GUIDE.md`
- **Examples:** `DEMO_MODE_IMPLEMENTATION_EXAMPLES.md`
- **TODO List:** `DEMO_MODE_TODO.md`
- **Summary:** `DEMO_MODE_COMPLETE.md`

## 🚫 Common Mistakes

```python
# ❌ WRONG - API call happens first
data = await api_call()
if await is_demo_user(username):
    return demo_data

# ✅ CORRECT - Check first
if await is_demo_user(username):
    return demo_data
data = await api_call()
```

## 📊 Demo Portfolio

Total Value: **~$207,480 USD**

- Wallets: $121,040 (6 chains)
- DeFi: $85,000 (6 positions)
- NFTs: $1,440 (10 NFTs)

## 🔐 Security

**Demo users NEVER:**
- ❌ Make real API calls
- ❌ Access real wallet data
- ❌ Use API keys
- ❌ Modify real data

**Always:**
- ✅ Get fake data
- ✅ Zero external calls
- ✅ Instant responses

---

*Pin this for quick reference during integration*
