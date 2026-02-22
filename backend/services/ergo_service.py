"""
Ergo Service - Fetches wallet data using the Ergo Explorer API.

Native unit: nanoERG (10^9 nanoERG = 1 ERG).
API: https://explorer.ergoplatform.com/api/v1 (no key required)
"""

import logging
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.http_client import get_client

logger = logging.getLogger(__name__)

ERGO_EXPLORER_BASE_URL = "https://explorer.ergoplatform.com/api/v1"
NANOERG_DIVISOR = 10 ** 9  # 1 ERG = 10^9 nanoERG


class ErgoService:
    """Service for fetching Ergo wallet data via the Ergo Explorer API."""

    def __init__(self):
        self.base_url = ERGO_EXPLORER_BASE_URL

    def _is_valid_address(self, address: str) -> bool:
        """Check if address looks like a valid Ergo address (base58, starts with 9)."""
        if not isinstance(address, str):
            return False
        # Ergo mainnet P2PK addresses start with '9' and are ~51 chars
        if address.startswith('9') and 40 <= len(address) <= 60:
            return True
        return False

    async def get_address_info(self, address: str) -> Optional[dict]:
        """Get ERG balance for an Ergo address."""
        if not self._is_valid_address(address):
            logger.error(f"Invalid Ergo address: {address}")
            return None

        try:
            client = get_client("ergo_explorer", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/addresses/{address}/balance/total",
                timeout=30.0,
            )

            if response.status_code == 404:
                return {
                    "address": address,
                    "balance_erg": 0.0,
                    "blockchain": "ergo",
                    "source": "ergo_explorer",
                }

            if response.status_code != 200:
                logger.error(f"Ergo Explorer balance error: {response.status_code}")
                return None

            data = response.json()
            confirmed = data.get("confirmed", {})
            balance_nanoerg = int(confirmed.get("nanoErgs", 0))
            balance_erg = balance_nanoerg / NANOERG_DIVISOR

            return {
                "address": address,
                "balance_erg": balance_erg,
                "blockchain": "ergo",
                "source": "ergo_explorer",
            }

        except Exception as e:
            logger.error(f"Ergo get_address_info error: {e}")
            return None


# Singleton instance
ergo_service = ErgoService()
