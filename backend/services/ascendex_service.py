"""
AscendEX Exchange Service - Portfolio tracking via AscendEX API.
Uses HMAC-SHA256 with timestamp in headers.
"""
import sys
import os
import logging
import time
import hmac
import hashlib
import base64
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService

logger = logging.getLogger(__name__)


class AscendEXService(BaseExchangeService):
    EXCHANGE_NAME = "ascendex"
    DISPLAY_NAME = "AscendEX"
    API_BASE = "https://ascendex.com"
    BALANCE_ENDPOINT = "/api/pro/v1/cash/balance"
    API_NAME = "ascendex"
    ENV_KEY = "ASCENDEX_API_KEY"
    ENV_SECRET = "ASCENDEX_API_SECRET"
    HTTP_CLIENT_NAME = "ascendex"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """AscendEX: timestamp + path signed with HMAC-SHA256 base64."""
        timestamp = str(int(time.time() * 1000))
        # AscendEX signs: timestamp + path_without_prefix
        sign_str = f"{timestamp}+{endpoint}"

        signature = base64.b64encode(
            hmac.new(
                self._api_secret.encode('utf-8'),
                sign_str.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode()

        return {
            'x-auth-key': self._cached_key or '',
            'x-auth-signature': signature,
            'x-auth-timestamp': timestamp,
            'Content-Type': 'application/json'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        for item in data.get('data', []):
            available = float(item.get('availableBalance', 0))
            total = float(item.get('totalBalance', 0))
            locked = total - available
            if total > 0:
                assets.append({
                    'currency': item.get('asset', ''),
                    'name': item.get('asset', ''),
                    'balance': total,
                    'available_balance': available,
                    'hold_balance': max(locked, 0),
                    'needs_price': True
                })
        return assets


ascendex_service = AscendEXService()
