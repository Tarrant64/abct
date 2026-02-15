"""
Filecoin Service - Fetches Filecoin (FIL) wallet data using Glif RPC API.

Glif RPC API is free and requires no API key.

Provides:
- FIL balance
- Miner info (for f0 miner addresses)

Filecoin has no native token standard like ERC-20, so token lists are always empty.

Uses persistent database caching to reduce API calls.
"""

import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_cache, set_cache
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Filecoin uses 18 decimal places (attoFIL)
ATTOFIL_PER_FIL = 10**18

GLIF_RPC_URL = "https://api.node.glif.io/rpc/v1"


class FilecoinService:
    """Service for fetching Filecoin wallet data from Glif RPC API (no API key required)."""

    def __init__(self):
        self._balance_cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)

    @staticmethod
    def is_filecoin_address(address: str) -> bool:
        """
        Check if an address is a valid Filecoin address.

        Filecoin address types:
        - f0: ID addresses (f0 + digits)
        - f1: secp256k1 addresses (f1 + 39 base32 chars)
        - f3: BLS addresses (f3 + 86 base32 chars)
        - f4: Delegated addresses (f4 + variable length)

        Simple validation: starts with f0/f1/f3/f4 and at least 3 chars.
        """
        if not address or len(address) < 3:
            return False
        return address.startswith(('f0', 'f1', 'f3', 'f4'))

    async def _rpc_call(self, method: str, params: list) -> Optional[dict]:
        """
        Make a JSON-RPC call to the Glif RPC endpoint.

        Args:
            method: The JSON-RPC method name (e.g. Filecoin.StateGetActor)
            params: The parameters for the method

        Returns:
            The JSON-RPC response dict, or None on error
        """
        try:
            client = get_client("glif_rpc", timeout=30.0)
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": 1
            }
            response = await client.post(GLIF_RPC_URL, json=payload)

            if response.status_code != 200:
                logger.error(f"Glif RPC error: HTTP {response.status_code}")
                return None

            return response.json()

        except Exception as e:
            logger.error(f"Error in Glif RPC call ({method}): {e}")
            return None

    async def get_balance(self, address: str) -> Optional[float]:
        """
        Get FIL balance for an address using Filecoin.StateGetActor.

        The StateGetActor RPC returns the actor state which includes Balance
        as a string in attoFIL (10^-18 FIL).

        Returns:
            FIL balance as float, or None if error
        """
        try:
            data = await self._rpc_call("Filecoin.StateGetActor", [address, None])

            if data is None:
                return None

            # Check for RPC-level error (actor not found, etc.)
            if data.get("error"):
                error_msg = data["error"].get("message", "Unknown error")
                logger.debug(f"Filecoin StateGetActor error for {address}: {error_msg}")
                return 0.0

            result = data.get("result")
            if not result:
                return 0.0

            balance_attofil = result.get("Balance", "0")
            balance_fil = int(balance_attofil) / ATTOFIL_PER_FIL

            return balance_fil

        except Exception as e:
            logger.error(f"Error fetching FIL balance for {address}: {e}")
            return None

    async def get_miner_info(self, address: str) -> Optional[dict]:
        """
        Get miner info for an f0 miner address using Filecoin.StateMinerInfo.

        Only applicable for f0 miner/actor addresses. Returns None for
        non-miner addresses or on error.

        Returns:
            Miner info dict, or None if not a miner or on error
        """
        if not address.startswith("f0"):
            return None

        try:
            data = await self._rpc_call("Filecoin.StateMinerInfo", [address, None])

            if data is None:
                return None

            if data.get("error"):
                error_msg = data["error"].get("message", "Unknown error")
                logger.debug(f"Filecoin StateMinerInfo error for {address}: {error_msg}")
                return None

            result = data.get("result")
            if not result:
                return None

            return {
                "owner": result.get("Owner"),
                "worker": result.get("Worker"),
                "sector_size": result.get("SectorSize"),
                "window_post_proof_type": result.get("WindowPoStProofType"),
                "peer_id": result.get("PeerId"),
                "multiaddrs": result.get("Multiaddrs"),
            }

        except Exception as e:
            logger.error(f"Error fetching miner info for {address}: {e}")
            return None

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get complete address info including FIL balance and optional miner info.

        Filecoin has no native token standard, so tokens is always an empty list.

        Returns:
            Dictionary with balance and address info
        """
        if not self.is_filecoin_address(address):
            return None

        # Check memory cache
        if address in self._balance_cache:
            cached = self._balance_cache[address]
            if datetime.now() - cached['cached_at'] < self._cache_ttl:
                return cached['data']

        balance_fil = await self.get_balance(address)

        if balance_fil is None:
            return None

        result = {
            'address': address,
            'balance_fil': balance_fil or 0,
            'tokens': [],
            'token_count': 0,
            'blockchain': 'filecoin',
            'source': 'glif_rpc'
        }

        # Include miner info for f0 addresses
        if address.startswith("f0"):
            miner_info = await self.get_miner_info(address)
            if miner_info:
                result['miner_info'] = miner_info

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
            'chain': 'filecoin',
            'name': 'Filecoin',
            'configured': True,  # No API key needed
            'cached_balances': len(self._balance_cache)
        }


# Singleton instance
filecoin_service = FilecoinService()
