"""
Backpack Exchange Service - Portfolio tracking via Backpack Exchange API.
Uses Ed25519 signatures (base64-encoded public/private key pair).
"""
import sys
import os
import logging
import time
import base64
from typing import Optional
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService

logger = logging.getLogger(__name__)


class BackpackService(BaseExchangeService):
    EXCHANGE_NAME = "backpack"
    DISPLAY_NAME = "Backpack"
    API_BASE = "https://api.backpack.exchange"
    BALANCE_ENDPOINT = "/api/v1/capital"
    API_NAME = "backpack"
    ENV_KEY = "BACKPACK_API_KEY"
    ENV_SECRET = "BACKPACK_API_SECRET"
    HTTP_CLIENT_NAME = "backpack"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """Backpack: Ed25519 signature over instruction + timestamp + window."""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import (
                Encoding, PublicFormat, PrivateFormat, NoEncryption, load_der_private_key
            )
        except ImportError:
            logger.error("cryptography package not installed. Run: pip install cryptography")
            return {}

        timestamp = str(int(time.time() * 1000))
        window = '5000'

        # The instruction for balance queries
        instruction = 'balanceQuery'
        query_string = urlencode(sorted(params.items())) if params else ''

        sign_str = f"instruction={instruction}&timestamp={timestamp}&window={window}"
        if query_string:
            sign_str = f"instruction={instruction}&{query_string}&timestamp={timestamp}&window={window}"

        try:
            secret_bytes = base64.b64decode(self._api_secret)
            private_key = Ed25519PrivateKey.from_private_bytes(secret_bytes)
            signature = base64.b64encode(
                private_key.sign(sign_str.encode('utf-8'))
            ).decode()
        except Exception as e:
            logger.error(f"Backpack Ed25519 signing error: {e}")
            return {}

        suffix = f"?{query_string}" if query_string else ''

        return {
            'X-API-Key': self._cached_key or '',
            'X-Signature': signature,
            'X-Timestamp': timestamp,
            'X-Window': window,
            'Content-Type': 'application/json',
            '_url_suffix': suffix
        }

    def _parse_balances(self, data) -> list:
        assets = []
        if isinstance(data, dict):
            for currency, info in data.items():
                if isinstance(info, dict):
                    available = float(info.get('available', 0))
                    locked = float(info.get('locked', 0))
                    total = available + locked
                    if total > 0:
                        assets.append({
                            'currency': currency,
                            'name': currency,
                            'balance': total,
                            'available_balance': available,
                            'hold_balance': locked,
                            'needs_price': True
                        })
        return assets


backpack_service = BackpackService()
