"""
Robinhood Exchange Service - Portfolio tracking via Robinhood API.
Uses OAuth2 Bearer token authentication.

Note: Robinhood does not have an official public API. This uses the unofficial
API endpoints that the mobile app uses. Users need to provide their OAuth2
access token directly from session headers.
"""
import sys
import os
import logging
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService

logger = logging.getLogger(__name__)


class RobinhoodService(BaseExchangeService):
    EXCHANGE_NAME = "robinhood"
    DISPLAY_NAME = "Robinhood"
    API_BASE = "https://api.robinhood.com"
    BALANCE_ENDPOINT = "/accounts/"
    API_NAME = "robinhood"
    ENV_KEY = "ROBINHOOD_ACCESS_TOKEN"
    ENV_SECRET = ""  # Only needs bearer token
    HTTP_CLIENT_NAME = "robinhood"

    async def ensure_configured(self) -> bool:
        """Robinhood only needs an OAuth2 access token."""
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
        """Robinhood: OAuth2 Bearer token."""
        return {
            'Authorization': f'Bearer {self._cached_key or ""}',
            'Content-Type': 'application/json'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        results = data.get('results', []) if isinstance(data, dict) else []
        for account in results:
            # Get buying power / cash
            cash = float(account.get('portfolio_cash', 0))
            if cash > 0:
                assets.append({
                    'currency': 'USD',
                    'name': 'USD',
                    'balance': cash,
                    'available_balance': cash,
                    'hold_balance': 0,
                    'needs_price': False
                })
        return assets

    async def get_account_balances(self, user_id: int = None) -> dict:
        """Robinhood account balances - note limited public API support."""
        data = await self._make_request(self.BALANCE_ENDPOINT)
        if data is None:
            return self._standard_balance_response(
                [], configured=await self.ensure_configured()
            )
        assets = self._parse_balances(data)
        return self._standard_balance_response(assets)


robinhood_service = RobinhoodService()
