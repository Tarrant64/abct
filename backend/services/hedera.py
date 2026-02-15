"""
Hedera Service - Fetches Hedera Hashgraph (HBAR) wallet data using the Mirror Node REST API.

Mirror Node API is free and requires no API key.

Provides:
- HBAR balance
- HTS (Hedera Token Service) token balances
- Staking info (staked node, pending rewards)

Uses persistent database caching to reduce API calls.
"""

import logging
import re
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_cache, set_cache
from services.http_client import get_client

logger = logging.getLogger(__name__)

# HBAR uses 8 decimal places (tinybars)
TINYBARS_PER_HBAR = 10**8

MIRROR_NODE_BASE_URL = "https://mainnet-public.mirrornode.hedera.com/api/v1"

# Regex for Hedera account IDs: shard.realm.account (e.g., 0.0.1234567)
HEDERA_ADDRESS_PATTERN = re.compile(r'^\d+\.\d+\.\d+$')


class HederaService:
    """Service for fetching Hedera Hashgraph wallet data from Mirror Node API (no API key required)."""

    def __init__(self):
        self._balance_cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)

    @staticmethod
    def is_hedera_address(address: str) -> bool:
        """Check if an address is a valid Hedera account ID (e.g., 0.0.1234567)."""
        if not address:
            return False
        return bool(HEDERA_ADDRESS_PATTERN.match(address))

    async def get_account_balance(self, address: str) -> Optional[float]:
        """
        Get HBAR balance for an account.

        The Mirror Node returns balance in tinybars (1 HBAR = 100,000,000 tinybars).

        Returns:
            HBAR balance as float, or None if error
        """
        try:
            client = get_client("hedera_mirror", timeout=30.0)
            response = await client.get(
                f"{MIRROR_NODE_BASE_URL}/accounts/{address}"
            )

            if response.status_code == 404:
                # Account doesn't exist
                return 0.0

            if response.status_code != 200:
                logger.error(f"Hedera Mirror Node API error: {response.status_code}")
                return None

            data = response.json()

            balance_tinybars = data.get('balance', {}).get('balance', 0)
            balance_hbar = balance_tinybars / TINYBARS_PER_HBAR

            return balance_hbar

        except Exception as e:
            logger.error(f"Error fetching HBAR balance: {e}")
            return None

    async def get_tokens(self, address: str) -> List[dict]:
        """
        Get HTS (Hedera Token Service) token balances for an account.

        Fetches token associations from the account tokens endpoint, then
        retrieves metadata for each token.

        Returns:
            List of token balance dictionaries
        """
        try:
            client = get_client("hedera_mirror", timeout=30.0)
            all_tokens_raw = []

            # Paginate through token associations
            url = f"{MIRROR_NODE_BASE_URL}/accounts/{address}/tokens"
            while url:
                response = await client.get(url)

                if response.status_code != 200:
                    logger.error(f"Hedera Mirror Node tokens API error: {response.status_code}")
                    break

                data = response.json()
                all_tokens_raw.extend(data.get('tokens', []))

                # Handle pagination via links.next
                next_link = data.get('links', {}).get('next')
                if next_link:
                    # next_link is a relative path like /api/v1/accounts/.../tokens?token.id=gt:...
                    url = f"https://mainnet-public.mirrornode.hedera.com{next_link}"
                else:
                    url = None

            tokens = []
            for token_entry in all_tokens_raw:
                token_id = token_entry.get('token_id')
                balance_raw = token_entry.get('balance', 0)

                if not token_id or balance_raw == 0:
                    continue

                # Fetch token metadata (name, symbol, decimals)
                metadata = await self._get_token_metadata(client, token_id)

                decimals = metadata.get('decimals', 0)
                balance = balance_raw / (10 ** decimals) if decimals > 0 else balance_raw

                if balance > 0:
                    tokens.append({
                        "contract_address": token_id,
                        "symbol": metadata.get("symbol", "UNKNOWN"),
                        "name": metadata.get("name", "Unknown Token"),
                        "decimals": decimals,
                        "balance": balance,
                        "balance_raw": balance_raw
                    })

            return tokens

        except Exception as e:
            logger.error(f"Error fetching HTS token balances: {e}")
            return []

    async def _get_token_metadata(self, client, token_id: str) -> dict:
        """Get metadata for an HTS token from the Mirror Node."""
        # Check database cache first
        cache_key = f"hedera_token_meta:{token_id}"
        cached = get_cache(cache_key)
        if cached:
            return cached

        try:
            response = await client.get(
                f"{MIRROR_NODE_BASE_URL}/tokens/{token_id}"
            )

            if response.status_code == 200:
                data = response.json()
                metadata = {
                    'name': data.get('name', 'Unknown Token'),
                    'symbol': data.get('symbol', 'UNKNOWN'),
                    'decimals': int(data.get('decimals', '0'))
                }
                # Cache token metadata for 24 hours (rarely changes)
                set_cache(cache_key, metadata, ttl=86400)
                return metadata

        except Exception as e:
            logger.debug(f"Error fetching Hedera token metadata for {token_id}: {e}")

        return {'name': 'Unknown Token', 'symbol': 'UNKNOWN', 'decimals': 0}

    async def get_staking_info(self, address: str) -> Optional[dict]:
        """
        Get staking info for an account from the account endpoint.

        Returns staking details including staked node, pending rewards, and
        whether the account has declined rewards.

        Returns:
            Dictionary with staking info, or None if error
        """
        try:
            client = get_client("hedera_mirror", timeout=30.0)
            response = await client.get(
                f"{MIRROR_NODE_BASE_URL}/accounts/{address}"
            )

            if response.status_code != 200:
                logger.error(f"Hedera Mirror Node API error for staking: {response.status_code}")
                return None

            data = response.json()

            staked_node_id = data.get('staked_node_id')
            staked_account_id = data.get('staked_account_id')
            pending_reward_tinybars = data.get('pending_reward', 0)
            decline_reward = data.get('decline_reward', False)
            stake_period_start = data.get('stake_period_start')

            is_staking = staked_node_id is not None or staked_account_id is not None

            return {
                'is_staking': is_staking,
                'staked_node_id': staked_node_id,
                'staked_account_id': staked_account_id,
                'pending_reward_tinybars': pending_reward_tinybars,
                'pending_reward_hbar': pending_reward_tinybars / TINYBARS_PER_HBAR if pending_reward_tinybars else 0,
                'decline_reward': decline_reward,
                'stake_period_start': stake_period_start
            }

        except Exception as e:
            logger.error(f"Error fetching Hedera staking info: {e}")
            return None

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get complete address info including HBAR balance, HTS tokens, and staking.

        This is the main entry point that combines all account data.

        Returns:
            Dictionary with balance, tokens, and staking info
        """
        if not self.is_hedera_address(address):
            return None

        # Check memory cache
        if address in self._balance_cache:
            cached = self._balance_cache[address]
            if datetime.now() - cached['cached_at'] < self._cache_ttl:
                return cached['data']

        hbar_balance = await self.get_account_balance(address)
        tokens = await self.get_tokens(address)
        staking = await self.get_staking_info(address)

        if hbar_balance is None:
            return None

        result = {
            'address': address,
            'balance_hbar': hbar_balance or 0,
            'tokens': tokens,
            'token_count': len(tokens),
            'staking': staking,
            'blockchain': 'hedera',
            'source': 'mirror_node'
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
            'chain': 'hedera',
            'name': 'Hedera Hashgraph',
            'configured': True,  # No API key needed
            'cached_balances': len(self._balance_cache)
        }


# Singleton instance
hedera_service = HederaService()
