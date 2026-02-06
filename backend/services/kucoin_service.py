"""
KuCoin Service - Fetches portfolio data from KuCoin using REST API.
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
from config import KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE
from services.http_client import get_client

logger = logging.getLogger(__name__)

KUCOIN_API_BASE = "https://api.kucoin.com"


class KuCoinService:
    """Service for fetching portfolio data from KuCoin."""

    def __init__(self):
        self.api_key = KUCOIN_API_KEY
        self.api_secret = KUCOIN_API_SECRET
        self.api_passphrase = KUCOIN_API_PASSPHRASE

    def is_configured(self) -> bool:
        """Check if KuCoin API is properly configured."""
        return bool(self.api_key and self.api_secret and self.api_passphrase)

    def _generate_signature(self, timestamp: str, method: str, endpoint: str, body: str = '') -> str:
        """Generate HMAC SHA256 signature for KuCoin API."""
        str_to_sign = timestamp + method.upper() + endpoint + body
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode('utf-8'),
                str_to_sign.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode()
        return signature

    def _generate_passphrase_signature(self) -> str:
        """Generate signature for passphrase."""
        passphrase_signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode('utf-8'),
                self.api_passphrase.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode()
        return passphrase_signature

    async def _make_request(self, endpoint: str, method: str = 'GET', params: dict = None) -> Optional[dict]:
        """Make an authenticated request to the KuCoin API."""
        if not self.is_configured():
            logger.warning("KuCoin API not configured")
            return None

        try:
            timestamp = str(int(time.time() * 1000))
            signature = self._generate_signature(timestamp, method, endpoint)
            passphrase_signature = self._generate_passphrase_signature()

            headers = {
                "KC-API-KEY": self.api_key,
                "KC-API-SIGN": signature,
                "KC-API-TIMESTAMP": timestamp,
                "KC-API-PASSPHRASE": passphrase_signature,
                "KC-API-KEY-VERSION": "2",
                "Content-Type": "application/json"
            }

            url = f"{KUCOIN_API_BASE}{endpoint}"

            client = get_client("kucoin", timeout=30.0)
            response = await client.request(method, url, headers=headers)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"KuCoin API HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"KuCoin API error: {e}")
            return None

    async def get_account_balances(self, user_id: int = None) -> Dict:
        """Get account balances from KuCoin."""
        data = await self._make_request("/api/v1/accounts")

        if not data or data.get("code") != "200000":
            return {
                "exchange": "kucoin",
                "configured": self.is_configured(),
                "assets": [],
                "total_usd": 0,
                "asset_count": 0
            }

        # Extract balances
        assets = []
        accounts = data.get("data", [])

        # Group by currency (KuCoin has separate accounts for trade, main, etc.)
        currency_totals = {}
        for account in accounts:
            if account.get("type") in ["trade", "main"]:  # Only include trade and main accounts
                currency = account["currency"]
                balance = float(account.get("balance", 0))
                available = float(account.get("available", 0))
                holds = float(account.get("holds", 0))

                if currency not in currency_totals:
                    currency_totals[currency] = {
                        "balance": 0,
                        "available": 0,
                        "holds": 0
                    }

                currency_totals[currency]["balance"] += balance
                currency_totals[currency]["available"] += available
                currency_totals[currency]["holds"] += holds

        # Convert to assets list
        for currency, totals in currency_totals.items():
            if totals["balance"] > 0:
                assets.append({
                    "currency": currency,
                    "name": currency,
                    "balance": totals["balance"],
                    "available_balance": totals["available"],
                    "hold_balance": totals["holds"],
                    "needs_price": True
                })

        return {
            "exchange": "kucoin",
            "configured": True,
            "assets": assets,
            "total_usd": 0,  # Will be calculated by router
            "asset_count": len(assets)
        }


# Create singleton instance
kucoin_service = KuCoinService()
