"""
Cardano Transaction Indexer

Uses Blockfrost /addresses/{addr}/transactions to collect tx IDs.
Paginates through all transactions for an address.
"""

import logging
from typing import List, Optional

from engine.models import TxIndexEntry, ChainId
from engine.indexing.base import TxIndexer
from services.http_client import get_client, fetch_with_retry, blockfrost_fetch
from services.api_key_manager import APIKeyManager
from config import BLOCKFROST_BASE_URL

logger = logging.getLogger(__name__)

_blockfrost_keys = APIKeyManager("blockfrost", "BLOCKFROST_API_KEY")


class CardanoIndexer(TxIndexer):
    chain = ChainId.CARDANO
    provider_name = "blockfrost"

    async def index(self, user_id: int, account_id: str,
                    cursor_start: Optional[str] = None,
                    cursor_end: Optional[str] = None) -> List[TxIndexEntry]:
        api_key = await _blockfrost_keys.get_api_key()
        if not api_key:
            logger.warning("No Blockfrost API key for Cardano indexing")
            return []

        entries = []
        page = 1

        # Determine endpoint: stake addresses use /accounts/, payment addresses use /addresses/
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
                # Address has no transactions
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

        logger.info(f"Cardano indexed {len(entries)} txs for {account_id[:20]}...")
        return entries
