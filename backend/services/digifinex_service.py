"""
DigiFinex Exchange Service - Portfolio tracking via DigiFinex API.
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


class DigiFinexService(BaseExchangeService):
    EXCHANGE_NAME = "digifinex"
    DISPLAY_NAME = "DigiFinex"
    API_BASE = "https://openapi.digifinex.com"
    BALANCE_ENDPOINT = "/v3/spot/assets"
    API_NAME = "digifinex"
    ENV_KEY = "DIGIFINEX_API_KEY"
    ENV_SECRET = "DIGIFINEX_API_SECRET"
    HTTP_CLIENT_NAME = "digifinex"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """DigiFinex: timestamp + sign in headers, HMAC-SHA256 over timestamp+params."""
        timestamp = str(int(time.time()))
        query_string = urlencode(sorted(params.items())) if params else ''

        sign_str = timestamp + query_string
        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        suffix = f"?{query_string}" if query_string else ''

        return {
            'ACCESS-KEY': self._cached_key or '',
            'ACCESS-SIGN': signature,
            'ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json',
            '_url_suffix': suffix
        }

    def _parse_balances(self, data) -> list:
        assets = []
        for item in data.get('list', []):
            free = float(item.get('free', 0))
            total_val = float(item.get('total', 0))
            frozen = total_val - free
            if total_val > 0:
                assets.append({
                    'currency': item.get('currency', '').upper(),
                    'name': item.get('currency', '').upper(),
                    'balance': total_val,
                    'available_balance': free,
                    'hold_balance': max(frozen, 0),
                    'needs_price': True
                })
        return assets


digifinex_service = DigiFinexService()
