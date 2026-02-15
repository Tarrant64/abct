"""
Sui Service - Fetches Sui wallet data using the Sui JSON-RPC API.

The Sui fullnode JSON-RPC API is free and requires no API key.

Provides:
- SUI balance (native coin)
- Non-SUI token balances with metadata
- Staking info (delegated stakes and rewards)

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

# SUI uses 9 decimal places (MIST)
MIST_PER_SUI = 10**9

SUI_RPC_URL = "https://fullnode.mainnet.sui.io:443"

# Native SUI coin type
SUI_COIN_TYPE = "0x2::sui::SUI"


class SuiService:
    """Service for fetching Sui wallet data from JSON-RPC API (no API key required)."""

    def __init__(self):
        self._balance_cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)

    @staticmethod
    def is_sui_address(address: str) -> bool:
        """Check if an address is a valid Sui address (0x + 64 hex chars = 66 total)."""
        if not address or not address.startswith('0x') or len(address) != 66:
            return False
        try:
            int(address[2:], 16)
            return True
        except ValueError:
            return False

    async def _rpc_call(self, method: str, params: list) -> Optional[dict]:
        """
        Make a JSON-RPC call to the Sui fullnode.

        Args:
            method: JSON-RPC method name (e.g. 'suix_getBalance')
            params: List of parameters for the method

        Returns:
            The full JSON-RPC response dict, or None on error
        """
        try:
            client = get_client("sui_rpc", timeout=30.0)
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params
            }
            response = await client.post(SUI_RPC_URL, json=payload)

            if response.status_code != 200:
                logger.error(f"Sui RPC error: HTTP {response.status_code} for {method}")
                return None

            data = response.json()

            if "error" in data:
                logger.error(f"Sui RPC error in {method}: {data['error']}")
                return None

            return data

        except Exception as e:
            logger.error(f"Error calling Sui RPC {method}: {e}")
            return None

    async def get_balance(self, address: str) -> Optional[float]:
        """
        Get native SUI balance for an address.

        Uses suix_getBalance with the native SUI coin type.
        Response: result.totalBalance is a string in MIST.

        Returns:
            SUI balance as float, or None if error
        """
        try:
            data = await self._rpc_call("suix_getBalance", [address, SUI_COIN_TYPE])

            if data is None:
                return None

            result = data.get("result", {})
            total_balance_mist = result.get("totalBalance", "0")
            balance_sui = int(total_balance_mist) / MIST_PER_SUI

            return balance_sui

        except Exception as e:
            logger.error(f"Error fetching SUI balance: {e}")
            return None

    async def get_all_balances(self, address: str) -> List[dict]:
        """
        Get all non-SUI token balances for an address.

        Uses suix_getAllBalances to get all coin types, then fetches metadata
        for each non-native token via suix_getCoinMetadata.

        Returns:
            List of token balance dicts
        """
        try:
            data = await self._rpc_call("suix_getAllBalances", [address])

            if data is None:
                return []

            balances = data.get("result", [])

            if not balances:
                return []

            tokens = []
            for coin in balances:
                coin_type = coin.get("coinType", "")

                # Skip native SUI - handled separately by get_balance
                if coin_type == SUI_COIN_TYPE:
                    continue

                balance_raw = int(coin.get("totalBalance", "0"))
                if balance_raw == 0:
                    continue

                # Fetch metadata for this coin type
                metadata = await self._get_coin_metadata(coin_type)

                decimals = metadata.get("decimals", 9)
                balance = balance_raw / (10 ** decimals)

                if balance > 0:
                    tokens.append({
                        "contract_address": coin_type,
                        "symbol": metadata.get("symbol", "UNKNOWN"),
                        "name": metadata.get("name", "Unknown Token"),
                        "decimals": decimals,
                        "balance": balance,
                        "balance_raw": balance_raw
                    })

            return tokens

        except Exception as e:
            logger.error(f"Error fetching Sui token balances: {e}")
            return []

    async def _get_coin_metadata(self, coin_type: str) -> dict:
        """
        Get metadata for a coin type via suix_getCoinMetadata.

        Args:
            coin_type: Full coin type string (e.g. '0x...::module::CoinName')

        Returns:
            Dict with name, symbol, decimals, description
        """
        try:
            data = await self._rpc_call("suix_getCoinMetadata", [coin_type])

            if data is not None and data.get("result"):
                result = data["result"]
                return {
                    "name": result.get("name", "Unknown Token"),
                    "symbol": result.get("symbol", "UNKNOWN"),
                    "decimals": result.get("decimals", 9),
                    "description": result.get("description", "")
                }

        except Exception as e:
            logger.debug(f"Error fetching Sui coin metadata for {coin_type}: {e}")

        return {"name": "Unknown Token", "symbol": "UNKNOWN", "decimals": 9, "description": ""}

    async def get_staking(self, address: str) -> List[dict]:
        """
        Get staking (delegated stakes) for an address.

        Uses suix_getStakes which returns an array of staking objects.
        Each object has validatorAddress and a stakes[] array with
        principal, estimatedReward, stakeActiveEpoch, and status.

        Returns:
            List of staking position dicts with validator, principal, reward, status
        """
        try:
            data = await self._rpc_call("suix_getStakes", [address])

            if data is None:
                return []

            staking_groups = data.get("result", [])

            if not staking_groups:
                return []

            positions = []
            for group in staking_groups:
                validator = group.get("validatorAddress", "")
                stakes = group.get("stakes", [])

                for stake in stakes:
                    principal_mist = int(stake.get("principal", "0"))
                    reward_mist = int(stake.get("estimatedReward", "0"))
                    principal_sui = principal_mist / MIST_PER_SUI
                    reward_sui = reward_mist / MIST_PER_SUI

                    positions.append({
                        "validator": validator,
                        "principal_sui": principal_sui,
                        "reward_sui": reward_sui,
                        "status": stake.get("status", "unknown"),
                        "stake_active_epoch": stake.get("stakeActiveEpoch", ""),
                        "stake_request_epoch": stake.get("stakeRequestEpoch", "")
                    })

            return positions

        except Exception as e:
            logger.error(f"Error fetching Sui staking info: {e}")
            return []

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get complete address info including SUI balance, tokens, and staking.

        Returns:
            Dictionary with balance, token, and staking info, or None on error
        """
        if not self.is_sui_address(address):
            return None

        # Check memory cache
        if address in self._balance_cache:
            cached = self._balance_cache[address]
            if datetime.now() - cached['cached_at'] < self._cache_ttl:
                return cached['data']

        sui_balance = await self.get_balance(address)
        tokens = await self.get_all_balances(address)
        staking = await self.get_staking(address)

        if sui_balance is None:
            return None

        result = {
            'address': address,
            'balance_sui': sui_balance or 0,
            'tokens': tokens,
            'token_count': len(tokens),
            'staking': staking,
            'blockchain': 'sui',
            'source': 'sui_rpc'
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
            'chain': 'sui',
            'name': 'Sui',
            'configured': True,  # No API key needed
            'cached_balances': len(self._balance_cache)
        }


# Singleton instance
sui_service = SuiService()
