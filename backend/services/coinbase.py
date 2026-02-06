"""
Coinbase Service - Fetches portfolio data from Coinbase using CDP API.

Uses CDP API Key authentication with JWT signing.
Requires JSON file upload with 'name' and 'privateKey' fields.
Only returns assets with USD value >= $1.00.
"""

import httpx
import logging
import json
import time
from typing import Dict, List, Optional
import sys
import os
from services.http_client import get_client

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

COINBASE_API_BASE = "https://api.coinbase.com"

# Minimum USD value threshold for displaying assets
MIN_USD_VALUE = 1.00


class CoinbaseService:
    """Service for fetching portfolio data from Coinbase CDP API."""

    def __init__(self):
        self.api_name = 'coinbase'
        self._credentials_cache = {}
        self._cache_time = {}

    async def get_cdp_credentials(self, user_id: int = 1) -> Optional[Dict]:
        """
        Get CDP API credentials (name + privateKey) from database.

        Returns:
            Dict with 'name' and 'privateKey' or None if not configured
        """
        # Check cache first (5 minute TTL)
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        cache_key = f"cdp_creds_{user_id}"

        if cache_key in self._credentials_cache:
            if now - self._cache_time.get(cache_key, datetime.min) < timedelta(minutes=5):
                return self._credentials_cache[cache_key]

        # Try database
        try:
            from database import get_api_setting
            setting = await get_api_setting(self.api_name, user_id=user_id)

            if setting and setting.get('enabled') and setting.get('api_key'):
                # api_key field stores the JSON credentials
                try:
                    credentials = json.loads(setting['api_key'])
                    if 'name' in credentials and 'privateKey' in credentials:
                        self._credentials_cache[cache_key] = credentials
                        self._cache_time[cache_key] = now
                        return credentials
                except json.JSONDecodeError:
                    logger.error("Failed to parse CDP API credentials JSON from database, trying file fallback")
        except Exception as e:
            logger.debug(f"Could not fetch CDP credentials from database: {e}")

        # Try loading from file (fallback for development)
        cdp_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cdp_api_key.json')
        if os.path.exists(cdp_file):
            try:
                with open(cdp_file, 'r') as f:
                    credentials = json.load(f)
                    if 'name' in credentials and 'privateKey' in credentials:
                        logger.info("Loaded CDP credentials from file (development mode)")
                        self._credentials_cache[cache_key] = credentials
                        self._cache_time[cache_key] = now
                        return credentials
            except Exception as e:
                logger.error(f"Failed to load CDP credentials from file: {e}")

        return None

    async def is_configured(self, user_id: int = 1) -> bool:
        """Check if CDP API credentials are configured."""
        credentials = await self.get_cdp_credentials(user_id)
        return credentials is not None

    def _generate_jwt(self, api_key_name: str, private_key: str, request_method: str, request_path: str) -> str:
        """
        Generate JWT token for CDP API authentication.

        Args:
            api_key_name: The 'name' field from CDP API key JSON
            private_key: The 'privateKey' field (PEM format EC private key)
            request_method: HTTP method (GET, POST, etc.)
            request_path: API endpoint path (e.g., '/api/v3/brokerage/accounts')

        Returns:
            JWT token string
        """
        try:
            import jwt
            import secrets
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.backends import default_backend
        except ImportError:
            logger.error("PyJWT and cryptography libraries required for CDP API. Install: pip install PyJWT cryptography")
            raise

        # Extract key ID from full path (e.g., 'organizations/.../apiKeys/KEY_ID')
        key_id = api_key_name.split('/')[-1]

        # Load private key
        try:
            private_key_obj = serialization.load_pem_private_key(
                private_key.encode(),
                password=None,
                backend=default_backend()
            )
        except Exception as e:
            logger.error(f"Failed to load private key: {e}")
            raise

        # Create JWT payload (use format from working version)
        uri = f"{request_method} {COINBASE_API_BASE.replace('https://', '').replace('http://', '')}{request_path}"

        now = int(time.time())
        payload = {
            'sub': key_id,  # Use extracted key ID, not full path
            'iss': 'cdp',
            'nbf': now,
            'exp': now + 120,  # 2 minute expiry
            'aud': ['cdp_service'],  # Add audience field
            'uris': [uri]  # Plural 'uris' as array
        }

        # Generate JWT with proper random nonce
        token = jwt.encode(
            payload,
            private_key_obj,
            algorithm='ES256',
            headers={'kid': key_id, 'nonce': secrets.token_hex(16)}
        )

        return token

    async def _get_headers(self, request_method: str, request_path: str, user_id: int = None) -> dict:
        """Get request headers with CDP JWT authentication."""
        credentials = await self.get_cdp_credentials(user_id=user_id or 1)

        if not credentials:
            return {}

        try:
            jwt_token = self._generate_jwt(
                credentials['name'],
                credentials['privateKey'],
                request_method,
                request_path
            )

            return {
                "Authorization": f"Bearer {jwt_token}",
                "Content-Type": "application/json",
            }
        except Exception as e:
            logger.error(f"Failed to generate CDP JWT: {e}")
            return {}

    async def _make_request(self, method: str, path: str, params: dict = None, user_id: int = None) -> Optional[dict]:
        """Make an authenticated request to the Coinbase CDP API."""
        if not await self.is_configured(user_id=user_id or 1):
            logger.warning("Coinbase CDP API not configured")
            return None

        try:
            headers = await self._get_headers(method, path, user_id=user_id)

            if not headers:
                logger.error("Failed to generate CDP authentication headers")
                return None

            logger.info(f"Coinbase CDP API request: {method} {path}")

            client = get_client("coinbase_api", timeout=30.0)

            url = f"{COINBASE_API_BASE}{path}"
            if method == "GET":
                response = await client.get(url, headers=headers, params=params)
            else:
                response = await client.request(method, url, headers=headers, params=params)

            logger.info(f"Coinbase API response: {response.status_code}")

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Coinbase API error: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Coinbase API request failed: {e}")
            return None

    async def get_accounts(self, user_id: int = None) -> List[dict]:
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

            data = await self._make_request("GET", path, params, user_id=user_id)
            if not data:
                break

            accounts.extend(data.get("accounts", []))

            # Check for pagination
            if data.get("has_next") and data.get("cursor"):
                cursor = data["cursor"]
            else:
                break

        return accounts

    async def get_portfolio(self, user_id: int = None) -> Dict[str, any]:
        """
        Get portfolio summary with all asset balances.

        Returns:
            {
                'total_value_usd': float,
                'assets': [
                    {
                        'currency': str,
                        'balance': float,
                        'value_usd': float,
                        'available_balance': float,
                        'hold_balance': float
                    }
                ]
            }
        """
        accounts = await self.get_accounts(user_id=user_id)
        if not accounts:
            logger.warning("Coinbase: No accounts returned from API")
            return {'total_value_usd': 0.0, 'assets': []}

        logger.info(f"Coinbase: Processing {len(accounts)} accounts")
        total_value = 0.0
        assets = []
        for account in accounts:
            try:
                currency = account.get('currency', 'UNKNOWN')

                # CDP API v3 has available_balance and hold structure
                available_bal = account.get('available_balance', {})
                available = float(available_bal.get('value', 0))

                hold_bal = account.get('hold', {})
                held = float(hold_bal.get('value', 0))

                total_balance = available + held

                # Skip if no balance at all
                if total_balance <= 0:
                    continue

                asset_data = {
                    'currency': currency,
                    'name': account.get('name', currency),
                    'balance': total_balance,
                    'available_balance': available,
                    'hold_balance': held,
                    'uuid': account.get('uuid', ''),
                }

                # Check if this is USD directly
                if currency == 'USD':
                    asset_data['value_usd'] = total_balance
                    if total_balance >= MIN_USD_VALUE:
                        assets.append(asset_data)
                        total_value += total_balance
                else:
                    # For crypto assets, price will be calculated by router
                    asset_data['value_usd'] = 0.0  # To be calculated
                    asset_data['needs_price'] = True
                    assets.append(asset_data)

            except Exception as e:
                logger.error(f"Error processing Coinbase account: {e}")
                continue

        logger.info(f"Coinbase: Returning {len(assets)} assets with total USD ${total_value:.2f}")
        return {
            'total_value_usd': total_value,
            'assets': assets,
            'account_count': len(accounts),
            'filtered_count': len(assets)
        }

    async def get_portfolio_balances(self, user_id: int = None) -> dict:
        """
        Get portfolio balances in standardized format for exchange router.

        Args:
            user_id: Optional user ID (for multi-user support)

        Returns:
            Standardized exchange portfolio format matching other exchange services
        """
        if not await self.is_configured(user_id=user_id):
            return {
                'exchange': 'coinbase',
                'configured': False,
                'assets': [],
                'total_usd': 0,
                'asset_count': 0
            }

        try:
            portfolio = await self.get_portfolio(user_id=user_id)

            # Convert to standardized format
            standardized_assets = []
            for asset in portfolio.get('assets', []):
                standardized_assets.append({
                    'currency': asset['currency'],
                    'name': asset.get('name', asset['currency']),
                    'balance': asset['balance'],
                    'available_balance': asset.get('available_balance', asset['balance']),
                    'hold_balance': asset.get('hold_balance', 0.0),
                    'value_usd': asset.get('value_usd', 0.0),
                    'uuid': asset.get('uuid', ''),
                    'needs_price': asset.get('needs_price', asset.get('value_usd', 0.0) == 0)
                })

            return {
                'exchange': 'coinbase',
                'configured': True,
                'assets': standardized_assets,
                'total_usd': portfolio.get('total_value_usd', 0),
                'asset_count': len(standardized_assets)
            }

        except Exception as e:
            logger.error(f"Error fetching Coinbase portfolio balances: {e}")
            return {
                'exchange': 'coinbase',
                'configured': True,
                'assets': [],
                'total_usd': 0,
                'asset_count': 0,
                'error': str(e)
            }

    async def get_open_orders(self, user_id: int = None) -> dict:
        """
        Get open orders from Coinbase.

        Returns:
            Orders list (CDP API v3 format)
        """
        data = await self._make_request("GET", "/api/v3/brokerage/orders/historical/batch", user_id=user_id)

        if not data:
            return {
                'exchange': 'coinbase',
                'orders': [],
                'total_count': 0
            }

        orders = data.get('orders', [])
        # Filter for open orders only
        open_orders = [o for o in orders if o.get('status') in ['OPEN', 'PENDING']]

        return {
            'exchange': 'coinbase',
            'orders': open_orders,
            'total_count': len(open_orders)
        }

    async def get_spot_price(self, currency_pair: str) -> Optional[float]:
        """
        Get spot price for a currency pair (e.g., 'BTC-USD').
        Uses public Coinbase API endpoint - no authentication required.
        """
        path = f"/v2/prices/{currency_pair}/spot"

        try:
            client = get_client("coinbase_api", timeout=30.0)
            response = await client.get(f"{COINBASE_API_BASE}{path}")
            if response.status_code == 200:
                data = response.json()
                return float(data.get("data", {}).get("amount", 0))
        except Exception as e:
            logger.error(f"Error getting spot price for {currency_pair}: {e}")

        return None

    async def get_transactions(self, user_id: int = None, limit: int = 100) -> List[dict]:
        """
        Get transaction history from Coinbase.

        Returns:
            List of transactions from CDP API v3
        """
        transactions = []
        path = "/api/v3/brokerage/orders/historical/batch"
        cursor = None

        try:
            while len(transactions) < limit:
                params = {
                    "limit": min(250, limit - len(transactions)),
                    "order_status": "FILLED"  # Only completed transactions
                }
                if cursor:
                    params["cursor"] = cursor

                data = await self._make_request("GET", path, params, user_id=user_id)
                if not data:
                    break

                orders = data.get("orders", [])
                transactions.extend(orders)

                # Check for pagination
                if data.get("has_next") and data.get("cursor"):
                    cursor = data["cursor"]
                else:
                    break

            logger.info(f"Fetched {len(transactions)} Coinbase transactions")
            return transactions[:limit]

        except Exception as e:
            logger.error(f"Error fetching Coinbase transactions: {e}")
            return []


# Singleton instance
coinbase_service = CoinbaseService()
