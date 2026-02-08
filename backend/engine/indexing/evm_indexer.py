"""
EVM Transaction Indexer

Uses Etherscan-compatible APIs (Etherscan, Basescan, Polygonscan) to collect tx IDs.
Supports Ethereum, Polygon, and Base via chain-parameterized configuration.
"""

import logging
from typing import List, Optional, Dict

from engine.models import TxIndexEntry, ChainId
from engine.indexing.base import TxIndexer
from services.http_client import get_client, fetch_with_retry
from services.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

# Chain-specific configurations matching existing etherscan_service.py
CHAIN_CONFIGS: Dict[str, Dict] = {
    "ethereum": {
        "base_url": "https://api.etherscan.io/api",
        "client_name": "etherscan",
    },
    "polygon": {
        "base_url": "https://api.polygonscan.com/api",
        "client_name": "etherscan",
    },
    "base": {
        "base_url": "https://api.basescan.org/api",
        "client_name": "etherscan",
    },
}

_etherscan_keys = APIKeyManager("etherscan", "ETHERSCAN_API_KEY")


class EvmIndexer(TxIndexer):
    provider_name = "etherscan"

    def __init__(self, chain: ChainId):
        self.chain = chain

    async def index(self, user_id: int, account_id: str,
                    cursor_start: Optional[str] = None,
                    cursor_end: Optional[str] = None) -> List[TxIndexEntry]:
        config = CHAIN_CONFIGS.get(self.chain.value)
        if not config:
            logger.error(f"No EVM config for chain {self.chain.value}")
            return []

        api_key = await _etherscan_keys.get_api_key()
        if not api_key:
            logger.warning(f"No Etherscan API key for {self.chain.value} indexing")
            return []

        client = get_client(config["client_name"], timeout=30.0)
        entries = []

        # Fetch normal transactions
        start_block = int(cursor_start) if cursor_start else 0
        end_block = int(cursor_end) if cursor_end else 99999999

        page = 1
        while True:
            params = {
                "module": "account",
                "action": "txlist",
                "address": account_id,
                "startblock": start_block,
                "endblock": end_block,
                "page": page,
                "offset": 1000,
                "sort": "asc",
                "apikey": api_key,
            }

            resp = await fetch_with_retry(
                client, "GET", config["base_url"], params=params,
            )
            if resp.status_code != 200:
                break

            data = resp.json()
            result = data.get("result", [])
            if not isinstance(result, list) or not result:
                break

            for tx in result:
                entries.append(TxIndexEntry(
                    user_id=user_id,
                    chain=self.chain,
                    account_id=account_id,
                    tx_id=tx.get("hash", ""),
                    block_height=int(tx.get("blockNumber", 0)),
                    block_time=int(tx.get("timeStamp", 0)),
                ))

            if len(result) < 1000:
                break
            page += 1

        # Also fetch internal transactions
        page = 1
        while True:
            params = {
                "module": "account",
                "action": "txlistinternal",
                "address": account_id,
                "startblock": start_block,
                "endblock": end_block,
                "page": page,
                "offset": 1000,
                "sort": "asc",
                "apikey": api_key,
            }

            resp = await fetch_with_retry(
                client, "GET", config["base_url"], params=params,
            )
            if resp.status_code != 200:
                break

            data = resp.json()
            result = data.get("result", [])
            if not isinstance(result, list) or not result:
                break

            seen_txids = {e.tx_id for e in entries}
            for tx in result:
                txid = tx.get("hash", "")
                if txid and txid not in seen_txids:
                    entries.append(TxIndexEntry(
                        user_id=user_id,
                        chain=self.chain,
                        account_id=account_id,
                        tx_id=txid,
                        block_height=int(tx.get("blockNumber", 0)),
                        block_time=int(tx.get("timeStamp", 0)),
                    ))
                    seen_txids.add(txid)

            if len(result) < 1000:
                break
            page += 1

        # Also fetch ERC-20 token transfers
        page = 1
        while True:
            params = {
                "module": "account",
                "action": "tokentx",
                "address": account_id,
                "startblock": start_block,
                "endblock": end_block,
                "page": page,
                "offset": 1000,
                "sort": "asc",
                "apikey": api_key,
            }

            resp = await fetch_with_retry(
                client, "GET", config["base_url"], params=params,
            )
            if resp.status_code != 200:
                break

            data = resp.json()
            result = data.get("result", [])
            if not isinstance(result, list) or not result:
                break

            seen_txids = {e.tx_id for e in entries}
            for tx in result:
                txid = tx.get("hash", "")
                if txid and txid not in seen_txids:
                    entries.append(TxIndexEntry(
                        user_id=user_id,
                        chain=self.chain,
                        account_id=account_id,
                        tx_id=txid,
                        block_height=int(tx.get("blockNumber", 0)),
                        block_time=int(tx.get("timeStamp", 0)),
                    ))
                    seen_txids.add(txid)

            if len(result) < 1000:
                break
            page += 1

        logger.info(f"EVM({self.chain.value}) indexed {len(entries)} txs for {account_id[:12]}...")
        return entries
