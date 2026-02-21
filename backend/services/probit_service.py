"""
ProBit Exchange Service - Portfolio tracking via ProBit API.
Uses OAuth2 client credentials to get a token, then fetches balances.
"""
import sys
import os
import logging
import base64
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService
from services.http_client import get_client
import httpx

logger = logging.getLogger(__name__)


class ProBitService(BaseExchangeService):
    EXCHANGE_NAME = "probit"
    DISPLAY_NAME = "ProBit"
    API_BASE = "https://api.probit.com"
    BALANCE_ENDPOINT = "/api/exchange/v1/balance"
    API_NAME = "probit"
    ENV_KEY = "PROBIT_CLIENT_ID"
    ENV_SECRET = "PROBIT_CLIENT_SECRET"
    HTTP_CLIENT_NAME = "probit"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        return {'Content-Type': 'application/json'}

    def _parse_balances(self, data) -> list:
        assets = []
        for item in data.get('data', []):
            available = float(item.get('available', 0))
            total = float(item.get('total', 0))
            currency_id = item.get('currency_id', '')
            if total > 0:
                assets.append({
                    'currency': currency_id,
                    'name': currency_id,
                    'balance': total,
                    'available_balance': available,
                    'hold_balance': max(total - available, 0),
                    'needs_price': True
                })
        return assets

    async def _get_access_token(self) -> Optional[str]:
        """Get OAuth2 access token via client credentials."""
        try:
            credentials = base64.b64encode(
                f"{self._cached_key or ''}:{self._api_secret}".encode('utf-8')
            ).decode('utf-8')

            client = get_client(self.HTTP_CLIENT_NAME, timeout=self.REQUEST_TIMEOUT)
            response = await client.post(
                "https://accounts.probit.com/token",
                content='grant_type=client_credentials',
                headers={
                    'Authorization': f'Basic {credentials}',
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            )
            response.raise_for_status()
            return response.json().get('access_token')
        except Exception as e:
            logger.error(f"ProBit auth error: {e}")
            return None

    async def get_account_balances(self, user_id: int = None) -> dict:
        """ProBit uses OAuth2 bearer token for balance requests."""
        if not await self.ensure_configured():
            return self._standard_balance_response([], configured=False)

        token = await self._get_access_token()
        if not token:
            return self._standard_balance_response([])

        try:
            client = get_client(self.HTTP_CLIENT_NAME, timeout=self.REQUEST_TIMEOUT)
            response = await client.get(
                f"{self.API_BASE}{self.BALANCE_ENDPOINT}",
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                }
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"ProBit API HTTP error: {e.response.status_code} - {e.response.text}")
            return self._standard_balance_response([])
        except Exception as e:
            logger.error(f"ProBit API error: {e}")
            return self._standard_balance_response([])

        assets = self._parse_balances(data)
        return self._standard_balance_response(assets)


probit_service = ProBitService()
