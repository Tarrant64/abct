"""
Aptos Service - Fetches Aptos (APT) wallet data using the Aptos REST API.

The Aptos fullnode REST API is free and requires no API key.

Provides:
- APT balance (native coin)
- Token balances (other coins in CoinStore resources)
- Staking info (StakePool, DelegationPool resources)
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

# APT uses 8 decimal places (Octas)
OCTAS_PER_APT = 10**8

APTOS_BASE_URL = "https://fullnode.mainnet.aptoslabs.com/v1"

# The native APT coin type
APT_COIN_TYPE = "0x1::aptos_coin::AptosCoin"
COIN_STORE_PREFIX = "0x1::coin::CoinStore<"


class AptosService:
    """Service for fetching Aptos wallet data from the Aptos REST API (no API key required)."""

    def __init__(self):
        self._balance_cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)

    @staticmethod
    def is_aptos_address(address: str) -> bool:
        """
        Check if an address is a valid Aptos address.

        Aptos addresses start with '0x' followed by 64 hex characters (66 chars total).
        """
        if not address or not address.startswith('0x') or len(address) != 66:
            return False
        try:
            int(address[2:], 16)
            return True
        except ValueError:
            return False

    async def get_account_resources(self, address: str) -> Optional[List[dict]]:
        """
        Fetch all resources for an Aptos account.

        GET /accounts/{address}/resources

        Returns:
            List of resource objects with 'type' and 'data' fields, or None on error.
        """
        try:
            client = get_client("aptos", timeout=30.0)
            response = await client.get(
                f"{APTOS_BASE_URL}/accounts/{address}/resources"
            )

            if response.status_code == 404:
                # Account not found / not yet created on-chain
                logger.debug(f"Aptos account not found: {address}")
                return []

            if response.status_code != 200:
                logger.error(f"Aptos API error: {response.status_code} for {address}")
                return None

            return response.json()

        except Exception as e:
            logger.error(f"Error fetching Aptos account resources: {e}")
            return None

    def _extract_apt_balance(self, resources: List[dict]) -> float:
        """
        Extract native APT balance from account resources.

        Looks for 0x1::coin::CoinStore<0x1::aptos_coin::AptosCoin> resource.

        Returns:
            APT balance as float.
        """
        apt_store_type = f"{COIN_STORE_PREFIX}{APT_COIN_TYPE}>"

        for resource in resources:
            if resource.get('type') == apt_store_type:
                try:
                    value = resource['data']['coin']['value']
                    return int(value) / OCTAS_PER_APT
                except (KeyError, ValueError, TypeError) as e:
                    logger.warning(f"Error parsing APT balance: {e}")
                    return 0.0

        return 0.0

    def _extract_tokens(self, resources: List[dict]) -> List[dict]:
        """
        Extract non-APT token balances from CoinStore resources.

        Scans for all 0x1::coin::CoinStore<T> resources where T is not the native APT coin.

        Returns:
            List of token dictionaries.
        """
        apt_store_type = f"{COIN_STORE_PREFIX}{APT_COIN_TYPE}>"
        tokens = []

        for resource in resources:
            res_type = resource.get('type', '')

            # Must be a CoinStore but not the native APT coin
            if not res_type.startswith(COIN_STORE_PREFIX) or res_type == apt_store_type:
                continue

            try:
                # Extract the coin type T from CoinStore<T>
                # res_type = "0x1::coin::CoinStore<0xabc::module::CoinName>"
                coin_type = res_type[len(COIN_STORE_PREFIX):-1]  # strip prefix and trailing >

                value = resource['data']['coin']['value']
                balance_raw = int(value)

                if balance_raw == 0:
                    continue

                # Parse coin type to get a readable name/symbol
                # Coin type format: 0xADDR::module_name::StructName
                symbol, name = self._parse_coin_type(coin_type)

                # Default to 8 decimals for Aptos coins
                decimals = 8
                balance = balance_raw / (10 ** decimals)

                if balance > 0:
                    tokens.append({
                        "contract_address": coin_type,
                        "symbol": symbol,
                        "name": name,
                        "decimals": decimals,
                        "balance": balance,
                        "balance_raw": balance_raw
                    })

            except (KeyError, ValueError, TypeError) as e:
                logger.debug(f"Error parsing token resource: {e}")
                continue

        return tokens

    @staticmethod
    def _parse_coin_type(coin_type: str) -> tuple:
        """
        Parse an Aptos coin type string into symbol and name.

        Input format: "0xADDR::module_name::StructName"
        Example: "0x1::aptos_coin::AptosCoin" -> ("AptosCoin", "AptosCoin")
        Example: "0xf22b...::asset::USDC" -> ("USDC", "USDC")

        Returns:
            (symbol, name) tuple.
        """
        try:
            parts = coin_type.split("::")
            if len(parts) >= 3:
                # Use the last segment as both symbol and name
                struct_name = parts[-1]
                return (struct_name, struct_name)
            elif len(parts) == 2:
                return (parts[-1], parts[-1])
            else:
                return ("UNKNOWN", "Unknown Token")
        except Exception:
            return ("UNKNOWN", "Unknown Token")

    def _extract_staking(self, resources: List[dict]) -> List[dict]:
        """
        Extract staking information from account resources.

        Looks for:
        - 0x1::stake::StakePool
        - 0x1::staking_contract::* resources
        - 0x1::delegation_pool::DelegationPool

        Returns:
            List of staking position dictionaries.
        """
        staking = []

        for resource in resources:
            res_type = resource.get('type', '')
            data = resource.get('data', {})

            try:
                # Direct StakePool
                if res_type == '0x1::stake::StakePool':
                    active = int(data.get('active', {}).get('value', 0))
                    inactive = int(data.get('inactive', {}).get('value', 0))
                    pending_active = int(data.get('pending_active', {}).get('value', 0))
                    pending_inactive = int(data.get('pending_inactive', {}).get('value', 0))

                    staked_octas = active + pending_active
                    pending_withdrawal_octas = inactive + pending_inactive

                    if staked_octas > 0 or pending_withdrawal_octas > 0:
                        staking.append({
                            'type': 'stake_pool',
                            'staked_apt': staked_octas / OCTAS_PER_APT,
                            'pending_withdrawal_apt': pending_withdrawal_octas / OCTAS_PER_APT
                        })

                # Delegation pool
                elif res_type == '0x1::delegation_pool::DelegationPool':
                    active = int(data.get('active_shares', {}).get('total_coins', 0))
                    inactive = int(data.get('inactive_shares', {}).get('total_coins', 0))
                    pending = int(data.get('pending_withdrawal_shares', {}).get('total_coins', 0))

                    staked_octas = active
                    pending_withdrawal_octas = inactive + pending

                    if staked_octas > 0 or pending_withdrawal_octas > 0:
                        staking.append({
                            'type': 'delegation_pool',
                            'staked_apt': staked_octas / OCTAS_PER_APT,
                            'pending_withdrawal_apt': pending_withdrawal_octas / OCTAS_PER_APT
                        })

                # Staking contracts
                elif res_type.startswith('0x1::staking_contract::'):
                    # Extract whatever balance info is available
                    staked_value = 0
                    pending_value = 0

                    # Try common field patterns
                    if 'stake_pool' in data:
                        pool = data['stake_pool']
                        staked_value = int(pool.get('active', {}).get('value', 0))
                        pending_value = int(pool.get('pending_inactive', {}).get('value', 0))
                    elif 'principal' in data:
                        staked_value = int(data.get('principal', 0))

                    if staked_value > 0 or pending_value > 0:
                        staking.append({
                            'type': 'staking_contract',
                            'staked_apt': staked_value / OCTAS_PER_APT,
                            'pending_withdrawal_apt': pending_value / OCTAS_PER_APT
                        })

            except (KeyError, ValueError, TypeError) as e:
                logger.debug(f"Error parsing staking resource {res_type}: {e}")
                continue

        return staking

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get complete address info including APT balance, tokens, and staking.

        Returns:
            Dictionary with balance, token, and staking info, or None on error.
        """
        if not self.is_aptos_address(address):
            return None

        # Check memory cache
        if address in self._balance_cache:
            cached = self._balance_cache[address]
            if datetime.now() - cached['cached_at'] < self._cache_ttl:
                return cached['data']

        # Fetch all resources in a single API call
        resources = await self.get_account_resources(address)

        if resources is None:
            return None

        # Empty list means account not found - return zero balance
        if len(resources) == 0:
            result = {
                'address': address,
                'balance_apt': 0.0,
                'tokens': [],
                'token_count': 0,
                'staking': [],
                'blockchain': 'aptos',
                'source': 'aptos_api'
            }
        else:
            balance_apt = self._extract_apt_balance(resources)
            tokens = self._extract_tokens(resources)
            staking = self._extract_staking(resources)

            result = {
                'address': address,
                'balance_apt': balance_apt,
                'tokens': tokens,
                'token_count': len(tokens),
                'staking': staking,
                'blockchain': 'aptos',
                'source': 'aptos_api'
            }

        # Update memory cache
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
            'chain': 'aptos',
            'name': 'Aptos',
            'configured': True,  # No API key needed
            'cached_balances': len(self._balance_cache)
        }


# Singleton instance
aptos_service = AptosService()
