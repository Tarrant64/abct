"""
Upbit Exchange Service - Portfolio tracking via Upbit API.
Uses JWT authentication.
"""
import sys
import os
import logging
import uuid
import hashlib
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService

logger = logging.getLogger(__name__)


class UpbitService(BaseExchangeService):
    EXCHANGE_NAME = "upbit"
    DISPLAY_NAME = "Upbit"
    API_BASE = "https://api.upbit.com"
    BALANCE_ENDPOINT = "/v1/accounts"
    API_NAME = "upbit"
    ENV_KEY = "UPBIT_ACCESS_KEY"
    ENV_SECRET = "UPBIT_SECRET_KEY"
    HTTP_CLIENT_NAME = "upbit"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """Upbit uses JWT with HS256 signed token."""
        try:
            import jwt as pyjwt
        except ImportError:
            logger.error("PyJWT not installed. Run: pip install PyJWT")
            return {}

        payload = {
            'access_key': self._cached_key or '',
            'nonce': str(uuid.uuid4()),
        }

        token = pyjwt.encode(payload, self._api_secret, algorithm='HS256')
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        for item in (data if isinstance(data, list) else []):
            balance = float(item.get('balance', 0))
            locked = float(item.get('locked', 0))
            total = balance + locked
            currency = item.get('currency', '')
            if total > 0:
                assets.append({
                    'currency': currency,
                    'name': currency,
                    'balance': total,
                    'available_balance': balance,
                    'hold_balance': locked,
                    'needs_price': True
                })
        return assets


upbit_service = UpbitService()
