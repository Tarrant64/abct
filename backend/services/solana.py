"""
Solana Service - Fetches Solana wallet data using Helius API.

Helius API provides comprehensive Solana data including:
- SOL balance
- SPL token balances
- NFT holdings
- Transaction history
"""

import httpx
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import HELIUS_BASE_URL
from services.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

# Lamports per SOL
LAMPORTS_PER_SOL = 1_000_000_000


class SolanaService(APIKeyManager):
    """Service for fetching Solana wallet data from Helius API."""

    def __init__(self):
        super().__init__(api_name='helius', env_var='HELIUS_API_KEY')
        self.base_url = HELIUS_BASE_URL
        self._balance_cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)

    async def is_configured(self) -> bool:
        """Check if the API key is configured."""
        key = await self.get_api_key()
        return bool(key)

    def is_solana_address(self, address: str) -> bool:
        """Check if an address is a valid Solana address."""
        if not address:
            return False

        # Solana addresses are base58 encoded, 32-44 characters
        if len(address) < 32 or len(address) > 44:
            return False

        # Base58 character set (no 0, O, I, l)
        base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
        return all(c in base58_chars for c in address)

    async def _fetch_token_metadata(self, client: httpx.AsyncClient, mint_addresses: List[str]) -> Dict[str, dict]:
        """
        Fetch token metadata for a list of mint addresses.
        Returns a dict mapping mint address to metadata.
        """
        if not mint_addresses:
            return {}

        try:
            response = await client.post(
                f"{self.base_url}/token-metadata",
                params={"api-key": await self.get_api_key()},
                json={"mintAccounts": mint_addresses}
            )

            if response.status_code != 200:
                logger.warning(f"Token metadata API error: {response.status_code}")
                return {}

            metadata_list = response.json()
            result = {}

            for item in metadata_list:
                mint = item.get('account', '')
                on_chain = item.get('onChainMetadata', {})
                metadata = on_chain.get('metadata', {})
                data = metadata.get('data', {})

                if data:
                    result[mint] = {
                        'symbol': data.get('symbol', ''),
                        'name': data.get('name', ''),
                    }

            return result

        except Exception as e:
            logger.warning(f"Error fetching token metadata: {e}")
            return {}

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get SOL balance and SPL tokens for a Solana address.

        Returns:
        {
            'address': '...',
            'balance_sol': 1.234,
            'balance_lamports': 1234000000,
            'tokens': [
                {'mint': '...', 'symbol': 'USDC', 'balance': 100.0, 'decimals': 6}
            ],
            'source': 'helius'
        }
        """
        if not self.is_solana_address(address):
            return None

        if not await self.is_configured():
            logger.warning("Helius API key not configured")
            return None

        # Check cache
        if address in self._balance_cache:
            cached = self._balance_cache[address]
            if datetime.now() - cached['cached_at'] < self._cache_ttl:
                return cached['data']

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Get SOL balance and token balances using the balances endpoint
                response = await client.get(
                    f"{self.base_url}/addresses/{address}/balances",
                    params={"api-key": await self.get_api_key()}
                )

                if response.status_code != 200:
                    logger.error(f"Helius API error: {response.status_code} - {response.text}")
                    return None

                data = response.json()

                # Parse native SOL balance
                native_balance = data.get('nativeBalance', 0)
                balance_sol = native_balance / LAMPORTS_PER_SOL

                # Parse SPL tokens - first pass to get balances
                tokens = []
                unknown_mints = []

                for token in data.get('tokens', []):
                    try:
                        mint = token.get('mint', '')
                        amount = token.get('amount', 0)
                        decimals = token.get('decimals', 0)

                        # Calculate human-readable balance
                        balance = amount / (10 ** decimals) if decimals > 0 else amount

                        # Skip tokens with zero balance
                        if balance <= 0:
                            continue

                        # Get token info if available
                        token_info = token.get('tokenInfo', {})
                        symbol = token_info.get('symbol', '')
                        name = token_info.get('name', '')

                        # Track mints that need metadata lookup
                        if not symbol:
                            unknown_mints.append(mint)

                        tokens.append({
                            'mint': mint,
                            'symbol': symbol or 'UNKNOWN',
                            'name': name,
                            'balance': balance,
                            'amount_raw': amount,
                            'decimals': decimals
                        })
                    except Exception as e:
                        logger.debug(f"Error parsing token: {e}")
                        continue

                # Fetch metadata for tokens with unknown symbols
                if unknown_mints:
                    metadata = await self._fetch_token_metadata(client, unknown_mints)

                    # Update tokens with fetched metadata
                    for token in tokens:
                        if token['symbol'] == 'UNKNOWN' and token['mint'] in metadata:
                            meta = metadata[token['mint']]
                            token['symbol'] = meta.get('symbol', 'UNKNOWN')
                            token['name'] = meta.get('name', '')

                result_data = {
                    'address': address,
                    'balance_sol': balance_sol,
                    'balance_lamports': native_balance,
                    'tokens': tokens,
                    'token_count': len(tokens),
                    'source': 'helius'
                }

                # Cache the result
                self._balance_cache[address] = {
                    'data': result_data,
                    'cached_at': datetime.now()
                }

                return result_data

        except Exception as e:
            logger.error(f"Error fetching Solana balance: {e}")
            return None

    async def get_token_balances(self, address: str) -> List[dict]:
        """Get all SPL token balances for an address."""
        info = await self.get_address_info(address)
        if info:
            return info.get('tokens', [])
        return []

    def get_rate_limit_status(self) -> dict:
        """Get current rate limit status."""
        return {
            'configured': self.is_configured(),
            'cache_size': len(self._balance_cache),
            'cache_ttl_minutes': self._cache_ttl.total_seconds() / 60
        }

    def clear_cache(self):
        """Clear the balance cache."""
        self._balance_cache.clear()


# Singleton instance
solana_service = SolanaService()
