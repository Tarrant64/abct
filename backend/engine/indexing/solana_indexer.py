"""
Solana Transaction Indexer

Uses Helius getSignaturesForAddress RPC to collect transaction signatures.
"""

import logging
from typing import List, Optional

from engine.models import TxIndexEntry, ChainId
from engine.indexing.base import TxIndexer
from services.http_client import get_client, fetch_with_retry
from services.api_key_manager import APIKeyManager
from config import HELIUS_RPC_URL

logger = logging.getLogger(__name__)

_helius_keys = APIKeyManager("helius", "HELIUS_API_KEY")


class SolanaIndexer(TxIndexer):
    chain = ChainId.SOLANA
    provider_name = "helius"

    async def index(self, user_id: int, account_id: str,
                    cursor_start: Optional[str] = None,
                    cursor_end: Optional[str] = None) -> List[TxIndexEntry]:
        api_key = await _helius_keys.get_api_key()
        rpc_url = f"{HELIUS_RPC_URL}/?api-key={api_key}" if api_key else "https://api.mainnet-beta.solana.com"

        client = get_client("helius", timeout=30.0)
        entries = []
        before = cursor_start  # Signature pagination cursor

        while True:
            params = [account_id, {"limit": 1000}]
            if before:
                params[1]["before"] = before
            if cursor_end:
                params[1]["until"] = cursor_end

            resp = await fetch_with_retry(
                client, "POST", rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getSignaturesForAddress",
                    "params": params,
                },
            )
            if resp.status_code != 200:
                break

            data = resp.json()
            result = data.get("result", [])
            if not result:
                break

            for sig_info in result:
                signature = sig_info.get("signature", "")
                entries.append(TxIndexEntry(
                    user_id=user_id,
                    chain=ChainId.SOLANA,
                    account_id=account_id,
                    tx_id=signature,
                    block_height=sig_info.get("slot"),
                    block_time=sig_info.get("blockTime"),
                ))

            if len(result) < 1000:
                break
            before = result[-1].get("signature")

        logger.info(f"Solana indexed {len(entries)} txs for {account_id[:12]}...")
        return entries
