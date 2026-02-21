"""
Bitvavo Exchange Service - Portfolio tracking via Bitvavo API.
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


class BitvavoService(BaseExchangeService):
    EXCHANGE_NAME = "bitvavo"
    DISPLAY_NAME = "Bitvavo"
    API_BASE = "https://api.bitvavo.com"
    BALANCE_ENDPOINT = "/v2/balance"
    API_NAME = "bitvavo"
    ENV_KEY = "BITVAVO_API_KEY"
    ENV_SECRET = "BITVAVO_API_SECRET"
    HTTP_CLIENT_NAME = "bitvavo"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """Bitvavo: timestamp + method + path + body signed with HMAC-SHA256."""
        timestamp = str(int(time.time() * 1000))
        hash_string = timestamp + method.upper() + '/v2' + endpoint.replace('/v2', '') + body

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            hash_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return {
            'Bitvavo-Access-Key': self._cached_key or '',
            'Bitvavo-Access-Signature': signature,
            'Bitvavo-Access-Timestamp': timestamp,
            'Bitvavo-Access-Window': '10000',
            'Content-Type': 'application/json'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        for item in (data if isinstance(data, list) else []):
            available = float(item.get('available', 0))
            in_order = float(item.get('inOrder', 0))
            total = available + in_order
            if total > 0:
                assets.append({
                    'currency': item.get('symbol', ''),
                    'name': item.get('symbol', ''),
                    'balance': total,
                    'available_balance': available,
                    'hold_balance': in_order,
                    'needs_price': True
                })
        return assets


bitvavo_service = BitvavoService()
