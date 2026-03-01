"""
Cardano Transaction Hydrator

Uses Blockfrost /txs/{hash}/utxos to fetch full UTXO details.
"""

import logging
from typing import Dict, Any, Optional

from engine.models import ChainId
from engine.hydration.base import TxHydrator
from services.http_client import get_client, fetch_with_retry, blockfrost_fetch
from services.api_key_manager import APIKeyManager
from config import BLOCKFROST_BASE_URL

logger = logging.getLogger(__name__)

_blockfrost_keys = APIKeyManager("blockfrost", "BLOCKFROST_API_KEY")


class CardanoHydrator(TxHydrator):
    chain = ChainId.CARDANO
    provider_name = "blockfrost"

    async def hydrate(self, tx_id: str) -> Optional[Dict[str, Any]]:
        api_key = await _blockfrost_keys.get_api_key()
        if not api_key:
            return None

        headers = {"project_id": api_key}

        # Fetch transaction metadata
        tx_resp = await blockfrost_fetch(
            f"/txs/{tx_id}",
            headers=headers,
            timeout=30.0
        )
        if tx_resp.status_code != 200:
            logger.warning(f"Blockfrost tx detail error for {tx_id[:16]}...: HTTP {tx_resp.status_code}")
            return None
        tx_data = tx_resp.json()

        # Fetch UTXO details
        utxo_resp = await blockfrost_fetch(
            f"/txs/{tx_id}/utxos",
            headers=headers,
            timeout=30.0
        )
        if utxo_resp.status_code != 200:
            logger.warning(f"Blockfrost utxo error for {tx_id[:16]}...: HTTP {utxo_resp.status_code}")
            return None
        utxo_data = utxo_resp.json()

        return {
            "tx_hash": tx_id,
            "block_height": tx_data.get("block_height"),
            "block_time": tx_data.get("block_time"),
            "fees": tx_data.get("fees", "0"),
            "inputs": utxo_data.get("inputs", []),
            "outputs": utxo_data.get("outputs", []),
        }
