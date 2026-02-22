"""
Zilliqa Service - Fetches wallet data using the Zilliqa JSON-RPC API.

Native unit: Qa (10^12 Qa = 1 ZIL).
API: https://api.zilliqa.com (no key required)
"""

import logging
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.http_client import get_client

logger = logging.getLogger(__name__)

ZILLIQA_API_URL = "https://api.zilliqa.com"
QA_DIVISOR = 10 ** 12  # 1 ZIL = 10^12 Qa


class ZilliqaService:
    """Service for fetching Zilliqa wallet data via JSON-RPC."""

    def __init__(self):
        self.api_url = ZILLIQA_API_URL

    def _is_valid_address(self, address: str) -> bool:
        """Check if address looks like a valid Zilliqa address (0x + 40 hex or zil1 bech32)."""
        if not isinstance(address, str):
            return False
        # Bech32 format: zil1... (39 chars)
        if address.startswith('zil1') and len(address) == 39:
            return True
        # Hex format: 0x + 40 hex chars
        if address.lower().startswith('0x') and len(address) == 42:
            try:
                int(address[2:], 16)
                return True
            except ValueError:
                pass
        return False

    async def get_address_info(self, address: str) -> Optional[dict]:
        """Get ZIL balance for a Zilliqa address."""
        if not self._is_valid_address(address):
            logger.error(f"Invalid Zilliqa address: {address}")
            return None

        try:
            client = get_client("zilliqa_api", timeout=30.0)
            payload = {
                "id": "1",
                "jsonrpc": "2.0",
                "method": "GetBalance",
                "params": [address.lower().replace("0x", "").replace("zil1", "")
                           if not address.startswith("zil1") else address],
            }
            # For bech32 addresses, use them directly; for hex strip 0x
            if address.lower().startswith('0x'):
                addr_param = address[2:].lower()
            else:
                addr_param = address

            payload["params"] = [addr_param]

            response = await client.post(
                self.api_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(f"Zilliqa API error: {response.status_code}")
                return None

            data = response.json()
            error = data.get("error")
            if error:
                # Account not found = 0 balance
                if "-5" in str(error.get("code", "")):
                    return {
                        "address": address,
                        "balance_zil": 0.0,
                        "blockchain": "zilliqa",
                        "source": "zilliqa_api",
                    }
                logger.error(f"Zilliqa RPC error: {error}")
                return None

            result = data.get("result", {})
            balance_qa = int(result.get("balance", 0))
            balance_zil = balance_qa / QA_DIVISOR

            return {
                "address": address,
                "balance_zil": balance_zil,
                "blockchain": "zilliqa",
                "source": "zilliqa_api",
            }

        except Exception as e:
            logger.error(f"Zilliqa get_address_info error: {e}")
            return None


# Singleton instance
zilliqa_service = ZilliqaService()
