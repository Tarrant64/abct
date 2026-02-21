"""
BitFlyer Exchange Service - Portfolio tracking via BitFlyer API.
Uses HMAC-SHA256 signed headers.
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


class BitFlyerService(BaseExchangeService):
    EXCHANGE_NAME = "bitflyer"
    DISPLAY_NAME = "BitFlyer"
    API_BASE = "https://api.bitflyer.com"
    BALANCE_ENDPOINT = "/v1/me/getbalance"
    API_NAME = "bitflyer"
    ENV_KEY = "BITFLYER_API_KEY"
    ENV_SECRET = "BITFLYER_API_SECRET"
    HTTP_CLIENT_NAME = "bitflyer"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """BitFlyer: timestamp + method + path + body signed with HMAC-SHA256."""
        timestamp = str(int(time.time()))
        text = timestamp + method.upper() + endpoint + body

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            text.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return {
            'ACCESS-KEY': self._cached_key or '',
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-SIGN': signature,
            'Content-Type': 'application/json'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        for item in (data if isinstance(data, list) else []):
            currency = item.get('currency_code', '')
            available = float(item.get('available', 0))
            amount = float(item.get('amount', 0))
            if amount > 0:
                assets.append({
                    'currency': currency,
                    'name': currency,
                    'balance': amount,
                    'available_balance': available,
                    'hold_balance': max(amount - available, 0),
                    'needs_price': True
                })
        return assets


bitflyer_service = BitFlyerService()
