"""
XRP Service - Fetches XRP Ledger wallet data using XRPL public JSON-RPC API.

XRPL Cluster API is free and requires no API key.

Provides:
- XRP balance
- Trust line token balances
- Account info

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

# XRP uses 6 decimal places (drops)
DROPS_PER_XRP = 10**6

XRPL_BASE_URL = "https://xrplcluster.com"


class XRPService:
    """Service for fetching XRP Ledger wallet data from XRPL Cluster API (no API key required)."""

    def __init__(self):
        self._balance_cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)

    @staticmethod
    def is_xrp_address(address: str) -> bool:
        """Check if an address is a valid XRP address (starts with r, 25-35 base58 chars)."""
        if not address or not address.startswith('r') or not (25 <= len(address) <= 35):
            return False
        base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
        return all(c in base58_chars for c in address)

    async def get_xrp_balance(self, address: str) -> Optional[float]:
        """
        Get XRP balance for an address using account_info JSON-RPC method.

        Returns:
            XRP balance as float, or None if error
        """
        try:
            client = get_client("xrplcluster", timeout=30.0)
            payload = {
                "method": "account_info",
                "params": [{"account": address, "ledger_index": "validated"}]
            }
            response = await client.post(XRPL_BASE_URL, json=payload)

            if response.status_code != 200:
                logger.error(f"XRPL API error: {response.status_code}")
                return None

            data = response.json()
            result = data.get('result', {})

            # Account not found returns error "actNotFound"
            if result.get('error') == 'actNotFound':
                return 0.0

            if result.get('error'):
                logger.error(f"XRPL account_info error: {result.get('error')}")
                return None

            account_data = result.get('account_data', {})
            balance_drops = int(account_data.get('Balance', '0'))
            balance_xrp = balance_drops / DROPS_PER_XRP

            return balance_xrp

        except Exception as e:
            logger.error(f"Error fetching XRP balance: {e}")
            return None

    async def get_trust_line_balances(self, address: str) -> List[dict]:
        """
        Get trust line (token) balances for an address using account_lines JSON-RPC method.

        Returns:
            List of token balances
        """
        try:
            client = get_client("xrplcluster", timeout=30.0)
            payload = {
                "method": "account_lines",
                "params": [{"account": address, "ledger_index": "validated"}]
            }
            response = await client.post(XRPL_BASE_URL, json=payload)

            if response.status_code != 200:
                logger.error(f"XRPL API error for trust lines: {response.status_code}")
                return []

            data = response.json()
            result = data.get('result', {})

            # Account not found or error
            if result.get('error'):
                logger.debug(f"XRPL account_lines error: {result.get('error')}")
                return []

            lines = result.get('lines', [])

            tokens = []
            for line in lines:
                balance = float(line.get('balance', '0'))
                if balance <= 0:
                    continue

                currency = line.get('currency', 'UNKNOWN')
                issuer = line.get('account', '')

                tokens.append({
                    'contract_address': issuer,
                    'symbol': currency,
                    'name': f"{currency} ({issuer[:8]}...)",
                    'decimals': 0,  # Trust line balances are already in human-readable format
                    'balance': balance,
                    'balance_raw': balance,
                })

            return tokens

        except Exception as e:
            logger.error(f"Error fetching XRP trust line balances: {e}")
            return []

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get complete address info including XRP balance and trust line tokens.

        Returns:
            Dictionary with balance and token info
        """
        if not self.is_xrp_address(address):
            return None

        # Check cache
        if address in self._balance_cache:
            cached = self._balance_cache[address]
            if datetime.now() - cached['cached_at'] < self._cache_ttl:
                return cached['data']

        xrp_balance = await self.get_xrp_balance(address)
        tokens = await self.get_trust_line_balances(address)

        if xrp_balance is None:
            return None

        result = {
            'address': address,
            'balance_xrp': xrp_balance or 0,
            'tokens': tokens,
            'token_count': len(tokens),
            'blockchain': 'xrp',
            'source': 'xrplcluster'
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
            'chain': 'xrp',
            'name': 'XRP Ledger',
            'configured': True,  # No API key needed
            'cached_balances': len(self._balance_cache)
        }


# Singleton instance
xrp_service = XRPService()
