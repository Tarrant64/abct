"""
HTX (Huobi) Exchange Service - Portfolio tracking via HTX API.

HTX requires fetching account ID first, then fetching balances for that account.
"""
import sys
import os
import logging
import time
import hmac
import hashlib
import base64
from urllib.parse import urlencode
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.base_exchange import BaseExchangeService, BinanceStyleAuth

logger = logging.getLogger(__name__)


class HTXService(BinanceStyleAuth, BaseExchangeService):
    EXCHANGE_NAME = "htx"
    DISPLAY_NAME = "HTX"
    API_BASE = "https://api.huobi.pro"
    BALANCE_ENDPOINT = "/v1/account/accounts"
    API_NAME = "htx"
    ENV_KEY = "HTX_API_KEY"
    ENV_SECRET = "HTX_API_SECRET"
    HTTP_CLIENT_NAME = "htx"

    def _get_key_header(self) -> str:
        # HTX uses AccessKeyId in query string, not a header
        return 'X-HTX-APIKEY'  # Not actually used for HTX auth

    def _generate_auth_headers(
        self, method: str, endpoint: str,
        params: Optional[dict] = None, body: str = ''
    ) -> dict:
        """HTX uses its own auth: AccessKeyId, SignatureMethod, SignatureVersion, Timestamp in query string."""
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())
        sign_params = {
            'AccessKeyId': self._cached_key or '',
            'SignatureMethod': 'HmacSHA256',
            'SignatureVersion': '2',
            'Timestamp': timestamp,
        }
        if params:
            sign_params.update(params)

        sorted_params = sorted(sign_params.items())
        query_string = urlencode(sorted_params)

        host = 'api.huobi.pro'
        pre_signed = f"{method.upper()}\n{host}\n{endpoint}\n{query_string}"

        signature = base64.b64encode(
            hmac.new(
                self._api_secret.encode('utf-8'),
                pre_signed.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode()

        return {
            '_url_suffix': f'?{query_string}&Signature={signature}'
        }

    def _parse_balances(self, data) -> list:
        assets = []
        for item in data.get('data', []):
            balance = float(item.get('balance', 0))
            balance_type = item.get('type', '')
            currency = item.get('currency', '').upper()
            if balance > 0 and currency:
                # HTX returns separate trade/frozen entries per currency
                if balance_type == 'trade':
                    assets.append({
                        'currency': currency,
                        'name': currency,
                        'balance': balance,
                        'available_balance': balance,
                        'hold_balance': 0,
                        'needs_price': True
                    })
                elif balance_type == 'frozen':
                    # Add frozen to hold_balance of existing entry
                    for asset in assets:
                        if asset['currency'] == currency:
                            asset['hold_balance'] += balance
                            asset['balance'] += balance
                            break
                    else:
                        assets.append({
                            'currency': currency,
                            'name': currency,
                            'balance': balance,
                            'available_balance': 0,
                            'hold_balance': balance,
                            'needs_price': True
                        })
        return assets

    async def get_account_balances(self, user_id: int = None) -> dict:
        """HTX requires fetching account ID first, then balance for that account."""
        # Step 1: get accounts list
        accounts_data = await self._make_request('/v1/account/accounts')
        if not accounts_data:
            return self._standard_balance_response(
                [], configured=await self.ensure_configured()
            )

        accounts = accounts_data.get('data', [])
        # Find the spot account
        account_id = None
        for acc in accounts:
            if acc.get('type') == 'spot' and acc.get('state') == 'working':
                account_id = acc.get('id')
                break
        if account_id is None and accounts:
            account_id = accounts[0].get('id')

        if not account_id:
            return self._standard_balance_response([])

        # Step 2: get balances for that account
        balance_data = await self._make_request(f'/v1/account/accounts/{account_id}/balance')
        if not balance_data:
            return self._standard_balance_response([])

        assets = self._parse_balances(balance_data)
        return self._standard_balance_response(assets)


htx_service = HTXService()
