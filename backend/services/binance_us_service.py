"""
Binance.US Service - Fetches portfolio data from Binance.US using REST API.
Uses HMAC SHA256 authentication (same as Binance.com but different base URL).
"""

import httpx
import logging
import time
import hmac
import hashlib
from typing import Dict, List, Optional
from urllib.parse import urlencode
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BINANCE_US_API_KEY, BINANCE_US_API_SECRET

logger = logging.getLogger(__name__)

BINANCE_US_API_BASE = "https://api.binance.us"


class BinanceUSService:
    """Service for fetching portfolio data from Binance.US."""

    def __init__(self):
        self.api_key = BINANCE_US_API_KEY
        self.api_secret = BINANCE_US_API_SECRET

    def is_configured(self) -> bool:
        """Check if Binance.US API is properly configured."""
        return bool(self.api_key and self.api_secret)

    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC SHA256 signature for Binance.US API."""
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    async def _make_request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make an authenticated request to the Binance.US API."""
        if not self.is_configured():
            logger.warning("Binance.US API not configured")
            return None

        try:
            if params is None:
                params = {}

            # Add timestamp
            params['timestamp'] = int(time.time() * 1000)

            # Create query string and signature
            query_string = urlencode(params)
            signature = self._generate_signature(query_string)
            query_string += f"&signature={signature}"

            url = f"{BINANCE_US_API_BASE}{endpoint}?{query_string}"
            headers = {
                "X-MBX-APIKEY": self.api_key
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"Binance.US API HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Binance.US API error: {e}")
            return None

    async def get_account_balances(self, user_id: int = None) -> Dict:
        """Get account balances from Binance.US."""
        data = await self._make_request("/api/v3/account")

        if not data:
            return {
                "exchange": "binance_us",
                "configured": self.is_configured(),
                "assets": [],
                "total_usd": 0,
                "asset_count": 0
            }

        # Extract non-zero balances
        assets = []
        for balance in data.get("balances", []):
            free = float(balance.get("free", 0))
            locked = float(balance.get("locked", 0))
            total = free + locked

            if total > 0:
                assets.append({
                    "currency": balance["asset"],
                    "name": balance["asset"],
                    "balance": total,
                    "available_balance": free,
                    "hold_balance": locked,
                    "needs_price": True
                })

        return {
            "exchange": "binance_us",
            "configured": True,
            "assets": assets,
            "total_usd": 0,  # Will be calculated by router
            "asset_count": len(assets)
        }


# Create singleton instance
binance_us_service = BinanceUSService()
