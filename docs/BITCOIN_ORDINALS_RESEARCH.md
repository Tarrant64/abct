# Bitcoin Ordinals NFT Support - Research & Implementation Plan

**Document Version:** 1.0
**Date:** January 27, 2026
**Status:** Research Complete - Ready for Implementation Decision

---

## Executive Summary

### Feasibility Assessment: HIGHLY FEASIBLE ✅

Bitcoin Ordinals (inscriptions) can be successfully integrated into ABCT following the same multi-chain NFT pattern used for Ethereum, Solana, Polygon, and Base. Multiple mature APIs are available with free tiers, and the integration complexity is comparable to existing blockchain implementations.

### Recommended Approach

**Primary API:** Hiro Ordinals API (free, open-source, comprehensive)
**Backup API:** Ordiscan API (free tier available)
**Floor Prices:** SimpleHash API or OKX NFT API
**Estimated Implementation Time:** 2-3 days for full integration
**Complexity Level:** Medium (similar to Ethereum/Solana NFT services)

### Key Benefits

- Completes multi-chain NFT support across all major ecosystems
- Leverages existing Bitcoin wallet infrastructure (already tracks BTC balances)
- Growing market with significant value tracking potential
- Follows established ABCT architecture patterns
- Multiple free API options available

---

## 1. Understanding Bitcoin Ordinals

### What Are Bitcoin Ordinals?

Bitcoin Ordinals (also called inscriptions) are NFTs created directly on the Bitcoin blockchain by inscribing data onto individual satoshis (the smallest unit of Bitcoin). Unlike Ethereum NFTs which use smart contracts, Ordinals inscribe arbitrary data directly into Bitcoin transactions using witness data.

### Key Characteristics

- **Inscription ID**: Unique identifier for each ordinal (format: `{txid}i{index}`)
- **Inscription Number**: Sequential number assigned when inscribed
- **Satoshi Number**: The specific satoshi that holds the inscription
- **Content Types**: Images (PNG, JPEG, WebP, GIF), HTML, text, JSON, and more
- **Metadata**: Stored on-chain using CBOR format in witness data
- **Collections**: Grouped by similar traits, creators, or themes
- **Storage**: Permanently on Bitcoin blockchain (no IPFS needed)

### How They Differ from Traditional NFTs

| Feature | Bitcoin Ordinals | Ethereum/Solana NFTs |
|---------|-----------------|---------------------|
| Storage | On-chain (in witness data) | Metadata often on IPFS/Arweave |
| Smart Contracts | No contracts needed | ERC-721/ERC-1155 contracts |
| Ownership Tracking | UTXO-based | Contract state |
| Content Size | Limited by transaction size | External storage, unlimited |
| Immutability | Permanent on Bitcoin | Depends on storage solution |
| Transferability | Standard Bitcoin transactions | Contract function calls |

### Data Available for Tracking

1. **Inscription Metadata**
   - Inscription ID (unique identifier)
   - Inscription number
   - Owner's Bitcoin address
   - Content type (MIME type)
   - Content size
   - Block height and timestamp
   - Genesis transaction and address

2. **Collection Information**
   - Collection name and symbol
   - Total supply
   - Floor price (in BTC and USD)
   - Trading volume
   - Number of listings
   - Verified status

3. **Visual Content**
   - Image data (retrievable via API)
   - Content URL for display
   - Thumbnail generation supported

4. **Market Data**
   - Floor prices by collection
   - Historical price data
   - Trading activity
   - Market cap per collection

---

## 2. API Research & Comparison

### 2.1 Hiro Ordinals API ⭐ RECOMMENDED PRIMARY

**Website:** https://docs.hiro.so/bitcoin/ordinals/api
**GitHub:** https://github.com/hirosystems/ordinals-api
**Base URL:** `https://api.hiro.so/ordinals/v1`

#### Pros
- Completely **free and open-source**
- Comprehensive API with full inscription indexing
- Well-documented with examples
- Active development and community
- No authentication required for basic usage
- Supports BRC-20 tokens
- Real-time data with new blocks
- Reorg-aware (handles blockchain reorganizations)

#### Cons
- No built-in floor price data
- Rate limits on free tier (not publicly specified)
- May need backup API for redundancy

#### Key Endpoints
```
GET /inscriptions?address={bitcoin_address}
GET /inscriptions/{inscription_id}
GET /inscriptions/{inscription_id}/content
GET /inscriptions (filter by mime_type, rarity, etc.)
GET /stats/inscriptions
```

#### Example Response Structure
```json
{
  "limit": 20,
  "offset": 0,
  "total": 150,
  "results": [
    {
      "id": "38c46a8bf7ec90bc7f6b797e7dc84baa97f4e5fd4286b92fe1b50176d03b18dci0",
      "number": 248751,
      "address": "bc1p8aq8s3z9xl87e74twfk93mljxq6alv4a79yheadx33t9np4g2wkqqt8kc5",
      "genesis_address": "bc1p8aq8s3z9xl87e74twfk93mljxq6alv4a79yheadx33t9np4g2wkqqt8kc5",
      "genesis_block_height": 779000,
      "genesis_timestamp": 1676358400000,
      "content_type": "image/png",
      "content_length": 52345,
      "value": "10000",
      "sat_ordinal": "257418248345364",
      "sat_rarity": "common",
      "tx_id": "38c46a8bf7ec90bc7f6b797e7dc84baa97f4e5fd4286b92fe1b50176d03b18dc"
    }
  ]
}
```

#### Authentication
None required for basic usage. Rate limits apply but are generous for typical use cases.

---

### 2.2 Ordiscan API

**Website:** https://ordiscan.com/docs/api
**Base URL:** `https://api.ordiscan.com/v1`

#### Pros
- Free tier available
- Clean API design
- Good documentation
- Collection floor price data available
- UTXOs endpoint (useful for inscriptions)
- BRC-20 support

#### Cons
- Requires API key (free registration)
- Rate limits stricter than Hiro
- Smaller community than Hiro

#### Key Endpoints
```
GET /address/{address}/activity
GET /address/{address}/utxos
GET /inscription/{inscription_id}
GET /collections
GET /collection/{slug}
```

#### Collection Data with Floor Prices
```json
{
  "slug": "bitcoin-puppets",
  "name": "Bitcoin Puppets",
  "supply": 10000,
  "floor_price_in_sats": 24500000,
  "floor_price_in_usd": 16250.50,
  "market_cap_in_btc": 245.0,
  "market_cap_in_usd": 16250500.00,
  "listings": 125,
  "verified": true
}
```

#### Authentication
Requires Bearer token:
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  https://api.ordiscan.com/v1/address/{address}/activity
```

---

### 2.3 SimpleHash API

**Website:** https://simplehash.com/chains/bitcoin
**Docs:** https://docs.simplehash.com

#### Pros
- Multi-chain support (80+ chains including Bitcoin Ordinals)
- Excellent floor price data
- Real-time marketplace data
- Comprehensive NFT metadata
- Professional-grade API
- Single API for all chains

#### Cons
- Paid tiers required for production use
- Free tier very limited (100 requests/day)
- Overkill if only need Bitcoin Ordinals

#### Use Case
Best as a **floor price data source** rather than primary ordinals API. Could complement Hiro for market data.

#### Key Features
- Historical floor prices
- Multi-marketplace aggregation
- Trait-based floor prices
- Real-time price updates

---

### 2.4 OKX NFT API

**Website:** https://www.okx.com/web3/build/docs/waas/marketplace-ordinals-api
**Base URL:** `https://web3.okx.com/api/v5/mktplace/nft/ordinals/`

#### Pros
- OKX marketplace integration
- Collection floor prices included
- Listing and activity data
- Free tier available (30 QPM)

#### Cons
- Requires API key setup with HMAC signatures
- More complex authentication
- Marketplace-focused (may not cover all inscriptions)

#### Use Case
Good for **floor price data** and marketplace activity. Less useful for general inscription discovery.

---

### 2.5 Magic Eden Ordinals API

**Website:** https://docs.magiceden.io/reference/ordinals-overview
**Base URL:** Magic Eden API endpoints

#### Pros
- Large marketplace data
- Free tier (30 QPM)
- Collection data with floor prices
- Active marketplace integration

#### Cons
- Marketplace-centric (may miss non-listed inscriptions)
- Requires attribution
- Rate limits may be restrictive

#### Use Case
Best as a **supplementary floor price source** for popular collections.

---

### 2.6 QuickNode Ordinals & Runes API

**Website:** https://marketplace.quicknode.com/add-on/ordinals-json-rpc-api

#### Pros
- JSON-RPC interface
- Good for blockchain node operators
- Comprehensive inscription data

#### Cons
- Requires QuickNode account
- Paid add-on
- Not ideal for wallet portfolio tracking

#### Use Case
Too complex and expensive for ABCT's needs. Skip this option.

---

## 3. API Selection & Strategy

### Recommended Architecture

#### Primary: Hiro Ordinals API (Free)
- List all inscriptions by Bitcoin address
- Fetch inscription metadata
- Retrieve content for display
- Get inscription count and stats

#### Secondary: Ordiscan API (Free Tier)
- Backup for inscription discovery
- Collection floor price data
- Fallback if Hiro is rate-limited

#### Floor Prices: Multiple Sources
1. **Ordiscan** - Primary floor price source (free, reliable)
2. **CoinGecko** - Backup for popular collections
3. **Magic Eden** - Supplement for marketplace data

### Data Flow Strategy

```
Bitcoin Address
    ↓
Hiro API: Get inscriptions by address
    ↓
Parse inscription metadata
    ↓
Ordiscan: Get collection floor prices
    ↓
Combine data + calculate USD values
    ↓
Store in ABCT database cache
    ↓
Display in NFT Wall
```

---

## 4. Technical Architecture

### 4.1 Backend Service Layer

Create new service file: `/backend/services/bitcoin_ordinals.py`

**Pattern:** Follow existing NFT service patterns (Ethereum, Solana, etc.)

```python
"""
Bitcoin Ordinals Service - Fetches Bitcoin inscriptions (ordinals) using Hiro API.

Hiro Ordinals API provides:
- Inscription ownership data by address
- Inscription metadata (content type, size, etc.)
- Content retrieval for display
- Historical inscription data

Uses persistent database caching to reduce API calls.
"""

import httpx
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from config import HIRO_ORDINALS_API_URL, ORDISCAN_API_KEY
from database import get_cache, set_cache

logger = logging.getLogger(__name__)

# Cache settings
BTC_ORDINALS_CACHE_KEY = "btc_ordinals_all_data"
BTC_ORDINALS_CACHE_TTL = 86400 * 30  # 30 days

class BitcoinOrdinalsService:
    """Service for fetching Bitcoin Ordinals (inscriptions)."""

    def __init__(self):
        self.hiro_base_url = "https://api.hiro.so/ordinals/v1"
        self.ordiscan_base_url = "https://api.ordiscan.com/v1"
        self.ordiscan_api_key = ORDISCAN_API_KEY
        self._ordinals_cache: Dict[str, dict] = {}
        self._collection_cache: Dict[str, dict] = {}
        self.last_refresh: Optional[datetime] = None
        self._db_cache_loaded = False

    def is_configured(self) -> bool:
        """Hiro API requires no config, always available."""
        return True

    async def get_inscriptions_for_address(
        self,
        address: str,
        limit: int = 100
    ) -> Optional[List[dict]]:
        """
        Fetch all inscriptions owned by a Bitcoin address.
        Uses Hiro Ordinals API (free, no auth required).
        """
        try:
            all_inscriptions = []
            offset = 0

            async with httpx.AsyncClient(timeout=30.0) as client:
                while True:
                    response = await client.get(
                        f"{self.hiro_base_url}/inscriptions",
                        params={
                            'address': address,
                            'limit': limit,
                            'offset': offset
                        }
                    )

                    if response.status_code != 200:
                        logger.error(f"Hiro API error: {response.status_code}")
                        return None

                    data = response.json()
                    results = data.get('results', [])
                    all_inscriptions.extend(results)

                    # Check if we have more pages
                    total = data.get('total', 0)
                    if offset + len(results) >= total:
                        break

                    offset += limit

            return all_inscriptions

        except Exception as e:
            logger.error(f"Error fetching ordinals: {e}")
            return None

    async def get_collection_floor_price(self, collection_slug: str) -> Optional[dict]:
        """
        Get floor price for a collection using Ordiscan API.
        Falls back to cache if API unavailable.
        """
        if not self.ordiscan_api_key:
            logger.warning("Ordiscan API key not configured")
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.ordiscan_base_url}/collection/{collection_slug}",
                    headers={"Authorization": f"Bearer {self.ordiscan_api_key}"}
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        'floor_price_sats': data.get('floor_price_in_sats'),
                        'floor_price_btc': data.get('floor_price_in_sats', 0) / 100_000_000,
                        'floor_price_usd': data.get('floor_price_in_usd'),
                        'supply': data.get('supply'),
                        'listings': data.get('listings'),
                        'verified': data.get('verified', False)
                    }
        except Exception as e:
            logger.error(f"Error fetching collection floor price: {e}")

        return None

    def _parse_inscription(self, inscription_data: dict, btc_address: str) -> dict:
        """Parse Hiro API inscription into standard ABCT format."""
        inscription_id = inscription_data.get('id')
        inscription_number = inscription_data.get('number')
        content_type = inscription_data.get('content_type', 'unknown')

        # Extract collection info from inscription metadata (if available)
        # Collections are typically identified by similar traits or creator
        collection_name = self._extract_collection_name(inscription_data)

        return {
            'inscription_id': inscription_id,
            'inscription_number': inscription_number,
            'name': f"Inscription #{inscription_number}",
            'address': btc_address,
            'content_type': content_type,
            'content_length': inscription_data.get('content_length'),
            'image_url': f"{self.hiro_base_url}/inscriptions/{inscription_id}/content",
            'sat_ordinal': inscription_data.get('sat_ordinal'),
            'sat_rarity': inscription_data.get('sat_rarity', 'common'),
            'genesis_address': inscription_data.get('genesis_address'),
            'genesis_block': inscription_data.get('genesis_block_height'),
            'timestamp': inscription_data.get('genesis_timestamp'),
            'collection': {
                'name': collection_name or 'Uncategorized',
                'floor_price_btc': None,  # To be filled by floor price API
                'floor_price_sats': None,
                'verified': False
            }
        }

    def _extract_collection_name(self, inscription_data: dict) -> Optional[str]:
        """
        Try to identify collection from inscription metadata.
        Many collections include collection info in metadata or can be
        identified by inscription number ranges or genesis addresses.
        """
        # This would need collection mapping logic
        # For now, return None and use "Uncategorized"
        return None

    async def get_all_bitcoin_ordinals(
        self,
        force_refresh: bool = False
    ) -> List[dict]:
        """
        Get all ordinals across all Bitcoin wallets.
        Uses persistent caching to minimize API calls.
        """
        # Check cache first (unless force refresh)
        if not force_refresh and self._ordinals_cache:
            return list(self._ordinals_cache.values())

        # Try to load from database cache
        if not force_refresh and not self._db_cache_loaded:
            cached_data = await get_cache(BTC_ORDINALS_CACHE_KEY)
            if cached_data:
                self._ordinals_cache = cached_data
                self._db_cache_loaded = True
                self.last_refresh = datetime.now()
                return list(self._ordinals_cache.values())

        # Fetch fresh data from API
        from database import get_all_wallets
        wallets = await get_all_wallets()
        btc_wallets = [w for w in wallets if w['blockchain'] == 'bitcoin']

        all_ordinals = []

        for wallet in btc_wallets:
            address = wallet['address']
            inscriptions = await self.get_inscriptions_for_address(address)

            if inscriptions:
                for inscription in inscriptions:
                    ordinal = self._parse_inscription(inscription, address)
                    all_ordinals.append(ordinal)

        # Enrich with collection floor prices
        all_ordinals = await self._enrich_with_floor_prices(all_ordinals)

        # Update cache
        self._ordinals_cache = {o['inscription_id']: o for o in all_ordinals}
        await set_cache(
            BTC_ORDINALS_CACHE_KEY,
            self._ordinals_cache,
            BTC_ORDINALS_CACHE_TTL
        )
        self.last_refresh = datetime.now()

        return all_ordinals

    async def _enrich_with_floor_prices(self, ordinals: List[dict]) -> List[dict]:
        """Add floor price data to ordinals by collection."""
        # Group by collection
        collections = {}
        for ordinal in ordinals:
            collection_name = ordinal['collection']['name']
            if collection_name not in collections:
                collections[collection_name] = []
            collections[collection_name].append(ordinal)

        # Fetch floor prices for each collection
        for collection_name in collections:
            # Convert collection name to slug (lowercase, hyphens)
            slug = collection_name.lower().replace(' ', '-')

            floor_data = await self.get_collection_floor_price(slug)

            if floor_data:
                # Apply floor price to all ordinals in this collection
                for ordinal in collections[collection_name]:
                    ordinal['collection'].update(floor_data)

        return ordinals

    async def get_nft_summary(self) -> dict:
        """Get summary statistics for all Bitcoin ordinals."""
        all_ordinals = await self.get_all_bitcoin_ordinals()

        # Group by collection
        collections_map = {}

        for ordinal in all_ordinals:
            collection_name = ordinal['collection']['name']

            if collection_name not in collections_map:
                collections_map[collection_name] = {
                    'name': collection_name,
                    'nft_count': 0,
                    'floor_price_btc': ordinal['collection'].get('floor_price_btc'),
                    'total_value_btc': 0,
                    'verified': ordinal['collection'].get('verified', False)
                }

            collections_map[collection_name]['nft_count'] += 1

            # Add to total value if floor price available
            if collections_map[collection_name]['floor_price_btc']:
                collections_map[collection_name]['total_value_btc'] += \
                    collections_map[collection_name]['floor_price_btc']

        collections = list(collections_map.values())
        total_value_btc = sum(c['total_value_btc'] for c in collections)

        return {
            'total_ordinals': len(all_ordinals),
            'total_collections': len(collections),
            'total_value_btc': total_value_btc,
            'collections': collections
        }

    def clear_cache(self):
        """Clear in-memory cache."""
        self._ordinals_cache = {}
        self._collection_cache = {}
        self._db_cache_loaded = False

    def get_status(self) -> dict:
        """Get service status."""
        return {
            "hiro_api": "available",
            "ordiscan_configured": bool(self.ordiscan_api_key),
            "cached_ordinals": len(self._ordinals_cache),
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "floor_prices": "available" if self.ordiscan_api_key else "limited"
        }

# Singleton instance
bitcoin_ordinals_service = BitcoinOrdinalsService()
```

### 4.2 API Router Endpoints

Add to `/backend/routers/nfts.py`:

```python
# ============================================================================
# BITCOIN ORDINALS ENDPOINTS
# ============================================================================

from services.bitcoin_ordinals import bitcoin_ordinals_service

@router.get("/bitcoin")
async def get_bitcoin_ordinals(force_refresh: bool = False):
    """
    Get all Bitcoin Ordinals (inscriptions) across all Bitcoin wallets.
    Returns ordinals with collection data, floor prices, and values.
    """
    if not bitcoin_ordinals_service.is_configured():
        return {
            'configured': False,
            'message': 'Bitcoin Ordinals service not available',
            'ordinals': [],
            'total_count': 0,
            'total_value_usd': 0
        }

    all_ordinals = await bitcoin_ordinals_service.get_all_bitcoin_ordinals(
        force_refresh=force_refresh
    )

    # Get BTC price for USD conversion
    btc_price = await pricing_service.get_price('BTC')

    # Calculate USD values
    total_value_usd = 0.0
    total_value_btc = 0.0

    for ordinal in all_ordinals:
        floor_price_btc = ordinal['collection'].get('floor_price_btc', 0) or 0
        usd_value = floor_price_btc * btc_price
        ordinal['floor_price_usd'] = usd_value
        total_value_usd += usd_value
        total_value_btc += floor_price_btc

    # Sort by USD value (highest first)
    all_ordinals.sort(key=lambda x: x.get('floor_price_usd', 0), reverse=True)

    return {
        'configured': True,
        'ordinals': all_ordinals,
        'total_count': len(all_ordinals),
        'valued_count': sum(1 for o in all_ordinals if o.get('floor_price_usd', 0) > 0),
        'total_value_usd': total_value_usd,
        'total_value_btc': total_value_btc,
        'btc_price': btc_price,
        'last_updated': bitcoin_ordinals_service.last_refresh.isoformat()
            if bitcoin_ordinals_service.last_refresh else None
    }


@router.get("/bitcoin/summary")
async def get_bitcoin_ordinals_summary():
    """
    Get a summary of all Bitcoin Ordinals grouped by collection.
    """
    if not bitcoin_ordinals_service.is_configured():
        return {
            'configured': False,
            'message': 'Bitcoin Ordinals service not available'
        }

    summary = await bitcoin_ordinals_service.get_nft_summary()

    # Get BTC price for USD conversion
    btc_price = await pricing_service.get_price('BTC')

    # Add USD values
    summary['total_value_usd'] = summary['total_value_btc'] * btc_price
    summary['btc_price'] = btc_price
    summary['configured'] = True

    # Add USD values to collections
    for collection in summary['collections']:
        collection['total_value_usd'] = collection['total_value_btc'] * btc_price
        if collection.get('floor_price_btc'):
            collection['floor_price_usd'] = collection['floor_price_btc'] * btc_price

    # Sort collections by value (highest first)
    summary['collections'].sort(
        key=lambda x: x.get('total_value_usd', 0),
        reverse=True
    )

    return summary


@router.post("/bitcoin/refresh")
async def refresh_bitcoin_ordinals():
    """Force refresh all Bitcoin Ordinals data."""
    if not bitcoin_ordinals_service.is_configured():
        return {
            'configured': False,
            'message': 'Bitcoin Ordinals service not available'
        }

    bitcoin_ordinals_service.clear_cache()
    all_ordinals = await bitcoin_ordinals_service.get_all_bitcoin_ordinals(
        force_refresh=True
    )

    return {
        'message': f'Refreshed {len(all_ordinals)} Bitcoin Ordinals',
        'count': len(all_ordinals)
    }


@router.get("/bitcoin/status")
async def get_bitcoin_ordinals_status():
    """Get Bitcoin Ordinals service status including API configuration."""
    return bitcoin_ordinals_service.get_status()
```

### 4.3 Configuration Updates

Add to `/backend/config.py`:

```python
# Bitcoin Ordinals API Configuration
HIRO_ORDINALS_API_URL = "https://api.hiro.so/ordinals/v1"
ORDISCAN_API_KEY = os.getenv("ORDISCAN_API_KEY", "")  # Optional, free tier
```

Add to `.env.example`:

```bash
# Bitcoin Ordinals (Optional - enables floor price data)
ORDISCAN_API_KEY=your_ordiscan_api_key_here
```

### 4.4 Database Schema

Bitcoin Ordinals data will use the existing caching infrastructure. No new tables needed, but we can extend the `nft_floor_prices` table to support Bitcoin:

```sql
-- Add blockchain column to nft_floor_prices table (migration)
ALTER TABLE nft_floor_prices ADD COLUMN blockchain TEXT DEFAULT 'cardano';

-- Create index for Bitcoin lookups
CREATE INDEX IF NOT EXISTS idx_nft_floor_prices_blockchain
ON nft_floor_prices(blockchain);

-- Update unique constraint to include blockchain
-- This allows same collection name across different blockchains
```

Alternatively, ordinals data is stored in the standard cache table as JSON, similar to Ethereum/Solana NFTs.

### 4.5 Frontend Integration

#### Update `/frontend/nft-wall.html`

Add Bitcoin tab to NFT wall:

```html
<!-- In the blockchain tabs section -->
<button class="blockchain-tab" data-chain="bitcoin">
    <i class="fab fa-bitcoin"></i> Bitcoin Ordinals
</button>
```

Add fetch logic:

```javascript
async function fetchBitcoinOrdinals() {
    try {
        showLoadingSpinner('bitcoin');
        const response = await fetch(`${API_BASE_URL}/nfts/bitcoin`);
        const data = await response.json();

        if (data.configured && data.ordinals) {
            displayOrdinals(data.ordinals, data.btc_price);
            updateBitcoinSummary(data);
        } else {
            showNotConfigured('bitcoin', data.message);
        }
    } catch (error) {
        console.error('Error fetching Bitcoin ordinals:', error);
        showError('bitcoin', 'Failed to load Bitcoin ordinals');
    } finally {
        hideLoadingSpinner('bitcoin');
    }
}

function displayOrdinals(ordinals, btcPrice) {
    const container = document.getElementById('bitcoin-nfts-container');

    if (ordinals.length === 0) {
        container.innerHTML = '<p>No Bitcoin Ordinals found</p>';
        return;
    }

    container.innerHTML = ordinals.map(ordinal => `
        <div class="nft-card">
            <img src="${ordinal.image_url}"
                 alt="${ordinal.name}"
                 loading="lazy"
                 onerror="this.src='images/placeholder-nft.png'">
            <div class="nft-info">
                <h4>${ordinal.name}</h4>
                <p class="collection">${ordinal.collection.name}</p>
                <p class="inscription-number">#${ordinal.inscription_number}</p>
                ${ordinal.floor_price_usd ? `
                    <p class="floor-price">
                        Floor: ${formatBTC(ordinal.collection.floor_price_btc)} BTC
                        <span class="usd">(${formatUSD(ordinal.floor_price_usd)})</span>
                    </p>
                ` : '<p class="no-price">No floor price</p>'}
                <p class="rarity">Rarity: ${ordinal.sat_rarity}</p>
            </div>
        </div>
    `).join('');
}
```

#### Update `/frontend/dashboard.html`

Add Bitcoin Ordinals to NFT summary section:

```javascript
async function loadNFTSummary() {
    // ... existing code ...

    // Fetch Bitcoin Ordinals summary
    const btcOrdinalsResponse = await fetch(`${API_BASE_URL}/nfts/bitcoin/summary`);
    const btcOrdinalsData = await btcOrdinalsResponse.json();

    if (btcOrdinalsData.configured) {
        totalNFTValue += btcOrdinalsData.total_value_usd || 0;
        totalNFTCount += btcOrdinalsData.total_ordinals || 0;

        // Add to breakdown
        nftBreakdown.push({
            chain: 'Bitcoin',
            count: btcOrdinalsData.total_ordinals,
            value: btcOrdinalsData.total_value_usd,
            icon: 'bitcoin'
        });
    }

    // Update UI
    displayNFTSummary(totalNFTCount, totalNFTValue, nftBreakdown);
}
```

---

## 5. Implementation Plan

### Phase 1: Backend Service (Day 1 - 6 hours)

**Tasks:**
1. ✅ Create `/backend/services/bitcoin_ordinals.py`
2. ✅ Implement `BitcoinOrdinalsService` class
3. ✅ Add Hiro API integration for inscriptions
4. ✅ Add Ordiscan API integration for floor prices
5. ✅ Implement caching (in-memory and database)
6. ✅ Add parsing and data transformation
7. ✅ Write unit tests

**Acceptance Criteria:**
- Service can fetch inscriptions by Bitcoin address
- Floor prices are retrieved and cached
- Data is properly formatted for frontend
- Caching reduces API calls
- Error handling and logging in place

---

### Phase 2: API Endpoints (Day 1 - 2 hours)

**Tasks:**
1. ✅ Add Bitcoin Ordinals endpoints to `/backend/routers/nfts.py`
2. ✅ Implement `GET /nfts/bitcoin`
3. ✅ Implement `GET /nfts/bitcoin/summary`
4. ✅ Implement `POST /nfts/bitcoin/refresh`
5. ✅ Implement `GET /nfts/bitcoin/status`
6. ✅ Update `GET /nfts/all/summary` to include Bitcoin
7. ✅ Test all endpoints with Postman/curl

**Acceptance Criteria:**
- All endpoints return proper JSON responses
- USD conversion works correctly
- Multi-chain summary includes Bitcoin
- Refresh endpoint clears cache properly

---

### Phase 3: Configuration & Environment (Day 1 - 1 hour)

**Tasks:**
1. ✅ Add `ORDISCAN_API_KEY` to `config.py`
2. ✅ Update `.env.example` with new variable
3. ✅ Update documentation with API key setup
4. ✅ Test with and without Ordiscan API key

**Acceptance Criteria:**
- Service works without API key (using Hiro only)
- Floor prices work when API key is configured
- Clear error messages when APIs unavailable

---

### Phase 4: Frontend Integration (Day 2 - 4 hours)

**Tasks:**
1. ✅ Add Bitcoin tab to NFT Wall (`/frontend/nft-wall.html`)
2. ✅ Implement `fetchBitcoinOrdinals()` function
3. ✅ Implement `displayOrdinals()` rendering
4. ✅ Add Bitcoin to dashboard NFT summary
5. ✅ Style Bitcoin NFT cards
6. ✅ Handle image loading and errors
7. ✅ Test responsive design

**Acceptance Criteria:**
- Bitcoin tab appears in NFT Wall
- Ordinals display with images and metadata
- Floor prices show in BTC and USD
- Responsive on mobile devices
- Loading states and error handling work

---

### Phase 5: Image Caching Integration (Day 2 - 2 hours)

**Tasks:**
1. ✅ Update `/backend/services/nft_image_service.py` for Bitcoin
2. ✅ Add `bitcoin` to enabled chains
3. ✅ Implement content fetching from Hiro API
4. ✅ Add Bitcoin to batch caching endpoints
5. ✅ Test image caching and thumbnails

**Acceptance Criteria:**
- Bitcoin ordinals can be cached locally
- Thumbnails generated properly
- Image URLs work in NFT Wall
- Batch caching processes Bitcoin ordinals

---

### Phase 6: Testing & Documentation (Day 3 - 2 hours)

**Tasks:**
1. ✅ Test with real Bitcoin addresses containing ordinals
2. ✅ Verify floor price accuracy against marketplace
3. ✅ Test caching behavior (cold start, warm cache)
4. ✅ Test rate limiting and error recovery
5. ✅ Update user documentation
6. ✅ Create API documentation
7. ✅ Add Bitcoin to deployment guides

**Acceptance Criteria:**
- All features work with real data
- Documentation is complete and accurate
- Error messages are clear and helpful
- Performance is acceptable (< 2 seconds load time)

---

### Phase 7: Deployment (Day 3 - 1 hour)

**Tasks:**
1. ✅ Deploy backend updates
2. ✅ Deploy frontend updates
3. ✅ Configure environment variables
4. ✅ Monitor for errors
5. ✅ Verify in production

**Acceptance Criteria:**
- Bitcoin Ordinals appear in production NFT Wall
- No errors in logs
- Performance is good
- Users can see their ordinals

---

## 6. Code Examples

### Example 1: Fetch Inscriptions by Address

```python
async def example_fetch_inscriptions():
    """Example: Fetch all inscriptions for a Bitcoin address."""
    from services.bitcoin_ordinals import bitcoin_ordinals_service

    address = "bc1p8aq8s3z9xl87e74twfk93mljxq6alv4a79yheadx33t9np4g2wkqqt8kc5"

    inscriptions = await bitcoin_ordinals_service.get_inscriptions_for_address(address)

    print(f"Found {len(inscriptions)} inscriptions")

    for inscription in inscriptions[:5]:  # Show first 5
        print(f"  - Inscription #{inscription['number']}")
        print(f"    ID: {inscription['id']}")
        print(f"    Type: {inscription['content_type']}")
        print(f"    Rarity: {inscription['sat_rarity']}")
        print()
```

**Output:**
```
Found 23 inscriptions
  - Inscription #248751
    ID: 38c46a8bf7ec90bc7f6b797e7dc84baa97f4e5fd4286b92fe1b50176d03b18dci0
    Type: image/png
    Rarity: common

  - Inscription #248752
    ID: 4e9b3c5a2d1f8e7b9a0c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5i0
    Type: text/html
    Rarity: uncommon
```

### Example 2: Get Collection Floor Price

```python
async def example_get_floor_price():
    """Example: Get floor price for a Bitcoin Ordinals collection."""
    from services.bitcoin_ordinals import bitcoin_ordinals_service

    collection_slug = "bitcoin-puppets"

    floor_data = await bitcoin_ordinals_service.get_collection_floor_price(collection_slug)

    if floor_data:
        print(f"Collection: {collection_slug}")
        print(f"Floor Price: {floor_data['floor_price_btc']:.8f} BTC")
        print(f"Floor Price: ${floor_data['floor_price_usd']:.2f}")
        print(f"Supply: {floor_data['supply']}")
        print(f"Listings: {floor_data['listings']}")
        print(f"Verified: {floor_data['verified']}")
    else:
        print("Floor price not available")
```

**Output:**
```
Collection: bitcoin-puppets
Floor Price: 0.24500000 BTC
Floor Price: $16,250.50
Supply: 10000
Listings: 125
Verified: True
```

### Example 3: API Request to Get Ordinals

**cURL:**
```bash
# Get all Bitcoin Ordinals
curl http://localhost:8069/nfts/bitcoin

# Get Bitcoin Ordinals summary
curl http://localhost:8069/nfts/bitcoin/summary

# Force refresh
curl -X POST http://localhost:8069/nfts/bitcoin/refresh

# Get service status
curl http://localhost:8069/nfts/bitcoin/status
```

**Response Example:**
```json
{
  "configured": true,
  "ordinals": [
    {
      "inscription_id": "38c46a8bf7ec90bc7f6b797e7dc84baa97f4e5fd4286b92fe1b50176d03b18dci0",
      "inscription_number": 248751,
      "name": "Inscription #248751",
      "address": "bc1p8aq8s3z9xl87e74twfk93mljxq6alv4a79yheadx33t9np4g2wkqqt8kc5",
      "content_type": "image/png",
      "content_length": 52345,
      "image_url": "https://api.hiro.so/ordinals/v1/inscriptions/38c46a8b.../content",
      "sat_ordinal": "257418248345364",
      "sat_rarity": "common",
      "floor_price_usd": 16250.50,
      "collection": {
        "name": "Bitcoin Puppets",
        "floor_price_btc": 0.245,
        "floor_price_sats": 24500000,
        "verified": true,
        "floor_price_usd": 16250.50
      }
    }
  ],
  "total_count": 23,
  "valued_count": 18,
  "total_value_usd": 292509.00,
  "total_value_btc": 4.41,
  "btc_price": 66300.00,
  "last_updated": "2026-01-27T18:30:00Z"
}
```

---

## 7. Challenges & Limitations

### Challenge 1: Collection Identification

**Issue:** Unlike Ethereum (smart contracts) or Cardano (policy IDs), Bitcoin Ordinals don't have a standard collection identifier.

**Solution:**
- Use inscription metadata when available
- Maintain mapping of inscription number ranges to collections
- Use Ordiscan/Magic Eden collection data
- Allow manual collection tagging

**Workaround:**
Collections are identified by:
1. Metadata field (if present)
2. Genesis address patterns
3. Inscription number ranges
4. External API collection mappings

### Challenge 2: Floor Price Accuracy

**Issue:** Floor prices vary across marketplaces and aren't standardized.

**Solution:**
- Use multiple sources (Ordiscan, Magic Eden, OKX)
- Cache floor prices with timestamps
- Display data source to user
- Update prices incrementally (similar to Cardano NFTs)

**Mitigation:**
- Accept that floor prices are estimates
- Focus on popular collections first
- Add disclaimer in UI

### Challenge 3: Image Loading Performance

**Issue:** Fetching images directly from Bitcoin blockchain is slow.

**Solution:**
- Use Hiro's CDN for content delivery
- Implement local image caching (already exists)
- Generate thumbnails for faster loading
- Lazy load images in NFT Wall

**Implementation:**
```python
# Content URL points to Hiro CDN, not raw blockchain
image_url = f"https://api.hiro.so/ordinals/v1/inscriptions/{inscription_id}/content"
```

### Challenge 4: Rate Limits

**Issue:** Free APIs have rate limits that could impact large wallets.

**Solution:**
- Aggressive database caching (30-day TTL)
- Pagination when fetching inscriptions
- Rate limit handling with retries
- Fallback to cached data on errors

**Mitigation:**
```python
# Implement exponential backoff
for attempt in range(3):
    try:
        response = await client.get(url)
        if response.status_code == 429:
            await asyncio.sleep(2 ** attempt)
            continue
        break
    except Exception as e:
        if attempt == 2:
            # Use cached data
            return cached_ordinals
```

### Challenge 5: Large Collections

**Issue:** Some addresses may have hundreds or thousands of inscriptions.

**Solution:**
- Paginated API calls
- Background processing for initial load
- Only load top collections by value
- Option to filter low-value ordinals

**Implementation:**
```python
# Filter ordinals < $100 floor price
MIN_ORDINAL_VALUE_USD = 100.0

filtered_ordinals = [
    o for o in all_ordinals
    if o.get('floor_price_usd', 0) >= MIN_ORDINAL_VALUE_USD
]
```

---

## 8. Testing Strategy

### Unit Tests

Create `/backend/tests/test_bitcoin_ordinals.py`:

```python
import pytest
from services.bitcoin_ordinals import bitcoin_ordinals_service

@pytest.mark.asyncio
async def test_fetch_inscriptions_valid_address():
    """Test fetching inscriptions for a valid address."""
    address = "bc1p8aq8s3z9xl87e74twfk93mljxq6alv4a79yheadx33t9np4g2wkqqt8kc5"
    inscriptions = await bitcoin_ordinals_service.get_inscriptions_for_address(address)

    assert inscriptions is not None
    assert isinstance(inscriptions, list)
    if len(inscriptions) > 0:
        assert 'id' in inscriptions[0]
        assert 'number' in inscriptions[0]

@pytest.mark.asyncio
async def test_parse_inscription():
    """Test inscription parsing logic."""
    mock_inscription = {
        'id': 'test123i0',
        'number': 12345,
        'content_type': 'image/png',
        'address': 'bc1test',
        'genesis_address': 'bc1test',
        'genesis_block_height': 800000,
        'sat_rarity': 'common'
    }

    parsed = bitcoin_ordinals_service._parse_inscription(mock_inscription, 'bc1test')

    assert parsed['inscription_id'] == 'test123i0'
    assert parsed['name'] == 'Inscription #12345'
    assert parsed['content_type'] == 'image/png'

@pytest.mark.asyncio
async def test_collection_floor_price():
    """Test floor price fetching (requires API key)."""
    if not bitcoin_ordinals_service.ordiscan_api_key:
        pytest.skip("Ordiscan API key not configured")

    floor_data = await bitcoin_ordinals_service.get_collection_floor_price('bitcoin-puppets')

    if floor_data:
        assert 'floor_price_btc' in floor_data
        assert floor_data['floor_price_btc'] > 0
```

### Integration Tests

Test real Bitcoin addresses:

```python
TEST_ADDRESSES = [
    'bc1p8aq8s3z9xl87e74twfk93mljxq6alv4a79yheadx33t9np4g2wkqqt8kc5',  # Known to have ordinals
    'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh',  # Empty address
]

@pytest.mark.asyncio
async def test_real_bitcoin_addresses():
    """Test with real Bitcoin addresses."""
    for address in TEST_ADDRESSES:
        inscriptions = await bitcoin_ordinals_service.get_inscriptions_for_address(address)
        assert inscriptions is not None
        print(f"Address {address[:10]}... has {len(inscriptions)} inscriptions")
```

### Manual Testing Checklist

- [ ] Add Bitcoin wallet with ordinals to ABCT
- [ ] Visit NFT Wall, click Bitcoin tab
- [ ] Verify ordinals display with images
- [ ] Check floor prices are accurate
- [ ] Test on mobile (responsive design)
- [ ] Test with wallet that has no ordinals
- [ ] Test with wallet that has many ordinals (>100)
- [ ] Verify caching works (fast second load)
- [ ] Test refresh button
- [ ] Check dashboard shows Bitcoin in NFT summary

---

## 9. Estimated Effort & Resources

### Time Breakdown

| Phase | Task | Estimated Time |
|-------|------|----------------|
| 1 | Backend Service Implementation | 6 hours |
| 2 | API Endpoints | 2 hours |
| 3 | Configuration & Environment | 1 hour |
| 4 | Frontend Integration | 4 hours |
| 5 | Image Caching | 2 hours |
| 6 | Testing & Documentation | 2 hours |
| 7 | Deployment | 1 hour |
| **Total** | | **18 hours (~2-3 days)** |

### Complexity Assessment

| Aspect | Complexity | Notes |
|--------|-----------|-------|
| API Integration | **Medium** | Well-documented APIs, similar to existing services |
| Data Modeling | **Low** | Follows existing NFT patterns |
| Frontend Changes | **Low** | Reuse existing NFT Wall components |
| Image Handling | **Medium** | Need to handle Bitcoin-specific content URLs |
| Collection Mapping | **Medium** | No standard collection IDs, need creative solution |
| Testing | **Low** | Similar to other NFT services |
| **Overall** | **MEDIUM** | Comparable to Ethereum/Solana NFT integrations |

### Resource Requirements

**APIs:**
- Hiro Ordinals API - Free, no auth (PRIMARY)
- Ordiscan API - Free tier, requires key (OPTIONAL for floor prices)

**Infrastructure:**
- No new servers/services needed
- Uses existing database for caching
- Uses existing image caching system

**External Dependencies:**
- None (both APIs are free)

**Team Requirements:**
- 1 developer (backend + frontend)
- ~2-3 days of focused work
- Assumes familiarity with ABCT codebase

---

## 10. Recommendation

### Should We Implement This?

**YES - HIGHLY RECOMMENDED** ✅

### Reasons to Implement

1. **Strategic Completeness**
   - ABCT already tracks Bitcoin balances
   - Completes multi-chain NFT coverage (Cardano, ETH, Solana, Polygon, Base, Bitcoin)
   - Positions ABCT as comprehensive crypto portfolio tracker

2. **Low Risk, High Value**
   - Free APIs available (no ongoing costs)
   - Moderate implementation effort (2-3 days)
   - Follows established patterns (minimal architectural changes)
   - Significant value addition for users with Bitcoin ordinals

3. **Market Relevance**
   - Bitcoin Ordinals growing in popularity
   - Major collections have significant value (floor > 0.1 BTC)
   - User demand for cross-chain NFT tracking

4. **Technical Feasibility**
   - Hiro API is production-ready and well-maintained
   - Similar complexity to existing NFT integrations
   - Good documentation and support

5. **Future Proofing**
   - BRC-20 token support available (fungible tokens on Bitcoin)
   - Runes protocol support coming (new token standard)
   - Can expand to include rare sats tracking

### Implementation Priority

**Priority Level:** MEDIUM-HIGH

**Suggested Timeline:**
- **Week 1:** Backend implementation (Phases 1-3)
- **Week 2:** Frontend + testing (Phases 4-6)
- **Week 3:** Deployment + monitoring (Phase 7)

### Alternative: Minimal Implementation

If time is limited, start with a **minimal viable version**:

1. **Phase 1 Only:** Backend service with basic inscription listing
2. **Skip:** Floor prices (display "Not available")
3. **Skip:** Image caching (load from Hiro CDN directly)
4. **Basic Frontend:** Simple list view, no fancy styling

This reduces implementation to **1 day** and can be enhanced later.

---

## 11. Next Steps

### Immediate Actions

1. **Decision:** Get approval to proceed with implementation
2. **Setup:** Register for Ordiscan API key (if floor prices desired)
3. **Testing:** Identify Bitcoin addresses with ordinals for testing
4. **Scheduling:** Allocate 2-3 days for focused development

### Post-Implementation Enhancements

**Version 1.1 (Future):**
- BRC-20 token support (fungible tokens on Bitcoin)
- Rare sats tracking (satoshis with special properties)
- Collection tagging/categorization UI
- Advanced filtering (by rarity, collection, value)

**Version 1.2 (Future):**
- Historical floor price charts
- Ordinals activity feed (transfers, listings)
- Price alerts for collections
- Direct marketplace links (Magic Eden, Ordinals Wallet)

**Version 2.0 (Future):**
- Runes protocol support (new Bitcoin token standard)
- Multi-marketplace floor price aggregation
- Portfolio analytics (best/worst performing ordinals)
- Tax reporting for ordinals sales

---

## 12. References & Sources

### Documentation
- [Hiro Ordinals API Overview](https://docs.hiro.so/bitcoin/ordinals/api)
- [Ordiscan API Documentation](https://ordiscan.com/docs/api)
- [Ordinals Theory Handbook - Inscriptions](https://docs.ordinals.com/inscriptions.html)
- [SimpleHash Bitcoin Ordinals NFT API](https://simplehash.com/chains/bitcoin)
- [Magic Eden Ordinals API Overview](https://docs.magiceden.io/reference/ordinals-overview)

### API Services
- [Hiro Ordinals API](https://www.hiro.so/ordinals-api)
- [GitHub: Hiro Ordinals API](https://github.com/hirosystems/ordinals-api)
- [OKX NFT Ordinals API](https://www.okx.com/web3/build/docs/waas/marketplace-ordinals-api)
- [Ordinals Wallet API](https://blog.ordinalswallet.com/api)

### Market Data
- [CoinGecko Bitcoin NFT Collections](https://www.coingecko.com/en/nft/chains/ordinals)
- [NFT Price Floor - Bitcoin NFTs](https://nftpricefloor.com/top-nft-blockchains/bitcoin-nfts)
- [Bitcoin Ordinals Price Tracker - OrdinalHub](https://ordinalhub.com/price-tracking)

### Educational Resources
- [Bitcoin Ordinals, Inscriptions and Curses: A Primer - SimpleHash](https://simplehash.com/blog/bitcoin-ordinals-inscriptions-and-curses-a-primer)
- [Bitcoin Ordinals - A Guide for 2026 - Webopedia](https://www.webopedia.com/crypto/learn/bitcoin-ordinals-guide/)
- [Complete Bitcoin Ordinals Guide - Magic Eden](https://community.magiceden.io/learn/ordinals-guide)
- [What Are Ordinals? Bitcoin NFTs Explained - Chainlink](https://chain.link/education-hub/ordinals-bitcoin-nfts)
- [List of Best Bitcoin Ordinals Wallets for 2026](https://101blockchains.com/best-bitcoin-ordinals-wallets/)

### Technical Specifications
- [Metadata Standard - Ordinal Theory Handbook](https://docs.ordinals.com/inscriptions/metadata.html)
- [Inscription with Metadata - OrdinalsView](https://docs.ordinalsview.com/docs/category/inscription-with-metadata/)
- [Bitcoin Ordinals Metadata JSON Format - Gamma.io](https://support.gamma.io/hc/en-us/articles/16289612591123)

### Development Tools
- [Ordiscan SDK - GitHub](https://github.com/ordiscan/ordiscan-sdk)
- [Awesome Ordinals - Curated List](https://github.com/neu-fi/awesome-ordinals)
- [QuickNode Ordinals & Runes API](https://marketplace.quicknode.com/add-on/ordinals-json-rpc-api)

---

## Appendix A: Sample API Responses

### Hiro API - Get Inscriptions by Address

**Request:**
```bash
GET https://api.hiro.so/ordinals/v1/inscriptions?address=bc1p8aq8s3z9xl87e74twfk93mljxq6alv4a79yheadx33t9np4g2wkqqt8kc5&limit=20&offset=0
```

**Response:**
```json
{
  "limit": 20,
  "offset": 0,
  "total": 23,
  "results": [
    {
      "id": "38c46a8bf7ec90bc7f6b797e7dc84baa97f4e5fd4286b92fe1b50176d03b18dci0",
      "number": 248751,
      "address": "bc1p8aq8s3z9xl87e74twfk93mljxq6alv4a79yheadx33t9np4g2wkqqt8kc5",
      "genesis_address": "bc1p8aq8s3z9xl87e74twfk93mljxq6alv4a79yheadx33t9np4g2wkqqt8kc5",
      "genesis_block_height": 779000,
      "genesis_block_hash": "00000000000000000002a7c4c1e48d76c5a37902165a270156b7a8d72728a054",
      "genesis_tx_id": "38c46a8bf7ec90bc7f6b797e7dc84baa97f4e5fd4286b92fe1b50176d03b18dc",
      "genesis_fee": "3500",
      "genesis_timestamp": 1676358400000,
      "location": "38c46a8bf7ec90bc7f6b797e7dc84baa97f4e5fd4286b92fe1b50176d03b18dc:0:0",
      "output": "38c46a8bf7ec90bc7f6b797e7dc84baa97f4e5fd4286b92fe1b50176d03b18dc:0",
      "value": "10000",
      "offset": "0",
      "sat_ordinal": "257418248345364",
      "sat_rarity": "common",
      "sat_coinbase_height": 125000,
      "mime_type": "image/png",
      "content_type": "image/png",
      "content_length": "52345",
      "timestamp": 1676358400000,
      "tx_id": "38c46a8bf7ec90bc7f6b797e7dc84baa97f4e5fd4286b92fe1b50176d03b18dc"
    },
    {
      "id": "4e9b3c5a2d1f8e7b9a0c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5i0",
      "number": 248752,
      "address": "bc1p8aq8s3z9xl87e74twfk93mljxq6alv4a79yheadx33t9np4g2wkqqt8kc5",
      "genesis_address": "bc1pxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
      "genesis_block_height": 779100,
      "genesis_timestamp": 1676365600000,
      "content_type": "text/html;charset=utf-8",
      "content_length": "1542",
      "value": "10000",
      "sat_ordinal": "257418248345365",
      "sat_rarity": "uncommon",
      "timestamp": 1676365600000
    }
  ]
}
```

### Ordiscan API - Get Collection Details

**Request:**
```bash
GET https://api.ordiscan.com/v1/collection/bitcoin-puppets
Authorization: Bearer YOUR_API_KEY
```

**Response:**
```json
{
  "slug": "bitcoin-puppets",
  "name": "Bitcoin Puppets",
  "description": "10K unique puppets inscribed on Bitcoin",
  "supply": 10000,
  "floor_price_in_sats": 24500000,
  "floor_price_in_usd": 16250.50,
  "market_cap_in_btc": 245.0,
  "market_cap_in_usd": 16250500.00,
  "volume_24h_btc": 12.5,
  "volume_24h_usd": 828250.00,
  "listings": 125,
  "sales_24h": 18,
  "holders": 8234,
  "verified": true,
  "created_at": "2023-02-15T10:30:00Z",
  "inscription_range": {
    "start": 100000,
    "end": 110000
  },
  "website": "https://bitcoinpuppets.com",
  "twitter": "https://twitter.com/bitcoinpuppets",
  "image": "https://cdn.ordiscan.com/collections/bitcoin-puppets.png"
}
```

---

## Appendix B: Environment Setup

### Required Environment Variables

Add to `.env` file:

```bash
# Bitcoin Ordinals Configuration (Optional)
# Get free API key from: https://ordiscan.com/docs/api
ORDISCAN_API_KEY=your_ordiscan_api_key_here
```

### Optional Configuration

If you want more floor price sources:

```bash
# SimpleHash API (Paid)
SIMPLEHASH_API_KEY=your_simplehash_api_key_here

# Magic Eden API (Free tier: 30 QPM)
MAGIC_EDEN_API_KEY=your_magic_eden_api_key_here
```

### Testing Bitcoin Addresses

Use these addresses for testing (known to contain ordinals):

```python
TEST_BITCOIN_ADDRESSES = [
    # Address with Bitcoin Puppets
    'bc1p8aq8s3z9xl87e74twfk93mljxq6alv4a79yheadx33t9np4g2wkqqt8kc5',

    # Address with Ordinal Maxi Biz
    'bc1pxltsjkgezhz7wjz5c7svfy5sswqquv5caed94f8dl3xlt06ctn8svfcmh4',

    # Address with Quantum Cats
    'bc1pws6pvj75rcsc2eglpp9k570prnjh40nfpyahlyumk8y8smjayvasyhns5c',

    # Empty address (for negative testing)
    'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh'
]
```

---

## Document Change Log

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-01-27 | Initial research document | Claude Agent |

---

**END OF DOCUMENT**
