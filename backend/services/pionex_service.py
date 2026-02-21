"""
Pionex Exchange Service - Portfolio tracking via Pionex API.
"""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService, BinanceStyleAuth

logger = logging.getLogger(__name__)


class PionexService(BinanceStyleAuth, BaseExchangeService):
    EXCHANGE_NAME = "pionex"
    DISPLAY_NAME = "Pionex"
    API_BASE = "https://api.pionex.com"
    BALANCE_ENDPOINT = "/api/v1/account/balances"
    API_NAME = "pionex"
    ENV_KEY = "PIONEX_API_KEY"
    ENV_SECRET = "PIONEX_API_SECRET"
    HTTP_CLIENT_NAME = "pionex"

    def _get_key_header(self) -> str:
        return 'PIONEX-KEY'

    def _parse_balances(self, data) -> list:
        assets = []
        result = data.get('data', {})
        for item in result.get('balances', []):
            free = float(item.get('free', 0))
            frozen = float(item.get('frozen', 0))
            total = free + frozen
            if total > 0:
                assets.append({
                    'currency': item.get('coin', ''),
                    'name': item.get('coin', ''),
                    'balance': total,
                    'available_balance': free,
                    'hold_balance': frozen,
                    'needs_price': True
                })
        return assets


pionex_service = PionexService()
