"""
CoinStats Transaction Hydrator

Uses CoinStats API for non-Cardano chains.
NEVER used for Cardano.
"""

import logging
from typing import Dict, Any, Optional

from engine.models import ChainId
from engine.hydration.base import TxHydrator
from services.http_client import get_client, fetch_with_retry
from services.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

_coinstats_keys = APIKeyManager("coinstats", "COINSTATS_API_KEY")

CHAIN_MAP = {
    "bitcoin": "bitcoin",
    "ethereum": "ethereum",
    "solana": "solana",
    "polygon": "polygon",
    "base": "base",
}


class CoinStatsHydrator(TxHydrator):
    provider_name = "coinstats"

    def __init__(self, chain: ChainId):
        if chain == ChainId.CARDANO:
            raise ValueError("CoinStats cannot be used for Cardano")
        self.chain = chain

    async def hydrate(self, tx_id: str) -> Optional[Dict[str, Any]]:
        if self.chain == ChainId.CARDANO:
            return None

        api_key = await _coinstats_keys.get_api_key()
        if not api_key:
            return None

        chain_id = CHAIN_MAP.get(self.chain.value)
        if not chain_id:
            return None

        client = get_client("coinstats", timeout=30.0)
        resp = await fetch_with_retry(
            client, "GET",
            f"https://openapiv1.coinstats.app/wallet/transaction/{tx_id}",
            params={"network": chain_id},
            headers={"X-API-KEY": api_key},
        )
        if resp.status_code != 200:
            return None

        return resp.json()
