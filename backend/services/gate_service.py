"""
Gate.io Service - Fetches portfolio data from Gate.io using REST API.
Uses HMAC SHA512 authentication with API key and secret.
"""

import httpx
import logging
import time
import hmac
import hashlib
from typing import Dict, List, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import GATE_API_KEY, GATE_API_SECRET
from services.http_client import get_client

logger = logging.getLogger(__name__)

GATE_API_BASE = "https://api.gateio.ws"


class GateService:
    """Service for fetching portfolio data from Gate.io."""

    def __init__(self):
        self.api_key = GATE_API_KEY
        self.api_secret = GATE_API_SECRET

    def is_configured(self) -> bool:
        """Check if Gate.io API is properly configured."""
        return bool(self.api_key and self.api_secret)

    def _generate_signature(self, method: str, url_path: str, query_string: str, payload_string: str, timestamp: str) -> str:
        """Generate HMAC SHA512 signature for Gate.io API."""
        hashed_payload = hashlib.sha512(payload_string.encode('utf-8')).hexdigest()
        sign_string = f"{method}\n{url_path}\n{query_string}\n{hashed_payload}\n{timestamp}"

        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            sign_string.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()

        return signature

    async def _make_request(self, endpoint: str, method: str = 'GET', params: dict = None) -> Optional[dict]:
        """Make an authenticated request to the Gate.io API."""
        if not self.is_configured():
            logger.warning("Gate.io API not configured")
            return None

        try:
            timestamp = str(int(time.time()))
            query_string = ''
            payload_string = ''

            signature = self._generate_signature(method, endpoint, query_string, payload_string, timestamp)

            headers = {
                "KEY": self.api_key,
                "SIGN": signature,
                "Timestamp": timestamp,
                "Content-Type": "application/json"
            }

            url = f"{GATE_API_BASE}{endpoint}"

            client = get_client("gate", timeout=30.0)
            response = await client.request(method, url, headers=headers)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"Gate.io API HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Gate.io API error: {e}")
            return None

    async def get_account_balances(self, user_id: int = None) -> Dict:
        """Get account balances from Gate.io."""
        data = await self._make_request("/api/v4/spot/accounts")

        if not data:
            return {
                "exchange": "gate",
                "configured": self.is_configured(),
                "assets": [],
                "total_usd": 0,
                "asset_count": 0
            }

        # Extract balances
        assets = []
        for detail in data:
            available = float(detail.get("available", 0))
            locked = float(detail.get("locked", 0))
            balance = available + locked

            if balance > 0:
                assets.append({
                    "currency": detail["currency"],
                    "name": detail["currency"],
                    "balance": balance,
                    "available_balance": available,
                    "hold_balance": locked,
                    "needs_price": True
                })

        return {
            "exchange": "gate",
            "configured": True,
            "assets": assets,
            "total_usd": 0,  # Will be calculated by router
            "asset_count": len(assets)
        }

    async def test_connection(self) -> dict:
        """Test API connectivity with a lightweight authenticated request."""
        try:
            result = await self._make_request("/api/v4/spot/accounts")
            if result is not None:
                return {"success": True, "message": "Connected successfully"}
            return {"success": False, "message": "Authentication failed or API unreachable"}
        except Exception as e:
            return {"success": False, "message": str(e)}


# Create singleton instance
gate_service = GateService()
