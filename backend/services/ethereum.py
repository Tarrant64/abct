"""
Ethereum Service - Fetches Ethereum wallet data using Alchemy API as primary source.

Primary: Alchemy ETH mainnet (JSON-RPC) - eth_getBalance, alchemy_getTokenBalances
Fallback: Public RPC for native ETH balance only (no ERC-20 tokens)

Previous implementation used Beaconcha.in (1 req/min, 1000/month).
Alchemy provides 30M compute units/month free tier, no rate limit bottleneck.
"""

import httpx
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ALCHEMY_ETH_URL
from services.api_key_manager import APIKeyManager
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Wei per ETH
WEI_PER_ETH = 10**18


class EthereumService(APIKeyManager):
    """Service for fetching Ethereum wallet data from Alchemy API with public RPC fallback."""

    PUBLIC_RPC_URL = "https://ethereum-rpc.publicnode.com"

    def __init__(self):
        super().__init__(api_name='alchemy', env_var='ALCHEMY_API_KEY')
        self._balance_cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=10)

    async def _get_v2_url(self) -> str:
        """Get Alchemy v2 API URL with API key."""
        api_key = await self.get_api_key()
        if not api_key:
            return ""
        return f"{ALCHEMY_ETH_URL}/v2/{api_key}"

    async def is_configured(self) -> bool:
        """Check if the API key is configured."""
        key = await self.get_api_key()
        return bool(key)

    def is_ethereum_address(self, address: str) -> bool:
        """Check if an address is a valid Ethereum address."""
        if not address:
            return False
        address = address.lower()
        if address.startswith('0x') and len(address) == 42:
            try:
                int(address[2:], 16)
                return True
            except ValueError:
                return False
        return False

    async def get_address_balance(self, address: str) -> Optional[dict]:
        """
        Get ETH balance and ERC-20 tokens for an Ethereum address.

        Uses Alchemy JSON-RPC: eth_getBalance + alchemy_getTokenBalances + alchemy_getTokenMetadata.
        Falls back to public RPC if Alchemy is not configured.

        Returns:
        {
            'address': '0x...',
            'balance_eth': 1.234,
            'tokens': [
                {'symbol': 'USDC', 'name': 'USD Coin', 'balance': 100.0, 'decimals': 6, 'contract_address': '0x...'}
            ],
            'token_count': 5,
            'source': 'alchemy'
        }
        """
        if not self.is_ethereum_address(address):
            return None

        address = address.lower()

        # Check cache
        if address in self._balance_cache:
            cached = self._balance_cache[address]
            if datetime.now() - cached['cached_at'] < self._cache_ttl:
                return cached['data']

        if not await self.is_configured():
            logger.info(f"Alchemy not configured for Ethereum, using public RPC fallback for {address[:10]}")
            return await self.get_balance_from_public_rpc(address)

        v2_url = await self._get_v2_url()
        if not v2_url:
            return await self.get_balance_from_public_rpc(address)

        try:
            client = get_client("alchemy", timeout=30.0)

            # Fetch native ETH balance
            balance_response = await client.post(
                v2_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_getBalance",
                    "params": [address, "latest"]
                }
            )

            if balance_response.status_code != 200:
                logger.error(f"Alchemy ETH balance error: {balance_response.status_code}")
                return await self.get_balance_from_public_rpc(address)

            balance_data = balance_response.json()
            if "error" in balance_data:
                logger.error(f"Alchemy ETH balance error: {balance_data['error']}")
                return await self.get_balance_from_public_rpc(address)

            balance_wei = int(balance_data.get("result", "0x0"), 16)
            balance_eth = balance_wei / WEI_PER_ETH

            # Fetch ERC-20 token balances
            tokens = await self._fetch_token_balances(client, v2_url, address)

            result_data = {
                'address': address,
                'balance_eth': balance_eth,
                'tokens': tokens,
                'token_count': len(tokens),
                'source': 'alchemy'
            }

            # Cache the result
            self._balance_cache[address] = {
                'data': result_data,
                'cached_at': datetime.now()
            }

            logger.info(f"Alchemy: fetched ETH balance {balance_eth:.6f} ETH + {len(tokens)} tokens for {address[:10]}")
            return result_data

        except Exception as e:
            logger.error(f"Error fetching ETH balance from Alchemy: {e}")
            return await self.get_balance_from_public_rpc(address)

    async def _fetch_token_balances(self, client, v2_url: str, address: str) -> List[dict]:
        """Fetch ERC-20 token balances using Alchemy-specific methods."""
        try:
            # Get all ERC-20 token balances
            token_response = await client.post(
                v2_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "alchemy_getTokenBalances",
                    "params": [address, "erc20"]
                }
            )

            if token_response.status_code != 200:
                logger.warning(f"Alchemy token balances error: {token_response.status_code}")
                return []

            token_data = token_response.json()
            if "error" in token_data:
                logger.warning(f"Alchemy token balances error: {token_data['error']}")
                return []

            result = token_data.get("result", {})
            token_balances = result.get("tokenBalances", [])

            tokens = []
            for tb in token_balances:
                balance_hex = tb.get("tokenBalance", "0x0")
                if balance_hex == "0x0" or balance_hex == "0x":
                    continue

                contract_address = tb.get("contractAddress", "")
                balance_raw = int(balance_hex, 16)

                # Get token metadata
                metadata = await self._get_token_metadata(client, v2_url, contract_address)

                decimals = metadata.get("decimals", 18)
                balance = balance_raw / (10 ** decimals) if decimals else balance_raw

                if balance <= 0:
                    continue

                symbol = metadata.get("symbol", "UNKNOWN")
                name = metadata.get("name", "")

                # Skip spam tokens
                if any(s in symbol.lower() for s in ['http', 'visit', '.com', '.io', '.xyz']):
                    continue

                tokens.append({
                    'symbol': symbol,
                    'name': name,
                    'balance': balance,
                    'decimals': decimals,
                    'contract_address': contract_address
                })

            return tokens

        except Exception as e:
            logger.error(f"Error fetching ERC-20 tokens: {e}")
            return []

    async def _get_token_metadata(self, client, v2_url: str, contract_address: str) -> dict:
        """Get metadata for a token contract using alchemy_getTokenMetadata."""
        try:
            response = await client.post(
                v2_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "alchemy_getTokenMetadata",
                    "params": [contract_address]
                }
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("result", {})

        except Exception as e:
            logger.debug(f"Error fetching token metadata for {contract_address}: {e}")

        return {}

    async def get_balance_from_public_rpc(self, address: str) -> Optional[dict]:
        """
        Fallback method to get ETH balance from public RPC.
        Only returns native ETH balance (no ERC-20 tokens).
        """
        if not self.is_ethereum_address(address):
            return None

        try:
            client = get_client("public_rpc_eth", timeout=30.0)
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
                logger.error(f"Ethereum public RPC error: {response.status_code}")
                return None

            data = response.json()

            if 'error' in data:
                logger.error(f"Ethereum public RPC error: {data['error']}")
                return None

            balance_wei = int(data.get('result', '0x0'), 16)
            balance_eth = balance_wei / WEI_PER_ETH

            result_data = {
                'address': address,
                'balance_eth': balance_eth,
                'tokens': [],
                'token_count': 0,
                'source': 'public_rpc'
            }

            logger.info(f"Fetched ETH balance from public RPC: {balance_eth:.6f} ETH")

            self._balance_cache[address] = {
                'data': result_data,
                'cached_at': datetime.now()
            }

            return result_data

        except Exception as e:
            logger.error(f"Error fetching ETH balance from public RPC: {e}")
            return None

    async def resolve_ens(self, name_or_address: str) -> Optional[dict]:
        """
        Resolve ENS name to address using Alchemy.

        Uses eth_call to the ENS registry if Alchemy is configured,
        otherwise returns None (will be replaced by Moralis ENS in Phase 4).
        """
        # ENS resolution will be moved to Moralis in Phase 4
        # For now, keep a stub that returns None
        return None

    def get_rate_limit_status(self) -> dict:
        """Get current rate limit status (no longer rate-limited with Alchemy)."""
        return {
            'configured': True,
            'provider': 'alchemy',
            'rate_limited': False,
            'note': 'Alchemy free tier: 30M compute units/month'
        }

    def clear_cache(self):
        """Clear the balance cache."""
        self._balance_cache.clear()


# Singleton instance
ethereum_service = EthereumService()
