"""
XT.com Exchange Service - Portfolio tracking via XT.com API.
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


class XTService(BaseExchangeService):
    EXCHANGE_NAME = "xt"
    DISPLAY_NAME = "XT.com"
    API_BASE = "https://sapi.xt.com"
    BALANCE_ENDPOINT = "/v4/balance"
    API_NAME = "xt"
    ENV_KEY = "XT_API_KEY"
    ENV_SECRET = "XT_API_SECRET"
    HTTP_CLIENT_NAME = "xt"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """XT.com: Aliyun-style signature with sorted params."""
        timestamp = str(int(time.time() * 1000))
        query_string = urlencode(sorted(params.items())) if params else ''

        # XT sign: #time={timestamp}&method={METHOD}&query={querystring}#{body}
        sign_str = f"#time={timestamp}&method={method.upper()}&query={query_string}#{body}"

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        suffix = f"?{query_string}" if query_string else ''

        return {
            'xt-validate-appkey': self._cached_key or '',
            'xt-validate-timestamp': timestamp,
            'xt-validate-signature': signature,
            'xt-validate-algorithms': 'HmacSHA256',
            'Content-Type': 'application/json',
            '_url_suffix': suffix
        }

    def _parse_balances(self, data) -> list:
        assets = []
        result = data.get('result', {})
        for item in result.get('assets', []):
            available = float(item.get('availableAmount', 0))
            frozen = float(item.get('frozenAmount', 0))
            total = available + frozen
            if total > 0:
                assets.append({
                    'currency': item.get('currency', '').upper(),
                    'name': item.get('currency', '').upper(),
                    'balance': total,
                    'available_balance': available,
                    'hold_balance': frozen,
                    'needs_price': True
                })
        return assets


xt_service = XTService()
