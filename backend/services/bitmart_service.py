"""
BitMart Exchange Service - Portfolio tracking via BitMart API.

BitMart uses HMAC-SHA256 with timestamp+memo+body signed together.
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


class BitMartService(BaseExchangeService):
    EXCHANGE_NAME = "bitmart"
    DISPLAY_NAME = "BitMart"
    API_BASE = "https://api-cloud.bitmart.com"
    BALANCE_ENDPOINT = "/spot/v1/wallet"
    API_NAME = "bitmart"
    ENV_KEY = "BITMART_API_KEY"
    ENV_SECRET = "BITMART_API_SECRET"
    HTTP_CLIENT_NAME = "bitmart"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """BitMart: sign timestamp#memo#body with HMAC-SHA256."""
        timestamp = str(int(time.time() * 1000))
        memo = ''  # BitMart uses memo as part of signing; empty for basic auth
        sign_str = f"{timestamp}#{memo}#{body}"

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return {
            'X-BM-KEY': self._cached_key or '',
            'X-BM-SIGN': signature,
            'X-BM-TIMESTAMP': timestamp,
            'Content-Type': 'application/json'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        for wallet in data.get('data', {}).get('wallet', []):
            available = float(wallet.get('available', 0))
            frozen = float(wallet.get('frozen', 0))
            total = available + frozen
            if total > 0:
                assets.append({
                    'currency': wallet.get('id', ''),
                    'name': wallet.get('name', wallet.get('id', '')),
                    'balance': total,
                    'available_balance': available,
                    'hold_balance': frozen,
                    'needs_price': True
                })
        return assets


bitmart_service = BitMartService()
