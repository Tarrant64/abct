"""
Stellar Service - Fetches wallet data using the Horizon REST API.

Supports:
- Native XLM balance
- Trustline (token) balances

Horizon API is free, no key required.
"""

import logging
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.http_client import get_client

logger = logging.getLogger(__name__)

HORIZON_BASE_URL = "https://horizon.stellar.org"
STROOPS_DIVISOR = 10 ** 7  # 1 XLM = 10^7 stroops


class StellarService:
    """Service for fetching Stellar wallet data via Horizon REST API."""

    def __init__(self):
        self.base_url = HORIZON_BASE_URL

    def _is_valid_address(self, address: str) -> bool:
        """Check if address looks like a valid Stellar public key."""
        return (
            isinstance(address, str)
            and address.startswith('G')
            and len(address) == 56
        )

    async def get_address_info(self, address: str) -> Optional[dict]:
        """Get XLM balance and trustline token balances."""
        if not self._is_valid_address(address):
            logger.error(f"Invalid Stellar address: {address}")
            return None

        try:
            client = get_client("stellar_horizon", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/accounts/{address}",
                timeout=30.0,
            )

            if response.status_code == 404:
                # Account not funded / doesn't exist
                return {
                    "address": address,
                    "balance_xlm": 0.0,
                    "tokens": [],
                    "token_count": 0,
                    "blockchain": "stellar",
                    "source": "horizon",
                }

            if response.status_code != 200:
                logger.error(f"Horizon error: {response.status_code}")
                return None

            data = response.json()
            balances = data.get("balances", [])

            balance_xlm = 0.0
            tokens = []

            for bal in balances:
                asset_type = bal.get("asset_type", "")
                amount = float(bal.get("balance", "0"))

                if asset_type == "native":
                    balance_xlm = amount
                else:
                    asset_code = bal.get("asset_code", "")
                    asset_issuer = bal.get("asset_issuer", "")
                    if amount > 0:
                        tokens.append({
                            "contract_address": f"{asset_code}:{asset_issuer[:12]}",
                            "symbol": asset_code,
                            "name": asset_code,
                            "decimals": 7,
                            "balance_raw": str(int(amount * STROOPS_DIVISOR)),
                            "balance": amount,
                        })

            return {
                "address": address,
                "balance_xlm": balance_xlm,
                "tokens": tokens,
                "token_count": len(tokens),
                "blockchain": "stellar",
                "source": "horizon",
            }

        except Exception as e:
            logger.error(f"Stellar get_address_info error: {e}")
            return None


# Singleton instance
stellar_service = StellarService()
