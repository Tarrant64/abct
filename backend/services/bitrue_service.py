"""
Bitrue Exchange Service - Portfolio tracking via Bitrue API.

Bitrue is Binance-compatible and uses X-MBX-APIKEY header.
"""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService, BinanceStyleAuth

logger = logging.getLogger(__name__)


class BitrueService(BinanceStyleAuth, BaseExchangeService):
    EXCHANGE_NAME = "bitrue"
    DISPLAY_NAME = "Bitrue"
    API_BASE = "https://openapi.bitrue.com"
    BALANCE_ENDPOINT = "/api/v1/account"
    API_NAME = "bitrue"
    ENV_KEY = "BITRUE_API_KEY"
    ENV_SECRET = "BITRUE_API_SECRET"
    HTTP_CLIENT_NAME = "bitrue"

    def _get_key_header(self) -> str:
        return 'X-MBX-APIKEY'

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


bitrue_service = BitrueService()
