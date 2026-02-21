"""
Base Exchange Service - Abstract base class for all exchange integrations.

Provides shared authentication, request handling, and balance formatting
so new exchanges only need to override auth headers and balance parsing.

Auth mixins:
- HMAC-SHA256 query string (Binance-style): Bybit, MEXC, HTX, BingX, etc.
- HMAC-SHA256 base64 (OKX-style): Phemex, WOO X, AscendEX, KuCoin, etc.
- HMAC-SHA512 (Gate-style): Kraken, CoinSpot
- HMAC-SHA384 (Gemini-style): Bitfinex, BTSE
"""

import httpx
import logging
import time
import hmac
import hashlib
import base64
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from urllib.parse import urlencode
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.api_key_manager import APIKeyManager
from services.http_client import get_client

logger = logging.getLogger(__name__)


class BaseExchangeService(APIKeyManager, ABC):
    """Abstract base for all exchange integrations.

    Subclasses must define class attributes and override:
    - EXCHANGE_NAME: str - internal name (e.g., 'kraken')
    - DISPLAY_NAME: str - human-readable name (e.g., 'Kraken')
    - API_BASE: str - base URL (e.g., 'https://api.kraken.com')
    - BALANCE_ENDPOINT: str - endpoint for fetching balances
    - API_NAME: str - name in api_settings DB table
    - ENV_KEY: str - env var for API key (e.g., 'KRAKEN_API_KEY')
    - ENV_SECRET: str - env var for API secret
    - ENV_PASSPHRASE: str | None - env var for passphrase (optional)
    - REQUIRES_PASSPHRASE: bool - whether exchange needs a passphrase
    - HTTP_CLIENT_NAME: str - name for the http_client pool

    Override:
    - _generate_auth_headers(method, endpoint, params, body) -> dict
    - _parse_balances(data) -> list[dict]  (optional, has default)
    """

    EXCHANGE_NAME: str = ""
    DISPLAY_NAME: str = ""
    API_BASE: str = ""
    BALANCE_ENDPOINT: str = ""
    API_NAME: str = ""
    ENV_KEY: str = ""
    ENV_SECRET: str = ""
    ENV_PASSPHRASE: str = None
    REQUIRES_PASSPHRASE: bool = False
    HTTP_CLIENT_NAME: str = ""
    REQUEST_TIMEOUT: float = 30.0

    def __init__(self):
        super().__init__(api_name=self.API_NAME, env_var=self.ENV_KEY)
        self._api_secret: str = ""
        self._api_passphrase: str = ""

    async def ensure_configured(self) -> bool:
        """Load credentials from DB/env and check if ready."""
        creds = await self.get_api_credentials()
        self._api_secret = creds.get('api_secret', '')
        self._api_passphrase = creds.get('api_passphrase', '')

        # Also check env vars for secret/passphrase as fallback
        if not self._api_secret and self.ENV_SECRET:
            self._api_secret = os.getenv(self.ENV_SECRET, '')
        if not self._api_passphrase and self.ENV_PASSPHRASE:
            self._api_passphrase = os.getenv(self.ENV_PASSPHRASE, '')

        key = creds.get('api_key', '')
        if not key and self.ENV_KEY:
            key = os.getenv(self.ENV_KEY, '')

        if self.REQUIRES_PASSPHRASE:
            return bool(key and self._api_secret and self._api_passphrase)
        return bool(key and self._api_secret)

    @abstractmethod
    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """Generate exchange-specific authentication headers.

        Returns:
            dict with headers AND optionally a '_url_suffix' key
            that gets appended to the URL (for query-string auth like Binance).
        """
        ...

    async def _make_request(
        self, endpoint: str, method: str = 'GET',
        params: Optional[dict] = None, body: str = ''
    ) -> Optional[dict]:
        """Make an authenticated request to the exchange API."""
        if not await self.ensure_configured():
            logger.warning(f"{self.DISPLAY_NAME} API not configured")
            return None

        try:
            auth = self._generate_auth_headers(method, endpoint, params, body)
            url_suffix = auth.pop('_url_suffix', '')
            url = f"{self.API_BASE}{endpoint}{url_suffix}"

            client = get_client(self.HTTP_CLIENT_NAME, timeout=self.REQUEST_TIMEOUT)
            response = await client.request(method, url, headers=auth)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"{self.DISPLAY_NAME} API HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"{self.DISPLAY_NAME} API error: {e}")
            return None

    def _standard_balance_response(
        self, assets: List[dict], configured: bool = True
    ) -> dict:
        """Build the standard balance response dict."""
        return {
            "exchange": self.EXCHANGE_NAME,
            "configured": configured,
            "assets": assets,
            "total_usd": 0,  # Calculated by router
            "asset_count": len(assets)
        }

    async def get_account_balances(self, user_id: int = None) -> dict:
        """Get account balances. Subclasses can override for custom parsing."""
        data = await self._make_request(self.BALANCE_ENDPOINT)

        if data is None:
            return self._standard_balance_response(
                [], configured=await self.ensure_configured()
            )

        assets = self._parse_balances(data)
        return self._standard_balance_response(assets)

    def _parse_balances(self, data) -> List[dict]:
        """Parse raw API response into standard asset list.

        Default implementation handles common formats. Override for custom parsing.
        Returns list of dicts with: currency, name, balance, available_balance,
        hold_balance, needs_price.
        """
        return []

    async def test_connection(self) -> dict:
        """Test API connectivity with a lightweight authenticated request."""
        try:
            result = await self._make_request(self.BALANCE_ENDPOINT)
            if result is not None:
                return {"success": True, "message": "Connected successfully"}
            return {"success": False, "message": "Authentication failed or API unreachable"}
        except Exception as e:
            return {"success": False, "message": str(e)}


# ============================================================================
# Auth Mixins - shared signature generation methods
# ============================================================================

class BinanceStyleAuth:
    """Mixin for Binance-style HMAC-SHA256 query string auth.

    Used by: Binance, Bybit, MEXC, HTX, BingX, Poloniex, LBank, BitMart,
    WhiteBIT, CoinEx, Bitvavo, Bitrue, XT.com, DigiFinex, CoinW, Pionex.

    Auth pattern: timestamp + params in query string, HMAC-SHA256 signature
    appended as &signature= param. API key sent in header.
    """

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        if params is None:
            params = {}

        params['timestamp'] = int(time.time() * 1000)
        query_string = urlencode(params)

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return {
            self._get_key_header(): self._cached_key or '',
            '_url_suffix': f'?{query_string}&signature={signature}'
        }

    def _get_key_header(self) -> str:
        """Override for exchanges with different header names."""
        return 'X-MBX-APIKEY'


class OKXStyleAuth:
    """Mixin for OKX-style HMAC-SHA256 base64 auth.

    Used by: OKX, KuCoin, Bitget, Phemex, WOO X, AscendEX, Deribit, BitFlyer.

    Auth pattern: timestamp + method + path + body signed with HMAC-SHA256,
    base64-encoded. Key, signature, timestamp, passphrase all in headers.
    """

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        timestamp = self._get_timestamp()
        message = timestamp + method.upper() + endpoint + body

        signature = base64.b64encode(
            hmac.new(
                self._api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode()

        headers = self._build_okx_headers(timestamp, signature)
        return headers

    def _get_timestamp(self) -> str:
        """Get timestamp in exchange-specific format."""
        return time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())

    def _build_okx_headers(self, timestamp: str, signature: str) -> dict:
        """Build headers dict. Override per exchange for different header names."""
        return {
            'OK-ACCESS-KEY': self._cached_key or '',
            'OK-ACCESS-SIGN': signature,
            'OK-ACCESS-TIMESTAMP': timestamp,
            'OK-ACCESS-PASSPHRASE': self._api_passphrase,
            'Content-Type': 'application/json'
        }


class GateStyleAuth:
    """Mixin for Gate.io-style HMAC-SHA512 auth.

    Used by: Gate.io, CoinSpot.

    Auth pattern: SHA512 of payload, then sign method+path+query+hashed_payload+timestamp
    with HMAC-SHA512. Key, signature, timestamp in headers.
    """

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        timestamp = str(int(time.time()))
        query_string = ''
        payload_string = body or ''

        hashed_payload = hashlib.sha512(
            payload_string.encode('utf-8')
        ).hexdigest()

        sign_string = f"{method.upper()}\n{endpoint}\n{query_string}\n{hashed_payload}\n{timestamp}"

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            sign_string.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()

        return {
            'KEY': self._cached_key or '',
            'SIGN': signature,
            'Timestamp': timestamp,
            'Content-Type': 'application/json'
        }


class GeminiStyleAuth:
    """Mixin for Gemini-style HMAC-SHA384 auth.

    Used by: Gemini, Bitfinex, BTSE.

    Auth pattern: base64-encoded JSON payload, HMAC-SHA384 signature.
    """

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        import json

        nonce = str(int(time.time() * 1000))
        payload = {
            'request': endpoint,
            'nonce': nonce,
        }
        if params:
            payload.update(params)

        payload_json = json.dumps(payload)
        payload_b64 = base64.b64encode(payload_json.encode('utf-8')).decode()

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            payload_b64.encode('utf-8'),
            hashlib.sha384
        ).hexdigest()

        return {
            'X-GEMINI-APIKEY': self._cached_key or '',
            'X-GEMINI-PAYLOAD': payload_b64,
            'X-GEMINI-SIGNATURE': signature,
            'Content-Type': 'text/plain'
        }


class KrakenStyleAuth:
    """Mixin for Kraken-style HMAC-SHA512 auth.

    Unique to Kraken: SHA256 of (nonce + POST data), then HMAC-SHA512
    with base64-decoded secret over (path + SHA256 hash).
    """

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        nonce = str(int(time.time() * 1000))

        if params is None:
            params = {}
        params['nonce'] = nonce
        post_data = urlencode(params)

        # SHA256 of nonce + post_data
        sha256_hash = hashlib.sha256(
            (nonce + post_data).encode('utf-8')
        ).digest()

        # HMAC-SHA512 of path + SHA256 hash with base64-decoded secret
        hmac_msg = endpoint.encode('utf-8') + sha256_hash
        secret_decoded = base64.b64decode(self._api_secret)

        signature = base64.b64encode(
            hmac.new(secret_decoded, hmac_msg, hashlib.sha512).digest()
        ).decode()

        return {
            'API-Key': self._cached_key or '',
            'API-Sign': signature,
            'Content-Type': 'application/x-www-form-urlencoded',
            '_url_suffix': '',
            '_post_data': post_data,
        }
