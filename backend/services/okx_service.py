"""
OKX Service - Fetches portfolio data from OKX using REST API.
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
from config import OKX_API_KEY, OKX_API_SECRET, OKX_API_PASSPHRASE
from services.http_client import get_client

logger = logging.getLogger(__name__)

OKX_API_BASE = "https://www.okx.com"


class OKXService:
    """Service for fetching portfolio data from OKX."""

    def __init__(self):
        self.api_key = OKX_API_KEY
        self.api_secret = OKX_API_SECRET
        self.api_passphrase = OKX_API_PASSPHRASE

    def is_configured(self) -> bool:
        """Check if OKX API is properly configured."""
        return bool(self.api_key and self.api_secret and self.api_passphrase)

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = '') -> str:
        """Generate HMAC SHA256 signature for OKX API."""
        message = timestamp + method + request_path + body
        mac = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode()

    async def _make_request(self, endpoint: str, method: str = 'GET', params: dict = None) -> Optional[dict]:
        """Make an authenticated request to the OKX API."""
        if not self.is_configured():
            logger.warning("OKX API not configured")
            return None

        try:
            timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
            signature = self._generate_signature(timestamp, method, endpoint)

            headers = {
                "OK-ACCESS-KEY": self.api_key,
                "OK-ACCESS-SIGN": signature,
                "OK-ACCESS-TIMESTAMP": timestamp,
                "OK-ACCESS-PASSPHRASE": self.api_passphrase,
                "Content-Type": "application/json"
            }

            url = f"{OKX_API_BASE}{endpoint}"

            client = get_client("okx", timeout=30.0)
            response = await client.request(method, url, headers=headers)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"OKX API HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"OKX API error: {e}")
            return None

    async def get_account_balances(self, user_id: int = None) -> Dict:
        """Get account balances from OKX."""
        data = await self._make_request("/api/v5/account/balance")

        if not data or data.get("code") != "0":
            return {
                "exchange": "okx",
                "configured": self.is_configured(),
                "assets": [],
                "total_usd": 0,
                "asset_count": 0
            }

        # Extract balances
        assets = []
        balance_data = data.get("data", [])
        if balance_data:
            details = balance_data[0].get("details", [])
            for detail in details:
                balance = float(detail.get("cashBal", 0))
                if balance > 0:
                    assets.append({
                        "currency": detail["ccy"],
                        "name": detail["ccy"],
                        "balance": balance,
                        "available_balance": float(detail.get("availBal", 0)),
                        "hold_balance": balance - float(detail.get("availBal", 0)),
                        "needs_price": True
                    })

        return {
            "exchange": "okx",
            "configured": True,
            "assets": assets,
            "total_usd": 0,  # Will be calculated by router
            "asset_count": len(assets)
        }


# Create singleton instance
okx_service = OKXService()
