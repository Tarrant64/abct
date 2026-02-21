"""
HitBTC Exchange Service - Portfolio tracking via HitBTC API v3.
Uses HTTP Basic Authentication (API key as username, secret as password).
"""
import sys
import os
import logging
import base64
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService

logger = logging.getLogger(__name__)


class HitBTCService(BaseExchangeService):
    EXCHANGE_NAME = "hitbtc"
    DISPLAY_NAME = "HitBTC"
    API_BASE = "https://api.hitbtc.com"
    BALANCE_ENDPOINT = "/api/3/spot/balance"
    API_NAME = "hitbtc"
    ENV_KEY = "HITBTC_API_KEY"
    ENV_SECRET = "HITBTC_API_SECRET"
    HTTP_CLIENT_NAME = "hitbtc"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """HitBTC: HTTP Basic Auth with API key:secret base64 encoded."""
        credentials = f"{self._cached_key or ''}:{self._api_secret}"
        encoded = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        return {
            'Authorization': f'Basic {encoded}',
            'Content-Type': 'application/json'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        items = data if isinstance(data, list) else data.get('result', [])
        for item in items:
            available = float(item.get('available', 0))
            reserved = float(item.get('reserved', 0))
            total = available + reserved
            currency = item.get('currency', '')
            if total > 0:
                assets.append({
                    'currency': currency,
                    'name': currency,
                    'balance': total,
                    'available_balance': available,
                    'hold_balance': reserved,
                    'needs_price': True
                })
        return assets


hitbtc_service = HitBTCService()
