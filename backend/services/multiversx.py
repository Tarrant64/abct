"""
MultiversX Service - Fetches MultiversX (formerly Elrond) wallet data using the public API.

MultiversX API is free and requires no API key.

Provides:
- EGLD balance
- ESDT token balances
- Staking/delegation info

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

# EGLD uses 18 decimal places (like ETH wei)
EGLD_DECIMALS = 18

MULTIVERSX_BASE_URL = "https://api.multiversx.com"


class MultiversXService:
    """Service for fetching MultiversX wallet data from the public API (no API key required)."""

    def __init__(self):
        self._balance_cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)

    @staticmethod
    def is_multiversx_address(address: str) -> bool:
        """Check if an address is a valid MultiversX address (erd1 + 58 alphanumeric chars = 62 total)."""
        if not address or not address.startswith('erd1') or len(address) != 62:
            return False
        alphanumeric = set('0123456789abcdefghijklmnopqrstuvwxyz')
        return all(c in alphanumeric for c in address)

    async def get_account_balance(self, address: str) -> Optional[float]:
        """
        Get EGLD balance for an address.

        GET /accounts/{address}
        Response: { "balance": "..." } in atomic units (1 EGLD = 10^18 atomic units)

        Returns:
            EGLD balance as float, or None if error
        """
        try:
            client = get_client("multiversx", timeout=30.0)
            response = await client.get(
                f"{MULTIVERSX_BASE_URL}/accounts/{address}"
            )

            if response.status_code == 404:
                # Account doesn't exist or has zero balance
                return 0.0

            if response.status_code != 200:
                logger.error(f"MultiversX API error: {response.status_code}")
                return None

            data = response.json()
            balance_raw = data.get('balance', '0')
            balance_egld = int(balance_raw) / (10 ** EGLD_DECIMALS)

            return balance_egld

        except Exception as e:
            logger.error(f"Error fetching EGLD balance: {e}")
            return None

    async def get_tokens(self, address: str) -> List[dict]:
        """
        Get ESDT token balances for an address.

        GET /accounts/{address}/tokens
        Response: array of token objects with identifier, name, ticker, balance, decimals

        Returns:
            List of token balances
        """
        try:
            client = get_client("multiversx", timeout=30.0)
            response = await client.get(
                f"{MULTIVERSX_BASE_URL}/accounts/{address}/tokens"
            )

            if response.status_code == 404:
                return []

            if response.status_code != 200:
                logger.error(f"MultiversX API error for tokens: {response.status_code}")
                return []

            data = response.json()

            if not isinstance(data, list):
                return []

            tokens = []
            for token_obj in data:
                identifier = token_obj.get('identifier', '')
                ticker = token_obj.get('ticker', '')
                name = token_obj.get('name', 'Unknown Token')
                decimals = token_obj.get('decimals', 0)
                balance_str = token_obj.get('balance', '0')

                balance_raw = int(balance_str)
                if balance_raw == 0:
                    continue

                balance = balance_raw / (10 ** decimals) if decimals > 0 else float(balance_raw)

                if balance > 0:
                    tokens.append({
                        "contract_address": identifier,
                        "symbol": ticker or identifier,
                        "name": name,
                        "decimals": decimals,
                        "balance": balance,
                        "balance_raw": balance_raw
                    })

            return tokens

        except Exception as e:
            logger.error(f"Error fetching MultiversX tokens: {e}")
            return []

    async def get_delegation(self, address: str) -> List[dict]:
        """
        Get staking/delegation info for an address.

        GET /accounts/{address}/delegation
        Response: array of delegation objects with address (provider), userActiveStake, claimableRewards
        Values are in atomic units (18 decimals).

        Returns:
            List of delegation entries with staked and claimable amounts
        """
        try:
            client = get_client("multiversx", timeout=30.0)
            response = await client.get(
                f"{MULTIVERSX_BASE_URL}/accounts/{address}/delegation"
            )

            if response.status_code == 404:
                return []

            if response.status_code != 200:
                logger.error(f"MultiversX API error for delegation: {response.status_code}")
                return []

            data = response.json()

            if not isinstance(data, list):
                return []

            delegations = []
            for deleg_obj in data:
                provider = deleg_obj.get('address', '')
                staked_raw = deleg_obj.get('userActiveStake', '0')
                claimable_raw = deleg_obj.get('claimableRewards', '0')

                staked_egld = int(staked_raw) / (10 ** EGLD_DECIMALS)
                claimable_egld = int(claimable_raw) / (10 ** EGLD_DECIMALS)

                if staked_egld > 0 or claimable_egld > 0:
                    delegations.append({
                        "provider": provider,
                        "staked_egld": staked_egld,
                        "claimable_egld": claimable_egld
                    })

            return delegations

        except Exception as e:
            logger.error(f"Error fetching MultiversX delegation: {e}")
            return []

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get complete address info including EGLD balance, ESDT tokens, and delegation.

        Returns:
            Dictionary with balance, token, and delegation info
        """
        if not self.is_multiversx_address(address):
            return None

        # Check cache
        if address in self._balance_cache:
            cached = self._balance_cache[address]
            if datetime.now() - cached['cached_at'] < self._cache_ttl:
                return cached['data']

        balance_egld = await self.get_account_balance(address)
        tokens = await self.get_tokens(address)
        delegation = await self.get_delegation(address)

        if balance_egld is None:
            return None

        result = {
            'address': address,
            'balance_egld': balance_egld or 0,
            'tokens': tokens,
            'token_count': len(tokens),
            'delegation': delegation,
            'blockchain': 'multiversx',
            'source': 'multiversx_api'
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
            'chain': 'multiversx',
            'name': 'MultiversX',
            'configured': True,  # No API key needed
            'cached_balances': len(self._balance_cache)
        }


# Singleton instance
multiversx_service = MultiversXService()
