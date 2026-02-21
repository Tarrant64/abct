"""
CoinEx Exchange Service - Portfolio tracking via CoinEx API.
"""
import sys
import os
import logging
import time
import hmac
import hashlib
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService

logger = logging.getLogger(__name__)


class CoinExService(BaseExchangeService):
    EXCHANGE_NAME = "coinex"
    DISPLAY_NAME = "CoinEx"
    API_BASE = "https://api.coinex.com"
    BALANCE_ENDPOINT = "/v2/assets/spot/balance"
    API_NAME = "coinex"
    ENV_KEY = "COINEX_API_KEY"
    ENV_SECRET = "COINEX_API_SECRET"
    HTTP_CLIENT_NAME = "coinex"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """CoinEx v2: X-COINEX-KEY + X-COINEX-SIGN + X-COINEX-TIMESTAMP."""
        timestamp = str(int(time.time() * 1000))
        # Sign: method + path + body + timestamp
        prepared_str = f"{method.upper()}{endpoint}{body}{timestamp}"

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            prepared_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return {
            'X-COINEX-KEY': self._cached_key or '',
            'X-COINEX-SIGN': signature,
            'X-COINEX-TIMESTAMP': timestamp,
            'Content-Type': 'application/json'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        for item in data.get('data', []):
            available = float(item.get('available', 0))
            frozen = float(item.get('frozen', 0))
            total = available + frozen
            if total > 0:
                assets.append({
                    'currency': item.get('ccy', ''),
                    'name': item.get('ccy', ''),
                    'balance': total,
                    'available_balance': available,
                    'hold_balance': frozen,
                    'needs_price': True
                })
        return assets


coinex_service = CoinExService()
