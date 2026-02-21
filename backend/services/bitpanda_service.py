"""
Bitpanda Exchange Service - Portfolio tracking via Bitpanda Pro API.
Uses Bearer token authentication.
"""
import sys
import os
import logging
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService

logger = logging.getLogger(__name__)


class BitpandaService(BaseExchangeService):
    EXCHANGE_NAME = "bitpanda"
    DISPLAY_NAME = "Bitpanda"
    API_BASE = "https://api.exchange.bitpanda.com"
    BALANCE_ENDPOINT = "/public/v1/account/balances"
    API_NAME = "bitpanda"
    ENV_KEY = "BITPANDA_API_KEY"
    ENV_SECRET = ""  # Bitpanda Pro only needs an API key
    HTTP_CLIENT_NAME = "bitpanda"

    async def ensure_configured(self) -> bool:
        """Bitpanda only needs an API key."""
        creds = await self.get_api_credentials()
        key = creds.get('api_key', '')
        if not key and self.ENV_KEY:
            import os as _os
            key = _os.getenv(self.ENV_KEY, '')
        return bool(key)

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        return {
            'Authorization': f'Bearer {self._cached_key or ""}',
            'Content-Type': 'application/json'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        for item in data.get('balances', []):
            available = float(item.get('available', 0))
            locked = float(item.get('locked', 0))
            total = available + locked
            currency = item.get('currency_code', '')
            if total > 0:
                assets.append({
                    'currency': currency,
                    'name': currency,
                    'balance': total,
                    'available_balance': available,
                    'hold_balance': locked,
                    'needs_price': True
                })
        return assets


bitpanda_service = BitpandaService()
