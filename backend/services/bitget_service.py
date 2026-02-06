"""
Bitget Service - Fetches portfolio data from Bitget using REST API.
Uses HMAC SHA256 authentication with API key, secret, and passphrase.
"""

import httpx
import logging
import time
import hmac
import hashlib
import base64
from typing import Dict, List, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASSPHRASE
from services.http_client import get_client

logger = logging.getLogger(__name__)

BITGET_API_BASE = "https://api.bitget.com"


class BitgetService:
    """Service for fetching portfolio data from Bitget."""

    def __init__(self):
        self.api_key = BITGET_API_KEY
        self.api_secret = BITGET_API_SECRET
        self.api_passphrase = BITGET_API_PASSPHRASE

    def is_configured(self) -> bool:
        """Check if Bitget API is properly configured."""
        return bool(self.api_key and self.api_secret and self.api_passphrase)

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = '') -> str:
        """Generate HMAC SHA256 signature for Bitget API."""
        message = timestamp + method.upper() + request_path + body
        mac = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode()

    async def _make_request(self, endpoint: str, method: str = 'GET', params: dict = None) -> Optional[dict]:
        """Make an authenticated request to the Bitget API."""
        if not self.is_configured():
            logger.warning("Bitget API not configured")
            return None

        try:
            timestamp = str(int(time.time() * 1000))
            signature = self._generate_signature(timestamp, method, endpoint)

            headers = {
                "ACCESS-KEY": self.api_key,
                "ACCESS-SIGN": signature,
                "ACCESS-TIMESTAMP": timestamp,
                "ACCESS-PASSPHRASE": self.api_passphrase,
                "Content-Type": "application/json",
                "locale": "en-US"
            }

            url = f"{BITGET_API_BASE}{endpoint}"

            client = get_client("bitget", timeout=30.0)
            response = await client.request(method, url, headers=headers)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"Bitget API HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Bitget API error: {e}")
            return None

    async def get_account_balances(self, user_id: int = None) -> Dict:
        """Get account balances from Bitget."""
        data = await self._make_request("/api/v2/spot/account/assets")

        if not data or data.get("code") != "00000":
            return {
                "exchange": "bitget",
                "configured": self.is_configured(),
                "assets": [],
                "total_usd": 0,
                "asset_count": 0
            }

        # Extract balances
        assets = []
        balance_data = data.get("data", [])
        for detail in balance_data:
            balance = float(detail.get("available", 0)) + float(detail.get("frozen", 0))
            if balance > 0:
                assets.append({
                    "currency": detail["coin"],
                    "name": detail["coin"],
                    "balance": balance,
                    "available_balance": float(detail.get("available", 0)),
                    "hold_balance": float(detail.get("frozen", 0)),
                    "needs_price": True
                })

        return {
            "exchange": "bitget",
            "configured": True,
            "assets": assets,
            "total_usd": 0,  # Will be calculated by router
            "asset_count": len(assets)
        }


# Create singleton instance
bitget_service = BitgetService()
