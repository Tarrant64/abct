"""
Bitcoin Transaction Indexer

Uses Blockstream API /address/{addr}/txs to collect tx IDs.
Paginates using the last_seen_txid cursor.
"""

import logging
from typing import List, Optional

from engine.models import TxIndexEntry, ChainId
from engine.indexing.base import TxIndexer
from services.http_client import get_client, fetch_with_retry
from config import BLOCKSTREAM_BASE_URL

logger = logging.getLogger(__name__)


class BitcoinIndexer(TxIndexer):
    chain = ChainId.BITCOIN
    provider_name = "blockstream"

    async def index(self, user_id: int, account_id: str,
                    cursor_start: Optional[str] = None,
                    cursor_end: Optional[str] = None) -> List[TxIndexEntry]:
        client = get_client("blockstream", timeout=30.0)
        entries = []
        last_seen_txid = cursor_start  # For pagination

        while True:
            url = f"{BLOCKSTREAM_BASE_URL}/address/{account_id}/txs"
            if last_seen_txid:
                url += f"/chain/{last_seen_txid}"

            resp = await fetch_with_retry(client, "GET", url)
            if resp.status_code != 200:
                logger.warning(
                    f"Blockstream indexing error for {account_id[:12]}...: "
                    f"HTTP {resp.status_code}"
                )
                break

            data = resp.json()
            if not data:
                break

            for tx in data:
                txid = tx.get("txid", "")
                status = tx.get("status", {})
                block_height = status.get("block_height")
                block_time = status.get("block_time")

                entries.append(TxIndexEntry(
                    user_id=user_id,
                    chain=ChainId.BITCOIN,
                    account_id=account_id,
                    tx_id=txid,
                    block_height=block_height,
                    block_time=block_time,
                ))

            # Blockstream returns 25 txs per page
            if len(data) < 25:
                break
            last_seen_txid = data[-1].get("txid", "")

        logger.info(f"Bitcoin indexed {len(entries)} txs for {account_id[:12]}...")
        return entries
