"""
Independent Reserve Exchange Service - Portfolio tracking via Independent Reserve API.
Uses HMAC-SHA256 with nonce.
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


class IndependentReserveService(BaseExchangeService):
    EXCHANGE_NAME = "independentreserve"
    DISPLAY_NAME = "Independent Reserve"
    API_BASE = "https://api.independentreserve.com"
    BALANCE_ENDPOINT = "/Private/GetAccounts"
    API_NAME = "independentreserve"
    ENV_KEY = "INDRES_API_KEY"
    ENV_SECRET = "INDRES_API_SECRET"
    HTTP_CLIENT_NAME = "independentreserve"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        return {'Content-Type': 'application/json'}

    def _parse_balances(self, data) -> list:
        assets = []
        for item in (data if isinstance(data, list) else []):
            available = float(item.get('AvailableBalance', 0))
            total = float(item.get('TotalBalance', 0))
            currency = item.get('CurrencyCode', '')
            if total > 0:
                assets.append({
                    'currency': currency.upper(),
                    'name': currency.upper(),
                    'balance': total,
                    'available_balance': available,
                    'hold_balance': max(total - available, 0),
                    'needs_price': True
                })
        return assets

    async def get_account_balances(self, user_id: int = None) -> dict:
        """Independent Reserve uses POST with nonce+signature in body."""
        if not await self.ensure_configured():
            return self._standard_balance_response([], configured=False)

        try:
            nonce = int(time.time() * 1000)
            url = f"{self.API_BASE}{self.BALANCE_ENDPOINT}"
            params_list = [url, f"apiKey={self._cached_key or ''}", f"nonce={nonce}"]
            sign_str = ','.join(params_list)

            signature = hmac.new(
                self._api_secret.encode('utf-8'),
                sign_str.encode('utf-8'),
                hashlib.sha256
            ).hexdigest().upper()

            payload = {
                'apiKey': self._cached_key or '',
                'nonce': nonce,
                'signature': signature
            }
            payload_json = json.dumps(payload)

            client = get_client(self.HTTP_CLIENT_NAME, timeout=self.REQUEST_TIMEOUT)
            response = await client.post(
                url, content=payload_json,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Independent Reserve API HTTP error: {e.response.status_code} - {e.response.text}")
            return self._standard_balance_response([])
        except Exception as e:
            logger.error(f"Independent Reserve API error: {e}")
            return self._standard_balance_response([])

        assets = self._parse_balances(data)
        return self._standard_balance_response(assets)


independentreserve_service = IndependentReserveService()
