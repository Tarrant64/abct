"""
MEXC Exchange Service - Portfolio tracking via MEXC API.
"""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService, BinanceStyleAuth

logger = logging.getLogger(__name__)


class MEXCService(BinanceStyleAuth, BaseExchangeService):
    EXCHANGE_NAME = "mexc"
    DISPLAY_NAME = "MEXC"
    API_BASE = "https://api.mexc.com"
    BALANCE_ENDPOINT = "/api/v3/account"
    API_NAME = "mexc"
    ENV_KEY = "MEXC_API_KEY"
    ENV_SECRET = "MEXC_API_SECRET"
    HTTP_CLIENT_NAME = "mexc"

    def _get_key_header(self) -> str:
        return 'X-MEXC-APIKEY'

    def _parse_balances(self, data) -> list:
        assets = []
        for balance in data.get('balances', []):
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


mexc_service = MEXCService()
