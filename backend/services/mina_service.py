"""
Mina Protocol Service - Fetches wallet data using the MinaExplorer GraphQL API.

Native unit: nanomina (10^9 nanomina = 1 MINA).
API: https://graphql.minaexplorer.com (no key required)
"""

import logging
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.http_client import get_client

logger = logging.getLogger(__name__)

MINA_GRAPHQL_URL = "https://graphql.minaexplorer.com"
NANOMINA_DIVISOR = 10 ** 9  # 1 MINA = 10^9 nanomina


class MinaService:
    """Service for fetching Mina Protocol wallet data via MinaExplorer GraphQL."""

    def __init__(self):
        self.graphql_url = MINA_GRAPHQL_URL

    def _is_valid_address(self, address: str) -> bool:
        """Check if address looks like a valid Mina address (starts with B62, ~55 chars)."""
        if not isinstance(address, str):
            return False
        if address.startswith('B62') and 50 <= len(address) <= 60:
            return True
        return False

    async def get_address_info(self, address: str) -> Optional[dict]:
        """Get MINA balance for an address."""
        if not self._is_valid_address(address):
            logger.error(f"Invalid Mina address: {address}")
            return None

        try:
            client = get_client("mina_explorer", timeout=30.0)
            query = """
            query AccountBalance($publicKey: String!) {
              account(publicKey: $publicKey) {
                balance {
                  total
                }
              }
            }
            """
            response = await client.post(
                self.graphql_url,
                json={"query": query, "variables": {"publicKey": address}},
                headers={"Content-Type": "application/json"},
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(f"Mina Explorer GraphQL error: {response.status_code}")
                return None

            data = response.json()
            if "errors" in data:
                logger.error(f"Mina GraphQL errors: {data['errors']}")
                return None

            account = data.get("data", {}).get("account")
            if not account:
                # Account doesn't exist yet (unfunded)
                return {
                    "address": address,
                    "balance_mina": 0.0,
                    "blockchain": "mina",
                    "source": "mina_explorer",
                }

            total_nanomina = int(account.get("balance", {}).get("total", 0))
            balance_mina = total_nanomina / NANOMINA_DIVISOR

            return {
                "address": address,
                "balance_mina": balance_mina,
                "blockchain": "mina",
                "source": "mina_explorer",
            }

        except Exception as e:
            logger.error(f"Mina get_address_info error: {e}")
            return None


# Singleton instance
mina_service = MinaService()
