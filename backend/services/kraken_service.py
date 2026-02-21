"""
Kraken Exchange Service - Portfolio tracking via Kraken API.
Uses KrakenStyleAuth (SHA256 + HMAC-SHA512 with base64-decoded secret).
"""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService, KrakenStyleAuth
from services.http_client import get_client
import httpx

logger = logging.getLogger(__name__)


class KrakenService(KrakenStyleAuth, BaseExchangeService):
    EXCHANGE_NAME = "kraken"
    DISPLAY_NAME = "Kraken"
    API_BASE = "https://api.kraken.com"
    BALANCE_ENDPOINT = "/0/private/Balance"
    API_NAME = "kraken"
    ENV_KEY = "KRAKEN_API_KEY"
    ENV_SECRET = "KRAKEN_API_SECRET"
    HTTP_CLIENT_NAME = "kraken"

    def _parse_balances(self, data) -> list:
        assets = []
        result = data.get('result', {})
        if isinstance(result, dict):
            for currency, balance_str in result.items():
                balance = float(balance_str)
                if balance > 0:
                    # Kraken prefixes currencies with X or Z
                    display = currency
                    if len(currency) == 4 and currency[0] in ('X', 'Z'):
                        display = currency[1:]
                    assets.append({
                        'currency': display,
                        'name': display,
                        'balance': balance,
                        'available_balance': balance,
                        'hold_balance': 0,
                        'needs_price': True
                    })
        return assets

    async def get_account_balances(self, user_id: int = None) -> dict:
        """Kraken uses POST requests for private endpoints."""
        if not await self.ensure_configured():
            return self._standard_balance_response([], configured=False)

        try:
            auth = self._generate_auth_headers('POST', self.BALANCE_ENDPOINT)
            post_data = auth.pop('_post_data', '')
            auth.pop('_url_suffix', '')

            url = f"{self.API_BASE}{self.BALANCE_ENDPOINT}"
            client = get_client(self.HTTP_CLIENT_NAME, timeout=self.REQUEST_TIMEOUT)
            response = await client.post(url, content=post_data, headers=auth)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Kraken API HTTP error: {e.response.status_code} - {e.response.text}")
            return self._standard_balance_response([])
        except Exception as e:
            logger.error(f"Kraken API error: {e}")
            return self._standard_balance_response([])

        if data.get('error'):
            logger.error(f"Kraken API errors: {data['error']}")
            return self._standard_balance_response([])

        assets = self._parse_balances(data)
        return self._standard_balance_response(assets)


kraken_service = KrakenService()
