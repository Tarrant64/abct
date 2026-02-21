"""
LBank Exchange Service - Portfolio tracking via LBank API.

LBank uses RSA or HMAC-SHA256 signature, slightly different from standard Binance style.
The signature is over: api_key + timestamp + params sorted + secret
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


class LBankService(BaseExchangeService):
    EXCHANGE_NAME = "lbank"
    DISPLAY_NAME = "LBank"
    API_BASE = "https://api.lbank.info"
    BALANCE_ENDPOINT = "/v2/user_info.do"
    API_NAME = "lbank"
    ENV_KEY = "LBANK_API_KEY"
    ENV_SECRET = "LBANK_API_SECRET"
    HTTP_CLIENT_NAME = "lbank"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """LBank HMAC-SHA256 signing: sign sorted param string."""
        timestamp = str(int(time.time() * 1000))
        sign_params = {
            'api_key': self._cached_key or '',
            'timestamp': timestamp,
        }
        if params:
            sign_params.update(params)

        # Sort and build pre-sign string
        sorted_items = sorted(sign_params.items())
        pre_sign = urlencode(sorted_items)

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            pre_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # LBank sends params + sign in body (POST) or query string (GET)
        sign_params['sign'] = signature
        query_string = urlencode(sign_params)

        return {
            '_url_suffix': f'?{query_string}'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        result = data.get('result', {})
        if isinstance(result, str):
            return assets
        info = result.get('info', {}) if isinstance(result, dict) else {}
        free_map = info.get('free', {})
        freeze_map = info.get('freeze', {})

        all_currencies = set(list(free_map.keys()) + list(freeze_map.keys()))
        for currency in all_currencies:
            free = float(free_map.get(currency, 0))
            frozen = float(freeze_map.get(currency, 0))
            total = free + frozen
            if total > 0:
                assets.append({
                    'currency': currency.upper(),
                    'name': currency.upper(),
                    'balance': total,
                    'available_balance': free,
                    'hold_balance': frozen,
                    'needs_price': True
                })
        return assets


lbank_service = LBankService()
