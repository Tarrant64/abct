"""
Deribit Exchange Service - Portfolio tracking via Deribit API.
Uses client credentials OAuth2 flow to get a bearer token, then fetches balances.
"""
import sys
import os
import logging
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService
from services.http_client import get_client
import httpx

logger = logging.getLogger(__name__)


class DeribitService(BaseExchangeService):
    EXCHANGE_NAME = "deribit"
    DISPLAY_NAME = "Deribit"
    API_BASE = "https://www.deribit.com"
    BALANCE_ENDPOINT = "/api/v2/private/get_account_summary"
    API_NAME = "deribit"
    ENV_KEY = "DERIBIT_CLIENT_ID"
    ENV_SECRET = "DERIBIT_CLIENT_SECRET"
    HTTP_CLIENT_NAME = "deribit"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        # Bearer token auth is handled in get_account_balances
        return {'Content-Type': 'application/json'}

    def _parse_balances(self, data) -> list:
        assets = []
        result = data.get('result', {})
        currency = result.get('currency', '')
        balance = float(result.get('balance', 0))
        available = float(result.get('available_funds', balance))
        if balance > 0:
            assets.append({
                'currency': currency,
                'name': currency,
                'balance': balance,
                'available_balance': available,
                'hold_balance': max(balance - available, 0),
                'needs_price': True
            })
        return assets

    async def _get_access_token(self) -> Optional[str]:
        """Authenticate via client credentials and return access token."""
        try:
            client = get_client(self.HTTP_CLIENT_NAME, timeout=self.REQUEST_TIMEOUT)
            response = await client.get(
                f"{self.API_BASE}/api/v2/public/auth",
                params={
                    'client_id': self._cached_key or '',
                    'client_secret': self._api_secret,
                    'grant_type': 'client_credentials'
                }
            )
            response.raise_for_status()
            data = response.json()
            return data.get('result', {}).get('access_token')
        except Exception as e:
            logger.error(f"Deribit auth error: {e}")
            return None

    async def get_account_balances(self, user_id: int = None) -> dict:
        """Fetch balances for BTC and ETH accounts."""
        if not await self.ensure_configured():
            return self._standard_balance_response([], configured=False)

        token = await self._get_access_token()
        if not token:
            return self._standard_balance_response([])

        assets = []
        client = get_client(self.HTTP_CLIENT_NAME, timeout=self.REQUEST_TIMEOUT)
        headers = {'Authorization': f'Bearer {token}'}

        for currency in ['BTC', 'ETH', 'USDC', 'USDT']:
            try:
                response = await client.get(
                    f"{self.API_BASE}/api/v2/private/get_account_summary",
                    params={'currency': currency, 'extended': True},
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()
                result = data.get('result', {})
                balance = float(result.get('balance', 0))
                available = float(result.get('available_funds', balance))
                if balance > 0:
                    assets.append({
                        'currency': currency,
                        'name': currency,
                        'balance': balance,
                        'available_balance': available,
                        'hold_balance': max(balance - available, 0),
                        'needs_price': True
                    })
            except Exception as e:
                logger.debug(f"Deribit {currency} balance error: {e}")

        return self._standard_balance_response(assets)


deribit_service = DeribitService()
