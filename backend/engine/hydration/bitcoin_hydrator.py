"""
Bitcoin Transaction Hydrator

Uses Blockstream /tx/{txid} to fetch full transaction details.
"""

import logging
from typing import Dict, Any, Optional

from engine.models import ChainId
from engine.hydration.base import TxHydrator
from services.http_client import get_client, fetch_with_retry
from config import BLOCKSTREAM_BASE_URL

logger = logging.getLogger(__name__)


class BitcoinHydrator(TxHydrator):
    chain = ChainId.BITCOIN
    provider_name = "blockstream"

    async def hydrate(self, tx_id: str) -> Optional[Dict[str, Any]]:
        client = get_client("blockstream", timeout=30.0)

        resp = await fetch_with_retry(
            client, "GET", f"{BLOCKSTREAM_BASE_URL}/tx/{tx_id}",
        )
        if resp.status_code != 200:
            logger.warning(f"Blockstream tx detail error for {tx_id[:16]}...: HTTP {resp.status_code}")
            return None

        data = resp.json()
        status = data.get("status", {})

        return {
            "txid": tx_id,
            "block_height": status.get("block_height"),
            "block_time": status.get("block_time"),
            "fee": data.get("fee", 0),
            "vin": data.get("vin", []),
            "vout": data.get("vout", []),
            "size": data.get("size"),
            "weight": data.get("weight"),
        }
