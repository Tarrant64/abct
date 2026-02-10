"""
Tron Service - Fetches Tron (TRX) wallet data using TronGrid API.

TronGrid API is free and requires no API key.

Provides:
- TRX balance
- TRC-20 token balances
- Account info

No NFT support initially (Tron NFTs are rare and lack a standard API).

Uses persistent database caching to reduce API calls.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_cache, set_cache
from services.http_client import get_client

logger = logging.getLogger(__name__)

# TRX uses 6 decimal places (SUN)
SUN_PER_TRX = 10**6

TRONGRID_BASE_URL = "https://api.trongrid.io"


class TronService:
    """Service for fetching Tron wallet data from TronGrid API (no API key required)."""

    def __init__(self):
        self._balance_cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)

    @staticmethod
    def is_tron_address(address: str) -> bool:
        """Check if an address is a valid Tron address (T + 33 base58 chars)."""
        if not address or not address.startswith('T') or len(address) != 34:
            return False
        base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
        return all(c in base58_chars for c in address)

    async def get_trx_balance(self, address: str) -> Optional[float]:
        """
        Get TRX balance for an address.

        Returns:
            TRX balance as float, or None if error
        """
        try:
            client = get_client("trongrid", timeout=30.0)
            response = await client.get(
                f"{TRONGRID_BASE_URL}/v1/accounts/{address}"
            )

            if response.status_code != 200:
                logger.error(f"TronGrid API error: {response.status_code}")
                return None

            data = response.json()

            if not data.get('data') or len(data['data']) == 0:
                # Account doesn't exist or has zero balance
                return 0.0

            account = data['data'][0]
            balance_sun = account.get('balance', 0)
            balance_trx = balance_sun / SUN_PER_TRX

            return balance_trx

        except Exception as e:
            logger.error(f"Error fetching TRX balance: {e}")
            return None

    async def get_trc20_balances(self, address: str) -> List[dict]:
        """
        Get TRC-20 token balances for an address.

        TronGrid returns trc20 array directly in the account endpoint.

        Returns:
            List of token balances
        """
        try:
            client = get_client("trongrid", timeout=30.0)
            response = await client.get(
                f"{TRONGRID_BASE_URL}/v1/accounts/{address}"
            )

            if response.status_code != 200:
                logger.error(f"TronGrid API error for tokens: {response.status_code}")
                return []

            data = response.json()

            if not data.get('data') or len(data['data']) == 0:
                return []

            account = data['data'][0]
            trc20_list = account.get('trc20', [])

            tokens = []
            for token_obj in trc20_list:
                # Each trc20 entry is a dict with {contract_address: balance_string}
                for contract_address, balance_str in token_obj.items():
                    balance_raw = int(balance_str)
                    if balance_raw == 0:
                        continue

                    # Fetch token metadata
                    metadata = await self._get_token_info(client, contract_address)

                    decimals = metadata.get('decimals', 6)
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
            logger.error(f"Error fetching TRC-20 balances: {e}")
            return []

    async def _get_token_info(self, client, contract_address: str) -> dict:
        """Get metadata for a TRC-20 token contract."""
        try:
            response = await client.get(
                f"{TRONGRID_BASE_URL}/v1/contracts/{contract_address}"
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('data') and len(data['data']) > 0:
                    contract_data = data['data'][0]
                    return {
                        'name': contract_data.get('name', 'Unknown Token'),
                        'symbol': contract_data.get('symbol', 'UNKNOWN'),
                        'decimals': contract_data.get('decimals', 6),
                        'logo': ''
                    }

        except Exception as e:
            logger.debug(f"Error fetching Tron token info: {e}")

        return {'name': 'Unknown Token', 'symbol': 'UNKNOWN', 'decimals': 6, 'logo': ''}

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get complete address info including TRX balance and TRC-20 tokens.

        Returns:
            Dictionary with balance and token info
        """
        if not self.is_tron_address(address):
            return None

        # Check cache
        if address in self._balance_cache:
            cached = self._balance_cache[address]
            if datetime.now() - cached['cached_at'] < self._cache_ttl:
                return cached['data']

        trx_balance = await self.get_trx_balance(address)
        tokens = await self.get_trc20_balances(address)

        if trx_balance is None:
            return None

        result = {
            'address': address,
            'balance_trx': trx_balance or 0,
            'tokens': tokens,
            'token_count': len(tokens),
            'blockchain': 'tron',
            'source': 'trongrid'
        }

        self._balance_cache[address] = {
            'data': result,
            'cached_at': datetime.now()
        }

        return result

    def clear_cache(self):
        """Clear all caches."""
        self._balance_cache.clear()

    def get_status(self) -> dict:
        """Get service status."""
        return {
            'chain': 'tron',
            'name': 'Tron',
            'configured': True,  # No API key needed
            'cached_balances': len(self._balance_cache)
        }


# Singleton instance
tron_service = TronService()
