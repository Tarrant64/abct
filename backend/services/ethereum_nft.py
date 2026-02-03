"""
Ethereum NFT Service - Fetches Ethereum NFTs using Alchemy API.

Alchemy NFT API provides:
- NFT ownership data
- Collection metadata
- Floor prices
- Spam filtering

Uses persistent database caching to reduce API calls and survive restarts.
"""

import httpx
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ALCHEMY_BASE_URL
from database import get_all_wallets, get_cache, set_cache
from services.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

# Cache settings
ETH_NFT_CACHE_KEY = "eth_nft_all_data"
ETH_NFT_CACHE_TTL = 86400 * 30  # 30 days - persistent until manual refresh


class EthereumNFTService(APIKeyManager):
    """Service for fetching Ethereum NFTs from Alchemy API."""

    def __init__(self):
        super().__init__(api_name='alchemy', env_var='ALCHEMY_API_KEY')
        self.base_url = ALCHEMY_BASE_URL
        self._nft_cache: Dict[str, dict] = {}
        self._collection_cache: Dict[str, dict] = {}  # contract_address -> collection data
        self._cache_ttl = timedelta(hours=24)  # In-memory cache validity
        self.last_refresh: Optional[datetime] = None
        self._db_cache_loaded = False  # Track if we've loaded from DB cache

    async def is_configured(self) -> bool:
        """Check if the API key is configured."""
        key = await self.get_api_key()
        return bool(key)

    async def get_nfts_for_owner(self, address: str, page_key: str = None) -> Optional[dict]:
        """
        Fetch NFTs owned by an address using Alchemy getNFTsForOwner.

        Args:
            address: Ethereum wallet address
            page_key: Optional pagination key for fetching more results

        Returns:
            Dictionary with NFTs and pagination info
        """
        if not await self.is_configured():
            logger.warning("Alchemy API key not configured")
            return None

        api_key = await self.get_api_key()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {
                    'owner': address,
                    'withMetadata': 'true',
                    'excludeFilters[]': 'SPAM',
                    'pageSize': 100
                }

                if page_key:
                    params['pageKey'] = page_key

                response = await client.get(
                    f"{self.base_url}/{api_key}/getNFTsForOwner",
                    params=params
                )

                if response.status_code != 200:
                    logger.error(f"Alchemy API error: {response.status_code} - {response.text}")
                    return None

                data = response.json()
                return data

        except Exception as e:
            logger.error(f"Error fetching Ethereum NFTs: {e}")
            return None

    def _parse_nft(self, nft_data: dict, wallet_address: str) -> dict:
        """
        Parse Alchemy NFT response into standard format.

        Args:
            nft_data: Raw NFT data from Alchemy
            wallet_address: Owner's wallet address

        Returns:
            Standardized NFT dictionary
        """
        contract = nft_data.get('contract', {})
        token_id = nft_data.get('tokenId', '')
        contract_address = contract.get('address', '')

        # Get NFT name
        name = nft_data.get('name') or nft_data.get('title') or f"Token #{token_id}"

        # Get collection info
        collection = contract.get('openSeaMetadata', {})
        collection_name = collection.get('collectionName') or contract.get('name', 'Unknown Collection')
        floor_price_eth = collection.get('floorPrice', 0)

        # Get image
        image = nft_data.get('image', {})
        image_url = image.get('cachedUrl') or image.get('originalUrl') or image.get('pngUrl', '')

        # Build links
        opensea_url = f"https://opensea.io/assets/ethereum/{contract_address}/{token_id}"
        etherscan_url = f"https://etherscan.io/nft/{contract_address}/{token_id}"

        return {
            'asset_id': f"{contract_address}_{token_id}",
            'contract_address': contract_address,
            'token_id': token_id,
            'name': name,
            'image_url': image_url,
            'collection': {
                'name': collection_name,
                'floor_price_eth': floor_price_eth,
                'verified': collection.get('safelistRequestStatus') == 'verified',
                'description': collection.get('description', ''),
                'image_url': collection.get('imageUrl', '')
            },
            'links': {
                'opensea': opensea_url,
                'etherscan': etherscan_url
            },
            'blockchain': 'ethereum',
            'wallet_address': wallet_address,
            'token_type': contract.get('tokenType', 'ERC721')
        }

    async def get_all_ethereum_nfts(self, user_id: int = None, force_refresh: bool = False) -> List[dict]:
        """
        Fetch all NFTs for all Ethereum wallets.
        Uses persistent database cache that survives server restarts.

        Args:
            force_refresh: Force refresh from API, ignoring cache

        Returns:
            List of all NFTs across all Ethereum wallets
        """
        # Try to load from persistent database cache first
        if not force_refresh and not self._db_cache_loaded:
            cached_data = await get_cache(ETH_NFT_CACHE_KEY)
            if cached_data:
                logger.info(f"Loaded {len(cached_data.get('nfts', []))} Ethereum NFTs from persistent cache")
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
            logger.warning("Alchemy API key not configured")
            return []

        # Get all Ethereum wallets
        wallets = await get_all_wallets(user_id=user_id)
        eth_wallets = [w for w in wallets if w['blockchain'] == 'ethereum']

        if not eth_wallets:
            logger.info("No Ethereum wallets found")
            return []

        all_nfts = []
        self._nft_cache.clear()

        for wallet in eth_wallets:
            address = wallet['address']
            page_key = None

            while True:
                data = await self.get_nfts_for_owner(address, page_key)

                if not data:
                    break

                owned_nfts = data.get('ownedNfts', [])

                for nft_data in owned_nfts:
                    parsed_nft = self._parse_nft(nft_data, address)
                    all_nfts.append(parsed_nft)
                    self._nft_cache[parsed_nft['asset_id']] = parsed_nft

                    # Cache collection data
                    contract_address = parsed_nft['contract_address']
                    if contract_address not in self._collection_cache:
                        self._collection_cache[contract_address] = {
                            'name': parsed_nft['collection']['name'],
                            'floor_price_eth': parsed_nft['collection']['floor_price_eth'],
                            'verified': parsed_nft['collection']['verified'],
                            'cached_at': datetime.now().isoformat()
                        }

                # Check for more pages
                page_key = data.get('pageKey')
                if not page_key:
                    break

            logger.info(f"Fetched {len(all_nfts)} NFTs for {address[:10]}...")

        self.last_refresh = datetime.now()

        # Save to persistent database cache
        await self._save_to_db_cache()

        return all_nfts

    async def _save_to_db_cache(self) -> None:
        """Save Ethereum NFT data to persistent database cache."""
        try:
            cache_data = {
                'nfts': list(self._nft_cache.values()),
                'collections': self._collection_cache,
                'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None
            }
            await set_cache(ETH_NFT_CACHE_KEY, cache_data, ETH_NFT_CACHE_TTL)
            logger.info(f"Saved {len(self._nft_cache)} Ethereum NFTs to persistent cache")
        except Exception as e:
            logger.error(f"Error saving Ethereum NFT cache to database: {e}")

    async def get_nft_summary(self, user_id: int = None) -> dict:
        """
        Get a summary of all Ethereum NFTs grouped by collection.

        Returns:
            Dictionary with collection summaries and totals
        """
        all_nfts = await self.get_all_ethereum_nfts(user_id=user_id)

        # Group by collection
        collections = {}
        total_value_eth = 0.0

        for nft in all_nfts:
            collection_name = nft['collection']['name']

            if collection_name not in collections:
                collections[collection_name] = {
                    'name': collection_name,
                    'contract_address': nft['contract_address'],
                    'floor_price_eth': nft['collection']['floor_price_eth'],
                    'verified': nft['collection']['verified'],
                    'nft_count': 0,
                    'total_value_eth': 0.0,
                    'nfts': []
                }

            collections[collection_name]['nft_count'] += 1
            floor_price = nft['collection'].get('floor_price_eth', 0) or 0
            collections[collection_name]['total_value_eth'] += floor_price
            total_value_eth += floor_price
            collections[collection_name]['nfts'].append({
                'name': nft['name'],
                'token_id': nft['token_id'],
                'image_url': nft['image_url'],
                'links': nft['links']
            })

        return {
            'collections': list(collections.values()),
            'total_collections': len(collections),
            'total_nfts': len(all_nfts),
            'total_value_eth': total_value_eth,
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
        collections_with_floor = sum(
            1 for c in self._collection_cache.values()
            if c.get('floor_price_eth') and c['floor_price_eth'] > 0
        )
        return {
            'configured': await self.is_configured(),
            'cached_nfts': len(self._nft_cache),
            'cached_collections': len(self._collection_cache),
            'collections_with_floor_price': collections_with_floor,
            'cache_ttl_hours': self._cache_ttl.total_seconds() / 3600,
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'db_cache_loaded': self._db_cache_loaded
        }


# Singleton instance
ethereum_nft_service = EthereumNFTService()
