"""
IOTA Service - Fetches wallet data using the IOTA Move-VM JSON-RPC API.

Post-rebasing IOTA uses MoveVM (similar to Sui).
Native unit: nanoIOTA (10^9 nanoIOTA = 1 IOTA).
RPC: https://api.mainnet.iota.cafe (no key required)
"""

import logging
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.http_client import get_client

logger = logging.getLogger(__name__)

IOTA_RPC_URL = "https://api.mainnet.iota.cafe"
NANOIOTA_DIVISOR = 10 ** 9  # 1 IOTA = 10^9 nanoIOTA


class IOTAService:
    """Service for fetching IOTA MoveVM wallet data via JSON-RPC."""

    def __init__(self):
        self.rpc_url = IOTA_RPC_URL

    def _is_valid_address(self, address: str) -> bool:
        """Check if address looks like a valid IOTA MoveVM address (0x + 64 hex chars)."""
        if not isinstance(address, str):
            return False
        if address.lower().startswith('0x') and len(address) == 66:
            try:
                int(address[2:], 16)
                return True
            except ValueError:
                pass
        return False

    async def get_address_info(self, address: str) -> Optional[dict]:
        """Get IOTA balance for an address."""
        if not self._is_valid_address(address):
            logger.error(f"Invalid IOTA address: {address}")
            return None

        try:
            client = get_client("iota_rpc", timeout=30.0)
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "iotax_getAllBalances",
                "params": [address],
            }
            response = await client.post(
                self.rpc_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(f"IOTA RPC error: {response.status_code}")
                return None

            data = response.json()
            if "error" in data:
                logger.error(f"IOTA RPC error: {data['error']}")
                return None

            balances = data.get("result", [])
            balance_iota = 0.0
            for bal in balances:
                coin_type = bal.get("coinType", "")
                # Native IOTA coin type
                if "iota::IOTA" in coin_type or coin_type == "0x2::iota::IOTA":
                    total_balance = int(bal.get("totalBalance", 0))
                    balance_iota = total_balance / NANOIOTA_DIVISOR
                    break

            return {
                "address": address,
                "balance_iota": balance_iota,
                "blockchain": "iota",
                "source": "iota_rpc",
            }

        except Exception as e:
            logger.error(f"IOTA get_address_info error: {e}")
            return None


# Singleton instance
iota_service = IOTAService()
