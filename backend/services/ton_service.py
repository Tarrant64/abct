"""
TON (The Open Network) Service - Fetches wallet data using TON Center REST API.

Supports:
- Native TON balance
- Jetton (token) balances via TON Center v2 API

API key optional but recommended for higher rate limits.
"""

import logging
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.http_client import get_client
from services.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

TON_CENTER_BASE_URL = "https://toncenter.com/api/v2"
NANOTON_DIVISOR = 10 ** 9  # 1 TON = 10^9 nanotons


class TONService(APIKeyManager):
    """Service for fetching TON wallet data using TON Center REST API."""

    def __init__(self):
        super().__init__(api_name='ton_center', env_var='TON_CENTER_API_KEY')
        self.base_url = TON_CENTER_BASE_URL

    def _is_valid_address(self, address: str) -> bool:
        """Check if address looks like a valid TON address (raw or user-friendly)."""
        if not isinstance(address, str):
            return False
        # User-friendly: EQ... or UQ... (48 chars base64)
        if address.startswith(('EQ', 'UQ')) and len(address) == 48:
            return True
        # Raw format: 0: or -1: followed by 64 hex chars
        if ':' in address:
            parts = address.split(':')
            if len(parts) == 2 and len(parts[1]) == 64:
                return True
        return False

    async def _get_headers(self) -> dict:
        """Get API headers with optional API key."""
        headers = {"Accept": "application/json"}
        key = await self.get_api_key()
        if key:
            headers["X-API-Key"] = key
        return headers

    async def get_address_info(self, address: str) -> Optional[dict]:
        """Get TON balance and jetton holdings for an address."""
        if not self._is_valid_address(address):
            logger.error(f"Invalid TON address: {address}")
            return None

        try:
            client = get_client("ton_center", timeout=30.0)
            headers = await self._get_headers()

            # Fetch native balance
            response = await client.get(
                f"{self.base_url}/getAddressBalance",
                params={"address": address},
                headers=headers,
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(f"TON Center balance error: {response.status_code}")
                return None

            data = response.json()
            if not data.get("ok"):
                logger.error(f"TON Center error: {data.get('error', 'unknown')}")
                return None

            balance_nano = int(data.get("result", "0"))
            balance_ton = balance_nano / NANOTON_DIVISOR

            # Fetch jetton balances
            tokens = []
            try:
                jetton_resp = await client.get(
                    f"{self.base_url}/getJettonWalletsByOwner",
                    params={"owner_address": address},
                    headers=headers,
                    timeout=30.0,
                )
                if jetton_resp.status_code == 200:
                    jetton_data = jetton_resp.json()
                    if jetton_data.get("ok"):
                        for jw in jetton_data.get("result", []):
                            jetton = jw.get("jetton_master", {})
                            metadata = jetton.get("metadata", {})
                            balance_raw = int(jw.get("balance", "0"))
                            decimals = int(metadata.get("decimals", 9))
                            symbol = metadata.get("symbol", "")
                            if balance_raw > 0 and symbol:
                                tokens.append({
                                    "contract_address": jetton.get("address", ""),
                                    "symbol": symbol,
                                    "name": metadata.get("name", symbol),
                                    "decimals": decimals,
                                    "balance_raw": balance_raw,
                                    "balance": balance_raw / (10 ** decimals),
                                })
            except Exception as e:
                logger.warning(f"TON jetton fetch failed: {e}")

            return {
                "address": address,
                "balance_ton": balance_ton,
                "tokens": tokens,
                "token_count": len(tokens),
                "blockchain": "ton",
                "source": "ton_center",
            }

        except Exception as e:
            logger.error(f"TON get_address_info error: {e}")
            return None


# Singleton instance
ton_service = TONService()
