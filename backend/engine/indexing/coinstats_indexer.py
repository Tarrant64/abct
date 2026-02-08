"""
CoinStats Transaction Indexer

Uses CoinStats API for non-Cardano chains.
NEVER used for Cardano — enforced at registry level and here.
"""

import logging
from typing import List, Optional

from engine.models import TxIndexEntry, ChainId
from engine.indexing.base import TxIndexer
from services.http_client import get_client, fetch_with_retry
from services.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

_coinstats_keys = APIKeyManager("coinstats", "COINSTATS_API_KEY")

# CoinStats chain identifiers
CHAIN_MAP = {
    "bitcoin": "bitcoin",
    "ethereum": "ethereum",
    "solana": "solana",
    "polygon": "polygon",
    "base": "base",
    # Cardano intentionally NOT mapped
}


class CoinStatsIndexer(TxIndexer):
    provider_name = "coinstats"

    def __init__(self, chain: ChainId):
        if chain == ChainId.CARDANO:
            raise ValueError("CoinStats cannot be used for Cardano")
        self.chain = chain

    async def index(self, user_id: int, account_id: str,
                    cursor_start: Optional[str] = None,
                    cursor_end: Optional[str] = None) -> List[TxIndexEntry]:
        if self.chain == ChainId.CARDANO:
            logger.error("CoinStats indexer called for Cardano — refusing")
            return []

        api_key = await _coinstats_keys.get_api_key()
        if not api_key:
            logger.warning("No CoinStats API key configured")
            return []

        chain_id = CHAIN_MAP.get(self.chain.value)
        if not chain_id:
            logger.warning(f"CoinStats: no chain mapping for {self.chain.value}")
            return []

        client = get_client("coinstats", timeout=30.0)
        entries = []
        page = 1

        while True:
            resp = await fetch_with_retry(
                client, "GET",
                f"https://openapiv1.coinstats.app/wallet/transactions",
                params={
                    "address": account_id,
                    "network": chain_id,
                    "page": page,
                    "limit": 100,
                },
                headers={"X-API-KEY": api_key},
            )

            if resp.status_code != 200:
                logger.warning(f"CoinStats indexing error: HTTP {resp.status_code}")
                break

            data = resp.json()
            txs = data.get("transactions", data.get("result", []))
            if not txs:
                break

            for tx in txs:
                tx_id = tx.get("hash", tx.get("txHash", ""))
                entries.append(TxIndexEntry(
                    user_id=user_id,
                    chain=self.chain,
                    account_id=account_id,
                    tx_id=tx_id,
                    block_height=tx.get("blockNumber", tx.get("block")),
                    block_time=tx.get("timestamp"),
                ))

            if len(txs) < 100:
                break
            page += 1

        logger.info(f"CoinStats indexed {len(entries)} txs for {self.chain.value}:{account_id[:12]}...")
        return entries
