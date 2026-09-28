"""
Solana Service - Fetches Solana wallet data using Helius API.

Helius API provides comprehensive Solana data including:
- SOL balance
- SPL token balances
- NFT holdings
- Transaction history

Note: the legacy Helius v0 `/addresses/{address}/balances` REST endpoint
(HELIUS_BASE_URL) has been retired by Helius (returns HTTP 404 "Method not
found" as of 2026-09). Balances are now fetched via the Helius DAS
`searchAssets` JSON-RPC method (tokenType="fungible", displayOptions with
showNativeBalance) on the RPC endpoint, which is the currently documented,
GA (non-beta), free-tier-compatible way to get native SOL + SPL token
balances in one call. Docs checked 2026-09-28:
https://www.helius.dev/docs/api-reference/das/searchassets
https://www.helius.dev/docs/api-reference/das/getassetsbyowner
https://www.helius.dev/docs/das/fungible-token-extension
(The newer REST "Wallet API" /v1/wallet/{address}/balances was considered
but is explicitly Beta with "endpoints and response formats may change"
and costs 100 credits/call, so it was not used here.)
"""

import httpx
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import HELIUS_RPC_URL
from services.api_key_manager import APIKeyManager
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Lamports per SOL
LAMPORTS_PER_SOL = 1_000_000_000


class SolanaService(APIKeyManager):
    """Service for fetching Solana wallet data from Helius API with public RPC fallback."""

    def __init__(self):
        super().__init__(api_name='helius', env_var='HELIUS_API_KEY')
        self.rpc_url = HELIUS_RPC_URL
        self.public_rpc_url = "https://api.mainnet-beta.solana.com"
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

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get SOL balance and SPL tokens for a Solana address.

        Uses Helius API for full data (SOL + SPL tokens).
        Falls back to public RPC for native SOL balance only if Helius unavailable.

        Returns:
        {
            'address': '...',
            'balance_sol': 1.234,
            'balance_lamports': 1234000000,
            'tokens': [
                {'mint': '...', 'symbol': 'USDC', 'balance': 100.0, 'decimals': 6}
            ],
            'source': 'helius' | 'public_rpc'
        }
        """
        if not self.is_solana_address(address):
            return None

        # If Helius not configured, use public RPC fallback
        if not await self.is_configured():
            logger.warning("Helius API key not configured, using public RPC fallback")
            return await self.get_balance_from_public_rpc(address)

        # Check cache
        if address in self._balance_cache:
            cached = self._balance_cache[address]
            if datetime.now() - cached['cached_at'] < self._cache_ttl:
                return cached['data']

        try:
            client = get_client("helius", timeout=30.0)
            api_key = await self.get_api_key()

            # Get SOL + SPL token balances via the Helius DAS `searchAssets`
            # JSON-RPC method. tokenType="fungible" restricts results to
            # fungible tokens (excludes NFTs), and displayOptions with
            # showNativeBalance folds the native SOL balance into the same
            # call. This replaces the retired v0 REST `/addresses/{address}
            # /balances` endpoint (HTTP 404 as of 2026-09).
            payload = {
                "jsonrpc": "2.0",
                "id": f"get-balances-{address}",
                "method": "searchAssets",
                "params": {
                    "ownerAddress": address,
                    "tokenType": "fungible",
                    "page": 1,
                    "limit": 1000,
                    "displayOptions": {
                        "showNativeBalance": True,
                        "showZeroBalance": False
                    }
                }
            }

            response = await client.post(
                f"{self.rpc_url}/?api-key={api_key}",
                json=payload
            )

            if response.status_code != 200:
                logger.error(f"Helius API error: {response.status_code} - {response.text}")
                return None

            data = response.json()

            if "error" in data:
                logger.error(f"Helius DAS API error: {data['error']}")
                return None

            result = data.get("result", {})

            # Parse native SOL balance
            native_balance_info = result.get('nativeBalance') or {}
            native_balance = native_balance_info.get('lamports', 0)
            balance_sol = native_balance / LAMPORTS_PER_SOL

            # Parse SPL (fungible) tokens
            tokens = []

            for item in result.get('items', []):
                try:
                    # Defensive: searchAssets(tokenType="fungible") should
                    # already exclude NFTs, but skip anything that isn't a
                    # fungible asset in case of API-shape changes.
                    interface = item.get('interface', '')
                    if interface not in ('FungibleToken', 'FungibleAsset'):
                        continue

                    token_info = item.get('token_info', {}) or {}
                    mint = item.get('id', '')
                    amount = token_info.get('balance', 0)
                    decimals = token_info.get('decimals', 0)

                    # Calculate human-readable balance (token_info.balance
                    # is the raw on-chain integer amount)
                    balance = amount / (10 ** decimals) if decimals > 0 else amount

                    # Skip tokens with zero balance
                    if balance <= 0:
                        continue

                    symbol = token_info.get('symbol', '')
                    content_metadata = (item.get('content') or {}).get('metadata', {}) or {}
                    name = content_metadata.get('name', '')

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
            logger.error(f"Error fetching Solana balance from Helius: {e}")
            logger.info("Attempting fallback to public RPC")
            # Try public RPC as fallback
            return await self.get_balance_from_public_rpc(address)

    async def get_balance_from_public_rpc(self, address: str) -> Optional[dict]:
        """
        Fallback method to get SOL balance from public RPC.

        Only returns native SOL balance (no SPL tokens).
        Used when Helius API is not configured or fails.

        Returns:
            {
                'address': '...',
                'balance_sol': 1.234,
                'balance_lamports': 1234000000,
                'tokens': [],
                'source': 'public_rpc'
            }
        """
        if not self.is_solana_address(address):
            return None

        try:
            client = get_client("helius", timeout=30.0)
            # Use Solana JSON-RPC to get balance
            response = await client.post(
                self.public_rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getBalance",
                    "params": [address]
                }
            )

            if response.status_code != 200:
                logger.error(f"Public RPC error: {response.status_code}")
                return None

            data = response.json()

            if 'error' in data:
                logger.error(f"Public RPC error: {data['error']}")
                return None

            # Get balance in lamports
            balance_lamports = data.get('result', {}).get('value', 0)
            balance_sol = balance_lamports / LAMPORTS_PER_SOL

            result_data = {
                'address': address,
                'balance_sol': balance_sol,
                'balance_lamports': balance_lamports,
                'tokens': [],  # Public RPC doesn't provide SPL tokens
                'token_count': 0,
                'source': 'public_rpc'
            }

            logger.info(f"Fetched SOL balance from public RPC: {balance_sol} SOL")
            return result_data

        except Exception as e:
            logger.error(f"Error fetching balance from public RPC: {e}")
            return None

    async def get_token_balances(self, address: str) -> List[dict]:
        """Get all SPL token balances for an address."""
        info = await self.get_address_info(address)
        if info:
            return info.get('tokens', [])
        return []

    async def get_rate_limit_status(self) -> dict:
        """Get current rate limit status."""
        return {
            'configured': await self.is_configured(),
            'cache_size': len(self._balance_cache),
            'cache_ttl_minutes': self._cache_ttl.total_seconds() / 60
        }

    def clear_cache(self):
        """Clear the balance cache."""
        self._balance_cache.clear()


# Singleton instance
solana_service = SolanaService()
