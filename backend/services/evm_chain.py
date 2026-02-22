"""
Generic EVM Chain Service - Fetches wallet data for EVM-compatible chains using Alchemy API.

Supports BNB Smart Chain (BSC), Arbitrum One, and Avalanche C-Chain.
Uses the same Alchemy API key as Ethereum/Polygon/Base.

Each chain instance provides:
- Native token balance
- ERC-20 token balances
- NFT holdings
- Public RPC fallback for native balance

Uses persistent database caching to reduce API calls and survive restarts.
"""

import httpx
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_cache, set_cache
from services.api_key_manager import APIKeyManager
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Wei per native token (same as ETH for all EVM chains)
WEI_PER_TOKEN = 10**18

# Chain configurations
EVM_CHAINS = {
    'bsc': {
        'name': 'BNB Smart Chain',
        'alchemy_base': 'https://bnb-mainnet.g.alchemy.com',
        'public_rpc': 'https://bsc-dataseed.binance.org/',
        'native_symbol': 'BNB',
        'balance_key': 'balance_bnb',
        'opensea_chain': 'bsc',
        'explorer_base': 'https://bscscan.com',
        'explorer_name': 'BscScan',
    },
    'arbitrum': {
        'name': 'Arbitrum One',
        'alchemy_base': 'https://arb-mainnet.g.alchemy.com',
        'public_rpc': 'https://arb1.arbitrum.io/rpc',
        'native_symbol': 'ETH',
        'balance_key': 'balance_eth',
        'opensea_chain': 'arbitrum',
        'explorer_base': 'https://arbiscan.io',
        'explorer_name': 'Arbiscan',
    },
    'avalanche': {
        'name': 'Avalanche C-Chain',
        'alchemy_base': 'https://avax-mainnet.g.alchemy.com',
        'public_rpc': 'https://api.avax.network/ext/bc/C/rpc',
        'native_symbol': 'AVAX',
        'balance_key': 'balance_avax',
        'opensea_chain': 'avalanche',
        'explorer_base': 'https://snowscan.xyz',
        'explorer_name': 'Snowscan',
    },
    'optimism': {
        'name': 'Optimism',
        'alchemy_base': 'https://opt-mainnet.g.alchemy.com',
        'public_rpc': 'https://mainnet.optimism.io',
        'native_symbol': 'ETH',
        'balance_key': 'balance_eth',
        'opensea_chain': 'optimism',
        'explorer_base': 'https://optimistic.etherscan.io',
        'explorer_name': 'Optimistic Etherscan',
    },
    'zksync': {
        'name': 'zkSync Era',
        'alchemy_base': 'https://zksync-mainnet.g.alchemy.com',
        'public_rpc': 'https://mainnet.era.zksync.io',
        'native_symbol': 'ETH',
        'balance_key': 'balance_eth',
        'opensea_chain': 'zksync',
        'explorer_base': 'https://explorer.zksync.io',
        'explorer_name': 'zkSync Explorer',
    },
    'linea': {
        'name': 'Linea',
        'alchemy_base': 'https://linea-mainnet.g.alchemy.com',
        'public_rpc': 'https://rpc.linea.build',
        'native_symbol': 'ETH',
        'balance_key': 'balance_eth',
        'opensea_chain': 'linea',
        'explorer_base': 'https://lineascan.build',
        'explorer_name': 'LineaScan',
    },
    'scroll': {
        'name': 'Scroll',
        'alchemy_base': 'https://scroll-mainnet.g.alchemy.com',
        'public_rpc': 'https://rpc.scroll.io',
        'native_symbol': 'ETH',
        'balance_key': 'balance_eth',
        'opensea_chain': 'scroll',
        'explorer_base': 'https://scrollscan.com',
        'explorer_name': 'Scrollscan',
    },
    'fantom': {
        'name': 'Fantom Opera',
        'alchemy_base': None,
        'public_rpc': 'https://rpc.ftm.tools',
        'native_symbol': 'FTM',
        'balance_key': 'balance_ftm',
        'opensea_chain': None,
        'explorer_base': 'https://ftmscan.com',
        'explorer_name': 'FtmScan',
    },
    'cronos': {
        'name': 'Cronos',
        'alchemy_base': None,
        'public_rpc': 'https://evm.cronos.org',
        'native_symbol': 'CRO',
        'balance_key': 'balance_cro',
        'opensea_chain': None,
        'explorer_base': 'https://cronoscan.com',
        'explorer_name': 'CronoScan',
    },
    'gnosis': {
        'name': 'Gnosis Chain',
        'alchemy_base': None,
        'public_rpc': 'https://rpc.gnosischain.com',
        'native_symbol': 'xDAI',
        'balance_key': 'balance_xdai',
        'opensea_chain': None,
        'explorer_base': 'https://gnosisscan.io',
        'explorer_name': 'GnosisScan',
    },
    'moonbeam': {
        'name': 'Moonbeam',
        'alchemy_base': None,
        'public_rpc': 'https://rpc.api.moonbeam.network',
        'native_symbol': 'GLMR',
        'balance_key': 'balance_glmr',
        'opensea_chain': None,
        'explorer_base': 'https://moonbeam.moonscan.io',
        'explorer_name': 'Moonscan',
    },
    'kaia': {
        'name': 'Kaia',
        'alchemy_base': None,
        'public_rpc': 'https://public-en.node.kaia.io',
        'native_symbol': 'KLAY',
        'balance_key': 'balance_klay',
        'opensea_chain': None,
        'explorer_base': 'https://kaiascan.io',
        'explorer_name': 'KaiaScan',
    },
}


class EVMChainService(APIKeyManager):
    """Generic service for fetching EVM chain wallet data from Alchemy API with public RPC fallback."""

    def __init__(self, chain_name: str):
        super().__init__(api_name='alchemy', env_var='ALCHEMY_API_KEY')
        if chain_name not in EVM_CHAINS:
            raise ValueError(f"Unknown EVM chain: {chain_name}. Supported: {list(EVM_CHAINS.keys())}")

        self.chain_name = chain_name
        self.config = EVM_CHAINS[chain_name]
        self.base_url = self.config['alchemy_base']
        self.public_rpc_url = self.config['public_rpc']
        self.native_symbol = self.config['native_symbol']
        self.balance_key = self.config['balance_key']

        self._balance_cache: Dict[str, dict] = {}
        self._nft_cache: Dict[str, dict] = {}
        self._collection_cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._nft_cache_ttl = timedelta(hours=24)
        self.last_nft_refresh: Optional[datetime] = None
        self._db_cache_loaded = False

        # Cache keys for persistent DB cache
        self._wallet_cache_key = f"{chain_name}_wallet_data"
        self._nft_cache_key = f"{chain_name}_nft_all_data"
        self._nft_db_cache_ttl = 86400 * 30  # 30 days

    @property
    def has_alchemy(self) -> bool:
        """Whether this chain has Alchemy API support."""
        return self.base_url is not None

    async def _get_v2_url(self) -> str:
        """Get Alchemy v2 API URL with API key."""
        if not self.has_alchemy:
            return ""
        api_key = await self.get_api_key()
        if not api_key:
            return ""
        return f"{self.base_url}/v2/{api_key}"

    async def _get_nft_url(self) -> str:
        """Get Alchemy NFT API URL with API key."""
        if not self.has_alchemy:
            return ""
        api_key = await self.get_api_key()
        if not api_key:
            return ""
        return f"{self.base_url}/nft/v3/{api_key}"

    async def is_configured(self) -> bool:
        """Check if the API key is configured or public RPC is available."""
        if not self.has_alchemy:
            return bool(self.public_rpc_url)
        key = await self.get_api_key()
        return bool(key)

    def is_valid_address(self, address: str) -> bool:
        """Check if an address is a valid EVM address (0x + 40 hex chars)."""
        if not address:
            return False
        if not address.startswith('0x'):
            return False
        if len(address) != 42:
            return False
        try:
            int(address[2:], 16)
            return True
        except ValueError:
            return False

    async def _get_native_balance_public_rpc(self, address: str) -> Optional[float]:
        """Get native balance via public RPC (fallback for non-Alchemy chains)."""
        if not self.public_rpc_url:
            return None
        try:
            client = get_client(f"evm_{self.chain_name}", timeout=15.0)
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_getBalance",
                "params": [address, "latest"]
            }
            response = await client.post(self.public_rpc_url, json=payload)
            if response.status_code != 200:
                return None
            data = response.json()
            if "error" in data:
                return None
            balance_wei = int(data.get("result", "0x0"), 16)
            return balance_wei / WEI_PER_TOKEN
        except Exception as e:
            logger.error(f"Error fetching {self.config['name']} balance via public RPC: {e}")
            return None

    async def get_native_balance(self, address: str) -> Optional[float]:
        """
        Get native token balance for an address.

        Returns:
            Balance as float, or None if error
        """
        if not self.has_alchemy:
            return await self._get_native_balance_public_rpc(address)

        if not await self.is_configured():
            logger.warning(f"Alchemy API key not configured for {self.config['name']}")
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
                logger.error(f"Alchemy {self.config['name']} API error: {response.status_code}")
                return None

            data = response.json()

            if "error" in data:
                logger.error(f"Alchemy {self.config['name']} API error: {data['error']}")
                return None

            balance_wei = int(data.get("result", "0x0"), 16)
            balance = balance_wei / WEI_PER_TOKEN

            return balance

        except Exception as e:
            logger.error(f"Error fetching {self.config['name']} balance: {e}")
            return None

    async def get_token_balances(self, address: str) -> List[dict]:
        """
        Get ERC-20 token balances for an address.

        Returns:
            List of token balances with metadata
        """
        if not self.has_alchemy:
            return []
        if not await self.is_configured():
            logger.warning(f"Alchemy API key not configured for {self.config['name']}")
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
                logger.error(f"Alchemy {self.config['name']} token API error: {response.status_code}")
                return []

            data = response.json()

            if "error" in data:
                logger.error(f"Alchemy {self.config['name']} token API error: {data['error']}")
                return []

            result = data.get("result", {})
            token_balances = result.get("tokenBalances", [])

            tokens = []
            for tb in token_balances:
                balance_hex = tb.get("tokenBalance", "0x0")
                if balance_hex == "0x0" or balance_hex == "0x":
                    continue

                contract_address = tb.get("contractAddress", "")
                balance_raw = int(balance_hex, 16)

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
            logger.error(f"Error fetching {self.config['name']} token balances: {e}")
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
        Get complete address info including native balance and tokens.

        Returns:
            Dictionary with balance and token info
        """
        if not self.is_valid_address(address):
            return None

        # Check cache
        if address in self._balance_cache:
            cached = self._balance_cache[address]
            if datetime.now() - cached['cached_at'] < self._cache_ttl:
                return cached['data']

        if not await self.is_configured():
            logger.info(f"Alchemy not configured for {self.config['name']}, using public RPC fallback for {address[:10]}")
            return await self.get_balance_from_public_rpc(address)

        native_balance = await self.get_native_balance(address)
        tokens = await self.get_token_balances(address)

        if native_balance is None:
            logger.info(f"Alchemy failed for {self.config['name']} {address[:10]}, trying public RPC fallback")
            return await self.get_balance_from_public_rpc(address)

        result = {
            'address': address,
            self.balance_key: native_balance or 0,
            'tokens': tokens,
            'token_count': len(tokens),
            'blockchain': self.chain_name,
            'source': 'alchemy'
        }

        self._balance_cache[address] = {
            'data': result,
            'cached_at': datetime.now()
        }

        return result

    async def get_balance_from_public_rpc(self, address: str) -> Optional[dict]:
        """
        Fallback method to get native balance from public RPC.
        Only returns native balance (no ERC-20 tokens).
        """
        if not self.is_valid_address(address):
            return None

        try:
            client = get_client("alchemy", timeout=30.0)
            response = await client.post(
                self.public_rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_getBalance",
                    "params": [address, "latest"]
                }
            )

            if response.status_code != 200:
                logger.error(f"{self.config['name']} public RPC error: {response.status_code}")
                return None

            data = response.json()

            if 'error' in data:
                logger.error(f"{self.config['name']} public RPC error: {data['error']}")
                return None

            balance_wei = int(data.get('result', '0x0'), 16)
            balance = balance_wei / WEI_PER_TOKEN

            result = {
                'address': address,
                self.balance_key: balance,
                'tokens': [],
                'token_count': 0,
                'blockchain': self.chain_name,
                'source': 'public_rpc'
            }

            logger.info(f"Fetched {self.native_symbol} balance from public RPC: {balance:.6f} {self.native_symbol}")

            self._balance_cache[address] = {
                'data': result,
                'cached_at': datetime.now()
            }

            return result

        except Exception as e:
            logger.error(f"Error fetching {self.config['name']} balance from public RPC: {e}")
            return None

    async def get_nfts_for_owner(self, address: str, page_key: str = None) -> Optional[dict]:
        """
        Fetch NFTs owned by an address using Alchemy getNFTsForOwner.

        Returns:
            Dictionary with NFTs and pagination info
        """
        if not self.has_alchemy:
            return None
        if not await self.is_configured():
            logger.warning(f"Alchemy API key not configured for {self.config['name']}")
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
                logger.error(f"Alchemy {self.config['name']} NFT API error: {response.status_code}")
                return None

            return response.json()

        except Exception as e:
            logger.error(f"Error fetching {self.config['name']} NFTs: {e}")
            return None

    def _parse_nft(self, nft_data: dict, wallet_address: str) -> dict:
        """Parse Alchemy NFT response into standard format."""
        contract = nft_data.get('contract', {})
        token_id = nft_data.get('tokenId', '')
        contract_address = contract.get('address', '')

        name = nft_data.get('name') or nft_data.get('title') or f"Token #{token_id}"

        collection = contract.get('openSeaMetadata', {})
        collection_name = collection.get('collectionName') or contract.get('name', 'Unknown Collection')
        floor_price = collection.get('floorPrice', 0)

        image = nft_data.get('image', {})
        image_url = image.get('cachedUrl') or image.get('originalUrl') or image.get('pngUrl', '')

        opensea_url = f"https://opensea.io/assets/{self.config['opensea_chain']}/{contract_address}/{token_id}"
        explorer_url = f"{self.config['explorer_base']}/nft/{contract_address}/{token_id}"

        floor_price_key = f"floor_price_{self.native_symbol.lower()}"

        return {
            'asset_id': f"{contract_address}_{token_id}",
            'contract_address': contract_address,
            'token_id': token_id,
            'name': name,
            'image_url': image_url,
            'collection': {
                'name': collection_name,
                floor_price_key: floor_price,
                'verified': collection.get('safelistRequestStatus') == 'verified',
                'description': collection.get('description', ''),
                'image_url': collection.get('imageUrl', '')
            },
            'links': {
                'opensea': opensea_url,
                self.config['explorer_name'].lower(): explorer_url
            },
            'blockchain': self.chain_name,
            'wallet_address': wallet_address,
            'token_type': contract.get('tokenType', 'ERC721')
        }

    async def get_all_nfts(self, wallets: List[dict], force_refresh: bool = False) -> List[dict]:
        """
        Fetch all NFTs for all wallets on this chain.

        Args:
            wallets: List of wallet dictionaries
            force_refresh: Force refresh from API

        Returns:
            List of all NFTs
        """
        # Try to load from persistent database cache first
        if not force_refresh and not self._db_cache_loaded:
            cached_data = await get_cache(self._nft_cache_key)
            if cached_data:
                logger.info(f"Loaded {len(cached_data.get('nfts', []))} {self.config['name']} NFTs from persistent cache")
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
            logger.warning(f"Alchemy API key not configured for {self.config['name']}")
            return []

        if not wallets:
            logger.info(f"No {self.config['name']} wallets provided")
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
                floor_price_key = f"floor_price_{self.native_symbol.lower()}"

                for nft_data in owned_nfts:
                    parsed_nft = self._parse_nft(nft_data, address)
                    all_nfts.append(parsed_nft)
                    self._nft_cache[parsed_nft['asset_id']] = parsed_nft

                    contract_addr = parsed_nft['contract_address']
                    if contract_addr not in self._collection_cache:
                        self._collection_cache[contract_addr] = {
                            'name': parsed_nft['collection']['name'],
                            floor_price_key: parsed_nft['collection'].get(floor_price_key, 0),
                            'verified': parsed_nft['collection']['verified'],
                            'cached_at': datetime.now().isoformat()
                        }

                page_key = data.get('pageKey')
                if not page_key:
                    break

            logger.info(f"Fetched {len(all_nfts)} NFTs for {self.config['name']} wallet {address[:10]}...")

        self.last_nft_refresh = datetime.now()

        # Save to persistent database cache
        await self._save_nft_cache()

        return all_nfts

    async def _save_nft_cache(self) -> None:
        """Save NFT data to persistent database cache."""
        try:
            cache_data = {
                'nfts': list(self._nft_cache.values()),
                'collections': self._collection_cache,
                'last_refresh': self.last_nft_refresh.isoformat() if self.last_nft_refresh else None
            }
            await set_cache(self._nft_cache_key, cache_data, self._nft_db_cache_ttl)
            logger.info(f"Saved {len(self._nft_cache)} {self.config['name']} NFTs to persistent cache")
        except Exception as e:
            logger.error(f"Error saving {self.config['name']} NFT cache: {e}")

    async def get_nft_summary(self, wallets: List[dict]) -> dict:
        """
        Get a summary of all NFTs grouped by collection.

        Returns:
            Dictionary with collection summaries
        """
        all_nfts = await self.get_all_nfts(wallets)

        collections = {}
        floor_price_key = f"floor_price_{self.native_symbol.lower()}"
        total_value_key = f"total_value_{self.native_symbol.lower()}"
        total_value = 0.0

        for nft in all_nfts:
            collection_name = nft['collection']['name']

            if collection_name not in collections:
                collections[collection_name] = {
                    'name': collection_name,
                    'contract_address': nft['contract_address'],
                    floor_price_key: nft['collection'].get(floor_price_key, 0),
                    'verified': nft['collection']['verified'],
                    'nft_count': 0,
                    total_value_key: 0.0,
                    'nfts': []
                }

            collections[collection_name]['nft_count'] += 1
            floor_price = nft['collection'].get(floor_price_key, 0) or 0
            collections[collection_name][total_value_key] += floor_price
            total_value += floor_price
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
            total_value_key: total_value,
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

    async def get_status(self) -> dict:
        """Get service status."""
        return {
            'chain': self.chain_name,
            'name': self.config['name'],
            'configured': await self.is_configured(),
            'cached_balances': len(self._balance_cache),
            'cached_nfts': len(self._nft_cache),
            'cached_collections': len(self._collection_cache),
            'last_nft_refresh': self.last_nft_refresh.isoformat() if self.last_nft_refresh else None
        }


# Singleton instances
bsc_service = EVMChainService('bsc')
arbitrum_service = EVMChainService('arbitrum')
avalanche_service = EVMChainService('avalanche')
optimism_service = EVMChainService('optimism')
zksync_service = EVMChainService('zksync')
linea_service = EVMChainService('linea')
scroll_service = EVMChainService('scroll')
fantom_service = EVMChainService('fantom')
cronos_service = EVMChainService('cronos')
gnosis_service = EVMChainService('gnosis')
moonbeam_service = EVMChainService('moonbeam')
kaia_service = EVMChainService('kaia')
