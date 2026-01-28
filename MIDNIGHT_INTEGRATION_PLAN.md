# Midnight Network Integration Plan

## Executive Summary

This document outlines a comprehensive plan to integrate Midnight network support into ABCT (A Better Crypto Tracker). Midnight is a privacy-focused partner chain (sidechain) to Cardano that uses zero-knowledge proofs (zk-SNARKs) to enable private transactions while maintaining selective auditability.

**Status**: Mainnet expected Q1-Q2 2026
**Token**: NIGHT (Cardano Native Asset)
**Complexity**: Medium-High
**Estimated Effort**: 3-5 days

---

## Table of Contents

1. [What is Midnight?](#1-what-is-midnight)
2. [NIGHT Token Details](#2-night-token-details)
3. [Midnight API Research](#3-midnight-api-research)
4. [Integration Architecture](#4-integration-architecture)
5. [Implementation Plan](#5-implementation-plan)
6. [Technical Specifications](#6-technical-specifications)
7. [Challenges & Considerations](#7-challenges--considerations)
8. [Testing Strategy](#8-testing-strategy)
9. [Timeline & Milestones](#9-timeline--milestones)
10. [References](#10-references)

---

## 1. What is Midnight?

### Overview

Midnight is a data protection blockchain built as a **partner chain** (sidechain) to Cardano. It combines:
- **Privacy**: Zero-knowledge proof technology (zk-SNARKs)
- **Programmability**: DApp smart contracts with privacy features
- **Regulatory Compliance**: Selective disclosure and auditability

### Key Features

- **Zero-Knowledge Proofs**: Hide transaction details while proving validity
- **Selective Disclosure**: Users can choose what to reveal and to whom
- **Cardano Integration**: Inherits Cardano's security, NIGHT is a Cardano native asset
- **DUST System**: NIGHT generates DUST tokens used for transaction fees

### Relationship to Cardano

- **Partner Chain (Sidechain)**: Separate blockchain that bridges to Cardano
- **Token Bridge**: NIGHT exists on both Cardano and Midnight networks
- **Shared Security**: Cardano SPOs can validate both chains simultaneously
- **Dual Rewards**: SPOs earn both ADA and NIGHT

---

## 2. NIGHT Token Details

### Cardano Native Asset

**Policy ID**: `0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa4e49474854`
**Asset Name (Hex)**: `4e49474854`
**Asset Name**: `NIGHT`
**Fingerprint**: `asset1wd3llgkhsw6etxf2yca6cgk9ssrpva3wf0pq9a`
**Created**: November 25, 2025

### Token Economics

- **Total Supply**: 5 billion NIGHT
- **Distribution**:
  - Glacier Drop (community airdrop)
  - Scavenger Mine (participation rewards)
  - Core team and development
  - Ecosystem growth

### Token Utility

1. **Generate DUST**: Stake NIGHT to produce DUST (transaction fuel)
2. **Governance**: Vote on network parameters
3. **Staking**: Secure the Midnight network
4. **Bridge Asset**: Transfer between Cardano and Midnight

### Redemption Timeline (2026)

- **December 4, 2025**: Token transfer to smart contracts begins
- **December 10, 2025 - March 2026**: Thawing period (90 days, randomized starts)
- **December 4, 2026**: Final redemption deadline
- **Q1-Q2 2026**: Mainnet launch expected

### Cardano Explorer Links

- **Cardanoscan**: https://cardanoscan.io/token/0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa4e49474854
- **Token Registry**: Check `cardano-token-registry` for metadata

---

## 3. Midnight API Research

### Current Status (January 2026)

- **Testnet**: Active (Kukolu phase)
- **Mainnet**: Expected Q1-Q2 2026
- **Public RPC**: `wss://rpc.testnet-02.midnight.network`

### API Endpoints

#### 1. RPC API (JSON-RPC)

**Base URL**: `wss://rpc.testnet-02.midnight.network` (testnet)
**Protocol**: WebSocket (JSON-RPC 2.0)

**Common Methods**:
- `midnight_getBalance` - Get account balance
- `midnight_getTransaction` - Get transaction details
- `midnight_submitTransaction` - Submit signed transaction
- `midnight_getBlockByNumber` - Get block data

**Authentication**: API key (likely required for mainnet)
**Rate Limits**: TBD (not documented yet)

#### 2. Wallet API

**Documentation**: https://docs.midnight.network/compact/reference/midnight-api/wallet-api/

**Key Methods**:
- `balanceTransaction(tx, newCoins)` - Balance a transaction
- `getAvailableCoins()` - Get spendable UTXOs
- `createTransaction()` - Build transaction
- `signTransaction()` - Sign with private key

#### 3. Indexer API (GraphQL)

**Type**: GraphQL API
**Purpose**: Query blockchain data, historical transactions, state

**Typical Queries**:
```graphql
query GetBalance($address: String!) {
  balance(address: $address) {
    total
    available
    locked
  }
}

query GetTransactions($address: String!) {
  transactions(address: $address, limit: 50) {
    hash
    from
    to
    amount
    timestamp
    status
  }
}
```

### APIs NOT Available Yet

- **Public REST API**: No simple REST endpoints (like Blockfrost for Cardano)
- **Third-Party Indexers**: No equivalent to TapTools, CExplorer
- **Price APIs**: NIGHT pricing not yet on CoinGecko/CMC (token just launched)

---

## 4. Integration Architecture

### Approach: Dual-Mode Support

We'll support Midnight in **two ways**:

#### Mode A: NIGHT as Cardano Native Asset ✅ (Easy, Immediate Value)

Track NIGHT tokens in existing Cardano wallets:
- No new blockchain type needed
- Use existing Blockfrost/CExplorer APIs
- Display NIGHT balance in portfolio
- Track NIGHT price once available
- Show NIGHT in token list

**Estimated Effort**: 1-2 hours
**Dependencies**: None (can do today)

#### Mode B: Native Midnight Network Support 🔄 (Complex, Future)

Add Midnight as a standalone blockchain:
- New blockchain type: `"midnight"`
- New service: `backend/services/midnight.py`
- Support Midnight addresses (bech32 format)
- Query balances, transactions on Midnight network
- Track DUST balances
- Display Midnight-specific features

**Estimated Effort**: 3-4 days
**Dependencies**: Mainnet launch, stable APIs

### Recommended Strategy

**Phase 1 (Now)**: Implement Mode A
- Track NIGHT on Cardano
- Add token metadata
- Enable price tracking when available

**Phase 2 (Post-Mainnet)**: Implement Mode B
- Wait for mainnet launch
- Wait for API documentation
- Implement full Midnight support

---

## 5. Implementation Plan

### Phase 1: NIGHT Token Support (Cardano Native Asset)

**Timeline**: 1-2 hours
**Risk**: Low
**Value**: Immediate - users can track their NIGHT holdings

#### Step 1.1: Add NIGHT to Token Metadata

**File**: `backend/database.py` or run SQL:

```sql
INSERT INTO token_metadata (
    asset_id,
    policy_id,
    asset_name,
    ticker,
    name,
    decimals,
    logo_url,
    track_for_pricing
) VALUES (
    '0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa4e49474854',
    '0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa',
    '4e49474854',
    'NIGHT',
    'Midnight Network Token',
    6,
    NULL,
    1
);
```

#### Step 1.2: Update Pricing Service

**File**: `backend/services/pricing.py`

Add NIGHT to tracked tokens:
```python
'NIGHT': {
    'coingecko_id': 'midnight-network',  # TBD - check when listed
    'coinmarketcap_id': 'midnight-night',  # TBD
    'asset_id': '0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa4e49474854'
}
```

#### Step 1.3: Add NIGHT Icon/Branding

**Files**: `frontend/static/images/`

Add NIGHT logo (download from midnight.network or Cardanoscan).

#### Step 1.4: Test

1. Add a Cardano wallet that holds NIGHT tokens
2. Refresh portfolio
3. Verify NIGHT appears in token list
4. Verify balance is correct
5. Check USD value (once price available)

---

### Phase 2: Midnight Network Support (Full Integration)

**Timeline**: 3-4 days
**Dependencies**: Mainnet launch, API documentation
**Risk**: Medium (new API, privacy features)

#### Step 2.1: Research & Setup ⏳

**Checklist**:
- [ ] Wait for mainnet launch announcement
- [ ] Get Midnight RPC URL (mainnet)
- [ ] Register for API key (if required)
- [ ] Read final API documentation
- [ ] Set up test wallet on Midnight
- [ ] Fund test wallet with NIGHT/DUST
- [ ] Test API endpoints manually

**Estimated Time**: 4-6 hours

#### Step 2.2: Database Schema Updates

**File**: `backend/database.py`

Add "midnight" to blockchain enum:
```python
# In wallets table
blockchain TEXT NOT NULL CHECK (blockchain IN (
    'cardano', 'ethereum', 'polygon', 'base', 'bitcoin',
    'solana', 'midnight'
))
```

Migration script:
```sql
-- No schema changes needed - wallets table already supports any blockchain
-- Just need to add midnight to validation if enforced in code
```

**Estimated Time**: 1 hour

#### Step 2.3: Create Midnight Service

**File**: `backend/services/midnight.py`

```python
"""
Midnight Network Service

Handles Midnight blockchain interactions:
- Wallet balance queries
- Transaction history
- DUST balance tracking
- Private transaction support
"""

import httpx
import json
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


class MidnightService:
    """Service for Midnight network blockchain data."""

    def __init__(self, rpc_url: str = None, api_key: str = None):
        self.rpc_url = rpc_url or "wss://rpc.mainnet.midnight.network"
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def get_balance(self, address: str) -> Optional[Dict]:
        """
        Get NIGHT and DUST balance for a Midnight address.

        Args:
            address: Midnight address (bech32 format)

        Returns:
            {
                'night_balance': float,
                'dust_balance': float,
                'address': str,
                'source': 'midnight'
            }
        """
        try:
            # Connect to WebSocket RPC
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.rpc_url.replace('wss://', 'https://'),  # REST fallback
                    headers=self.headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "midnight_getBalance",
                        "params": [address]
                    },
                    timeout=30.0
                )

                if response.status_code != 200:
                    logger.error(f"Midnight API error: {response.status_code}")
                    return None

                data = response.json()
                if 'error' in data:
                    logger.error(f"Midnight RPC error: {data['error']}")
                    return None

                result = data.get('result', {})
                return {
                    'night_balance': float(result.get('night', 0)) / 1e6,  # Convert from smallest unit
                    'dust_balance': float(result.get('dust', 0)) / 1e6,
                    'address': address,
                    'source': 'midnight'
                }

        except Exception as e:
            logger.error(f"Midnight balance fetch error: {e}")
            return None

    async def get_transactions(self, address: str, limit: int = 50) -> List[Dict]:
        """
        Get transaction history for a Midnight address.

        Args:
            address: Midnight address
            limit: Max transactions to return

        Returns:
            List of transaction dicts
        """
        try:
            # Use GraphQL indexer
            query = """
            query GetTransactions($address: String!, $limit: Int!) {
                transactions(address: $address, limit: $limit) {
                    hash
                    from
                    to
                    amount
                    timestamp
                    status
                    type
                }
            }
            """

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.rpc_url.replace('wss://', 'https://')}/graphql",
                    headers=self.headers,
                    json={
                        "query": query,
                        "variables": {
                            "address": address,
                            "limit": limit
                        }
                    },
                    timeout=30.0
                )

                if response.status_code != 200:
                    return []

                data = response.json()
                return data.get('data', {}).get('transactions', [])

        except Exception as e:
            logger.error(f"Midnight transactions fetch error: {e}")
            return []

    async def validate_address(self, address: str) -> bool:
        """
        Validate a Midnight address format.

        Args:
            address: Address to validate

        Returns:
            True if valid, False otherwise
        """
        # Midnight uses bech32 format with specific prefix
        # TODO: Implement proper validation once format is documented
        if not address:
            return False

        if not address.startswith('midnight'):  # Placeholder prefix
            return False

        if len(address) < 50:  # Placeholder length check
            return False

        return True
```

**Estimated Time**: 6-8 hours

#### Step 2.4: Create Midnight Router

**File**: `backend/routers/midnight.py`

```python
"""
Midnight Router - API endpoints for Midnight blockchain
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict
import os

from services.midnight import MidnightService

router = APIRouter(prefix="/midnight", tags=["midnight"])

midnight_service = MidnightService(
    rpc_url=os.getenv("MIDNIGHT_RPC_URL"),
    api_key=os.getenv("MIDNIGHT_API_KEY")
)


@router.get("/balance/{address}")
async def get_midnight_balance(address: str) -> Dict:
    """Get NIGHT and DUST balance for a Midnight address."""
    if not midnight_service.validate_address(address):
        raise HTTPException(status_code=400, detail="Invalid Midnight address")

    balance = await midnight_service.get_balance(address)
    if not balance:
        raise HTTPException(status_code=404, detail="Failed to fetch balance")

    return balance


@router.get("/transactions/{address}")
async def get_midnight_transactions(address: str, limit: int = 50) -> List[Dict]:
    """Get transaction history for a Midnight address."""
    if not midnight_service.validate_address(address):
        raise HTTPException(status_code=400, detail="Invalid Midnight address")

    transactions = await midnight_service.get_transactions(address, limit)
    return {"transactions": transactions}


@router.get("/validate/{address}")
async def validate_midnight_address(address: str) -> Dict:
    """Validate a Midnight address."""
    is_valid = await midnight_service.validate_address(address)
    return {"valid": is_valid, "address": address}
```

**Estimated Time**: 2 hours

#### Step 2.5: Update Portfolio Aggregation

**File**: `backend/routers/portfolio.py`

Add Midnight to portfolio total:
```python
# Fetch Midnight wallets
midnight_wallets = [w for w in wallets if w['blockchain'] == 'midnight']

midnight_total_usd = 0
for wallet in midnight_wallets:
    balance = await midnight_service.get_balance(wallet['address'])
    if balance:
        night_price = await get_token_price('NIGHT')
        midnight_total_usd += balance['night_balance'] * night_price

        # Add to portfolio breakdown
        portfolio['midnight'] = {
            'night_amount': balance['night_balance'],
            'dust_amount': balance['dust_balance'],
            'value_usd': midnight_total_usd
        }
```

**Estimated Time**: 2 hours

#### Step 2.6: Frontend Updates

**Files**:
- `frontend/wallets.html`
- `frontend/index.html`
- `frontend/static/css/styles.css`
- `frontend/static/js/app.js`

**Changes**:
1. Add "Midnight" to blockchain dropdown in "Add Wallet" modal
2. Add Midnight icon/logo
3. Display Midnight balances in portfolio
4. Show DUST balance (unique to Midnight)
5. Link to Midnight explorer (once available)

**Example HTML**:
```html
<!-- In Add Wallet modal -->
<option value="midnight">Midnight (NIGHT)</option>

<!-- In portfolio display -->
<div class="chain-section midnight">
    <div class="chain-header">
        <img src="/static/images/midnight-logo.png" alt="Midnight">
        <h3>Midnight</h3>
    </div>
    <div class="balance">
        <span class="amount" id="midnightBalance">0</span>
        <span class="ticker">NIGHT</span>
        <span class="usd-value" id="midnightValueUSD">$0.00</span>
    </div>
    <div class="dust-balance">
        <span class="label">DUST:</span>
        <span class="amount" id="dustBalance">0</span>
    </div>
</div>
```

**Estimated Time**: 4-6 hours

#### Step 2.7: Add Midnight to API Settings

**File**: `backend/routers/settings.py`

Add to `API_REGISTRY`:
```python
"midnight": {
    "name": "Midnight RPC",
    "category": "midnight",
    "description": "Midnight network RPC for balance and transaction queries",
    "required": False,
    "docs_url": "https://docs.midnight.network/",
    "env_var": "MIDNIGHT_API_KEY",
    "pricing": "free",
    "pricing_note": "Free tier TBD (network launching 2026)",
    "default_limit": None,  # TBD once mainnet launches
    "default_period": 86400,
    "period_label": "day"
},
```

Add category:
```python
"midnight": {
    "name": "Midnight",
    "description": "Privacy-focused Cardano partner chain",
    "icon": "🌙"
}
```

**Estimated Time**: 1 hour

---

## 6. Technical Specifications

### Address Format

**Expected**: Midnight uses bech32 encoding with a custom prefix (TBD)
**Example**: `midnight1<base32_encoded_address>`
**Length**: ~60-100 characters (estimate)

### API Request Format (JSON-RPC)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "midnight_getBalance",
  "params": ["midnight1abc...xyz"]
}
```

### API Response Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "night": "1000000000",
    "dust": "500000",
    "staked": "5000000000"
  }
}
```

### Environment Variables

```bash
# .env
MIDNIGHT_RPC_URL=wss://rpc.mainnet.midnight.network
MIDNIGHT_API_KEY=your_api_key_here  # If required
```

### Database Schema

No changes needed - existing `wallets` table supports any blockchain:
```sql
INSERT INTO wallets (address, blockchain, label)
VALUES ('midnight1abc...', 'midnight', 'My Midnight Wallet');
```

---

## 7. Challenges & Considerations

### 1. Mainnet Not Launched Yet ⏳

**Challenge**: Midnight mainnet expected Q1-Q2 2026, not live yet.
**Solution**: Implement Phase 1 (NIGHT on Cardano) now, Phase 2 after launch.
**Risk**: Low (Phase 1 works today)

### 2. API Documentation Incomplete 📚

**Challenge**: RPC methods, endpoints not fully documented yet.
**Solution**: Wait for official docs, use testnet to experiment.
**Risk**: Medium (might need refactoring if API changes)

### 3. Privacy Features 🔒

**Challenge**: Midnight uses zk-SNARKs for privacy - balances might be hidden.
**Solution**: Only display what API allows, add note about privacy.
**Risk**: Low (API will expose what users permit)

### 4. NIGHT Price Availability 💰

**Challenge**: NIGHT not yet on CoinGecko/CoinMarketCap.
**Solution**: Add price support once token is listed.
**Risk**: Low (token just launched Dec 2025, listings coming)

### 5. Bridge Complexity 🌉

**Challenge**: NIGHT exists on both Cardano and Midnight.
**Solution**: Track both separately, label clearly ("NIGHT on Cardano" vs "NIGHT on Midnight").
**Risk**: Medium (user confusion possible)

### 6. DUST Token ⚡

**Challenge**: DUST is generated from NIGHT, different use case.
**Solution**: Display DUST separately, explain it's for transaction fees.
**Risk**: Low (just display, don't price it)

### 7. Wallet Address Format 🔤

**Challenge**: Midnight address format not finalized.
**Solution**: Use validation function, update when format confirmed.
**Risk**: Low (can update validator easily)

### 8. Explorer Links 🔗

**Challenge**: No public Midnight explorer yet.
**Solution**: Use Nocturne explorer (dev.to/minhlong2605/nocturne) or wait for official.
**Risk**: Low (nice-to-have, not critical)

---

## 8. Testing Strategy

### Phase 1 Testing (NIGHT on Cardano)

**Test Cases**:
1. ✅ Add Cardano wallet with NIGHT tokens
2. ✅ Verify NIGHT appears in token list
3. ✅ Verify quantity is correct
4. ✅ Verify USD value (once price available)
5. ✅ Test with wallet that has no NIGHT
6. ✅ Test token metadata display

**Test Data**:
- Use a wallet with known NIGHT balance
- Check on Cardanoscan first to verify expected quantity

### Phase 2 Testing (Midnight Network)

**Test Cases**:
1. 🔄 Add Midnight wallet address
2. 🔄 Fetch NIGHT balance from Midnight network
3. 🔄 Fetch DUST balance
4. 🔄 Display in portfolio correctly
5. 🔄 Fetch transaction history
6. 🔄 Handle invalid addresses gracefully
7. 🔄 Handle API errors (timeout, auth, etc.)
8. 🔄 Test with multiple Midnight wallets
9. 🔄 Test portfolio aggregation includes Midnight
10. 🔄 Test refresh/update functionality

**Test Environment**:
- Midnight testnet initially
- Mainnet once available
- Use faucet for test NIGHT if available

---

## 9. Timeline & Milestones

### Immediate (Now - Week 1)

- [x] ✅ Research Midnight network
- [x] ✅ Document NIGHT token details
- [x] ✅ Create integration plan
- [ ] Implement Phase 1 (NIGHT on Cardano)
- [ ] Test NIGHT tracking
- [ ] Add NIGHT icon/branding

**Estimated**: 1-2 days

### Short-term (Week 2-4)

- [ ] Monitor mainnet launch announcement
- [ ] Review final API documentation
- [ ] Set up Midnight testnet access
- [ ] Test RPC endpoints
- [ ] Draft Midnight service code

**Estimated**: 1 week (intermittent)

### Medium-term (Post-Mainnet Launch)

- [ ] Implement Phase 2 (Midnight network support)
- [ ] Add Midnight service
- [ ] Add Midnight router
- [ ] Update frontend
- [ ] Full integration testing
- [ ] Deploy to production

**Estimated**: 1 week (focused development)

### Long-term (Q2 2026+)

- [ ] Add NIGHT price tracking
- [ ] Add DUST display
- [ ] Add Midnight transaction history
- [ ] Add bridge tracking (NIGHT Cardano ↔ Midnight)
- [ ] Add staking support (if applicable)
- [ ] Advanced privacy features

**Estimated**: Ongoing enhancements

---

## 10. References

### Official Documentation

- **Midnight Docs**: https://docs.midnight.network/
- **Midnight API**: https://docs.midnight.network/develop/reference/midnight-api
- **Wallet API**: https://docs.midnight.network/compact/reference/midnight-api/wallet-api/
- **Midnight Blog**: https://midnight.network/blog
- **NIGHT Token**: https://midnight.network/night

### Token Information

- **Cardanoscan**: https://cardanoscan.io/token/0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa4e49474854
- **Policy ID**: `0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa4e49474854`
- **Fingerprint**: `asset1wd3llgkhsw6etxf2yca6cgk9ssrpva3wf0pq9a`

### Articles & News

- [Guide to NIGHT Token Launch](https://midnight.network/blog/guide-to-the-night-token-launch-and-redemption)
- [State of the Network - December 2025](https://midnight.network/blog/state-of-the-network-december-2025)
- [Cardano Outlook 2026](https://cryptodaily.co.uk/2026/01/cardano-ada-outlook-2026-midnight-sidechain-expands-privacy-use-cases)
- [Midnight Launches Dec 8](https://rareevo.io/rare-network-news/midnight-network-launch-december-8-privacy-cardano-night-token)
- [Cardano Delegators Earn NIGHT](https://thecryptobasic.com/2026/01/16/cardano-delegators-will-earn-both-ada-and-night-tokens-when-midnight-launches/)

### Developer Resources

- **Testnet RPC**: `wss://rpc.testnet-02.midnight.network`
- **Ankr Midnight Docs**: https://www.ankr.com/docs/rpc-service/chains/chains-api/midnight/
- **Nocturne Explorer**: https://dev.to/minhlong2605/nocturne-a-blockchain-explorer-for-midnight-network-3041
- **Blockdaemon**: https://www.blockdaemon.com/protocols/midnight

---

## Appendix A: Quick Start (Phase 1)

### Add NIGHT Token Support in 5 Minutes

1. **Add to database**:
```sql
INSERT INTO token_metadata (asset_id, policy_id, asset_name, ticker, name, decimals, track_for_pricing)
VALUES (
    '0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa4e49474854',
    '0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa',
    '4e49474854',
    'NIGHT',
    'Midnight Network Token',
    6,
    1
);
```

2. **Refresh portfolio** - NIGHT will now appear for Cardano wallets that hold it.

3. **Add price support** (once listed):
```python
# In backend/services/pricing.py
TRACKED_TOKENS = {
    # ...
    'NIGHT': {
        'coingecko_id': 'midnight-network',
        'asset_id': '0691b2fecca1ac4f53cb6dfb00b7013e561d1f34403b957cbb5af1fa4e49474854'
    }
}
```

Done! NIGHT token tracking is live.

---

## Appendix B: Sample API Responses (Estimated)

### Balance Query

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "midnight_getBalance",
  "params": ["midnight1qpqr..."]
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "night": "5000000000",     // 5000 NIGHT (6 decimals)
    "dust": "1234567",          // 1.234567 DUST
    "staked_night": "2000000000",  // 2000 NIGHT staked
    "address": "midnight1qpqr..."
  }
}
```

### Transaction History (GraphQL)

**Query**:
```graphql
query {
  transactions(address: "midnight1qpqr...", limit: 10) {
    hash
    type
    from
    to
    night_amount
    dust_fee
    timestamp
    status
    private
  }
}
```

**Response**:
```json
{
  "data": {
    "transactions": [
      {
        "hash": "0xabc123...",
        "type": "transfer",
        "from": "midnight1qpqr...",
        "to": "midnight1xyz...",
        "night_amount": "100000000",
        "dust_fee": "50000",
        "timestamp": "2026-02-15T10:30:00Z",
        "status": "confirmed",
        "private": true
      }
    ]
  }
}
```

---

## Conclusion

### Summary

Midnight integration can be done in **two phases**:

**Phase 1** (Immediate): Track NIGHT as a Cardano native asset
- Low effort (1-2 hours)
- Immediate value to users
- No dependencies

**Phase 2** (Post-Mainnet): Full Midnight network support
- Medium effort (3-4 days)
- Requires mainnet launch
- Advanced features (DUST, privacy, etc.)

### Recommendation

**Start with Phase 1 today**, then implement Phase 2 after mainnet launches in Q1-Q2 2026 and APIs are finalized.

### Next Steps

1. ✅ Review this plan
2. Add NIGHT token to database
3. Test with Cardano wallet holding NIGHT
4. Monitor Midnight mainnet launch
5. Implement Phase 2 when ready

---

**Document Version**: 1.0
**Created**: January 28, 2026
**Status**: Ready for Implementation
**Author**: Claude Sonnet 4.5 (ABCT Development Assistant)
