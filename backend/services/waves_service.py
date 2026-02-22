"""
Waves Service - Fetches wallet data using the Waves public node REST API.

Native unit: wavelet (10^8 wavelets = 1 WAVES).
API: https://nodes.wavesnodes.com (no key required)
"""

import logging
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.http_client import get_client

logger = logging.getLogger(__name__)

WAVES_NODE_BASE_URL = "https://nodes.wavesnodes.com"
WAVELET_DIVISOR = 10 ** 8  # 1 WAVES = 10^8 wavelets


class WavesService:
    """Service for fetching Waves wallet data via the Waves public node REST API."""

    def __init__(self):
        self.base_url = WAVES_NODE_BASE_URL

    def _is_valid_address(self, address: str) -> bool:
        """Check if address looks like a valid Waves address (base58, ~35 chars)."""
        if not isinstance(address, str):
            return False
        # Waves mainnet addresses start with '3P' and are 35 chars
        if address.startswith('3') and 35 <= len(address) <= 36:
            return True
        return False

    async def get_address_info(self, address: str) -> Optional[dict]:
        """Get WAVES balance for an address."""
        if not self._is_valid_address(address):
            logger.error(f"Invalid Waves address: {address}")
            return None

        try:
            client = get_client("waves_node", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/addresses/balance/{address}",
                timeout=30.0,
            )

            if response.status_code == 400:
                return {
                    "address": address,
                    "balance_waves": 0.0,
                    "blockchain": "waves",
                    "source": "waves_node",
                }

            if response.status_code != 200:
                logger.error(f"Waves node balance error: {response.status_code}")
                return None

            data = response.json()
            balance_wavelet = int(data.get("balance", 0))
            balance_waves = balance_wavelet / WAVELET_DIVISOR

            return {
                "address": address,
                "balance_waves": balance_waves,
                "blockchain": "waves",
                "source": "waves_node",
            }

        except Exception as e:
            logger.error(f"Waves get_address_info error: {e}")
            return None


# Singleton instance
waves_service = WavesService()
