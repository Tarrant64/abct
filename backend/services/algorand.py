"""
Algorand Service - Fetches Algorand blockchain data using Pera API and Tatum.io.

APIs:
- Pera Wallet Public API (no key required): https://docs.perawallet.app/references/public-api
- Tatum.io Algorand (requires key): https://algorand-mainnet-algod.gateway.tatum.io

Provides wallet balances, ASA (Algorand Standard Assets) holdings, and transaction history.
"""

import httpx
import logging
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.api_key_manager import APIKeyManager
from services.http_client import get_client

logger = logging.getLogger(__name__)

# MicroAlgos per ALGO
MICROALGOS_PER_ALGO = 1_000_000


class AlgorandService(APIKeyManager):
    """Service for Algorand blockchain data using Pera API + Tatum.io."""

    def __init__(self):
        super().__init__(api_name='tatum_algorand', env_var='TATUM_ALGORAND_API_KEY')
        self.pera_base_url = "https://mainnet.api.perawallet.app"
        self.tatum_base_url = "https://algorand-mainnet-algod.gateway.tatum.io"
        self._balance_cache: Dict[str, dict] = {}
        self._cache_ttl = timedelta(minutes=5)

    async def is_configured(self) -> bool:
        """Check if Tatum API key is configured."""
        key = await self.get_api_key()
        return bool(key)

    def is_algorand_address(self, address: str) -> bool:
        """
        Check if an address is a valid Algorand address.
        Algorand addresses are 58-character base32 strings.
        """
        if not address or len(address) != 58:
            return False

        # Base32 character set (uppercase A-Z, digits 2-7)
        base32_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567')
        return all(c in base32_chars for c in address.upper())

    async def get_wallet_balance(self, address: str) -> Optional[dict]:
        """
        Get ALGO balance and account info.
        Uses Pera API first, falls back to Tatum.

        Returns:
        {
            'address': '...',
            'balance_algo': 123.456,
            'balance_microalgos': 123456000,
            'source': 'pera' or 'tatum'
        }
        """
        if not self.is_algorand_address(address):
            return None

        # Check cache
        if address in self._balance_cache:
            cached = self._balance_cache[address]
            if datetime.now() - cached['cached_at'] < self._cache_ttl:
                return cached['data']

        # Try Pera API first (no key required)
        result = await self._get_balance_pera(address)
        if result:
            self._balance_cache[address] = {
                'data': result,
                'cached_at': datetime.now()
            }
            return result

        # Fallback to Tatum if configured
        if await self.is_configured():
            result = await self._get_balance_tatum(address)
            if result:
                self._balance_cache[address] = {
                    'data': result,
                    'cached_at': datetime.now()
                }
                return result

        return None

    async def _get_balance_pera(self, address: str) -> Optional[dict]:
        """Fetch balance from Pera Wallet Public API."""
        try:
            client = get_client("pera", timeout=30.0)
            response = await client.get(
                f"{self.pera_base_url}/v1/accounts/{address}"
            )

            if response.status_code == 404:
                # Account exists but has no transactions
                return {
                    'address': address,
                    'balance_algo': 0.0,
                    'balance_microalgos': 0,
                    'source': 'pera'
                }

            if response.status_code != 200:
                logger.warning(f"Pera API error: {response.status_code}")
                return None

            data = response.json()
            balance_microalgos = data.get('amount', 0)
            balance_algo = balance_microalgos / MICROALGOS_PER_ALGO

            return {
                'address': address,
                'balance_algo': balance_algo,
                'balance_microalgos': balance_microalgos,
                'source': 'pera'
            }

        except Exception as e:
            logger.debug(f"Pera API error for {address[:20]}...: {e}")
            return None

    async def _get_balance_tatum(self, address: str) -> Optional[dict]:
        """Fetch balance from Tatum.io API."""
        try:
            client = get_client("pera", timeout=30.0)
            response = await client.get(
                f"{self.tatum_base_url}/v2/accounts/{address}",
                headers={"x-api-key": await self.get_api_key()}
            )

            if response.status_code == 404:
                return {
                    'address': address,
                    'balance_algo': 0.0,
                    'balance_microalgos': 0,
                    'source': 'tatum'
                }

            if response.status_code != 200:
                logger.warning(f"Tatum API error: {response.status_code}")
                return None

            data = response.json()
            balance_microalgos = data.get('amount', 0)
            balance_algo = balance_microalgos / MICROALGOS_PER_ALGO

            return {
                'address': address,
                'balance_algo': balance_algo,
                'balance_microalgos': balance_microalgos,
                'source': 'tatum'
            }

        except Exception as e:
            logger.debug(f"Tatum API error for {address[:20]}...: {e}")
            return None

    async def get_wallet_assets(self, address: str) -> List[dict]:
        """
        Get all ASAs (Algorand Standard Assets) for an address.

        Returns list of assets:
        [
            {
                'asset_id': 123456,
                'amount': 1000,
                'decimals': 6,
                'name': 'Asset Name',
                'unit_name': 'ASYM',
                'is_frozen': False
            }
        ]
        """
        if not self.is_algorand_address(address):
            return []

        # Try Pera first
        assets = await self._get_assets_pera(address)
        if assets is not None:
            return assets

        # Fallback to Tatum
        if await self.is_configured():
            assets = await self._get_assets_tatum(address)
            if assets is not None:
                return assets

        return []

    async def _get_assets_pera(self, address: str) -> Optional[List[dict]]:
        """Fetch ASAs from Pera API."""
        try:
            client = get_client("pera", timeout=30.0)
            response = await client.get(
                f"{self.pera_base_url}/v1/accounts/{address}/assets"
            )

            if response.status_code != 200:
                return None

            data = response.json()
            assets = []

            for asset in data.get('assets', []):
                # Skip assets with zero balance
                if asset.get('amount', 0) == 0:
                    continue

                assets.append({
                    'asset_id': asset.get('asset-id'),
                    'amount': asset.get('amount', 0),
                    'decimals': asset.get('decimals', 0),
                    'name': asset.get('name', ''),
                    'unit_name': asset.get('unit-name', ''),
                    'is_frozen': asset.get('is-frozen', False)
                })

            return assets

        except Exception as e:
            logger.debug(f"Pera assets error for {address[:20]}...: {e}")
            return None

    async def _get_assets_tatum(self, address: str) -> Optional[List[dict]]:
        """Fetch ASAs from Tatum API."""
        try:
            client = get_client("pera", timeout=30.0)
            response = await client.get(
                f"{self.tatum_base_url}/v2/accounts/{address}/assets",
                headers={"x-api-key": await self.get_api_key()}
            )

            if response.status_code != 200:
                return None

            data = response.json()
            assets = []

            for asset in data.get('assets', []):
                if asset.get('amount', 0) == 0:
                    continue

                assets.append({
                    'asset_id': asset.get('asset-id'),
                    'amount': asset.get('amount', 0),
                    'decimals': asset.get('decimals', 0),
                    'name': asset.get('name', ''),
                    'unit_name': asset.get('unit-name', ''),
                    'is_frozen': asset.get('is-frozen', False)
                })

            return assets

        except Exception as e:
            logger.debug(f"Tatum assets error for {address[:20]}...: {e}")
            return None

    async def get_asset_info(self, asset_id: int) -> Optional[dict]:
        """
        Get detailed information about an ASA.

        Returns:
        {
            'asset_id': 123456,
            'name': 'Asset Name',
            'unit_name': 'ASYM',
            'decimals': 6,
            'total': 1000000,
            'creator': 'ALGR...',
            'url': 'https://...',
            'metadata_hash': '...'
        }
        """
        # Try Pera first
        info = await self._get_asset_info_pera(asset_id)
        if info:
            return info

        # Fallback to Tatum
        if await self.is_configured():
            info = await self._get_asset_info_tatum(asset_id)
            if info:
                return info

        return None

    async def _get_asset_info_pera(self, asset_id: int) -> Optional[dict]:
        """Fetch asset info from Pera API."""
        try:
            client = get_client("pera", timeout=30.0)
            response = await client.get(
                f"{self.pera_base_url}/v1/assets/{asset_id}"
            )

            if response.status_code != 200:
                return None

            data = response.json()
            params = data.get('params', {})

            return {
                'asset_id': asset_id,
                'name': params.get('name', ''),
                'unit_name': params.get('unit-name', ''),
                'decimals': params.get('decimals', 0),
                'total': params.get('total', 0),
                'creator': params.get('creator', ''),
                'url': params.get('url', ''),
                'metadata_hash': params.get('metadata-hash', '')
            }

        except Exception as e:
            logger.debug(f"Pera asset info error for {asset_id}: {e}")
            return None

    async def _get_asset_info_tatum(self, asset_id: int) -> Optional[dict]:
        """Fetch asset info from Tatum API."""
        try:
            client = get_client("pera", timeout=30.0)
            response = await client.get(
                f"{self.tatum_base_url}/v2/assets/{asset_id}",
                headers={"x-api-key": await self.get_api_key()}
            )

            if response.status_code != 200:
                return None

            data = response.json()
            params = data.get('params', {})

            return {
                'asset_id': asset_id,
                'name': params.get('name', ''),
                'unit_name': params.get('unit-name', ''),
                'decimals': params.get('decimals', 0),
                'total': params.get('total', 0),
                'creator': params.get('creator', ''),
                'url': params.get('url', ''),
                'metadata_hash': params.get('metadata-hash', '')
            }

        except Exception as e:
            logger.debug(f"Tatum asset info error for {asset_id}: {e}")
            return None

    async def get_transactions(self, address: str, limit: int = 50) -> List[dict]:
        """
        Get transaction history for an address.

        Returns list of transactions with type, amount, timestamp, etc.
        """
        if not self.is_algorand_address(address):
            return []

        # Try Pera first
        txs = await self._get_transactions_pera(address, limit)
        if txs is not None:
            return txs

        # Fallback to Tatum
        if await self.is_configured():
            txs = await self._get_transactions_tatum(address, limit)
            if txs is not None:
                return txs

        return []

    async def _get_transactions_pera(self, address: str, limit: int) -> Optional[List[dict]]:
        """Fetch transactions from Pera API."""
        try:
            client = get_client("pera", timeout=30.0)
            response = await client.get(
                f"{self.pera_base_url}/v1/accounts/{address}/transactions",
                params={"limit": limit}
            )

            if response.status_code != 200:
                return None

            data = response.json()
            return data.get('transactions', [])

        except Exception as e:
            logger.debug(f"Pera transactions error for {address[:20]}...: {e}")
            return None

    async def _get_transactions_tatum(self, address: str, limit: int) -> Optional[List[dict]]:
        """Fetch transactions from Tatum API."""
        try:
            client = get_client("pera", timeout=30.0)
            response = await client.get(
                f"{self.tatum_base_url}/v2/accounts/{address}/transactions",
                headers={"x-api-key": await self.get_api_key()},
                params={"limit": limit}
            )

            if response.status_code != 200:
                return None

            data = response.json()
            return data.get('transactions', [])

        except Exception as e:
            logger.debug(f"Tatum transactions error for {address[:20]}...: {e}")
            return None

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get complete address info including balance and assets.
        This is the main method used by the wallet refresh logic.

        Returns:
        {
            'address': '...',
            'balance_algo': 123.456,
            'balance_microalgos': 123456000,
            'assets': [...],  # List of ASAs
            'source': 'pera' or 'tatum'
        }
        """
        balance_info = await self.get_wallet_balance(address)
        if not balance_info:
            return None

        assets = await self.get_wallet_assets(address)

        return {
            **balance_info,
            'assets': assets
        }

    def get_rate_limit_status(self) -> dict:
        """Get current rate limit status."""
        return {
            'configured': self.is_configured(),
            'cache_size': len(self._balance_cache),
            'cache_ttl_minutes': self._cache_ttl.total_seconds() / 60,
            'pera_available': True,  # Pera API is always available (no key)
            'tatum_available': self.is_configured()
        }

    def clear_cache(self):
        """Clear the balance cache."""
        self._balance_cache.clear()
        logger.info("Algorand cache cleared")


# Singleton instance
algorand_service = AlgorandService()
