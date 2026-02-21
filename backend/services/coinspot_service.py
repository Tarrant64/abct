"""
CoinSpot Exchange Service - Portfolio tracking via CoinSpot API.
Uses HMAC-SHA512 signed POST body.
"""
import sys
import os
import logging
import time
import hmac
import hashlib
import json
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService
from services.http_client import get_client
import httpx

logger = logging.getLogger(__name__)


class CoinSpotService(BaseExchangeService):
    EXCHANGE_NAME = "coinspot"
    DISPLAY_NAME = "CoinSpot"
    API_BASE = "https://www.coinspot.com.au"
    BALANCE_ENDPOINT = "/api/v2/ro/my/balances"
    API_NAME = "coinspot"
    ENV_KEY = "COINSPOT_API_KEY"
    ENV_SECRET = "COINSPOT_API_SECRET"
    HTTP_CLIENT_NAME = "coinspot"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """CoinSpot: nonce in body, sign JSON body with HMAC-SHA512."""
        nonce = int(time.time() * 1000)
        payload = {'nonce': nonce}
        payload_json = json.dumps(payload)

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            payload_json.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()

        return {
            'key': self._cached_key or '',
            'sign': signature,
            'Content-Type': 'application/json',
            '_coinspot_body': payload_json
        }

    def _parse_balances(self, data) -> list:
        assets = []
        balances = data.get('balances', [])
        for item in balances:
            if isinstance(item, dict):
                for currency, info in item.items():
                    if isinstance(info, dict):
                        balance = float(info.get('balance', 0))
                        if balance > 0:
                            assets.append({
                                'currency': currency.upper(),
                                'name': currency.upper(),
                                'balance': balance,
                                'available_balance': balance,
                                'hold_balance': 0,
                                'needs_price': True
                            })
        return assets

    async def get_account_balances(self, user_id: int = None) -> dict:
        """CoinSpot uses POST for balance endpoints."""
        if not await self.ensure_configured():
            return self._standard_balance_response([], configured=False)

        try:
            import time as t
            nonce = int(t.time() * 1000)
            payload = {'nonce': nonce}
            payload_json = json.dumps(payload)

            signature = hmac.new(
                self._api_secret.encode('utf-8'),
                payload_json.encode('utf-8'),
                hashlib.sha512
            ).hexdigest()

            headers = {
                'key': self._cached_key or '',
                'sign': signature,
                'Content-Type': 'application/json'
            }
            url = f"{self.API_BASE}{self.BALANCE_ENDPOINT}"
            client = get_client(self.HTTP_CLIENT_NAME, timeout=self.REQUEST_TIMEOUT)
            response = await client.post(url, content=payload_json, headers=headers)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"CoinSpot API HTTP error: {e.response.status_code} - {e.response.text}")
            return self._standard_balance_response([])
        except Exception as e:
            logger.error(f"CoinSpot API error: {e}")
            return self._standard_balance_response([])

        assets = self._parse_balances(data)
        return self._standard_balance_response(assets)


coinspot_service = CoinSpotService()
