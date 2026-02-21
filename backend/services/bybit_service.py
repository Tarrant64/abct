"""
Bybit Exchange Service - Portfolio tracking via Bybit API.
"""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService, BinanceStyleAuth

logger = logging.getLogger(__name__)


class BybitService(BinanceStyleAuth, BaseExchangeService):
    EXCHANGE_NAME = "bybit"
    DISPLAY_NAME = "Bybit"
    API_BASE = "https://api.bybit.com"
    BALANCE_ENDPOINT = "/v5/account/wallet-balance"
    API_NAME = "bybit"
    ENV_KEY = "BYBIT_API_KEY"
    ENV_SECRET = "BYBIT_API_SECRET"
    HTTP_CLIENT_NAME = "bybit"

    def _get_key_header(self) -> str:
        return 'X-BAPI-API-KEY'

    def _parse_balances(self, data) -> list:
        assets = []
        result = data.get('result', {})
        # Bybit returns a list of accounts (UNIFIED, CONTRACT, etc.)
        for account in result.get('list', []):
            for coin in account.get('coin', []):
                wallet_balance = float(coin.get('walletBalance', 0))
                free = float(coin.get('availableToWithdraw', 0))
                locked = wallet_balance - free
                if wallet_balance > 0:
                    assets.append({
                        'currency': coin.get('coin', ''),
                        'name': coin.get('coin', ''),
                        'balance': wallet_balance,
                        'available_balance': free,
                        'hold_balance': max(locked, 0),
                        'needs_price': True
                    })
        return assets

    async def get_account_balances(self, user_id: int = None) -> dict:
        """Get Bybit UNIFIED account balances. Requires accountType param."""
        data = await self._make_request(self.BALANCE_ENDPOINT, params={'accountType': 'UNIFIED'})
        if data is None:
            return self._standard_balance_response(
                [], configured=await self.ensure_configured()
            )
        assets = self._parse_balances(data)
        return self._standard_balance_response(assets)


bybit_service = BybitService()
