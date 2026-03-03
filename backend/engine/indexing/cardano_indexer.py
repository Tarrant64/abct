"""
Cardano Transaction Indexer

Uses direct DB Sync SQL (if available) or Blockfrost to collect tx IDs.
Triple fallback: SQL → Blockfrost RYO → Blockfrost.io
"""

import logging
from typing import List, Optional

from engine.models import TxIndexEntry, ChainId
from engine.indexing.base import TxIndexer
from services.http_client import blockfrost_fetch
from services.api_key_manager import APIKeyManager
from services.cardano_query import cardano_query

logger = logging.getLogger(__name__)

_blockfrost_keys = APIKeyManager("blockfrost", "BLOCKFROST_API_KEY")


class CardanoIndexer(TxIndexer):
    chain = ChainId.CARDANO
    provider_name = "blockfrost"

    async def index(self, user_id: int, account_id: str,
                    cursor_start: Optional[str] = None,
                    cursor_end: Optional[str] = None) -> List[TxIndexEntry]:

        async def _sql():
            from services.cardano_db_queries import get_address_transactions, get_stake_transactions
            # Convert Blockfrost-style cursor (block height string) to int
            from_block = int(cursor_start) if cursor_start else 0

            if account_id.startswith("stake1"):
                rows = await get_stake_transactions(account_id, from_block=from_block)
            else:
                rows = await get_address_transactions(account_id, from_block=from_block)

            entries = []
            for tx in rows:
                entries.append(TxIndexEntry(
                    user_id=user_id,
                    chain=ChainId.CARDANO,
                    account_id=account_id,
                    tx_id=tx["tx_hash"],
                    block_height=tx.get("block_height"),
                    block_time=tx.get("block_time"),
                ))
            return entries

        async def _blockfrost():
            api_key = await _blockfrost_keys.get_api_key()
            if not api_key:
                raise ValueError("No Blockfrost API key for Cardano indexing")

            entries = []
            page = 1

            if account_id.startswith("stake1"):
                base_path = f"/accounts/{account_id}/transactions"
            else:
                base_path = f"/addresses/{account_id}/transactions"

            while True:
                params = {"count": 100, "page": page, "order": "asc"}
                if cursor_start:
                    params["from"] = cursor_start
                if cursor_end:
                    params["to"] = cursor_end

                resp = await blockfrost_fetch(
                    base_path,
                    params=params,
                    headers={"project_id": api_key},
                    timeout=30.0
                )

                if resp.status_code == 404:
                    break
                if resp.status_code != 200:
                    logger.warning(
                        f"Blockfrost indexing error for {account_id[:20]}...: "
                        f"HTTP {resp.status_code}"
                    )
                    break

                data = resp.json()
                if not data:
                    break

                for tx in data:
                    entries.append(TxIndexEntry(
                        user_id=user_id,
                        chain=ChainId.CARDANO,
                        account_id=account_id,
                        tx_id=tx.get("tx_hash", ""),
                        block_height=tx.get("block_height"),
                        block_time=tx.get("block_time"),
                    ))

                if len(data) < 100:
                    break
                page += 1

            return entries

        try:
            entries = await cardano_query(
                sql_fn=_sql,
                blockfrost_fn=_blockfrost,
                operation=f"index({account_id[:20]}...)",
            )
            logger.info(f"Cardano indexed {len(entries)} txs for {account_id[:20]}...")
            return entries
        except Exception as e:
            logger.warning(f"Cardano indexing failed for {account_id[:20]}...: {e}")
            return []
