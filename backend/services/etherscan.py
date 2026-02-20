"""
Etherscan Service - Fetches blockchain data using Etherscan API.

The Etherscan API format is used by multiple block explorers:
- Etherscan (Ethereum mainnet)
- Basescan (Base)
- Polygonscan (Polygon)

Provides:
- Transaction history
- Token transfers
- Contract verification status
- Gas prices

Uses persistent database caching to reduce API calls.
"""

import asyncio
import httpx
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.api_key_manager import APIKeyManager
from database import get_cache, set_cache
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Etherscan V2 unified API — single endpoint with chainid parameter
ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"

# Cache settings
ETHERSCAN_CACHE_TTL = 300  # 5 minutes for transaction data


class EtherscanService(APIKeyManager):
    """Service for fetching EVM blockchain data from Etherscan-compatible APIs."""

    # Chain configurations — all use Etherscan V2 unified endpoint
    CHAINS = {
        'ethereum': {
            'base_url': ETHERSCAN_V2_URL,
            'chain_id': 1,
            'native_symbol': 'ETH',
            'explorer_name': 'Etherscan'
        },
        'base': {
            'base_url': ETHERSCAN_V2_URL,
            'chain_id': 8453,
            'native_symbol': 'ETH',
            'explorer_name': 'Basescan'
        },
        'polygon': {
            'base_url': ETHERSCAN_V2_URL,
            'chain_id': 137,
            'native_symbol': 'MATIC',
            'explorer_name': 'Polygonscan'
        },
        'bsc': {
            'base_url': ETHERSCAN_V2_URL,
            'chain_id': 56,
            'native_symbol': 'BNB',
            'explorer_name': 'BscScan'
        },
        'arbitrum': {
            'base_url': ETHERSCAN_V2_URL,
            'chain_id': 42161,
            'native_symbol': 'ETH',
            'explorer_name': 'Arbiscan'
        },
        'avalanche': {
            'base_url': ETHERSCAN_V2_URL,
            'chain_id': 43114,
            'native_symbol': 'AVAX',
            'explorer_name': 'Snowscan'
        }
    }

    def __init__(self):
        super().__init__(api_name='etherscan', env_var='ETHERSCAN_API_KEY')
        self._cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._has_api_key: Optional[bool] = None  # Cached key status

    async def is_configured(self) -> bool:
        """Check if the API key is configured."""
        key = await self.get_api_key()
        return bool(key)

    def _get_chain_config(self, chain: str) -> Optional[dict]:
        """Get configuration for a specific chain."""
        return self.CHAINS.get(chain.lower())

    async def _make_request(self, chain: str, params: dict) -> Optional[dict]:
        """
        Make a request to the Etherscan-compatible API.

        Works with or without an API key. Without a key, Etherscan allows
        ~1 request per 5 seconds (vs 5/sec with a free key).

        Args:
            chain: Chain name ('ethereum', 'base', 'polygon')
            params: API parameters

        Returns:
            API response data or None if error
        """
        chain_config = self._get_chain_config(chain)
        if not chain_config:
            logger.error(f"Unknown chain: {chain}")
            return None

        # V2 API requires chainid parameter
        params['chainid'] = chain_config['chain_id']

        # Add API key if available; works without one at reduced rate
        api_key = await self.get_api_key()
        if api_key:
            params['apikey'] = api_key
            if self._has_api_key is None:
                self._has_api_key = True
        else:
            if self._has_api_key is None:
                logger.info(f"No Etherscan API key configured — using keyless rate limit (slower)")
                self._has_api_key = False
            # Keyless rate limit: ~1 req per 5 seconds
            await asyncio.sleep(5)

        try:
            # Rate limit: Etherscan free tier = 5 calls/sec with key
            await asyncio.sleep(0.35)
            client = get_client("etherscan", timeout=30.0)
            response = await client.get(
                chain_config['base_url'],
                params=params
            )

            if response.status_code != 200:
                logger.error(f"{chain_config['explorer_name']} API error: {response.status_code}")
                return None

            data = response.json()

            if data.get('status') == '0':
                message = data.get('message', 'Unknown error')
                result = data.get('result', '')
                # "No transactions found" is not an error
                if 'No transactions found' in str(result):
                    return {'result': []}
                # Deprecation warnings - log but don't treat as error if data is empty
                if message == 'NOTOK' and 'deprecated' in str(result).lower():
                    logger.warning(f"{chain_config['explorer_name']} API: {message} - {result}")
                    # If result is empty list, treat as "no data" not "error"
                    if isinstance(result, list) and len(result) == 0:
                        return {'result': []}
                    # Still return data if it exists
                    if isinstance(result, list):
                        return data
                logger.warning(f"{chain_config['explorer_name']} API: {message} - {result}")
                return None

            return data

        except Exception as e:
            logger.error(f"Error making {chain_config['explorer_name']} request: {e}")
            return None

    async def get_eth_balance(self, chain: str, address: str) -> Optional[float]:
        """
        Get native token balance for an address.

        Args:
            chain: Chain name
            address: Wallet address

        Returns:
            Balance in native token (ETH/MATIC), or None if error
        """
        params = {
            'module': 'account',
            'action': 'balance',
            'address': address,
            'tag': 'latest'
        }

        data = await self._make_request(chain, params)
        if not data:
            return None

        try:
            balance_wei = int(data.get('result', '0'))
            return balance_wei / 10**18
        except (ValueError, TypeError):
            return None

    async def get_transactions(self, chain: str, address: str, limit: int = 10000,
                               startblock: int = 0) -> List[dict]:
        """
        Get full transaction history for an address with auto-pagination.

        Fetches up to `limit` transactions, paginating through Etherscan API
        in ascending order to get complete history from oldest to newest.

        Args:
            chain: Chain name
            address: Wallet address
            limit: Maximum total transactions to fetch (default 10000)
            startblock: Block number to start from (0 for full history)

        Returns:
            List of transactions
        """
        chain_config = self._get_chain_config(chain)
        if not chain_config:
            logger.error(f"Unknown chain for transactions: {chain}")
            return []
        logger.info(f"Fetching {chain} transactions for {address[:10]}... "
                     f"(using {chain_config['explorer_name']}, startblock={startblock})")

        all_transactions = []
        page = 1
        page_size = 10000  # Etherscan max per page

        while len(all_transactions) < limit:
            params = {
                'module': 'account',
                'action': 'txlist',
                'address': address,
                'startblock': startblock,
                'endblock': 99999999,
                'page': page,
                'offset': page_size,
                'sort': 'asc'
            }

            data = await self._make_request(chain, params)
            if not data:
                break

            transactions = data.get('result', [])
            if not isinstance(transactions, list) or len(transactions) == 0:
                break

            all_transactions.extend(transactions)
            logger.info(f"Page {page}: fetched {len(transactions)} transactions "
                        f"(total so far: {len(all_transactions)})")

            # If we got fewer than page_size, we've reached the end
            if len(transactions) < page_size:
                break

            page += 1
            # Safety: max 5 pages (50k transactions) to avoid runaway loops
            if page > 5:
                logger.warning(f"Hit pagination limit (5 pages) for {address[:10]}")
                break

            # Rate limit: Etherscan free tier allows 5 calls/sec
            await asyncio.sleep(0.25)

        logger.info(f"Successfully fetched {len(all_transactions)} total transactions "
                     f"from {chain_config['explorer_name']}")
        return [self._parse_transaction(tx, chain) for tx in all_transactions[:limit]]

    def _parse_transaction(self, tx: dict, chain: str) -> dict:
        """Parse a transaction into a standard format."""
        chain_config = self._get_chain_config(chain)
        native_symbol = chain_config['native_symbol'] if chain_config else 'ETH'

        value_wei = int(tx.get('value', '0'))
        value = value_wei / 10**18

        return {
            'hash': tx.get('hash', ''),
            'from': tx.get('from', ''),
            'to': tx.get('to', ''),
            'value': value,
            'value_formatted': f"{value:.6f} {native_symbol}",
            'gas_used': int(tx.get('gasUsed', '0')),
            'gas_price': int(tx.get('gasPrice', '0')),
            'timestamp': int(tx.get('timeStamp', '0')),
            'block_number': int(tx.get('blockNumber', '0')),
            'is_error': tx.get('isError', '0') == '1',
            'chain': chain
        }

    async def get_token_transfers(self, chain: str, address: str, limit: int = 10000,
                                   startblock: int = 0) -> List[dict]:
        """
        Get full ERC-20 token transfer history for an address with auto-pagination.

        Args:
            chain: Chain name
            address: Wallet address
            limit: Maximum total transfers to fetch (default 10000)
            startblock: Block number to start from (0 for full history)

        Returns:
            List of token transfers
        """
        chain_config = self._get_chain_config(chain)
        if not chain_config:
            logger.error(f"Unknown chain for token transfers: {chain}")
            return []
        logger.info(f"Fetching {chain} token transfers for {address[:10]}... "
                     f"(using {chain_config['explorer_name']}, startblock={startblock})")

        all_transfers = []
        page = 1
        page_size = 10000

        while len(all_transfers) < limit:
            params = {
                'module': 'account',
                'action': 'tokentx',
                'address': address,
                'startblock': startblock,
                'endblock': 99999999,
                'page': page,
                'offset': page_size,
                'sort': 'asc'
            }

            data = await self._make_request(chain, params)
            if not data:
                break

            transfers = data.get('result', [])
            if not isinstance(transfers, list) or len(transfers) == 0:
                break

            all_transfers.extend(transfers)
            logger.info(f"Page {page}: fetched {len(transfers)} token transfers "
                        f"(total so far: {len(all_transfers)})")

            if len(transfers) < page_size:
                break

            page += 1
            if page > 5:
                logger.warning(f"Hit pagination limit (5 pages) for token transfers {address[:10]}")
                break

            await asyncio.sleep(0.25)

        logger.info(f"Successfully fetched {len(all_transfers)} total token transfers "
                     f"from {chain_config['explorer_name']}")
        return [self._parse_token_transfer(tx, chain) for tx in all_transfers[:limit]]

    def _parse_token_transfer(self, tx: dict, chain: str) -> dict:
        """Parse a token transfer into a standard format."""
        decimals = int(tx.get('tokenDecimal', '18'))
        value_raw = int(tx.get('value', '0'))
        value = value_raw / (10 ** decimals)

        return {
            'hash': tx.get('hash', ''),
            'from': tx.get('from', ''),
            'to': tx.get('to', ''),
            'token_name': tx.get('tokenName', 'Unknown'),
            'token_symbol': tx.get('tokenSymbol', '???'),
            'token_address': tx.get('contractAddress', ''),
            'value': value,
            'value_formatted': f"{value:.6f} {tx.get('tokenSymbol', '???')}",
            'decimals': decimals,
            'timestamp': int(tx.get('timeStamp', '0')),
            'block_number': int(tx.get('blockNumber', '0')),
            'chain': chain
        }

    async def get_gas_price(self, chain: str = 'ethereum') -> Optional[dict]:
        """
        Get current gas prices.

        Args:
            chain: Chain name (default: ethereum)

        Returns:
            Dictionary with gas prices in Gwei
        """
        params = {
            'module': 'gastracker',
            'action': 'gasoracle'
        }

        data = await self._make_request(chain, params)
        if not data:
            return None

        result = data.get('result', {})
        if not isinstance(result, dict):
            return None

        return {
            'safe_gas_price': float(result.get('SafeGasPrice', 0)),
            'propose_gas_price': float(result.get('ProposeGasPrice', 0)),
            'fast_gas_price': float(result.get('FastGasPrice', 0)),
            'last_block': int(result.get('LastBlock', 0)),
            'chain': chain
        }

    async def get_contract_abi(self, chain: str, contract_address: str) -> Optional[str]:
        """
        Get the ABI for a verified contract.

        Args:
            chain: Chain name
            contract_address: Contract address

        Returns:
            ABI string or None if not verified
        """
        params = {
            'module': 'contract',
            'action': 'getabi',
            'address': contract_address
        }

        data = await self._make_request(chain, params)
        if not data:
            return None

        return data.get('result')

    async def get_status(self) -> dict:
        """Get service status."""
        return {
            'configured': await self.is_configured(),
            'supported_chains': list(self.CHAINS.keys()),
            'api_key_set': bool(await self.get_api_key())
        }


# Singleton instance
etherscan_service = EtherscanService()
