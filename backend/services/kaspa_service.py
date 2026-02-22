"""
Kaspa Service - Fetches wallet data using the Kaspa REST API.

Kaspa addresses start with 'kaspa:'.
Native unit: sompi (10^8 sompi = 1 KAS).
API: https://api.kaspa.org (no key required)
"""

import logging
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.http_client import get_client

logger = logging.getLogger(__name__)

KASPA_API_BASE_URL = "https://api.kaspa.org"
SOMPI_DIVISOR = 10 ** 8  # 1 KAS = 10^8 sompi


class KaspaService:
    """Service for fetching Kaspa wallet data via the Kaspa REST API."""

    def __init__(self):
        self.base_url = KASPA_API_BASE_URL

    def _is_valid_address(self, address: str) -> bool:
        """Check if address looks like a valid Kaspa address."""
        return isinstance(address, str) and address.startswith('kaspa:') and len(address) > 10

    async def get_address_info(self, address: str) -> Optional[dict]:
        """Get KAS balance for a Kaspa address."""
        if not self._is_valid_address(address):
            logger.error(f"Invalid Kaspa address: {address}")
            return None

        try:
            client = get_client("kaspa_api", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/addresses/{address}/balance",
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(f"Kaspa API balance error: {response.status_code}")
                return None

            data = response.json()
            balance_sompi = int(data.get("balance", 0))
            balance_kas = balance_sompi / SOMPI_DIVISOR

            return {
                "address": address,
                "balance_kas": balance_kas,
                "blockchain": "kaspa",
                "source": "kaspa_api",
            }

        except Exception as e:
            logger.error(f"Kaspa get_address_info error: {e}")
            return None


# Singleton instance
kaspa_service = KaspaService()
