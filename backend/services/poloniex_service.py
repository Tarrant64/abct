"""
Poloniex Exchange Service - Portfolio tracking via Poloniex API.
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


class PoloniexService(BaseExchangeService):
    EXCHANGE_NAME = "poloniex"
    DISPLAY_NAME = "Poloniex"
    API_BASE = "https://api.poloniex.com"
    BALANCE_ENDPOINT = "/accounts/balances"
    API_NAME = "poloniex"
    ENV_KEY = "POLONIEX_API_KEY"
    ENV_SECRET = "POLONIEX_API_SECRET"
    HTTP_CLIENT_NAME = "poloniex"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """Poloniex uses signTimestamp + HMAC-SHA256 over method\nrequestPath\nparams."""
        timestamp = str(int(time.time() * 1000))
        query_string = urlencode(params) if params else ''

        sign_str = f"{method.upper()}\n{endpoint}\n{query_string}\n\nsignTimestamp={timestamp}"
        if query_string:
            sign_str = f"{method.upper()}\n{endpoint}\n{query_string}&signTimestamp={timestamp}"
        else:
            sign_str = f"{method.upper()}\n{endpoint}\nsignTimestamp={timestamp}"

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        suffix = f"?signTimestamp={timestamp}&signature={signature}"
        if query_string:
            suffix = f"?{query_string}&signTimestamp={timestamp}&signature={signature}"

        return {
            'key': self._cached_key or '',
            '_url_suffix': suffix
        }

    def _parse_balances(self, data) -> list:
        assets = []
        # Poloniex /accounts/balances returns a list of accounts
        for account in (data if isinstance(data, list) else []):
            for balance_item in account.get('balances', []):
                currency = balance_item.get('currency', '')
                available = float(balance_item.get('available', 0))
                hold = float(balance_item.get('hold', 0))
                total = available + hold
                if total > 0:
                    assets.append({
                        'currency': currency,
                        'name': currency,
                        'balance': total,
                        'available_balance': available,
                        'hold_balance': hold,
                        'needs_price': True
                    })
        return assets


poloniex_service = PoloniexService()
