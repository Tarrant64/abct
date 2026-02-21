"""
WOO X Exchange Service - Portfolio tracking via WOO X API.
Uses HMAC-SHA256 with timestamp in query params.
"""
import sys
import os
import logging
import time
import hmac
import hashlib
from urllib.parse import urlencode
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService

logger = logging.getLogger(__name__)


class WOOXService(BaseExchangeService):
    EXCHANGE_NAME = "woox"
    DISPLAY_NAME = "WOO X"
    API_BASE = "https://api.woo.org"
    BALANCE_ENDPOINT = "/v3/balances"
    API_NAME = "woox"
    ENV_KEY = "WOOX_API_KEY"
    ENV_SECRET = "WOOX_API_SECRET"
    HTTP_CLIENT_NAME = "woox"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """WOO X: timestamp|method|path|query signed with HMAC-SHA256."""
        timestamp = str(int(time.time() * 1000))
        query_string = urlencode(sorted(params.items())) if params else ''

        sign_str = f"{timestamp}|{method.upper()}|{endpoint}|{query_string}"
        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        suffix = f"?{query_string}" if query_string else ''

        return {
            'x-api-key': self._cached_key or '',
            'x-api-signature': signature,
            'x-api-timestamp': timestamp,
            'Content-Type': 'application/json',
            '_url_suffix': suffix
        }

    def _parse_balances(self, data) -> list:
        assets = []
        for item in data.get('data', {}).get('holding', []):
            holding = float(item.get('holding', 0))
            frozen = float(item.get('frozen', 0))
            total = holding + frozen
            if total > 0:
                assets.append({
                    'currency': item.get('token', ''),
                    'name': item.get('token', ''),
                    'balance': total,
                    'available_balance': holding,
                    'hold_balance': frozen,
                    'needs_price': True
                })
        return assets


woox_service = WOOXService()
