"""
Coinbase Service - Fetches portfolio data from Coinbase using CDP API.

Uses JWT authentication with EC private key.
Only returns assets with USD value >= $1.00.
"""

import httpx
import logging
import time
import secrets
from typing import Dict, List, Optional
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import jwt
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import COINBASE_API_KEY_NAME, COINBASE_API_PRIVATE_KEY

logger = logging.getLogger(__name__)

COINBASE_API_BASE = "https://api.coinbase.com"

# Minimum USD value threshold for displaying assets
MIN_USD_VALUE = 1.00


class CoinbaseService:
    """Service for fetching portfolio data from Coinbase."""

    def __init__(self):
        self.api_key_name = COINBASE_API_KEY_NAME
        self.private_key_pem = COINBASE_API_PRIVATE_KEY
        self._private_key = None

    def _load_private_key(self):
        """Load the EC private key from PEM string."""
        if self._private_key is None and self.private_key_pem:
            self._private_key = serialization.load_pem_private_key(
                self.private_key_pem.encode(),
                password=None,
                backend=default_backend()
            )
        return self._private_key

    def _generate_jwt(self, request_method: str, request_path: str) -> str:
        """Generate a JWT token for Coinbase API authentication."""
        private_key = self._load_private_key()
        if not private_key:
            raise ValueError("Private key not loaded")

        # Extract key ID from key name (format: organizations/{org}/apiKeys/{key_id})
        key_id = self.api_key_name.split("/")[-1] if "/" in self.api_key_name else self.api_key_name

        uri = f"{request_method} {COINBASE_API_BASE.replace('https://', '')}{request_path}"

        now = int(time.time())
        payload = {
            "sub": key_id,
            "iss": "cdp",
            "nbf": now,
            "exp": now + 120,  # 2 minute expiry
            "aud": ["cdp_service"],
            "uris": [uri],
        }

        headers = {
            "kid": key_id,
            "nonce": secrets.token_hex(16),
        }

        token = jwt.encode(
            payload,
            private_key,
            algorithm="ES256",
            headers=headers
        )

        return token

    def is_configured(self) -> bool:
        """Check if Coinbase API is properly configured."""
        return bool(self.api_key_name and self.private_key_pem)

    async def _make_request(self, method: str, path: str, params: dict = None) -> Optional[dict]:
        """Make an authenticated request to the Coinbase API."""
        if not self.is_configured():
            logger.warning("Coinbase API not configured")
            return None

        try:
            token = self._generate_jwt(method, path)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{COINBASE_API_BASE}{path}"
                if method == "GET":
                    response = await client.get(url, headers=headers, params=params)
                else:
                    response = await client.request(method, url, headers=headers, params=params)

                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Coinbase API error: {response.status_code} - {response.text}")
                    return None

        except Exception as e:
            logger.error(f"Coinbase API request failed: {e}")
            return None

    async def get_accounts(self) -> List[dict]:
        """
        Get all accounts (wallets) from Coinbase.
        Paginates through all results.
        """
        accounts = []
        path = "/api/v3/brokerage/accounts"
        cursor = None

        while True:
            params = {"limit": 250}
            if cursor:
                params["cursor"] = cursor

            data = await self._make_request("GET", path, params)
            if not data:
                break

            accounts.extend(data.get("accounts", []))

            # Check for pagination
            if data.get("has_next") and data.get("cursor"):
                cursor = data["cursor"]
            else:
                break

        return accounts

    async def get_portfolio_balances(self, user_id: int = None) -> Dict:
        """
        Get portfolio balances from Coinbase.
        Includes both available and held balances (funds in open orders).
        Only returns assets with USD value >= MIN_USD_VALUE.
        """
        accounts = await self.get_accounts()

        if not accounts:
            return {
                "exchange": "coinbase",
                "configured": self.is_configured(),
                "assets": [],
                "total_usd": 0,
                "error": "No accounts found or API error"
            }

        assets = []
        total_usd = 0.0

        for account in accounts:
            try:
                # Get both available and held balances
                available = float(account.get("available_balance", {}).get("value", 0))
                held = float(account.get("hold", {}).get("value", 0))
                total_balance = available + held

                # Skip if no balance at all
                if total_balance <= 0:
                    continue

                currency = account.get("currency", "")

                asset_data = {
                    "currency": currency,
                    "name": account.get("name", currency),
                    "balance": total_balance,
                    "available_balance": available,
                    "hold_balance": held,
                    "uuid": account.get("uuid", ""),
                    "type": account.get("type", ""),
                }

                # Check if this is USD directly
                if currency == "USD":
                    asset_data["usd_value"] = total_balance
                    if total_balance >= MIN_USD_VALUE:
                        assets.append(asset_data)
                        total_usd += total_balance
                else:
                    # For crypto assets, we'll need to get prices
                    # Store with a placeholder, we'll calculate USD in the router
                    asset_data["usd_value"] = None  # To be calculated
                    asset_data["needs_price"] = True
                    assets.append(asset_data)

            except Exception as e:
                logger.error(f"Error processing account: {e}")
                continue

        return {
            "exchange": "coinbase",
            "configured": True,
            "assets": assets,
            "total_usd": total_usd,
            "account_count": len(accounts),
            "filtered_count": len(assets)
        }

    async def get_open_orders(self) -> List[dict]:
        """
        Get all open orders from Coinbase.
        Returns orders that are pending, open, or partially filled.
        """
        path = "/api/v3/brokerage/orders/historical/batch"
        params = {
            "order_status": ["OPEN", "PENDING", "QUEUED"],
            "limit": 100
        }

        data = await self._make_request("GET", path, params)
        if not data:
            return []

        orders = data.get("orders", [])
        return [
            {
                "order_id": order.get("order_id"),
                "product_id": order.get("product_id"),
                "side": order.get("side"),
                "order_type": order.get("order_type"),
                "status": order.get("status"),
                "size": order.get("order_configuration", {}).get("limit_limit_gtc", {}).get("base_size"),
                "price": order.get("order_configuration", {}).get("limit_limit_gtc", {}).get("limit_price"),
                "filled_size": order.get("filled_size"),
                "created_time": order.get("created_time"),
            }
            for order in orders
        ]

    async def get_spot_price(self, currency_pair: str) -> Optional[float]:
        """Get spot price for a currency pair (e.g., 'BTC-USD')."""
        path = f"/v2/prices/{currency_pair}/spot"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{COINBASE_API_BASE}{path}")
                if response.status_code == 200:
                    data = response.json()
                    return float(data.get("data", {}).get("amount", 0))
        except Exception as e:
            logger.error(f"Error getting spot price for {currency_pair}: {e}")

        return None


# Singleton instance
coinbase_service = CoinbaseService()
