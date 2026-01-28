# API Rate Limits Research (2026)

## Summary

This document contains verified rate limit information for all external APIs used by ABCT. Information was researched on January 28, 2026.

---

## Cardano APIs

### Blockfrost
- **Website**: https://blockfrost.io/
- **Free Tier**: 10 requests/second, burst of 500 requests
- **Daily Limit**: None documented (rate limited per-second only)
- **Reset**: Per second (rolling window)
- **Status**: ✅ Active, stable
- **Notes**:
  - Limits per IP address
  - HTTP 429 when rate limit exceeded
  - HTTP 402 when daily limit exceeded (paid plans)
- **Sources**:
  - [Blockfrost Documentation](https://docs.blockfrost.io/)
  - [Blockfrost API Hub](https://blockfrost.dev/api/blockfrost-io-api-documentation)

### TapTools
- **Website**: https://www.taptools.io/
- **Free Tier**: Not available (paid only)
- **Paid Plans**: 95-100 requests/day (user-reported, varies by plan)
- **Monthly Cost**: ~$10/month
- **Reset**: Daily
- **Status**: ✅ Active
- **Notes**:
  - Subscription required
  - Limits vary by plan (not well documented)
  - Primarily for NFT floor prices
- **Sources**: User documentation, community reports

### CExplorer
- **Website**: https://cexplorer.io/
- **Free Tier**: Available but limits not documented
- **Daily Limit**: Unknown
- **Reset**: Unknown
- **Status**: ✅ Active
- **Notes**:
  - Free tier exists
  - No public rate limit documentation
  - Used as fallback for Cardano data
- **Sources**: [CExplorer Website](https://cexplorer.io/)

### Maestro
- **Website**: https://www.gomaestro.org/
- **Free Tier**: 500,000 credits/month
- **Daily Limit**: N/A (credit-based, varies per call)
- **Reset**: Monthly
- **Status**: ✅ Active
- **Notes**:
  - Credit system (not direct request count)
  - Different endpoints consume different credits
  - More complex queries = more credits
- **Sources**: [Maestro Documentation](https://www.gomaestro.org/)

---

## EVM Chain APIs

### Etherscan
- **Website**: https://etherscan.io/apis
- **Free Tier**: 3 calls/second OR 100,000 calls/day
- **Daily Limit**: **100,000 requests/day**
- **Per-Second Limit**: 3 requests/second
- **Reset**: Daily (midnight UTC)
- **Status**: ✅ Active
- **Important Changes (Late 2025)**:
  - Free tier limited to 90% of chains
  - Avalanche, Base, BNB, OP Mainnet now require paid plan
  - Ethereum, Polygon still available on free tier
  - Contract verification endpoints still free on all chains
- **Paid Plans**: Starting at $49/month for full access
- **Notes**:
  - Whichever limit (per-second or daily) is hit first applies
  - HTTP 429 when rate limit exceeded
  - API key required
- **Sources**:
  - [Etherscan Rate Limits](https://docs.etherscan.io/resources/rate-limits)
  - [What's Changing in Free Tier](https://info.etherscan.com/whats-changing-in-the-free-api-tier-coverage-and-why/)

### Alchemy
- **Website**: https://www.alchemy.com/
- **Free Tier**: 30 million Compute Units (CU) per month
- **Daily Equivalent**: ~60,000 simple requests/day
- **Throughput**: 500 CU per second (CUPs)
- **Reset**: Monthly
- **Status**: ✅ Active
- **Compute Unit Examples**:
  - `eth_blockNumber`: 10 CU
  - `eth_call`: 26 CU
  - `eth_getLogs`: 75 CU (varies by range)
  - NFT API calls: 100-300 CU
- **Notes**:
  - Credit system (not direct request count)
  - ~1.8 million simple RPC requests with free tier
  - Conservative daily estimate: 60k requests (assumes avg 500 CU/request)
  - Supports Ethereum, Polygon, Base, Arbitrum, Optimism
  - HTTP 429 when rate limit exceeded
- **Sources**:
  - [Alchemy Pricing](https://www.alchemy.com/pricing)
  - [Free Tier Details](https://www.alchemy.com/support/free-tier-details)
  - [What are Compute Units?](https://www.alchemy.com/support/what-are-compute-units-cu-and-throughput-compute-units-cups)

### Beaconchain
- **Website**: https://beaconcha.in/
- **Free Tier**: Limited (not well documented)
- **Paid Plans**: Starting at $5/month
- **Status**: ✅ Active
- **Notes**:
  - Primarily for Ethereum beacon chain / staking
  - Free tier very limited
  - Premium required for serious use
- **Sources**: [Beaconchain Website](https://beaconcha.in/)

---

## Solana APIs

### Helius
- **Website**: https://helius.xyz/
- **Free Tier**: 1 million credits/month, 10 RPS
- **Daily Limit**: ~33,333 credits/day
- **Per-Second Limit**: 10 requests/second
- **Reset**: Monthly for credits, per-second for RPS
- **Status**: ✅ Active
- **Notes**:
  - Credit system similar to Alchemy
  - Different endpoints consume different credits
  - 10 RPS hard limit even on free tier
  - No email or credit card required for signup
  - Can upgrade seamlessly as you scale
- **Sources**:
  - [Helius Pricing](https://www.helius.dev/pricing)
  - [Plans and Rate Limits](https://www.helius.dev/docs/billing/plans-and-rate-limits)

---

## Pricing APIs

### CoinGecko
- **Website**: https://www.coingecko.com/en/api
- **Free Tiers**:
  - **Public API** (no registration): 5-15 calls/minute (variable)
  - **Demo API** (free registration): 30 calls/minute, 10,000 calls/month
- **Daily Limit (Demo)**: **333 calls/day** (10,000/month)
- **Reset**: Monthly (for call limit), per-minute (for rate limit)
- **Status**: ✅ Active
- **Recommendation**: Use Demo API (free registration) for stable limits
- **Paid Plans**: 500-1,000 calls/minute
- **Notes**:
  - Public API has variable rate limit based on global load
  - Demo API requires free account but provides stable limits
  - Very popular, extensive cryptocurrency coverage
  - No API key needed for Public API
- **Sources**:
  - [CoinGecko API Pricing](https://www.coingecko.com/en/api/pricing)
  - [Common Errors & Rate Limit](https://docs.coingecko.com/docs/common-errors-rate-limit)
  - [Rate Limit FAQ](https://support.coingecko.com/hc/en-us/articles/4538771776153)

### CoinMarketCap
- **Website**: https://coinmarketcap.com/api/
- **Free Tier**: 10,000 credits/month
- **Daily Limit**: **333 calls/day** (10,000/month ÷ 30)
- **Reset**: Monthly (credits), per-minute (rate limit)
- **Status**: ✅ Active
- **Credit System**:
  - 1 call credit = ~100 data points returned
  - Simple endpoints: 1 credit
  - Bulk endpoints: Multiple credits
- **Notes**:
  - API key required
  - Personal use only on free tier
  - No historical data on free tier
  - Only 11 core endpoints available
  - Rate limit: Multiple calls per second, resets every 60s
- **Sources**:
  - [CoinMarketCap API Pricing](https://coinmarketcap.com/api/pricing/)
  - [API FAQ](https://coinmarketcap.com/api/faq/)

---

## Rate Limit Comparison Table

| API | Free Daily Limit | Type | Reset Period | Notes |
|-----|------------------|------|--------------|-------|
| **Blockfrost** | N/A | Rate limit | Per-second | 10 req/sec, burst 500 |
| **Etherscan** | 100,000 | Quota + Rate | Daily | 3 req/sec OR 100k/day |
| **Alchemy** | ~60,000 | Credits | Monthly | 30M CU/month |
| **Helius** | ~33,333 | Credits | Monthly | 1M credits/month |
| **CoinGecko** | 333 | Quota | Monthly | 10k/month with Demo API |
| **CoinMarketCap** | 333 | Credits | Monthly | 10k credits/month |
| **TapTools** | 95-100 | Quota | Daily | Paid only, varies by plan |
| **CExplorer** | Unknown | Unknown | Unknown | No docs |
| **Maestro** | N/A | Credits | Monthly | 500k credits/month |
| **Beaconchain** | Unknown | Unknown | Unknown | Freemium |

---

## Implementation Recommendations

### High-Usage APIs
- **Etherscan**: 100k/day is generous for typical use
- **Alchemy**: 60k/day should be sufficient for most portfolios

### Medium-Usage APIs
- **Helius**: 33k/day is reasonable for Solana tracking
- **Blockfrost**: Per-second limit likely won't be an issue with caching

### Low-Usage APIs
- **CoinGecko**: 333/day requires careful caching
- **CoinMarketCap**: 333/day requires careful caching
- **TapTools**: 95-100/day very limited, use sparingly

### Optimization Strategies

1. **Aggressive Caching**:
   - Price data: 5-minute cache
   - Wallet balances: 10-minute cache
   - NFT floor prices: 1-hour cache
   - Token metadata: 24-hour cache

2. **Batch Requests**:
   - Use multi-asset endpoints when available
   - Batch price queries (e.g., get 50 tokens in one call)

3. **Fallback APIs**:
   - If one API hits limit, fall back to alternative
   - Example: Blockfrost → CExplorer for Cardano

4. **Rate Limit Awareness**:
   - Display usage % in admin panel (already implemented)
   - Alert at 80% usage
   - Automatically reduce refresh frequency at 90%

5. **Smart Refresh**:
   - Only refresh visible data
   - Longer intervals for rarely-viewed wallets
   - Pause background updates if approaching limit

---

## Future Considerations

### APIs to Watch

- **Midnight Network** (2026): Not yet launched, monitor for rate limits
- **Alternative Solana RPCs**: QuickNode, Triton, etc.
- **Cardano Indexers**: Kupo, Ogmios for self-hosted options

### Self-Hosted Alternatives

- **Cardano**: Run own Cardano node + Kupo + Ogmios (no limits)
- **Ethereum**: Run own Geth/Erigon node (no limits)
- **Solana**: Run own Solana validator (no limits)

**Tradeoff**: High setup cost, maintenance burden vs. API limits

---

## Changelog

- **2026-01-28**: Initial research and documentation
- **2025-11**: Etherscan reduced free tier coverage
- **2025-12**: Midnight network launched, NIGHT token created
- **2026-01**: Helius increased free tier from 500k to 1M credits

---

## Sources Summary

All information verified from official documentation:

- [Blockfrost API Documentation](https://docs.blockfrost.io/)
- [Etherscan Rate Limits](https://docs.etherscan.io/resources/rate-limits)
- [Etherscan Free Tier Changes](https://info.etherscan.com/whats-changing-in-the-free-api-tier-coverage-and-why/)
- [Alchemy Pricing](https://www.alchemy.com/pricing)
- [Alchemy Free Tier Details](https://www.alchemy.com/support/free-tier-details)
- [Helius Pricing](https://www.helius.dev/pricing)
- [Helius Plans & Rate Limits](https://www.helius.dev/docs/billing/plans-and-rate-limits)
- [CoinGecko API Pricing](https://www.coingecko.com/en/api/pricing)
- [CoinGecko Rate Limit FAQ](https://support.coingecko.com/hc/en-us/articles/4538771776153)
- [CoinMarketCap API Pricing](https://coinmarketcap.com/api/pricing/)
- [CoinMarketCap FAQ](https://coinmarketcap.com/api/faq/)

---

**Document Version**: 1.0
**Last Updated**: January 28, 2026
**Next Review**: April 2026
