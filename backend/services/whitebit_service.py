"""
WhiteBIT Exchange Service - Portfolio tracking via WhiteBIT API.

WhiteBIT uses POST for balance endpoint with HMAC-SHA512 + base64.
"""
import sys
import os
import logging
import time
import hmac
import hashlib
import json
import base64
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService
from services.http_client import get_client
import httpx

logger = logging.getLogger(__name__)


class WhiteBITService(BaseExchangeService):
    EXCHANGE_NAME = "whitebit"
    DISPLAY_NAME = "WhiteBIT"
    API_BASE = "https://whitebit.com"
    BALANCE_ENDPOINT = "/api/v4/trade-account/balance"
    API_NAME = "whitebit"
    ENV_KEY = "WHITEBIT_API_KEY"
    ENV_SECRET = "WHITEBIT_API_SECRET"
    HTTP_CLIENT_NAME = "whitebit"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """WhiteBIT: nonce + base64(json_body) signed with HMAC-SHA512."""
        nonce = str(int(time.time() * 1000))
        payload = {'request': endpoint, 'nonce': nonce}
        payload_json = json.dumps(payload)
        payload_b64 = base64.b64encode(payload_json.encode('utf-8')).decode()

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            payload_b64.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()

        return {
            'X-TXC-APIKEY': self._cached_key or '',
            'X-TXC-PAYLOAD': payload_b64,
            'X-TXC-SIGNATURE': signature,
            'Content-Type': 'application/json',
            '_whitebit_body': payload_json
        }

    def _parse_balances(self, data) -> list:
        assets = []
        result = data.get('result', data)
        if isinstance(result, dict):
            for currency, info in result.items():
                if isinstance(info, dict):
                    available = float(info.get('available', 0))
                    freeze = float(info.get('freeze', 0))
                    total = available + freeze
                    if total > 0:
                        assets.append({
                            'currency': currency,
                            'name': currency,
                            'balance': total,
                            'available_balance': available,
                            'hold_balance': freeze,
                            'needs_price': True
                        })
        return assets

    async def get_account_balances(self, user_id: int = None) -> dict:
        """WhiteBIT balance endpoint requires POST."""
        if not await self.ensure_configured():
            return self._standard_balance_response([], configured=False)

        try:
            nonce = str(int(time.time() * 1000))
            endpoint = self.BALANCE_ENDPOINT
            payload = {'request': endpoint, 'nonce': nonce}
            payload_json = json.dumps(payload)
            payload_b64 = base64.b64encode(payload_json.encode('utf-8')).decode()

            signature = hmac.new(
                self._api_secret.encode('utf-8'),
                payload_b64.encode('utf-8'),
                hashlib.sha512
            ).hexdigest()

            headers = {
                'X-TXC-APIKEY': self._cached_key or '',
                'X-TXC-PAYLOAD': payload_b64,
                'X-TXC-SIGNATURE': signature,
                'Content-Type': 'application/json'
            }
            url = f"{self.API_BASE}{endpoint}"
            client = get_client(self.HTTP_CLIENT_NAME, timeout=self.REQUEST_TIMEOUT)
            response = await client.post(url, content=payload_json, headers=headers)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"WhiteBIT API HTTP error: {e.response.status_code} - {e.response.text}")
            return self._standard_balance_response([])
        except Exception as e:
            logger.error(f"WhiteBIT API error: {e}")
            return self._standard_balance_response([])

        assets = self._parse_balances(data)
        return self._standard_balance_response(assets)


whitebit_service = WhiteBITService()
