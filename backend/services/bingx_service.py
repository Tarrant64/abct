"""
BingX Exchange Service - Portfolio tracking via BingX API.
"""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService, BinanceStyleAuth

logger = logging.getLogger(__name__)


class BingXService(BinanceStyleAuth, BaseExchangeService):
    EXCHANGE_NAME = "bingx"
    DISPLAY_NAME = "BingX"
    API_BASE = "https://open-api.bingx.com"
    BALANCE_ENDPOINT = "/openApi/spot/v1/account/balance"
    API_NAME = "bingx"
    ENV_KEY = "BINGX_API_KEY"
    ENV_SECRET = "BINGX_API_SECRET"
    HTTP_CLIENT_NAME = "bingx"

    def _get_key_header(self) -> str:
        return 'X-BX-APIKEY'

    def _parse_balances(self, data) -> list:
        assets = []
        balances = data.get('data', {}).get('balances', [])
        for balance in balances:
            free = float(balance.get('free', 0))
            locked = float(balance.get('locked', 0))
            total = free + locked
            if total > 0:
                assets.append({
                    'currency': balance.get('asset', ''),
                    'name': balance.get('asset', ''),
                    'balance': total,
                    'available_balance': free,
                    'hold_balance': locked,
                    'needs_price': True
                })
        return assets


bingx_service = BingXService()
