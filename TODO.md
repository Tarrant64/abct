# ABCT - TODO List

**Last Updated**: January 28, 2026
**Status**: Ready for User Implementation

---

## PART 1: API Utilization Tracking - Remaining Work

### High Priority (Do First)

- [ ] **Update remaining services to use TrackedAsyncClient**:

  **Services to Update**:
  - [ ] `backend/services/ethereum.py`
    - Change: `httpx.AsyncClient()` → `get_alchemy_client()`
    - Estimated time: 10 minutes

  - [ ] `backend/services/polygon.py`
    - Change: `httpx.AsyncClient()` → `get_alchemy_client()`
    - Estimated time: 10 minutes

  - [ ] `backend/services/base.py`
    - Change: `httpx.AsyncClient()` → `get_alchemy_client()`
    - Estimated time: 10 minutes

  - [ ] `backend/services/solana.py`
    - Change: `httpx.AsyncClient()` → `get_helius_client()`
    - Estimated time: 10 minutes

  - [ ] `backend/services/pricing.py`
    - Change: `httpx.AsyncClient()` → `get_coingecko_client()` / `get_coinmarketcap_client()`
    - Estimated time: 15 minutes

  - [ ] `backend/services/etherscan.py` (if exists)
    - Change: `httpx.AsyncClient()` → `get_etherscan_client()`
    - Estimated time: 10 minutes

  **Total Estimated Time**: 1-1.5 hours

### Testing

- [ ] **Test API Tracking**:
  ```bash
  # 1. Refresh portfolio with some wallets
  # 2. Check database for recorded calls:
  sqlite3 /path/to/abct.db "SELECT api_name, call_count, period_start FROM api_usage WHERE period_start >= date('now');"

  # Expected: Should see entries for blockfrost, taptools, etc. with call_count > 0
  ```

- [ ] **Test Frontend Display**:
  - Navigate to `http://192.168.50.225:8081/apis.html`
  - Expand "API Utilization" section
  - Verify call counts are NOT 0
  - Verify percentages calculated correctly
  - Verify color coding (green < 50%, yellow 50-80%, red > 80%)
  - Test "Edit Limit" button
  - Change a limit and save
  - Refresh and verify new limit applied

- [ ] **Test Edge Cases**:
  - Verify usage resets at midnight
  - Test with API that hits rate limit (should see HTTP 429)
  - Test with unconfigured API (should show N/A)

### Documentation

- [ ] **Add Usage Notes**:
  - Update README with API tracking information
  - Document how to view usage stats
  - Add troubleshooting section

---

## PART 2: Midnight Integration - Phase 1

### Immediate (NIGHT on Cardano)

- [ ] **Add NIGHT Token to Database**:
  ```bash
  # Option 1: Run SQL script
  cd /Users/chriscata/Documents/Claude-Projects/ABCT
  sqlite3 /path/to/abct.db < add_night_token.sql

  # Option 2: Manual SQL
  # (SQL provided in add_night_token.sql)
  ```

- [ ] **Test NIGHT Tracking**:
  - Find a Cardano wallet with NIGHT tokens
  - Add wallet to ABCT (if not already added)
  - Refresh portfolio
  - Verify NIGHT appears in token list
  - Verify quantity matches Cardanoscan
  - Check USD value (once NIGHT is listed on price APIs)

- [ ] **Add NIGHT Branding** (Optional):
  - Download Midnight logo from https://midnight.network/
  - Add to `frontend/static/images/midnight-logo.png`
  - Update CSS to display logo for NIGHT token

**Estimated Time**: 30 minutes - 1 hour

---

## PART 2: Midnight Integration - Phase 2

### Wait for Mainnet Launch (Q1-Q2 2026)

- [ ] **Monitor Mainnet Launch**:
  - Subscribe to Midnight announcements
  - Wait for official mainnet RPC URL
  - Get API key if required
  - Review final API documentation

### After Mainnet Launch

- [ ] **Implement Full Midnight Support**:
  - Create `backend/services/midnight.py` (template in MIDNIGHT_INTEGRATION_PLAN.md)
  - Create `backend/routers/midnight.py` (template in plan)
  - Update `backend/routers/portfolio.py` to include Midnight
  - Add "midnight" to blockchain enum
  - Update frontend to support Midnight addresses

- [ ] **Frontend Updates**:
  - Add Midnight option to "Add Wallet" dropdown
  - Add Midnight balance display
  - Add DUST balance display
  - Add Midnight transaction history view
  - Add link to Midnight explorer

- [ ] **Testing**:
  - Create test wallet on Midnight network
  - Add wallet to ABCT
  - Verify balance fetching works
  - Verify transaction history works
  - Test portfolio aggregation includes Midnight

**Estimated Time**: 3-4 days after mainnet launch

---

## PART 3: Enhancements (Optional, Low Priority)

### API Tracking Enhancements

- [ ] **Add Usage Alerts**:
  - Log warning when any API reaches 80% usage
  - Optional: Send email/notification at 90%
  - Display warning in admin dashboard

- [ ] **Add Historical Analytics**:
  - Keep last 30 days of usage data
  - Show usage charts/graphs
  - Identify usage patterns
  - Suggest optimization opportunities

- [ ] **Implement Smart Caching**:
  - Adjust cache TTL based on usage
  - Longer cache when approaching limits
  - Automatic refresh rate adjustment

- [ ] **Add Request Queuing** (Advanced):
  - Queue requests when near limit
  - Throttle automatically to stay under limit
  - Prioritize user-initiated vs background requests

### Midnight Enhancements

- [ ] **Add NIGHT Price Tracking**:
  - Monitor CoinGecko/CMC for NIGHT listing
  - Add to pricing service when available
  - Display USD value in portfolio

- [ ] **Add Bridge Tracking**:
  - Track NIGHT on both Cardano and Midnight
  - Label clearly which network
  - Show bridge transaction history

- [ ] **Add Staking Support**:
  - If Midnight supports staking
  - Display staked NIGHT
  - Calculate DUST generation rate
  - Show staking rewards

---

## Quick Wins (Do These First)

1. ✅ **API Tracking**: Update services (1-1.5 hours)
2. ✅ **API Tracking**: Test and verify (30 minutes)
3. ✅ **Midnight**: Add NIGHT token to DB (5 minutes)
4. ✅ **Midnight**: Test NIGHT tracking (15 minutes)

**Total Time for Quick Wins**: 2-2.5 hours

---

## Files Reference

### Documentation
- `API_TRACKING_IMPLEMENTATION.md` - Complete implementation guide
- `MIDNIGHT_INTEGRATION_PLAN.md` - Full Midnight integration plan
- `API_RATE_LIMITS_RESEARCH.md` - Verified rate limits
- `IMPLEMENTATION_SUMMARY.md` - Quick overview
- `TODO.md` (this file) - Task checklist

### Code
- `backend/middleware/api_tracker.py` - API tracking middleware (NEW)
- `backend/routers/settings.py` - Updated rate limits
- `backend/services/cardano.py` - Example implementation (UPDATED)
- `backend/services/taptools.py` - Example implementation (UPDATED)

### Scripts
- `add_night_token.sql` - Database migration for NIGHT token

---

## Testing Commands

### Check API Usage
```bash
# View current usage
sqlite3 /path/to/abct.db "SELECT api_name, call_count, period_start FROM api_usage WHERE period_start >= date('now') ORDER BY call_count DESC;"

# View via API
curl http://192.168.50.225:8081/settings/api-utilization | python -m json.tool

# Clear old usage data (optional)
sqlite3 /path/to/abct.db "DELETE FROM api_usage WHERE period_end < date('now', '-30 days');"
```

### Check NIGHT Token
```bash
# Verify NIGHT is in database
sqlite3 /path/to/abct.db "SELECT ticker, name, decimals FROM token_metadata WHERE ticker = 'NIGHT';"

# Check if any wallets have NIGHT
sqlite3 /path/to/abct.db "SELECT COUNT(*) FROM native_assets WHERE policy_id = '0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa';"
```

---

## Success Criteria

### API Tracking
- ✅ All services use `TrackedAsyncClient`
- ✅ API usage shows non-zero values in frontend
- ✅ Percentages calculated correctly
- ✅ No HTTP 429 errors during normal use
- ✅ Daily usage stays under 80% of limits

### Midnight Phase 1
- ✅ NIGHT token appears in token_metadata
- ✅ NIGHT balances display correctly for Cardano wallets
- ✅ Quantities match Cardanoscan
- ✅ Price tracking works (when available)

### Midnight Phase 2 (Post-Mainnet)
- ✅ Can add Midnight wallet addresses
- ✅ NIGHT and DUST balances fetch correctly
- ✅ Transaction history displays
- ✅ Portfolio includes Midnight totals
- ✅ Explorer links work

---

## Notes

- **API Tracking**: Infrastructure complete, just need to update services
- **Midnight Phase 1**: Can do immediately, no dependencies
- **Midnight Phase 2**: Requires mainnet launch (Q1-Q2 2026)
- **All code templates provided** in documentation
- **All rate limits verified** from official sources
- **Comprehensive testing procedures** documented

---

## Next Session Checklist

When you return to continue this work:

1. Read `IMPLEMENTATION_SUMMARY.md` for overview
2. Follow this TODO list in order
3. Start with "Quick Wins" section
4. Update this file as you complete tasks
5. Refer to detailed docs as needed

---

**Status**: Ready to implement
**Blocker**: None (all prerequisites met)
**Documentation**: Complete
**Code Examples**: Provided
**Estimated Total Effort**: 2-3 hours for Phase 1, 3-4 days for Phase 2 (post-mainnet)
