"""
Maestro Service - Tertiary Cardano API fallback.

Provides alternative Cardano blockchain data when Blockfrost and CExplorer are unavailable.
Free tier: 500,000 credits/month (credits vary per endpoint).

Auth: api-key header.
Base URL: https://mainnet.gomaestro-api.org/v1
"""

import logging
from typing import Dict, List, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.api_key_manager import APIKeyManager
from services.http_client import get_client

logger = logging.getLogger(__name__)

MAESTRO_BASE_URL = "https://mainnet.gomaestro-api.org/v1"


class MaestroService(APIKeyManager):
    """Lightweight Cardano API service as tertiary fallback after Blockfrost and CExplorer."""

    def __init__(self):
        super().__init__(api_name='maestro', env_var='MAESTRO_API_KEY')

    async def _get_headers(self) -> dict:
        """Get request headers with API key."""
        api_key = await self.get_api_key()
        if not api_key:
            return {}
        return {
            "api-key": api_key,
            "Accept": "application/json"
        }

    async def get_address_utxos(self, address: str) -> Optional[List[dict]]:
        """
        Get UTXOs for a Cardano address.

        Args:
            address: Cardano address (bech32 format)

        Returns:
            List of UTXO dicts or None
        """
        if not await self.is_configured():
            return None

        try:
            headers = await self._get_headers()
            client = get_client("maestro", timeout=30.0)
            response = await client.get(
                f"{MAESTRO_BASE_URL}/addresses/{address}/utxos",
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                return data.get('data', [])
            else:
                logger.warning(f"Maestro UTXOs error: {response.status_code}")

        except Exception as e:
            logger.error(f"Maestro get_address_utxos error: {e}")

        return None

    async def get_stake_info(self, stake_key: str) -> Optional[dict]:
        """
        Get stake account information.

        Args:
            stake_key: Cardano stake address (stake1...)

        Returns:
            Stake account info dict or None
        """
        if not await self.is_configured():
            return None

        try:
            headers = await self._get_headers()
            client = get_client("maestro", timeout=30.0)
            response = await client.get(
                f"{MAESTRO_BASE_URL}/accounts/{stake_key}",
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                return data.get('data', {})
            else:
                logger.warning(f"Maestro stake info error: {response.status_code}")

        except Exception as e:
            logger.error(f"Maestro get_stake_info error: {e}")

        return None

    async def get_asset_info(self, asset_id: str) -> Optional[dict]:
        """
        Get native asset information.

        Args:
            asset_id: Concatenated policy_id + hex_asset_name

        Returns:
            Asset info dict or None
        """
        if not await self.is_configured():
            return None

        try:
            headers = await self._get_headers()
            client = get_client("maestro", timeout=30.0)
            response = await client.get(
                f"{MAESTRO_BASE_URL}/assets/{asset_id}",
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                return data.get('data', {})
            else:
                logger.warning(f"Maestro asset info error: {response.status_code}")

        except Exception as e:
            logger.error(f"Maestro get_asset_info error: {e}")

        return None

    async def get_address_balance(self, address: str) -> Optional[dict]:
        """
        Get balance for a Cardano address by summing UTXOs.

        Returns:
            {lovelace: int, tokens: [{unit, quantity}]} or None
        """
        utxos = await self.get_address_utxos(address)
        if utxos is None:
            return None

        total_lovelace = 0
        tokens = {}

        for utxo in utxos:
            for asset in utxo.get('assets', []):
                unit = asset.get('unit', '')
                quantity = int(asset.get('amount', 0))
                if unit == 'lovelace':
                    total_lovelace += quantity
                else:
                    tokens[unit] = tokens.get(unit, 0) + quantity

        return {
            'lovelace': total_lovelace,
            'ada_balance': total_lovelace / 1_000_000,
            'tokens': [{'unit': u, 'quantity': q} for u, q in tokens.items()],
            'source': 'maestro'
        }

    def clear_cache(self):
        """Clear API key cache."""
        super().clear_cache()


# Singleton instance
maestro_service = MaestroService()
