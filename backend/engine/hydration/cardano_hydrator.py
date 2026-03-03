"""
Cardano Transaction Hydrator

Uses direct DB Sync SQL (if available) or Blockfrost /txs/{hash}/utxos
to fetch full UTXO details. Triple fallback: SQL → Blockfrost RYO → Blockfrost.io
"""

import logging
from typing import Dict, Any, Optional

from engine.models import ChainId
from engine.hydration.base import TxHydrator
from services.http_client import blockfrost_fetch
from services.api_key_manager import APIKeyManager
from services.cardano_query import cardano_query

logger = logging.getLogger(__name__)

_blockfrost_keys = APIKeyManager("blockfrost", "BLOCKFROST_API_KEY")


class CardanoHydrator(TxHydrator):
    chain = ChainId.CARDANO
    provider_name = "blockfrost"

    async def hydrate(self, tx_id: str) -> Optional[Dict[str, Any]]:
        async def _sql():
            from services.cardano_db_queries import get_tx_details, get_tx_utxos
            tx_data = await get_tx_details(tx_id)
            if tx_data is None:
                raise ValueError(f"Transaction {tx_id[:16]}... not found in DB Sync")
            utxo_data = await get_tx_utxos(tx_id)
            return {
                "tx_hash": tx_id,
                "block_height": tx_data["block_height"],
                "block_time": tx_data["block_time"],
                "fees": tx_data.get("fees", "0"),
                "inputs": utxo_data.get("inputs", []),
                "outputs": utxo_data.get("outputs", []),
            }

        async def _blockfrost():
            api_key = await _blockfrost_keys.get_api_key()
            if not api_key:
                raise ValueError("No Blockfrost API key")
            headers = {"project_id": api_key}

            tx_resp = await blockfrost_fetch(
                f"/txs/{tx_id}",
                headers=headers,
                timeout=30.0
            )
            if tx_resp.status_code != 200:
                raise ValueError(f"Blockfrost tx detail error: HTTP {tx_resp.status_code}")
            tx_data = tx_resp.json()

            utxo_resp = await blockfrost_fetch(
                f"/txs/{tx_id}/utxos",
                headers=headers,
                timeout=30.0
            )
            if utxo_resp.status_code != 200:
                raise ValueError(f"Blockfrost utxo error: HTTP {utxo_resp.status_code}")
            utxo_data = utxo_resp.json()

            return {
                "tx_hash": tx_id,
                "block_height": tx_data.get("block_height"),
                "block_time": tx_data.get("block_time"),
                "fees": tx_data.get("fees", "0"),
                "inputs": utxo_data.get("inputs", []),
                "outputs": utxo_data.get("outputs", []),
            }

        try:
            return await cardano_query(
                sql_fn=_sql,
                blockfrost_fn=_blockfrost,
                operation=f"hydrate({tx_id[:16]}...)",
            )
        except Exception as e:
            logger.warning(f"Hydration failed for {tx_id[:16]}...: {e}")
            return None
