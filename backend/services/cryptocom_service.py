"""
Crypto.com Exchange Service - Portfolio tracking via Crypto.com Exchange API.
Uses HMAC-SHA256 with sorted params.
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


class CryptoComService(BaseExchangeService):
    EXCHANGE_NAME = "cryptocom"
    DISPLAY_NAME = "Crypto.com"
    API_BASE = "https://api.crypto.com"
    BALANCE_ENDPOINT = "/exchange/v1/private/user-balance"
    API_NAME = "cryptocom"
    ENV_KEY = "CRYPTOCOM_API_KEY"
    ENV_SECRET = "CRYPTOCOM_API_SECRET"
    HTTP_CLIENT_NAME = "cryptocom"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        return {'Content-Type': 'application/json'}

    def _sign_request(self, method: str, endpoint: str, params: dict, nonce: int) -> str:
        """Crypto.com: sign sorted params joined as string."""
        param_str = ''
        if params:
            param_str = ''.join(f"{k}{v}" for k, v in sorted(params.items()))
        sign_str = f"{method}{nonce}{self._cached_key or ''}{param_str}"
        return hmac.new(
            self._api_secret.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _parse_balances(self, data) -> list:
        assets = []
        result = data.get('result', {})
        for item in result.get('data', []):
            for position in item.get('position_balances', []):
                quantity = float(position.get('quantity', 0))
                currency = position.get('instrument_name', '')
                if quantity > 0:
                    assets.append({
                        'currency': currency,
                        'name': currency,
                        'balance': quantity,
                        'available_balance': quantity,
                        'hold_balance': 0,
                        'needs_price': True
                    })
        return assets

    async def get_account_balances(self, user_id: int = None) -> dict:
        """Crypto.com uses POST with JSON body for private endpoints."""
        if not await self.ensure_configured():
            return self._standard_balance_response([], configured=False)

        try:
            nonce = int(time.time() * 1000)
            method = 'private/user-balance'
            params = {}
            sig = self._sign_request(method, self.BALANCE_ENDPOINT, params, nonce)

            payload = {
                'id': nonce,
                'method': method,
                'api_key': self._cached_key or '',
                'params': params,
                'nonce': nonce,
                'sig': sig
            }
            payload_json = json.dumps(payload)

            url = f"{self.API_BASE}{self.BALANCE_ENDPOINT}"
            client = get_client(self.HTTP_CLIENT_NAME, timeout=self.REQUEST_TIMEOUT)
            response = await client.post(
                url, content=payload_json,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Crypto.com API HTTP error: {e.response.status_code} - {e.response.text}")
            return self._standard_balance_response([])
        except Exception as e:
            logger.error(f"Crypto.com API error: {e}")
            return self._standard_balance_response([])

        assets = self._parse_balances(data)
        return self._standard_balance_response(assets)


cryptocom_service = CryptoComService()
