"""
Gemini Exchange Service - Portfolio tracking via Gemini API.
Uses GeminiStyleAuth (base64 JSON payload + HMAC-SHA384).
"""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService, GeminiStyleAuth

logger = logging.getLogger(__name__)


class GeminiService(GeminiStyleAuth, BaseExchangeService):
    EXCHANGE_NAME = "gemini"
    DISPLAY_NAME = "Gemini"
    API_BASE = "https://api.gemini.com"
    BALANCE_ENDPOINT = "/v1/balances"
    API_NAME = "gemini"
    ENV_KEY = "GEMINI_API_KEY"
    ENV_SECRET = "GEMINI_API_SECRET"
    HTTP_CLIENT_NAME = "gemini"

    def _parse_balances(self, data) -> list:
        assets = []
        for item in (data if isinstance(data, list) else []):
            available = float(item.get('available', 0))
            amount = float(item.get('amount', 0))
            if amount > 0:
                assets.append({
                    'currency': item.get('currency', ''),
                    'name': item.get('currency', ''),
                    'balance': amount,
                    'available_balance': available,
                    'hold_balance': max(amount - available, 0),
                    'needs_price': True
                })
        return assets

    async def get_account_balances(self, user_id: int = None) -> dict:
        """Gemini requires POST for private endpoints."""
        data = await self._make_request(self.BALANCE_ENDPOINT, method='POST')
        if data is None:
            return self._standard_balance_response(
                [], configured=await self.ensure_configured()
            )
        assets = self._parse_balances(data)
        return self._standard_balance_response(assets)


gemini_service = GeminiService()
