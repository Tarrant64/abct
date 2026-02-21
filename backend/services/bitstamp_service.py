"""
Bitstamp Exchange Service - Portfolio tracking via Bitstamp API v2.
Uses HMAC-SHA256 with API key, timestamp, nonce in headers.
"""
import sys
import os
import logging
import time
import hmac
import hashlib
import uuid
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService
from services.http_client import get_client
import httpx

logger = logging.getLogger(__name__)


class BitstampService(BaseExchangeService):
    EXCHANGE_NAME = "bitstamp"
    DISPLAY_NAME = "Bitstamp"
    API_BASE = "https://www.bitstamp.net"
    BALANCE_ENDPOINT = "/api/v2/account_balances/"
    API_NAME = "bitstamp"
    ENV_KEY = "BITSTAMP_API_KEY"
    ENV_SECRET = "BITSTAMP_API_SECRET"
    HTTP_CLIENT_NAME = "bitstamp"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        return {'Content-Type': 'application/x-www-form-urlencoded'}

    def _parse_balances(self, data) -> list:
        assets = []
        for item in (data if isinstance(data, list) else []):
            currency = item.get('currency', '')
            total = float(item.get('total', 0))
            available = float(item.get('available', total))
            reserved = float(item.get('reserved', 0))
            if total > 0:
                assets.append({
                    'currency': currency.upper(),
                    'name': currency.upper(),
                    'balance': total,
                    'available_balance': available,
                    'hold_balance': reserved,
                    'needs_price': True
                })
        return assets

    async def get_account_balances(self, user_id: int = None) -> dict:
        """Bitstamp API v2 auth with HMAC-SHA256."""
        if not await self.ensure_configured():
            return self._standard_balance_response([], configured=False)

        try:
            timestamp = str(int(time.time() * 1000))
            nonce = str(uuid.uuid4())
            content_type = 'application/x-www-form-urlencoded'
            payload = ''

            message = (
                f"BITSTAMP {self._cached_key or ''}"
                f"POST"
                f"www.bitstamp.net"
                f"{self.BALANCE_ENDPOINT}"
                f""
                f"{content_type}"
                f"{nonce}"
                f"{timestamp}"
                f"v2"
                f"{payload}"
            )

            signature = hmac.new(
                self._api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            headers = {
                'X-Auth': f'BITSTAMP {self._cached_key or ""}',
                'X-Auth-Signature': signature,
                'X-Auth-Nonce': nonce,
                'X-Auth-Timestamp': timestamp,
                'X-Auth-Version': 'v2',
                'Content-Type': content_type
            }

            url = f"{self.API_BASE}{self.BALANCE_ENDPOINT}"
            client = get_client(self.HTTP_CLIENT_NAME, timeout=self.REQUEST_TIMEOUT)
            response = await client.post(url, headers=headers)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Bitstamp API HTTP error: {e.response.status_code} - {e.response.text}")
            return self._standard_balance_response([])
        except Exception as e:
            logger.error(f"Bitstamp API error: {e}")
            return self._standard_balance_response([])

        assets = self._parse_balances(data)
        return self._standard_balance_response(assets)


bitstamp_service = BitstampService()
