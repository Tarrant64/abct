"""
NFT Service - Fetches and caches NFT data for Cardano.

Identifies NFTs from native assets (quantity = 1) and enriches with:
- Collection data from TapTools API (requires API key)
- Floor prices where available
- Metadata from Blockfrost as fallback
"""

import httpx
import logging
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BLOCKFROST_API_KEY, BLOCKFROST_BASE_URL, TAPTOOLS_API_KEY
from database import (
    get_all_wallets, get_wallet_assets, get_cache, set_cache,
    save_nft_floor_price, get_latest_nft_floor_price, get_all_nft_floor_prices,
    get_collections_needing_price_update, get_nft_price_stats
)

logger = logging.getLogger(__name__)

# TapTools API (requires API key for floor prices)
TAPTOOLS_API_BASE = "https://openapi.taptools.io/api/v1"

# Koios API (free, no auth required - for collection metadata)
KOIOS_API_BASE = "https://api.koios.rest/api/v1"

# Cache settings - use long TTL for persistent database cache
NFT_CACHE_KEY = "nft_all_data"
COLLECTION_CACHE_KEY_PREFIX = "nft_collection_"
NFT_CACHE_TTL = 86400 * 30  # 30 days - persistent until manual refresh
COLLECTION_CACHE_DURATION = timedelta(hours=24)  # In-memory cache for collection lookups


class NFTService:
    """Service for fetching and caching NFT data."""

    def __init__(self):
        self.nft_cache: Dict[str, dict] = {}  # In-memory cache for quick access
        self.collection_cache: Dict[str, dict] = {}  # policy_id -> collection data
        self.last_full_refresh: Optional[datetime] = None
        self.blockfrost_headers = {"project_id": BLOCKFROST_API_KEY}
        self.taptools_headers = {"x-api-key": TAPTOOLS_API_KEY} if TAPTOOLS_API_KEY else {}
        self._db_cache_loaded = False  # Track if we've loaded from DB cache
        self._rate_limited = False  # Track if we've hit TapTools rate limit
        self._rate_limit_reset: Optional[datetime] = None  # When rate limit resets

    def is_taptools_configured(self) -> bool:
        """Check if TapTools API key is configured."""
        return bool(TAPTOOLS_API_KEY)

    def is_rate_limited(self) -> bool:
        """Check if we're currently rate limited by TapTools."""
        if not self._rate_limited:
            return False
        # Rate limit resets after 24 hours
        if self._rate_limit_reset and datetime.now() > self._rate_limit_reset:
            self._rate_limited = False
            self._rate_limit_reset = None
            logger.info("TapTools rate limit has reset")
            return False
        return True

    def set_rate_limited(self):
        """Mark that we've hit the TapTools rate limit."""
        self._rate_limited = True
        self._rate_limit_reset = datetime.now() + timedelta(hours=24)
        logger.warning("TapTools API rate limit reached (100/day). Using cached data.")

    def get_status(self) -> dict:
        """Get NFT service status."""
        rate_limit_info = None
        if self.is_rate_limited():
            rate_limit_info = f"Rate limited until {self._rate_limit_reset.isoformat()}" if self._rate_limit_reset else "Rate limited"

        return {
            "taptools_configured": self.is_taptools_configured(),
            "koios_available": True,  # Koios is always available (free, no auth)
            "cached_nfts": len(self.nft_cache),
            "cached_collections": len(self.collection_cache),
            "last_refresh": self.last_full_refresh.isoformat() if self.last_full_refresh else None,
            "floor_prices": "rate_limited" if self.is_rate_limited() else ("available" if self.is_taptools_configured() else "unavailable (TapTools API key required)"),
            "rate_limit_status": rate_limit_info,
            "metadata_source": "TapTools + Koios" if self.is_taptools_configured() else "Koios (free)",
            "note": "TapTools API key required for floor prices. Get one at https://www.taptools.io/openapi/subscription" if not self.is_taptools_configured() else ("Rate limit reached - using cached floor prices" if self.is_rate_limited() else "Full NFT data available")
        }

    def is_nft(self, asset: dict) -> bool:
        """Determine if a native asset is an NFT (quantity = 1)."""
        try:
            quantity = int(asset.get('quantity', 0))
            return quantity == 1
        except (ValueError, TypeError):
            return False

    def _normalize_ipfs_url(self, url: str) -> Optional[str]:
        """Convert IPFS URLs to HTTP gateway URLs."""
        if not url:
            return None

        # Handle ipfs:// protocol
        if url.startswith('ipfs://'):
            ipfs_hash = url[7:]
            return f"https://ipfs.io/ipfs/{ipfs_hash}"

        # Handle Qm... IPFS hashes
        if url.startswith('Qm') and len(url) >= 46:
            return f"https://ipfs.io/ipfs/{url}"

        # Handle array format (CIP-25 allows arrays for long URLs)
        if isinstance(url, list):
            joined = ''.join(url)
            return self._normalize_ipfs_url(joined)

        # Already HTTP/HTTPS
        if url.startswith('http://') or url.startswith('https://'):
            return url

        # Handle data URIs (base64 images)
        if url.startswith('data:'):
            return url

        return None

    def _extract_image_from_metadata(self, metadata: dict) -> Optional[str]:
        """Extract image URL from CIP-25 NFT metadata."""
        if not metadata:
            return None

        # Direct image field (most common)
        image = metadata.get('image')
        if image:
            if isinstance(image, list):
                image = ''.join(image)
            return self._normalize_ipfs_url(image)

        # Check files array (CIP-25 standard)
        files = metadata.get('files', [])
        if files and isinstance(files, list):
            for file in files:
                if isinstance(file, dict):
                    media_type = file.get('mediaType', '')
                    if 'image' in media_type.lower():
                        src = file.get('src')
                        if src:
                            if isinstance(src, list):
                                src = ''.join(src)
                            return self._normalize_ipfs_url(src)

        # Check logo field
        logo = metadata.get('logo')
        if logo:
            if isinstance(logo, list):
                logo = ''.join(logo)
            return self._normalize_ipfs_url(logo)

        return None

    async def _fetch_nft_image_url(self, asset_id: str) -> Optional[str]:
        """Fetch the image URL for an NFT from Blockfrost metadata."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{BLOCKFROST_BASE_URL}/assets/{asset_id}",
                    headers=self.blockfrost_headers
                )

                if response.status_code == 200:
                    data = response.json()
                    # Try onchain_metadata first (CIP-25 standard)
                    onchain = data.get('onchain_metadata')
                    if onchain:
                        image_url = self._extract_image_from_metadata(onchain)
                        if image_url:
                            return image_url

                    # Try metadata field as fallback
                    metadata = data.get('metadata')
                    if metadata:
                        image_url = self._extract_image_from_metadata(metadata)
                        if image_url:
                            return image_url

                return None

        except Exception as e:
            logger.debug(f"Error fetching image for {asset_id[:20]}...: {e}")
            return None

    async def get_all_nfts(self, user_id: int = None, force_refresh: bool = False) -> List[dict]:
        """
        Get all NFTs across all Cardano wallets.
        Returns enriched NFT data with collection info and prices.
        Uses persistent database cache that survives server restarts.
        """
        # Try to load from persistent database cache first (user-specific)
        if not force_refresh and user_id is not None:
            cached_data = await get_cache(NFT_CACHE_KEY, user_id=user_id)
            if cached_data:
                logger.info(f"Loaded {len(cached_data.get('nfts', []))} NFTs from user {user_id} cache")
                # Return cached data directly without modifying instance variables
                return cached_data.get('nfts', [])

        # Always load floor prices from database first to reduce API calls
        await self.load_floor_prices_from_db()

        wallets = await get_all_wallets(user_id=user_id)
        cardano_wallets = [w for w in wallets if w['blockchain'] == 'cardano']

        all_nfts = []
        seen_assets = set()

        for wallet in cardano_wallets:
            assets = await get_wallet_assets(wallet['id'])

            for asset in assets:
                if not self.is_nft(asset):
                    continue

                asset_id = asset.get('asset_id', '')
                if asset_id in seen_assets:
                    continue
                seen_assets.add(asset_id)

                # Build NFT data
                nft_data = {
                    'asset_id': asset_id,
                    'policy_id': asset.get('policy_id', ''),
                    'asset_name': asset.get('asset_name', ''),
                    'asset_name_hex': asset_id[56:] if len(asset_id) > 56 else '',
                    'wallet_address': wallet['address'],
                    'wallet_label': wallet.get('label', ''),
                }

                all_nfts.append(nft_data)

        # Enrich NFTs with collection data (batch by policy_id)
        # Build temporary collection cache for this user's NFTs
        temp_collection_cache = {}
        policy_ids = list(set(nft['policy_id'] for nft in all_nfts))
        if policy_ids:
            logger.info(f"Fetching collection data for {len(policy_ids)} collections")
            # Load from DB first
            for pid in policy_ids:
                floor_price_data = await self._get_floor_price_from_db(pid)
                if floor_price_data:
                    temp_collection_cache[pid] = floor_price_data

            # Fetch any missing from API
            uncached_policy_ids = [pid for pid in policy_ids if pid not in temp_collection_cache]
            if uncached_policy_ids:
                await self._fetch_collection_data(uncached_policy_ids)
                # Copy to temp cache
                for pid in uncached_policy_ids:
                    if pid in self.collection_cache:
                        temp_collection_cache[pid] = self.collection_cache[pid]

        # Enrich each NFT with collection data
        enriched_nfts = []
        for nft in all_nfts:
            # Add collection data to NFT
            policy_id = nft['policy_id']
            collection = temp_collection_cache.get(policy_id, {})
            nft['collection'] = {
                'found': collection.get('found', False),
                'name': collection.get('name', ''),
                'verified': collection.get('verified', False),
                'floor_price_ada': collection.get('floor_price_ada'),
            }

            # Calculate price
            if nft.get('listing_price_ada'):
                nft['price_ada'] = nft['listing_price_ada']
                nft['price_source'] = 'listing'
            elif collection.get('floor_price_ada'):
                nft['price_ada'] = collection['floor_price_ada']
                nft['price_source'] = 'floor'
            else:
                nft['price_ada'] = None
                nft['price_source'] = None

            enriched_nfts.append(nft)

        # Save to persistent database cache (user-specific)
        if user_id is not None:
            await self._save_to_db_cache(enriched_nfts, temp_collection_cache, user_id)

        return enriched_nfts

    async def _save_to_db_cache(self, nfts: List[dict], collections: dict, user_id: int) -> None:
        """Save NFT data to persistent database cache (user-specific)."""
        try:
            # Prepare data for caching (convert datetime objects)
            cache_data = {
                'nfts': nfts,
                'collections': {
                    pid: {k: v.isoformat() if isinstance(v, datetime) else v for k, v in col.items()}
                    for pid, col in collections.items()
                },
                'last_refresh': datetime.now().isoformat()
            }
            await set_cache(NFT_CACHE_KEY, cache_data, NFT_CACHE_TTL, user_id=user_id)
            logger.info(f"Saved {len(nfts)} NFTs to user {user_id} cache")
        except Exception as e:
            logger.error(f"Error saving NFT cache to database: {e}")

    async def _fetch_collection_data(self, policy_ids: List[str]) -> None:
        """Fetch collection data from TapTools API for multiple policy IDs."""
        for policy_id in policy_ids:
            if policy_id in self.collection_cache:
                cache_entry = self.collection_cache[policy_id]
                if datetime.now() - cache_entry.get('cached_at', datetime.min) < COLLECTION_CACHE_DURATION:
                    continue

            try:
                # Only try TapTools if API key is configured and not rate limited
                if self.is_taptools_configured() and not self.is_rate_limited():
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        # Get collection info (name, description, etc.)
                        info_response = await client.get(
                            f"{TAPTOOLS_API_BASE}/nft/collection/info",
                            params={"policy": policy_id},
                            headers=self.taptools_headers
                        )

                        # Check for rate limiting immediately
                        if info_response.status_code == 429:
                            self.set_rate_limited()
                            # Fall through to Blockfrost fallback
                        else:
                            # Get collection stats (floor price, listings, volume)
                            stats_response = await client.get(
                                f"{TAPTOOLS_API_BASE}/nft/collection/stats",
                                params={"policy": policy_id},
                                headers=self.taptools_headers
                            )

                            # Check for rate limiting on stats call
                            if stats_response.status_code == 429:
                                self.set_rate_limited()
                                # Fall through to Blockfrost fallback
                            elif info_response.status_code == 200 or stats_response.status_code == 200:
                                info_data = info_response.json() if info_response.status_code == 200 else {}
                                stats_data = stats_response.json() if stats_response.status_code == 200 else {}

                                # Floor price is in stats endpoint as 'price'
                                floor_price = stats_data.get('price')

                                self.collection_cache[policy_id] = {
                                    'found': True,
                                    'name': info_data.get('name', ''),
                                    'description': info_data.get('description', ''),
                                    'floor_price_ada': float(floor_price) if floor_price else None,
                                    'verified': info_data.get('verified', False),
                                    'supply': stats_data.get('supply') or info_data.get('supply'),
                                    'listings': stats_data.get('listings', 0),
                                    'volume': stats_data.get('volume', 0),
                                    'top_offer': stats_data.get('topOffer'),
                                    'owners': stats_data.get('owners'),
                                    'source': 'taptools',
                                    'cached_at': datetime.now()
                                }
                                continue
                            elif info_response.status_code == 401:
                                logger.warning("TapTools API key invalid or expired")
                            elif info_response.status_code == 404 and stats_response.status_code == 404:
                                # Collection not found on TapTools, try Blockfrost
                                pass
                            else:
                                logger.debug(f"TapTools returned info:{info_response.status_code} stats:{stats_response.status_code} for {policy_id[:16]}...")

                # Fallback to Blockfrost for basic metadata (no floor price)
                self.collection_cache[policy_id] = await self._fetch_from_blockfrost(policy_id)

            except Exception as e:
                logger.error(f"Error fetching collection {policy_id[:16]}...: {e}")
                # Try Blockfrost as fallback
                try:
                    self.collection_cache[policy_id] = await self._fetch_from_blockfrost(policy_id)
                except:
                    self.collection_cache[policy_id] = {
                        'found': False,
                        'error': str(e),
                        'cached_at': datetime.now()
                    }

    async def _fetch_from_koios(self, policy_id: str) -> dict:
        """Fetch collection info from Koios API (free, no auth required)."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Get policy asset info from Koios
                response = await client.get(
                    f"{KOIOS_API_BASE}/policy_asset_info",
                    params={"_asset_policy": policy_id}
                )

                if response.status_code == 200:
                    assets = response.json()
                    if assets and len(assets) > 0:
                        # Find a good example asset with metadata
                        collection_name = None
                        total_supply = len(assets)

                        for asset in assets[:10]:  # Check first 10 assets
                            metadata = asset.get('minting_tx_metadata', {})
                            # CIP-25 metadata structure
                            cip25 = metadata.get('721', {}).get(policy_id, {})
                            if cip25:
                                # Get first asset's metadata
                                for asset_name, asset_meta in cip25.items():
                                    if isinstance(asset_meta, dict):
                                        # Try to extract collection/project name
                                        collection_name = (
                                            asset_meta.get('collection') or
                                            asset_meta.get('project') or
                                            asset_meta.get('name', '').split('#')[0].strip() or
                                            asset_meta.get('name', '').split(' ')[0].strip()
                                        )
                                        if collection_name:
                                            break
                            if collection_name:
                                break

                        return {
                            'found': True,
                            'name': collection_name or 'Unknown Collection',
                            'description': '',
                            'floor_price_ada': None,  # Koios doesn't provide floor prices
                            'verified': False,
                            'supply': total_supply,
                            'source': 'koios',
                            'cached_at': datetime.now()
                        }

        except Exception as e:
            logger.debug(f"Koios fallback failed for {policy_id[:16]}...: {e}")

        return None

    async def _fetch_from_blockfrost(self, policy_id: str) -> dict:
        """Fallback to fetch basic collection info from Blockfrost."""
        # First try Koios (free and often has better metadata)
        koios_result = await self._fetch_from_koios(policy_id)
        if koios_result:
            return koios_result

        # Fall back to Blockfrost
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{BLOCKFROST_BASE_URL}/assets/policy/{policy_id}",
                    headers=self.blockfrost_headers,
                    params={"count": 1}
                )

                if response.status_code == 200:
                    assets = response.json()
                    if assets and len(assets) > 0:
                        # Get metadata for the first asset to find collection name
                        first_asset = assets[0]
                        metadata = first_asset.get('onchain_metadata', {})
                        return {
                            'found': True,
                            'name': metadata.get('name', metadata.get('project', 'Unknown Collection')),
                            'description': metadata.get('description', ''),
                            'floor_price_ada': None,  # No price from Blockfrost
                            'verified': False,
                            'supply': None,
                            'source': 'blockfrost',
                            'cached_at': datetime.now()
                        }
        except Exception as e:
            logger.debug(f"Blockfrost fallback failed for {policy_id[:16]}...: {e}")

        return {
            'found': False,
            'cached_at': datetime.now()
        }

    async def _enrich_nft(self, nft: dict) -> dict:
        """Enrich a single NFT with collection data and metadata."""
        policy_id = nft['policy_id']
        asset_id = nft['asset_id']

        # Add collection data if available
        collection = self.collection_cache.get(policy_id, {})
        nft['collection'] = {
            'found': collection.get('found', False),
            'name': collection.get('name', ''),
            'verified': collection.get('verified', False),
            'floor_price_ada': collection.get('floor_price_ada'),
        }

        # Build links (jpg.store links still work for viewing)
        nft['links'] = {
            'jpgstore': f"https://www.jpg.store/asset/{asset_id}",
            'taptools': f"https://www.taptools.io/nft/asset/{asset_id}",
            'cexplorer': f"https://cexplorer.io/asset/{asset_id}",
            'cardanoscan': f"https://cardanoscan.io/token/{asset_id}",
        }

        # Try to get individual NFT listing price from TapTools
        nft['listing_price_ada'] = await self._get_nft_listing_price(asset_id)

        # Determine display price (listing price if available, otherwise floor)
        if nft['listing_price_ada']:
            nft['price_ada'] = nft['listing_price_ada']
            nft['price_source'] = 'listing'
        elif nft['collection']['floor_price_ada']:
            nft['price_ada'] = nft['collection']['floor_price_ada']
            nft['price_source'] = 'floor'
        else:
            nft['price_ada'] = None
            nft['price_source'] = None

        return nft

    async def batch_fetch_image_urls(self, nfts: List[dict], max_concurrent: int = 5) -> Dict[str, str]:
        """
        Batch fetch image URLs for multiple NFTs.
        Returns a dict mapping asset_id to image_url.
        """
        import asyncio

        results = {}
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_one(nft):
            async with semaphore:
                asset_id = nft.get('asset_id')
                if not asset_id:
                    return

                # Check if we already have the image URL cached
                if nft.get('image'):
                    results[asset_id] = nft['image']
                    return

                # Fetch from Blockfrost
                image_url = await self._fetch_nft_image_url(asset_id)
                if image_url:
                    results[asset_id] = image_url
                    # Also update the cached NFT
                    if asset_id in self.nft_cache:
                        self.nft_cache[asset_id]['image'] = image_url

        await asyncio.gather(*[fetch_one(nft) for nft in nfts])

        logger.info(f"Fetched {len(results)} image URLs for {len(nfts)} NFTs")
        return results

    async def _get_nft_listing_price(self, asset_id: str) -> Optional[float]:
        """Get the current listing price for an NFT from TapTools."""
        # Skip if TapTools not configured or rate limited
        if not self.is_taptools_configured() or self.is_rate_limited():
            return None

        try:
            # Extract policy_id from asset_id (first 56 characters)
            policy_id = asset_id[:56]
            asset_name_hex = asset_id[56:]

            async with httpx.AsyncClient(timeout=15.0) as client:
                # TapTools endpoint for NFT listings with auth
                response = await client.get(
                    f"{TAPTOOLS_API_BASE}/nft/asset/listings",
                    params={"policy": policy_id, "name": asset_name_hex},
                    headers=self.taptools_headers
                )

                if response.status_code == 429:
                    self.set_rate_limited()
                    return None

                if response.status_code == 200:
                    data = response.json()
                    # Data is a list of listings
                    if data and len(data) > 0:
                        # Get the lowest listing price
                        lowest = min(data, key=lambda x: float(x.get('price', float('inf'))))
                        price = lowest.get('price')
                        if price:
                            return float(price)  # TapTools returns price in ADA
                return None

        except Exception as e:
            logger.debug(f"Error getting listing price for {asset_id[:20]}...: {e}")
            return None

    async def get_nft_by_asset_id(self, asset_id: str) -> Optional[dict]:
        """Get a specific NFT by asset ID."""
        if asset_id in self.nft_cache:
            return self.nft_cache[asset_id]

        # Not in cache, try to fetch
        all_nfts = await self.get_all_nfts()
        return self.nft_cache.get(asset_id)

    async def get_nfts_by_collection(self, policy_id: str) -> List[dict]:
        """Get all NFTs for a specific collection (policy ID)."""
        all_nfts = await self.get_all_nfts()
        return [nft for nft in all_nfts if nft['policy_id'] == policy_id]

    async def get_nft_summary(self, user_id: int = None) -> dict:
        """Get a summary of all NFTs."""
        all_nfts = await self.get_all_nfts(user_id=user_id)

        # Group by collection
        collections = {}
        total_value = 0.0
        valued_count = 0

        for nft in all_nfts:
            policy_id = nft['policy_id']
            if policy_id not in collections:
                collections[policy_id] = {
                    'policy_id': policy_id,
                    'name': nft['collection'].get('name', 'Unknown Collection'),
                    'verified': nft['collection'].get('verified', False),
                    'found_on_jpgstore': nft['collection'].get('found', False),
                    'floor_price_ada': nft['collection'].get('floor_price_ada'),
                    'nfts': [],
                    'count': 0,
                    'total_value_ada': 0
                }

            collections[policy_id]['nfts'].append(nft)
            collections[policy_id]['count'] += 1

            if nft.get('price_ada'):
                collections[policy_id]['total_value_ada'] += nft['price_ada']
                total_value += nft['price_ada']
                valued_count += 1

        return {
            'total_nfts': len(all_nfts),
            'collections_count': len(collections),
            'valued_nfts': valued_count,
            'total_value_ada': total_value,
            'collections': list(collections.values()),
            'last_updated': self.last_full_refresh.isoformat() if self.last_full_refresh else None
        }

    def _update_nft_collection_data(self) -> None:
        """
        Update the embedded collection data in all cached NFTs with fresh data
        from the collection cache. This ensures floor prices from the DB are
        reflected in the NFT objects.
        """
        updated_count = 0
        for asset_id, nft in self.nft_cache.items():
            policy_id = nft.get('policy_id')
            if policy_id and policy_id in self.collection_cache:
                collection = self.collection_cache[policy_id]
                old_floor = nft.get('collection', {}).get('floor_price_ada')
                new_floor = collection.get('floor_price_ada')

                # Update collection data in the NFT
                nft['collection'] = {
                    'found': collection.get('found', False),
                    'name': collection.get('name', ''),
                    'verified': collection.get('verified', False),
                    'floor_price_ada': new_floor,
                }

                # Update price fields
                if nft.get('listing_price_ada'):
                    nft['price_ada'] = nft['listing_price_ada']
                    nft['price_source'] = 'listing'
                elif new_floor:
                    nft['price_ada'] = new_floor
                    nft['price_source'] = 'floor'
                else:
                    nft['price_ada'] = None
                    nft['price_source'] = None

                if old_floor != new_floor and new_floor is not None:
                    updated_count += 1

        if updated_count > 0:
            logger.info(f"Updated floor prices for {updated_count} NFTs from database")

    def _is_cache_valid(self) -> bool:
        """Check if the NFT cache is still valid."""
        if not self.last_full_refresh:
            return False
        return datetime.now() - self.last_full_refresh < timedelta(seconds=NFT_CACHE_TTL)

    def clear_cache(self):
        """Clear all caches."""
        self.nft_cache.clear()
        self.collection_cache.clear()
        self.last_full_refresh = None

    async def update_floor_price_cache(self, policy_id: str, floor_price: float):
        """
        Update the floor price for a collection in the cache and database.
        Used when syncing prices from external NFT Price Service.
        """
        # Update collection cache
        if policy_id in self.collection_cache:
            self.collection_cache[policy_id]['floor_price_ada'] = floor_price

        # Save to database for persistence
        try:
            from database import save_nft_floor_price
            await save_nft_floor_price({
                'policy_id': policy_id,
                'collection_name': self.collection_cache.get(policy_id, {}).get('name'),
                'floor_price_ada': floor_price,
                'listings': None,
                'supply': None,
                'verified': self.collection_cache.get(policy_id, {}).get('verified', False),
                'source': 'external_service',
                'fetched_at': None  # Will use current timestamp
            })
        except Exception as e:
            logger.warning(f"Failed to save floor price to DB: {e}")

    async def load_floor_prices_from_db(self) -> int:
        """
        Load stored floor prices from the database into the collection cache.
        This allows using historical price data without hitting rate limits.

        Updates existing cache entries with floor prices from the database
        if the DB has a price and the cache doesn't.

        Returns:
            Number of collections loaded/updated from database
        """
        try:
            stored_prices = await get_all_nft_floor_prices()
            loaded_count = 0

            for price_data in stored_prices:
                policy_id = price_data['policy_id']
                db_floor_price = price_data.get('floor_price_ada')

                if policy_id not in self.collection_cache:
                    # New collection - add to cache
                    self.collection_cache[policy_id] = {
                        'found': True,
                        'name': price_data.get('collection_name', ''),
                        'floor_price_ada': db_floor_price,
                        'verified': bool(price_data.get('verified')),
                        'supply': price_data.get('supply'),
                        'listings': price_data.get('listings', 0),
                        'source': price_data.get('source', 'database'),
                        'cached_at': datetime.fromisoformat(price_data['fetched_at']) if price_data.get('fetched_at') else datetime.now(),
                        'from_db': True
                    }
                    loaded_count += 1
                elif db_floor_price is not None:
                    # Collection exists in cache - update floor price if DB has one
                    existing = self.collection_cache[policy_id]
                    if existing.get('floor_price_ada') is None:
                        # Cache has no price, use DB price
                        existing['floor_price_ada'] = db_floor_price
                        existing['from_db'] = True
                        loaded_count += 1
                    elif existing.get('from_db'):
                        # Both from DB, use the newer price data
                        existing['floor_price_ada'] = db_floor_price
                        # Also update other fields from DB if available
                        if price_data.get('collection_name'):
                            existing['name'] = price_data['collection_name']
                        if price_data.get('listings'):
                            existing['listings'] = price_data['listings']
                        if price_data.get('supply'):
                            existing['supply'] = price_data['supply']
                        loaded_count += 1

            logger.info(f"Loaded/updated {loaded_count} floor prices from database")
            return loaded_count

        except Exception as e:
            logger.error(f"Error loading floor prices from database: {e}")
            return 0

    async def collect_floor_prices_incremental(self, batch_size: int = 5, max_batches: int = 3) -> dict:
        """
        Incrementally collect floor prices for collections that need updates.

        This method:
        1. Prioritizes collections without any price data
        2. Then updates collections with oldest data
        3. Stops gracefully on rate limits
        4. Saves progress to the database

        Args:
            batch_size: Number of collections to fetch per batch
            max_batches: Maximum number of batches to process (to limit API calls)

        Returns:
            dict with collection status
        """
        if not self.is_taptools_configured():
            return {
                'status': 'skipped',
                'reason': 'TapTools API key not configured',
                'collections_updated': 0
            }

        total_updated = 0
        total_skipped = 0
        total_rate_limited = 0
        rate_limit_hit = False

        for batch_num in range(max_batches):
            if rate_limit_hit:
                break

            # Get collections that need updates
            collections_to_update = await get_collections_needing_price_update(
                max_age_days=7,
                limit=batch_size
            )

            if not collections_to_update:
                logger.info("All collections have recent price data")
                break

            logger.info(f"Batch {batch_num + 1}: Fetching prices for {len(collections_to_update)} collections")

            async with httpx.AsyncClient(timeout=30.0) as client:
                for policy_id in collections_to_update:
                    try:
                        # Fetch from TapTools - add delay between calls to avoid rate limits
                        import asyncio

                        info_response = await client.get(
                            f"{TAPTOOLS_API_BASE}/nft/collection/info",
                            params={"policy": policy_id},
                            headers=self.taptools_headers
                        )

                        # Check for rate limiting on info call first
                        if info_response.status_code == 429:
                            logger.warning(f"Rate limited by TapTools, stopping collection")
                            rate_limit_hit = True
                            total_rate_limited += 1
                            break

                        # Small delay before stats call to respect rate limits
                        await asyncio.sleep(1.0)

                        stats_response = await client.get(
                            f"{TAPTOOLS_API_BASE}/nft/collection/stats",
                            params={"policy": policy_id},
                            headers=self.taptools_headers
                        )

                        # Check for rate limiting on stats call - save info data anyway
                        if stats_response.status_code == 429:
                            logger.warning(f"Rate limited by TapTools on stats call")
                            # Save partial data from info call if successful
                            if info_response.status_code == 200:
                                info_data = info_response.json()
                                collection_name = info_data.get('name', '')
                                price_data = {
                                    'policy_id': policy_id,
                                    'collection_name': collection_name,
                                    'floor_price_ada': None,  # No floor price without stats
                                    'supply': info_data.get('supply'),
                                    'verified': info_data.get('verified', False),
                                    'source': 'taptools-partial',
                                    'fetched_at': datetime.now().isoformat()
                                }
                                await save_nft_floor_price(price_data)
                                logger.info(f"Saved partial data for {collection_name or policy_id[:16]} (no floor price)")
                                total_updated += 1
                            rate_limit_hit = True
                            total_rate_limited += 1
                            break

                        if info_response.status_code == 200 or stats_response.status_code == 200:
                            info_data = info_response.json() if info_response.status_code == 200 else {}
                            stats_data = stats_response.json() if stats_response.status_code == 200 else {}

                            floor_price = stats_data.get('price')
                            collection_name = info_data.get('name', '')

                            # Save to database
                            price_data = {
                                'policy_id': policy_id,
                                'collection_name': collection_name,
                                'floor_price_ada': float(floor_price) if floor_price else None,
                                'listings': stats_data.get('listings', 0),
                                'supply': stats_data.get('supply') or info_data.get('supply'),
                                'verified': info_data.get('verified', False),
                                'source': 'taptools',
                                'fetched_at': datetime.now().isoformat()
                            }
                            await save_nft_floor_price(price_data)

                            # Update in-memory cache
                            self.collection_cache[policy_id] = {
                                'found': True,
                                'name': collection_name,
                                'floor_price_ada': float(floor_price) if floor_price else None,
                                'verified': info_data.get('verified', False),
                                'supply': stats_data.get('supply') or info_data.get('supply'),
                                'listings': stats_data.get('listings', 0),
                                'source': 'taptools',
                                'cached_at': datetime.now()
                            }

                            total_updated += 1
                            logger.debug(f"Updated price for {collection_name or policy_id[:16]}: {floor_price} ADA")

                        else:
                            # Try fallback to Koios for metadata (no floor price)
                            koios_data = await self._fetch_from_koios(policy_id)
                            if koios_data:
                                price_data = {
                                    'policy_id': policy_id,
                                    'collection_name': koios_data.get('name'),
                                    'floor_price_ada': None,
                                    'supply': koios_data.get('supply'),
                                    'verified': False,
                                    'source': 'koios',
                                    'fetched_at': datetime.now().isoformat()
                                }
                                await save_nft_floor_price(price_data)
                                self.collection_cache[policy_id] = koios_data
                                total_updated += 1
                            else:
                                total_skipped += 1

                        # Delay between collections to be nice to the API
                        await asyncio.sleep(1.5)

                    except Exception as e:
                        logger.error(f"Error fetching price for {policy_id[:16]}: {e}")
                        total_skipped += 1

            # Delay between batches
            if batch_num < max_batches - 1 and not rate_limit_hit:
                import asyncio
                await asyncio.sleep(2)

        # Get current stats
        stats = await get_nft_price_stats()

        return {
            'status': 'completed' if not rate_limit_hit else 'rate_limited',
            'collections_updated': total_updated,
            'collections_skipped': total_skipped,
            'rate_limited': rate_limit_hit,
            'coverage': stats
        }

    async def get_price_collection_status(self) -> dict:
        """Get the current status of NFT price data collection."""
        stats = await get_nft_price_stats()
        return {
            'taptools_configured': self.is_taptools_configured(),
            'in_memory_collections': len(self.collection_cache),
            'database_stats': stats
        }

    async def get_floor_price_for_collection(self, policy_id: str) -> Optional[float]:
        """
        Get floor price for a collection, checking multiple sources:
        1. In-memory cache
        2. Database
        3. Fetch from API (if not rate limited recently)
        """
        # Check in-memory cache first
        if policy_id in self.collection_cache:
            return self.collection_cache[policy_id].get('floor_price_ada')

        # Check database
        db_price = await get_latest_nft_floor_price(policy_id)
        if db_price and db_price.get('floor_price_ada'):
            # Load into memory cache
            self.collection_cache[policy_id] = {
                'found': True,
                'name': db_price.get('collection_name', ''),
                'floor_price_ada': db_price.get('floor_price_ada'),
                'verified': bool(db_price.get('verified')),
                'source': db_price.get('source', 'database'),
                'cached_at': datetime.fromisoformat(db_price['fetched_at']) if db_price.get('fetched_at') else datetime.now(),
                'from_db': True
            }
            return db_price.get('floor_price_ada')

        return None


# Singleton instance
nft_service = NFTService()
