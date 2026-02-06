"""
Ethereum Service - Fetches Ethereum wallet data using beaconcha.in API.

Free tier limits:
- 1 request per minute
- 1000 requests per month

Implements rate limiting and caching to stay within limits.
"""

import httpx
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BEACONCHAIN_BASE_URL
from services.api_key_manager import APIKeyManager
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Rate limiting settings
MIN_REQUEST_INTERVAL = 60  # 1 request per minute for free tier
MONTHLY_LIMIT = 1000


class EthereumService(APIKeyManager):
    """Service for fetching Ethereum wallet data from beaconcha.in with public RPC fallback."""

    PUBLIC_RPC_URL = "https://ethereum-rpc.publicnode.com"

    def __init__(self):
        super().__init__(api_name='beaconchain', env_var='BEACONCHAIN_API_KEY')
        self.base_url = BEACONCHAIN_BASE_URL
        self.last_request_time: Optional[datetime] = None
        self.request_count = 0
        self.request_count_reset: Optional[datetime] = None
        self._balance_cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=10)

    async def is_configured(self) -> bool:
        """Check if the API key is configured."""
        key = await self.get_api_key()
        return bool(key)

    def is_ethereum_address(self, address: str) -> bool:
        """Check if an address is a valid Ethereum address."""
        # Ethereum addresses start with 0x and are 42 characters
        if not address:
            return False
        address = address.lower()
        if address.startswith('0x') and len(address) == 42:
            try:
                # Check if it's valid hex
                int(address[2:], 16)
                return True
            except ValueError:
                return False
        return False

    async def _wait_for_rate_limit(self):
        """Wait if necessary to respect rate limits."""
        if self.last_request_time:
            elapsed = (datetime.now() - self.last_request_time).total_seconds()
            if elapsed < MIN_REQUEST_INTERVAL:
                wait_time = MIN_REQUEST_INTERVAL - elapsed
                logger.info(f"Rate limiting: waiting {wait_time:.1f}s before next request")
                await asyncio.sleep(wait_time)

    async def _make_request(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make a rate-limited request to beaconcha.in API."""
        if not await self.is_configured():
            logger.warning("Beaconcha.in API key not configured")
            return None

        # Reset monthly counter if needed
        if self.request_count_reset is None or datetime.now() > self.request_count_reset:
            self.request_count = 0
            self.request_count_reset = datetime.now() + timedelta(days=30)

        # Check monthly limit
        if self.request_count >= MONTHLY_LIMIT:
            logger.warning("Monthly request limit reached for beaconcha.in")
            return None

        # Wait for rate limit
        await self._wait_for_rate_limit()

        url = f"{self.base_url}{endpoint}"
        headers = {"apikey": await self.get_api_key()}

        try:
            client = get_client("beaconchain", timeout=30.0)
            response = await client.get(url, headers=headers, params=params)
            self.last_request_time = datetime.now()
            self.request_count += 1

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                logger.warning("Rate limited by beaconcha.in API")
                return None
            else:
                logger.error(f"Beaconcha.in API error: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error making beaconcha.in request: {e}")
            return None

    async def get_address_balance(self, address: str) -> Optional[dict]:
        """
        Get ETH balance and ERC-20 tokens for an Ethereum address.

        Returns:
        {
            'address': '0x...',
            'balance_eth': 1.234,
            'balance_wei': '1234000000000000000',
            'tokens': [
                {'symbol': 'USDC', 'name': 'USD Coin', 'balance': 100.0, 'decimals': 6}
            ]
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

        # Fetch from API
        result = await self._make_request(f"/execution/address/{address}")

        if not result or 'data' not in result:
            # Fallback to public RPC for native ETH balance
            logger.info(f"Beaconcha.in unavailable for {address[:10]}, trying public RPC fallback")
            return await self.get_balance_from_public_rpc(address)

        data = result['data']

        # Parse balance (API returns ETH as a string, not Wei)
        balance_str = data.get('ether', '0')
        try:
            balance_eth = float(balance_str)
        except (ValueError, TypeError):
            balance_eth = 0.0

        # Parse ERC-20 tokens
        # beaconcha.in returns balance as a string (already adjusted for decimals)
        tokens = []
        for token in data.get('tokens', []):
            try:
                # Balance is already human-readable from the API
                balance_str = token.get('balance', '0')
                balance = float(balance_str)

                # Skip spam tokens (usually have suspicious names)
                symbol = token.get('symbol', 'UNKNOWN')
                if 'http' in symbol.lower() or 'visit' in symbol.lower() or '.com' in symbol.lower():
                    continue

                tokens.append({
                    'symbol': symbol,
                    'name': token.get('name', ''),
                    'balance': balance,
                    'decimals': 18,  # Not provided by API, assume 18
                    'contract_address': token.get('address', '')
                })
            except (ValueError, TypeError) as e:
                logger.debug(f"Error parsing token: {e}")
                continue

        result_data = {
            'address': address,
            'balance_eth': balance_eth,
            'tokens': tokens,
            'token_count': len(tokens)
        }

        # Cache the result
        self._balance_cache[address] = {
            'data': result_data,
            'cached_at': datetime.now()
        }

        return result_data

    async def get_balance_from_public_rpc(self, address: str) -> Optional[dict]:
        """
        Fallback method to get ETH balance from public RPC.

        Only returns native ETH balance (no ERC-20 tokens).
        Used when beaconcha.in API is not configured or fails.
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
            balance_eth = balance_wei / (10**18)

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
        """Resolve ENS name to address or vice versa."""
        result = await self._make_request(f"/ens/{name_or_address}")

        if not result or 'data' not in result:
            return None

        data = result['data']
        return {
            'address': data.get('address'),
            'ens_name': data.get('name')
        }

    def get_rate_limit_status(self) -> dict:
        """Get current rate limit status."""
        time_until_next = 0
        if self.last_request_time:
            elapsed = (datetime.now() - self.last_request_time).total_seconds()
            time_until_next = max(0, MIN_REQUEST_INTERVAL - elapsed)

        return {
            'configured': self.is_configured(),
            'requests_this_month': self.request_count,
            'monthly_limit': MONTHLY_LIMIT,
            'seconds_until_next_request': time_until_next,
            'last_request': self.last_request_time.isoformat() if self.last_request_time else None
        }

    def clear_cache(self):
        """Clear the balance cache."""
        self._balance_cache.clear()


# Singleton instance
ethereum_service = EthereumService()
