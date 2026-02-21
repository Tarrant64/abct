"""
Phemex Exchange Service - Portfolio tracking via Phemex API.
Uses OKX-style HMAC-SHA256 base64 auth.
"""
import sys
import os
import logging
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService, OKXStyleAuth

logger = logging.getLogger(__name__)


class PhemexService(OKXStyleAuth, BaseExchangeService):
    EXCHANGE_NAME = "phemex"
    DISPLAY_NAME = "Phemex"
    API_BASE = "https://api.phemex.com"
    BALANCE_ENDPOINT = "/accounts/accountPositions"
    API_NAME = "phemex"
    ENV_KEY = "PHEMEX_API_KEY"
    ENV_SECRET = "PHEMEX_API_SECRET"
    HTTP_CLIENT_NAME = "phemex"

    def _get_timestamp(self) -> str:
        return str(int(time.time()))

    def _build_okx_headers(self, timestamp: str, signature: str) -> dict:
        return {
            'x-phemex-access-token': self._cached_key or '',
            'x-phemex-request-signature': signature,
            'x-phemex-request-expiry': str(int(timestamp) + 60),
            'Content-Type': 'application/json'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        result = data.get('data', {})
        for item in result.get('positions', []):
            currency = item.get('currency', '')
            balance = float(item.get('accountBalance', 0)) / 1e8  # Phemex uses satoshi-like units
            if balance > 0:
                assets.append({
                    'currency': currency,
                    'name': currency,
                    'balance': balance,
                    'available_balance': balance,
                    'hold_balance': 0,
                    'needs_price': True
                })
        return assets

    async def get_account_balances(self, user_id: int = None) -> dict:
        """Phemex spot wallet balance endpoint."""
        data = await self._make_request('/spot/wallets')
        if data is None:
            return self._standard_balance_response(
                [], configured=await self.ensure_configured()
            )
        assets = []
        for item in data.get('data', []):
            currency = item.get('currency', '')
            total = float(item.get('total', 0))
            locked = float(item.get('locked', 0))
            free = total - locked
            if total > 0:
                assets.append({
                    'currency': currency,
                    'name': currency,
                    'balance': total,
                    'available_balance': max(free, 0),
                    'hold_balance': locked,
                    'needs_price': True
                })
        return self._standard_balance_response(assets)


phemex_service = PhemexService()
