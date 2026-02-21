"""
Bitfinex Exchange Service - Portfolio tracking via Bitfinex API v2.
Uses HMAC-SHA384 signed headers.
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

logger = logging.getLogger(__name__)


class BitfinexService(BaseExchangeService):
    EXCHANGE_NAME = "bitfinex"
    DISPLAY_NAME = "Bitfinex"
    API_BASE = "https://api.bitfinex.com"
    BALANCE_ENDPOINT = "/v2/auth/r/wallets"
    API_NAME = "bitfinex"
    ENV_KEY = "BITFINEX_API_KEY"
    ENV_SECRET = "BITFINEX_API_SECRET"
    HTTP_CLIENT_NAME = "bitfinex"

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """Bitfinex v2: nonce + path + body signed with HMAC-SHA384."""
        nonce = str(int(time.time() * 1000000))
        body_json = body or '{}'
        sign_str = f"/api{endpoint}{nonce}{body_json}"

        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha384
        ).hexdigest()

        return {
            'bfx-apikey': self._cached_key or '',
            'bfx-nonce': nonce,
            'bfx-signature': signature,
            'Content-Type': 'application/json'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        # Bitfinex returns array of [WALLET_TYPE, CURRENCY, BALANCE, UNSETTLED_INTEREST, AVAILABLE_BALANCE]
        for wallet in (data if isinstance(data, list) else []):
            if len(wallet) >= 3:
                wallet_type = wallet[0]
                currency = wallet[1]
                balance = float(wallet[2]) if wallet[2] else 0
                available = float(wallet[4]) if len(wallet) > 4 and wallet[4] else balance
                if balance > 0 and wallet_type == 'exchange':
                    assets.append({
                        'currency': currency.lstrip('t').lstrip('f'),
                        'name': currency,
                        'balance': balance,
                        'available_balance': available if available else balance,
                        'hold_balance': max(balance - (available or balance), 0),
                        'needs_price': True
                    })
        return assets

    async def get_account_balances(self, user_id: int = None) -> dict:
        """Bitfinex requires POST for wallet endpoint."""
        data = await self._make_request(self.BALANCE_ENDPOINT, method='POST')
        if data is None:
            return self._standard_balance_response(
                [], configured=await self.ensure_configured()
            )
        assets = self._parse_balances(data)
        return self._standard_balance_response(assets)


bitfinex_service = BitfinexService()
