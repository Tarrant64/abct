"""
BTSE Exchange Service - Portfolio tracking via BTSE API.
Uses HMAC-SHA384 signed headers.
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


class BTSEService(BaseExchangeService):
    EXCHANGE_NAME = "btse"
    DISPLAY_NAME = "BTSE"
    API_BASE = "https://api.btse.com"
    BALANCE_ENDPOINT = "/spot/api/v3.2/user/wallet"
    API_NAME = "btse"
    ENV_KEY = "BTSE_API_KEY"
    ENV_SECRET = "BTSE_API_SECRET"
    HTTP_CLIENT_NAME = "btse"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """BTSE: nonce + path + body signed with HMAC-SHA384."""
        nonce = str(int(time.time() * 1000))
        sign_str = f"{endpoint}{nonce}{body}"

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha384
        ).hexdigest()

        return {
            'btse-api': self._cached_key or '',
            'btse-nonce': nonce,
            'btse-sign': signature,
            'Content-Type': 'application/json'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        for item in (data if isinstance(data, list) else []):
            total = float(item.get('total', 0))
            available = float(item.get('available', total))
            currency = item.get('currency', '')
            if total > 0:
                assets.append({
                    'currency': currency,
                    'name': currency,
                    'balance': total,
                    'available_balance': available,
                    'hold_balance': max(total - available, 0),
                    'needs_price': True
                })
        return assets


btse_service = BTSEService()
