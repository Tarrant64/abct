"""
Solana NFT Service - Fetches Solana NFTs using Helius DAS API.

Helius Digital Asset Standard (DAS) API provides:
- NFT ownership data via getAssetsByOwner
- Collection metadata
- Compressed NFT (cNFT) support
- Includes Helium hotspots and other Solana NFTs

Uses persistent database caching to reduce API calls and survive restarts.
"""

import httpx
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import HELIUS_RPC_URL
from database import get_all_wallets, get_cache, set_cache
from services.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

# Cache settings
SOL_NFT_CACHE_KEY = "sol_nft_all_data"
SOL_NFT_CACHE_TTL = 86400 * 30  # 30 days - persistent until manual refresh


class SolanaNFTService(APIKeyManager):
    """Service for fetching Solana NFTs from Helius DAS API."""

    def __init__(self):
        super().__init__(api_name='helius', env_var='HELIUS_API_KEY')
        self.rpc_url = HELIUS_RPC_URL
        self._nft_cache: Dict[str, dict] = {}
        self._collection_cache: Dict[str, dict] = {}  # collection_id -> collection data
        self._cache_ttl = timedelta(hours=24)  # In-memory cache validity
        self.last_refresh: Optional[datetime] = None
        self._db_cache_loaded = False

    async def is_configured(self) -> bool:
        """Check if the API key is configured."""
        key = await self.get_api_key()
        return bool(key)

    async def get_assets_by_owner(self, address: str, page: int = 1) -> Optional[dict]:
        """
        Fetch NFTs owned by an address using Helius DAS API (getAssetsByOwner).

        Args:
            address: Solana wallet address
            page: Page number (1-based)

        Returns:
            Dictionary with NFT assets and pagination info
        """
        if not await self.is_configured():
            logger.warning("Helius API key not configured")
            return None

        api_key = await self.get_api_key()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "jsonrpc": "2.0",
                    "id": f"get-assets-{address}-{page}",
                    "method": "getAssetsByOwner",
                    "params": {
                        "ownerAddress": address,
                        "page": page,
                        "limit": 1000,
                        "displayOptions": {
                            "showFungible": False,
                            "showNativeBalance": False,
                            "showCollectionMetadata": True,
                            "showUnverifiedCollections": True
                        }
                    }
                }

                response = await client.post(
                    f"{self.rpc_url}/?api-key={api_key}",
                    json=payload
                )

                if response.status_code != 200:
                    logger.error(f"Helius DAS API error: {response.status_code} - {response.text}")
                    return None

                data = response.json()

                if "error" in data:
                    logger.error(f"Helius DAS API error: {data['error']}")
                    return None

                return data.get("result", {})

        except Exception as e:
            logger.error(f"Error fetching Solana NFTs: {e}")
            return None

    # Whitelist of legitimate Solana NFT patterns (case-insensitive)
    # Only NFTs matching these patterns will be shown
    ALLOWED_NFT_PATTERNS = [
        'midas',       # Midas hotspot maker
        'bobcat',      # Bobcat hotspot maker
        'rak',         # RAKWireless hotspot maker
        'rakwireless', # RAKWireless full name
        'helium',      # General Helium NFTs
        'hotspot',     # Hotspot NFTs
    ]

    def _is_allowed_nft(self, name: str, collection_name: str, symbol: str) -> bool:
        """
        Check if an NFT should be shown based on whitelist patterns.
        Filters out spam/junk NFTs on Solana.
        """
        # Combine all text to check
        text_to_check = f"{name} {collection_name} {symbol}".lower()

        # Check if any allowed pattern matches
        for pattern in self.ALLOWED_NFT_PATTERNS:
            if pattern in text_to_check:
                return True
        return False

    def _parse_nft(self, asset_data: dict, wallet_address: str) -> Optional[dict]:
        """
        Parse Helius DAS asset response into standard format.

        Args:
            asset_data: Raw asset data from Helius
            wallet_address: Owner's wallet address

        Returns:
            Standardized NFT dictionary or None if not an NFT or if filtered as spam
        """
        # Skip fungible tokens
        interface = asset_data.get("interface", "")
        if interface in ["FungibleToken", "FungibleAsset"]:
            return None

        asset_id = asset_data.get("id", "")
        content = asset_data.get("content", {})
        metadata = content.get("metadata", {})

        # Get NFT name
        name = metadata.get("name", "") or f"Solana NFT #{asset_id[:8]}"

        # Get symbol for filtering
        symbol = metadata.get("symbol", "")

        # Get image from files or links
        files = content.get("files", [])
        links = content.get("links", {})
        image_url = ""

        if files:
            # Prefer CDN URI (Helius CDN caches Shadow Drive and avoids timeouts)
            for f in files:
                if f.get("cdn_uri"):
                    image_url = f["cdn_uri"]
                    break
                elif f.get("uri"):
                    image_url = f["uri"]
                    break

        if not image_url:
            image_url = links.get("image", "") or links.get("animation_url", "")

        # Get collection info from grouping
        grouping = asset_data.get("grouping", [])
        collection_id = ""
        collection_name = "Unknown Collection"

        for group in grouping:
            if group.get("group_key") == "collection":
                collection_id = group.get("group_value", "")
                # Collection metadata might be in collection_metadata field
                collection_meta = group.get("collection_metadata", {})
                if collection_meta:
                    collection_name = collection_meta.get("name", collection_name)
                break

        # If no collection name from grouping, use symbol or first creator
        if collection_name == "Unknown Collection":
            if symbol:
                collection_name = symbol
            else:
                creators = asset_data.get("creators", [])
                if creators:
                    collection_name = f"By {creators[0].get('address', '')[:8]}..."

        # Check for Helium-specific NFTs and set proper collection name
        if "helium" in name.lower() or "hotspot" in name.lower():
            collection_name = "Helium Hotspots"
        elif "iot" in name.lower() and "operations" in name.lower():
            collection_name = "Helium IOT Operations"
        elif "mobile" in name.lower() and "operations" in name.lower():
            collection_name = "Helium MOBILE Operations"

        # Filter out spam/junk NFTs - only show whitelisted patterns
        if not self._is_allowed_nft(name, collection_name, symbol):
            return None

        # Get attributes
        attributes = metadata.get("attributes", [])

        # Build explorer links
        solscan_url = f"https://solscan.io/token/{asset_id}"
        magiceden_url = f"https://magiceden.io/item-details/{asset_id}"

        # Get royalty info
        royalty = asset_data.get("royalty", {})
        royalty_percent = royalty.get("percent", 0)

        # Check if compressed NFT
        compression = asset_data.get("compression", {})
        is_compressed = compression.get("compressed", False)

        return {
            "asset_id": asset_id,
            "name": name,
            "description": metadata.get("description", ""),
            "image_url": image_url,
            "collection": {
                "id": collection_id,
                "name": collection_name,
                "floor_price_sol": None,  # Floor price would need separate API call
                "verified": False
            },
            "attributes": attributes,
            "links": {
                "solscan": solscan_url,
                "magiceden": magiceden_url
            },
            "blockchain": "solana",
            "wallet_address": wallet_address,
            "interface": interface,
            "is_compressed": is_compressed,
            "royalty_percent": royalty_percent * 100 if royalty_percent < 1 else royalty_percent
        }

    async def get_all_solana_nfts(self, user_id: int = None, force_refresh: bool = False) -> List[dict]:
        """
        Fetch all NFTs for all Solana wallets.
        Uses persistent database cache that survives server restarts.

        Args:
            force_refresh: Force refresh from API, ignoring cache

        Returns:
            List of all NFTs across all Solana wallets
        """
        # Try to load from persistent database cache first
        if not force_refresh and not self._db_cache_loaded:
            cached_data = await get_cache(SOL_NFT_CACHE_KEY)
            if cached_data:
                logger.info(f"Loaded {len(cached_data.get('nfts', []))} Solana NFTs from persistent cache")
                self._nft_cache = {nft['asset_id']: nft for nft in cached_data.get('nfts', [])}
                self._collection_cache = cached_data.get('collections', {})
                self.last_refresh = datetime.fromisoformat(cached_data['last_refresh']) if cached_data.get('last_refresh') else None
                self._db_cache_loaded = True
                return list(self._nft_cache.values())
            self._db_cache_loaded = True

        # Check in-memory cache validity
        if not force_refresh and self._is_cache_valid():
            return list(self._nft_cache.values())

        if not await self.is_configured():
            logger.warning("Helius API key not configured")
            return []

        # Get all Solana wallets
        wallets = await get_all_wallets(user_id=user_id)
        sol_wallets = [w for w in wallets if w['blockchain'] == 'solana']

        if not sol_wallets:
            logger.info("No Solana wallets found")
            return []

        all_nfts = []
        self._nft_cache.clear()

        for wallet in sol_wallets:
            address = wallet['address']
            page = 1
            total_fetched = 0

            while True:
                result = await self.get_assets_by_owner(address, page)

                if not result:
                    break

                items = result.get("items", [])
                total = result.get("total", 0)

                for asset_data in items:
                    parsed_nft = self._parse_nft(asset_data, address)
                    if parsed_nft:
                        all_nfts.append(parsed_nft)
                        self._nft_cache[parsed_nft['asset_id']] = parsed_nft

                        # Cache collection data
                        collection_id = parsed_nft['collection']['id']
                        if collection_id and collection_id not in self._collection_cache:
                            self._collection_cache[collection_id] = {
                                'name': parsed_nft['collection']['name'],
                                'floor_price_sol': parsed_nft['collection']['floor_price_sol'],
                                'cached_at': datetime.now().isoformat()
                            }

                total_fetched += len(items)

                # Check if there are more pages
                if total_fetched >= total or len(items) == 0:
                    break

                page += 1

            logger.info(f"Fetched {total_fetched} NFTs for Solana wallet {address[:8]}...")

        self.last_refresh = datetime.now()

        # Save to persistent database cache
        await self._save_to_db_cache()

        return all_nfts

    async def _save_to_db_cache(self) -> None:
        """Save Solana NFT data to persistent database cache."""
        try:
            cache_data = {
                'nfts': list(self._nft_cache.values()),
                'collections': self._collection_cache,
                'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None
            }
            await set_cache(SOL_NFT_CACHE_KEY, cache_data, SOL_NFT_CACHE_TTL)
            logger.info(f"Saved {len(self._nft_cache)} Solana NFTs to persistent cache")
        except Exception as e:
            logger.error(f"Error saving Solana NFT cache to database: {e}")

    async def get_nft_summary(self, user_id: int = None) -> dict:
        """
        Get a summary of all Solana NFTs grouped by collection.

        Returns:
            Dictionary with collection summaries and totals
        """
        all_nfts = await self.get_all_solana_nfts(user_id=user_id)

        # Group by collection
        collections = {}
        total_value_sol = 0.0

        for nft in all_nfts:
            collection_name = nft['collection']['name']

            if collection_name not in collections:
                collections[collection_name] = {
                    'name': collection_name,
                    'collection_id': nft['collection']['id'],
                    'floor_price_sol': nft['collection']['floor_price_sol'],
                    'nft_count': 0,
                    'total_value_sol': 0.0,
                    'nfts': []
                }

            collections[collection_name]['nft_count'] += 1
            floor_price = nft['collection'].get('floor_price_sol') or 0
            collections[collection_name]['total_value_sol'] += floor_price
            total_value_sol += floor_price
            collections[collection_name]['nfts'].append({
                'name': nft['name'],
                'asset_id': nft['asset_id'],
                'image_url': nft['image_url'],
                'links': nft['links'],
                'is_compressed': nft.get('is_compressed', False)
            })

        return {
            'collections': list(collections.values()),
            'total_collections': len(collections),
            'total_nfts': len(all_nfts),
            'total_value_sol': total_value_sol,
            'last_updated': self.last_refresh.isoformat() if self.last_refresh else None
        }

    def _is_cache_valid(self) -> bool:
        """Check if the in-memory NFT cache is still valid."""
        if not self.last_refresh:
            return False
        return datetime.now() - self.last_refresh < self._cache_ttl

    def clear_cache(self):
        """Clear all caches (in-memory and forces DB reload on next fetch)."""
        self._nft_cache.clear()
        self._collection_cache.clear()
        self.last_refresh = None
        self._db_cache_loaded = False

    async def get_status(self) -> dict:
        """Get service status and configuration."""
        return {
            'configured': await self.is_configured(),
            'cached_nfts': len(self._nft_cache),
            'cached_collections': len(self._collection_cache),
            'cache_ttl_hours': self._cache_ttl.total_seconds() / 3600,
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'db_cache_loaded': self._db_cache_loaded
        }


# Singleton instance
solana_nft_service = SolanaNFTService()
