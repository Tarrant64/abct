"""
Swyftx Exchange Service - Portfolio tracking via Swyftx API.
Uses Bearer token authentication (API key is the bearer token).
"""
import sys
import os
import logging
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService

logger = logging.getLogger(__name__)


class SwyftxService(BaseExchangeService):
    EXCHANGE_NAME = "swyftx"
    DISPLAY_NAME = "Swyftx"
    API_BASE = "https://api.swyftx.com.au"
    BALANCE_ENDPOINT = "/user/balance/"
    API_NAME = "swyftx"
    ENV_KEY = "SWYFTX_API_KEY"
    ENV_SECRET = ""  # Swyftx only needs an API key (bearer token)
    HTTP_CLIENT_NAME = "swyftx"

    async def ensure_configured(self) -> bool:
        """Swyftx only needs an API key."""
        creds = await self.get_api_credentials()
        key = creds.get('api_key', '')
        if not key and self.ENV_KEY:
            import os as _os
            key = _os.getenv(self.ENV_KEY, '')
        return bool(key)

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """Swyftx: API key used as Bearer token."""
        return {
            'Authorization': f'Bearer {self._cached_key or ""}',
            'Content-Type': 'application/json'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        for item in (data if isinstance(data, list) else data.get('data', [])):
            available = float(item.get('availableBalance', 0))
            total = float(item.get('totalBalance', 0))
            asset_code = item.get('assetId', item.get('code', ''))
            if total > 0 and asset_code:
                assets.append({
                    'currency': str(asset_code),
                    'name': str(asset_code),
                    'balance': total,
                    'available_balance': available,
                    'hold_balance': max(total - available, 0),
                    'needs_price': True
                })
        return assets


swyftx_service = SwyftxService()
