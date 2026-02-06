"""
Base Service - Fetches Base blockchain wallet data using Alchemy API.

Alchemy API provides:
- ETH balance (Base uses ETH as native token)
- ERC-20 token balances
- NFT holdings

Uses persistent database caching to reduce API calls and survive restarts.
"""

import httpx
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ALCHEMY_BASE_URL_CHAIN
from services.api_key_manager import APIKeyManager
from database import get_cache, set_cache
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Wei per ETH
WEI_PER_ETH = 10**18

# Cache settings
BASE_CACHE_KEY = "base_wallet_data"
BASE_NFT_CACHE_KEY = "base_nft_all_data"
BASE_CACHE_TTL = 86400 * 30  # 30 days


class BaseService(APIKeyManager):
    """Service for fetching Base blockchain wallet data from Alchemy API with public RPC fallback."""

    PUBLIC_RPC_URL = "https://base-rpc.publicnode.com"

    # Whitelist of legitimate Base NFT patterns (case-insensitive)
    # These are known legitimate NFT projects on Base
    ALLOWED_NFT_PATTERNS = [
        'book.io',      # Book.io digital books
        'dummies',      # "For Dummies" book series
        'mysterious island',  # Jules Verne book
        'ape$h!t',      # Book title
        'apeshit',      # Book title variant
    ]

    # Blacklist patterns for common scam NFTs
    SCAM_PATTERNS = [
        'airdrop',
        'claim',
        'voucher',
        'free eth',
        'free usd',
        'pancakeswap',
        'cakesv4',
        'steth',
        'lido',
        'daonext',
        'boxdao',
        'ethereum-event',
        't.ly/',
        'claim your',
        'redeem',
    ]

    def __init__(self):
        super().__init__(api_name='alchemy', env_var='ALCHEMY_API_KEY')
        self.base_url = ALCHEMY_BASE_URL_CHAIN
        self._balance_cache: Dict[str, dict] = {}
        self._nft_cache: Dict[str, dict] = {}
        self._collection_cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._nft_cache_ttl = timedelta(hours=24)
        self.last_nft_refresh: Optional[datetime] = None
        self._db_cache_loaded = False

    async def _get_v2_url(self) -> str:
        """Get Alchemy v2 API URL with API key."""
        api_key = await self.get_api_key()
        if not api_key:
            return ""
        return f"{self.base_url}/v2/{api_key}"

    async def _get_nft_url(self) -> str:
        """Get Alchemy NFT API URL with API key."""
        api_key = await self.get_api_key()
        if not api_key:
            return ""
        return f"{self.base_url}/nft/v3/{api_key}"

    def _is_allowed_nft(self, name: str, collection_name: str, description: str = '') -> bool:
        """
        Check if an NFT should be shown based on whitelist patterns.

        Args:
            name: NFT name
            collection_name: Collection name
            description: NFT description

        Returns:
            True if the NFT should be shown, False if it should be hidden
        """
        text_to_check = f"{name} {collection_name} {description}".lower()

        # First check if it matches any scam patterns
        for pattern in self.SCAM_PATTERNS:
            if pattern in text_to_check:
                return False

        # Then check if it matches any allowed patterns
        for pattern in self.ALLOWED_NFT_PATTERNS:
            if pattern in text_to_check:
                return True

        # By default, don't show unknown NFTs (they're likely scams on Base)
        return False

    async def is_configured(self) -> bool:
        """Check if the API key is configured."""
        key = await self.get_api_key()
        return bool(key)

    def is_base_address(self, address: str) -> bool:
        """Check if an address could be a Base address (same format as Ethereum)."""
        if not address:
            return False
        # Base addresses are the same format as Ethereum: 0x + 40 hex chars
        if not address.startswith('0x'):
            return False
        if len(address) != 42:
            return False
        try:
            int(address[2:], 16)
            return True
        except ValueError:
            return False

    async def get_eth_balance(self, address: str) -> Optional[float]:
        """
        Get ETH balance for an address on Base.

        Args:
            address: Base wallet address

        Returns:
            ETH balance as float, or None if error
        """
        if not await self.is_configured():
            logger.warning("Alchemy API key not configured")
            return None

        try:
            client = get_client("alchemy", timeout=30.0)
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_getBalance",
                "params": [address, "latest"]
            }

            response = await client.post(
                await self._get_v2_url(),
                json=payload
            )

            if response.status_code != 200:
                logger.error(f"Alchemy Base API error: {response.status_code}")
                return None

            data = response.json()

            if "error" in data:
                logger.error(f"Alchemy Base API error: {data['error']}")
                return None

            # Convert hex wei to ETH
            balance_wei = int(data.get("result", "0x0"), 16)
            balance_eth = balance_wei / WEI_PER_ETH

            return balance_eth

        except Exception as e:
            logger.error(f"Error fetching Base balance: {e}")
            return None

    async def get_token_balances(self, address: str) -> List[dict]:
        """
        Get ERC-20 token balances for an address on Base.

        Args:
            address: Base wallet address

        Returns:
            List of token balances with metadata
        """
        if not await self.is_configured():
            logger.warning("Alchemy API key not configured")
            return []

        try:
            client = get_client("alchemy", timeout=30.0)
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "alchemy_getTokenBalances",
                "params": [address, "erc20"]
            }

            response = await client.post(
                await self._get_v2_url(),
                json=payload
            )

            if response.status_code != 200:
                logger.error(f"Alchemy Base token API error: {response.status_code}")
                return []

            data = response.json()

            if "error" in data:
                logger.error(f"Alchemy Base token API error: {data['error']}")
                return []

            result = data.get("result", {})
            token_balances = result.get("tokenBalances", [])

            # Filter out zero balances and fetch metadata
            tokens = []
            for tb in token_balances:
                balance_hex = tb.get("tokenBalance", "0x0")
                if balance_hex == "0x0" or balance_hex == "0x":
                    continue

                contract_address = tb.get("contractAddress", "")
                balance_raw = int(balance_hex, 16)

                # Get token metadata
                metadata = await self._get_token_metadata(client, contract_address)

                decimals = metadata.get("decimals", 18)
                balance = balance_raw / (10 ** decimals)

                if balance > 0:
                    tokens.append({
                        "contract_address": contract_address,
                        "symbol": metadata.get("symbol", "UNKNOWN"),
                        "name": metadata.get("name", "Unknown Token"),
                        "decimals": decimals,
                        "balance": balance,
                        "balance_raw": balance_raw,
                        "logo": metadata.get("logo", "")
                    })

            return tokens

        except Exception as e:
            logger.error(f"Error fetching Base token balances: {e}")
            return []

    async def _get_token_metadata(self, client: httpx.AsyncClient, contract_address: str) -> dict:
        """Get metadata for a token contract."""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "alchemy_getTokenMetadata",
                "params": [contract_address]
            }

            response = await client.post(
                await self._get_v2_url(),
                json=payload
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("result", {})

        except Exception as e:
            logger.debug(f"Error fetching token metadata: {e}")

        return {}

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get complete address info including ETH balance and tokens.

        Args:
            address: Base wallet address

        Returns:
            Dictionary with balance and token info
        """
        if not self.is_base_address(address):
            return None

        # Check cache
        if address in self._balance_cache:
            cached = self._balance_cache[address]
            if datetime.now() - cached['cached_at'] < self._cache_ttl:
                return cached['data']

        if not await self.is_configured():
            logger.info(f"Alchemy not configured for Base, using public RPC fallback for {address[:10]}")
            return await self.get_balance_from_public_rpc(address)

        # Fetch data from Alchemy
        eth_balance = await self.get_eth_balance(address)
        tokens = await self.get_token_balances(address)

        # If Alchemy failed, try public RPC for at least the native balance
        if eth_balance is None:
            logger.info(f"Alchemy failed for Base {address[:10]}, trying public RPC fallback")
            return await self.get_balance_from_public_rpc(address)

        result = {
            'address': address,
            'balance_eth': eth_balance or 0,
            'tokens': tokens,
            'token_count': len(tokens),
            'blockchain': 'base',
            'source': 'alchemy'
        }

        # Cache result
        self._balance_cache[address] = {
            'data': result,
            'cached_at': datetime.now()
        }

        return result

    async def get_balance_from_public_rpc(self, address: str) -> Optional[dict]:
        """
        Fallback method to get ETH balance on Base from public RPC.

        Only returns native ETH balance (no ERC-20 tokens).
        Used when Alchemy API is not configured or fails.
        """
        if not self.is_base_address(address):
            return None

        try:
            client = get_client("public_rpc_base", timeout=30.0)
            response = await client.post(
                self.PUBLIC_RPC_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_getBalance",
                    "params": [address, "latest"]
                }
            )

            if response.status_code != 200:
                logger.error(f"Base public RPC error: {response.status_code}")
                return None

            data = response.json()

            if 'error' in data:
                logger.error(f"Base public RPC error: {data['error']}")
                return None

            balance_wei = int(data.get('result', '0x0'), 16)
            balance_eth = balance_wei / WEI_PER_ETH

            result = {
                'address': address,
                'balance_eth': balance_eth,
                'tokens': [],
                'token_count': 0,
                'blockchain': 'base',
                'source': 'public_rpc'
            }

            logger.info(f"Fetched Base ETH balance from public RPC: {balance_eth:.6f} ETH")

            self._balance_cache[address] = {
                'data': result,
                'cached_at': datetime.now()
            }

            return result

        except Exception as e:
            logger.error(f"Error fetching Base balance from public RPC: {e}")
            return None

    async def get_nfts_for_owner(self, address: str, page_key: str = None) -> Optional[dict]:
        """
        Fetch NFTs owned by an address on Base using Alchemy getNFTsForOwner.

        Args:
            address: Base wallet address
            page_key: Optional pagination key

        Returns:
            Dictionary with NFTs and pagination info
        """
        if not await self.is_configured():
            logger.warning("Alchemy API key not configured")
            return None

        try:
            client = get_client("alchemy", timeout=30.0)
            params = {
                'owner': address,
                'withMetadata': 'true',
                'excludeFilters[]': 'SPAM',
                'pageSize': 100
            }

            if page_key:
                params['pageKey'] = page_key

            response = await client.get(
                f"{await self._get_nft_url()}/getNFTsForOwner",
                params=params
            )

            if response.status_code != 200:
                logger.error(f"Alchemy Base NFT API error: {response.status_code}")
                return None

            return response.json()

        except Exception as e:
            logger.error(f"Error fetching Base NFTs: {e}")
            return None

    def _parse_nft(self, nft_data: dict, wallet_address: str) -> Optional[dict]:
        """
        Parse Alchemy NFT response into standard format.

        Args:
            nft_data: Raw NFT data from Alchemy
            wallet_address: Owner's wallet address

        Returns:
            Standardized NFT dictionary, or None if NFT should be filtered out
        """
        contract = nft_data.get('contract', {})
        token_id = nft_data.get('tokenId', '')
        contract_address = contract.get('address', '')

        # Get NFT name
        name = nft_data.get('name') or nft_data.get('title') or f"Token #{token_id}"

        # Get collection info
        collection = contract.get('openSeaMetadata', {})
        collection_name = collection.get('collectionName') or contract.get('name', 'Unknown Collection')
        floor_price = collection.get('floorPrice', 0)  # Floor price in ETH for Base

        # Get description for spam filtering
        description = nft_data.get('description', '')

        # Filter out spam/scam NFTs
        if not self._is_allowed_nft(name, collection_name, description):
            logger.debug(f"Filtering out NFT: {name} from {collection_name}")
            return None

        # Get image
        image = nft_data.get('image', {})
        image_url = image.get('cachedUrl') or image.get('originalUrl') or image.get('pngUrl', '')

        # Build links
        opensea_url = f"https://opensea.io/assets/base/{contract_address}/{token_id}"
        basescan_url = f"https://basescan.org/nft/{contract_address}/{token_id}"

        return {
            'asset_id': f"{contract_address}_{token_id}",
            'contract_address': contract_address,
            'token_id': token_id,
            'name': name,
            'image_url': image_url,
            'collection': {
                'name': collection_name,
                'floor_price_eth': floor_price,
                'verified': collection.get('safelistRequestStatus') == 'verified',
                'description': collection.get('description', ''),
                'image_url': collection.get('imageUrl', '')
            },
            'links': {
                'opensea': opensea_url,
                'basescan': basescan_url
            },
            'blockchain': 'base',
            'wallet_address': wallet_address,
            'token_type': contract.get('tokenType', 'ERC721')
        }

    async def get_all_base_nfts(self, wallets: List[dict], force_refresh: bool = False) -> List[dict]:
        """
        Fetch all NFTs for all Base wallets.

        Args:
            wallets: List of Base wallet dictionaries
            force_refresh: Force refresh from API

        Returns:
            List of all NFTs
        """
        # Try to load from persistent database cache first
        if not force_refresh and not self._db_cache_loaded:
            cached_data = await get_cache(BASE_NFT_CACHE_KEY)
            if cached_data:
                logger.info(f"Loaded {len(cached_data.get('nfts', []))} Base NFTs from persistent cache")
                self._nft_cache = {nft['asset_id']: nft for nft in cached_data.get('nfts', [])}
                self._collection_cache = cached_data.get('collections', {})
                self.last_nft_refresh = datetime.fromisoformat(cached_data['last_refresh']) if cached_data.get('last_refresh') else None
                self._db_cache_loaded = True
                return list(self._nft_cache.values())
            self._db_cache_loaded = True

        # Check in-memory cache validity
        if not force_refresh and self._is_nft_cache_valid():
            return list(self._nft_cache.values())

        if not await self.is_configured():
            logger.warning("Alchemy API key not configured")
            return []

        if not wallets:
            logger.info("No Base wallets provided")
            return []

        all_nfts = []
        self._nft_cache.clear()

        for wallet in wallets:
            address = wallet['address']
            page_key = None

            while True:
                data = await self.get_nfts_for_owner(address, page_key)

                if not data:
                    break

                owned_nfts = data.get('ownedNfts', [])

                for nft_data in owned_nfts:
                    parsed_nft = self._parse_nft(nft_data, address)
                    # Skip filtered NFTs (spam/scam)
                    if parsed_nft is None:
                        continue

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

            logger.info(f"Fetched {len(all_nfts)} NFTs for Base wallet {address[:10]}...")

        self.last_nft_refresh = datetime.now()

        # Save to persistent database cache
        await self._save_nft_cache()

        return all_nfts

    async def _save_nft_cache(self) -> None:
        """Save Base NFT data to persistent database cache."""
        try:
            cache_data = {
                'nfts': list(self._nft_cache.values()),
                'collections': self._collection_cache,
                'last_refresh': self.last_nft_refresh.isoformat() if self.last_nft_refresh else None
            }
            await set_cache(BASE_NFT_CACHE_KEY, cache_data, BASE_CACHE_TTL)
            logger.info(f"Saved {len(self._nft_cache)} Base NFTs to persistent cache")
        except Exception as e:
            logger.error(f"Error saving Base NFT cache: {e}")

    async def get_nft_summary(self, wallets: List[dict]) -> dict:
        """
        Get a summary of all Base NFTs grouped by collection.

        Args:
            wallets: List of Base wallet dictionaries

        Returns:
            Dictionary with collection summaries
        """
        all_nfts = await self.get_all_base_nfts(wallets)

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
            'last_updated': self.last_nft_refresh.isoformat() if self.last_nft_refresh else None
        }

    def _is_nft_cache_valid(self) -> bool:
        """Check if the NFT cache is still valid."""
        if not self.last_nft_refresh:
            return False
        return datetime.now() - self.last_nft_refresh < self._nft_cache_ttl

    def clear_cache(self):
        """Clear all caches."""
        self._balance_cache.clear()
        self._nft_cache.clear()
        self._collection_cache.clear()
        self.last_nft_refresh = None
        self._db_cache_loaded = False

    def get_status(self) -> dict:
        """Get service status."""
        return {
            'configured': self.is_configured(),
            'cached_balances': len(self._balance_cache),
            'cached_nfts': len(self._nft_cache),
            'cached_collections': len(self._collection_cache),
            'last_nft_refresh': self.last_nft_refresh.isoformat() if self.last_nft_refresh else None
        }


# Singleton instance
base_service = BaseService()
