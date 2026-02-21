"""
CoinW Exchange Service - Portfolio tracking via CoinW API.
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


class CoinWService(BaseExchangeService):
    EXCHANGE_NAME = "coinw"
    DISPLAY_NAME = "CoinW"
    API_BASE = "https://api.coinw.com"
    BALANCE_ENDPOINT = "/api/v1/private/user/balance"
    API_NAME = "coinw"
    ENV_KEY = "COINW_API_KEY"
    ENV_SECRET = "COINW_API_SECRET"
    HTTP_CLIENT_NAME = "coinw"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """CoinW: timestamp + nonce signed with HMAC-SHA256."""
        timestamp = str(int(time.time() * 1000))
        nonce = timestamp

        sign_params = {'nonce': nonce}
        if params:
            sign_params.update(params)

        query_string = urlencode(sorted(sign_params.items()))

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return {
            'X-API-KEY': self._cached_key or '',
            'X-API-SIGN': signature,
            'X-API-TIMESTAMP': timestamp,
            'Content-Type': 'application/json',
            '_url_suffix': f'?{query_string}&sign={signature}'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        result = data.get('data', data.get('result', {}))
        if isinstance(result, dict):
            balances = result.get('balances', result.get('assets', []))
        else:
            balances = result if isinstance(result, list) else []

        for item in balances:
            available = float(item.get('available', item.get('free', 0)))
            frozen = float(item.get('frozen', item.get('locked', 0)))
            total = available + frozen
            currency = item.get('currency', item.get('asset', item.get('coin', '')))
            if total > 0 and currency:
                assets.append({
                    'currency': currency.upper(),
                    'name': currency.upper(),
                    'balance': total,
                    'available_balance': available,
                    'hold_balance': frozen,
                    'needs_price': True
                })
        return assets


coinw_service = CoinWService()
