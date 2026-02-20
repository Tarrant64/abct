"""
Alchemy EVM Transaction Indexer

Uses Alchemy's alchemy_getAssetTransfers API for high-throughput EVM tx indexing.
Primary indexer (priority 70) with pre-hydration support.

Trade-offs:
- No gas fee data (gas_price=0x0, gas_used=0x0) -- acceptable for portfolio tracking
- Only returns successful transfers (failed txs are missed)
- Two calls per address (fromAddress + toAddress) -- API limitation
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from engine.models import TxIndexEntry, ChainId
from engine.indexing.base import TxIndexer
from services.http_client import get_client
from services.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)


async def _syslog(level: str, msg: str, **extra):
    """Write to the system logs page (LoggingService)."""
    try:
        from services.logging_service import get_logging_service
        svc = get_logging_service()
        if level == "error":
            await svc.error("alchemy-indexer", msg, **extra)
        elif level == "warning":
            await svc.warning("alchemy-indexer", msg, **extra)
        elif level == "info":
            await svc.info("alchemy-indexer", msg, **extra)
        else:
            await svc.debug("alchemy-indexer", msg, **extra)
    except Exception:
        pass


_alchemy_keys = APIKeyManager("alchemy", "ALCHEMY_API_KEY")

# Reuse same RPC URLs as the hydrator
ALCHEMY_RPC_URLS = {
    "ethereum": "https://eth-mainnet.g.alchemy.com/v2",
    "polygon": "https://polygon-mainnet.g.alchemy.com/v2",
    "base": "https://base-mainnet.g.alchemy.com/v2",
}

# ERC-20 Transfer(address,address,uint256) event signature
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

ASSET_TRANSFER_CATEGORIES = ["external", "internal", "erc20", "erc721", "erc1155"]


class AlchemyEvmIndexer(TxIndexer):
    provider_name = "alchemy"

    def __init__(self, chain: ChainId):
        self.chain = chain

    async def _get_rpc_url(self) -> Optional[str]:
        api_key = await _alchemy_keys.get_api_key()
        if not api_key:
            return None
        base = ALCHEMY_RPC_URLS.get(self.chain.value)
        if not base:
            return None
        return f"{base}/{api_key}"

    async def index(self, user_id: int, account_id: str,
                    cursor_start: Optional[str] = None,
                    cursor_end: Optional[str] = None) -> List[TxIndexEntry]:
        rpc_url = await self._get_rpc_url()
        if not rpc_url:
            await _syslog("error", f"No Alchemy API key -- cannot index {self.chain.value}")
            return []

        client = get_client("alchemy", timeout=30.0)

        # Parse block range
        try:
            start_block = hex(int(cursor_start)) if cursor_start else "0x0"
        except (ValueError, TypeError):
            start_block = "0x0"
        try:
            end_block = hex(int(cursor_end)) if cursor_end else "latest"
        except (ValueError, TypeError):
            end_block = "latest"

        # Collect transfers from both directions (API limitation)
        all_transfers: List[Dict] = []
        for direction_key in ("fromAddress", "toAddress"):
            page_key = None
            while True:
                params = {
                    "fromBlock": start_block,
                    "toBlock": end_block,
                    direction_key: account_id,
                    "category": ASSET_TRANSFER_CATEGORIES,
                    "withMetadata": True,
                    "maxCount": "0x3e8",  # 1000 per page
                }
                if page_key:
                    params["pageKey"] = page_key

                resp = await client.post(
                    rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "alchemy_getAssetTransfers",
                        "params": [params],
                    },
                    timeout=30.0,
                )

                if resp.status_code != 200:
                    await _syslog("error", f"Alchemy API returned {resp.status_code} "
                                  f"for {self.chain.value} {direction_key}")
                    break

                data = resp.json()
                if "error" in data:
                    err_msg = data["error"].get("message", "Unknown RPC error")
                    await _syslog("error", f"Alchemy RPC error: {err_msg}")
                    break

                result = data.get("result", {})
                transfers = result.get("transfers", [])
                all_transfers.extend(transfers)

                page_key = result.get("pageKey")
                if not page_key:
                    break

        if not all_transfers:
            await _syslog("info", f"Alchemy({self.chain.value}) indexed 0 transfers "
                          f"for {account_id[:12]}...")
            return []

        # Group transfers by tx hash for dedup and pre-hydration
        tx_map: Dict[str, Dict] = {}
        entries: List[TxIndexEntry] = []
        seen_tx_ids: set = set()

        for transfer in all_transfers:
            tx_hash = transfer.get("hash", "")
            if not tx_hash:
                continue

            if tx_hash not in tx_map:
                block_num_hex = transfer.get("blockNum", "0x0")
                block_num = int(block_num_hex, 16) if block_num_hex else 0

                metadata = transfer.get("metadata", {})
                block_timestamp_str = metadata.get("blockTimestamp", "")
                block_time = _parse_iso_timestamp(block_timestamp_str)

                tx_map[tx_hash] = {
                    "block_num": block_num,
                    "block_time": block_time,
                    "transfers": [],
                }

            tx_map[tx_hash]["transfers"].append(transfer)

            if tx_hash not in seen_tx_ids:
                seen_tx_ids.add(tx_hash)
                info = tx_map[tx_hash]
                entries.append(TxIndexEntry(
                    user_id=user_id,
                    chain=self.chain,
                    account_id=account_id,
                    tx_id=tx_hash,
                    block_height=info["block_num"],
                    block_time=info["block_time"],
                ))

        # Pre-hydrate engine_tx_raw
        await self._pre_hydrate(tx_map)

        await _syslog("info", f"Alchemy({self.chain.value}) indexed {len(entries)} txs for "
                       f"{account_id[:12]}... (from {len(all_transfers)} transfers)")
        return entries

    # ------------------------------------------------------------------
    # Pre-hydration helpers
    # ------------------------------------------------------------------

    async def _pre_hydrate(self, tx_map: Dict[str, Dict]):
        """Store Alchemy transfer data as engine_tx_raw for the normalizer."""
        from engine import db as engine_db

        if not tx_map:
            return

        batch = []
        for tx_hash, info in tx_map.items():
            raw_data = self._to_hydrated_format(tx_hash, info)
            batch.append({
                "chain": self.chain.value,
                "tx_id": tx_hash,
                "raw_data": raw_data,
                "provider": "alchemy",
            })

        await engine_db.upsert_tx_raw_batch(batch)
        logger.debug(f"Pre-hydrated {len(batch)} tx_raw entries from Alchemy")

    def _to_hydrated_format(self, tx_hash: str, info: Dict) -> Dict[str, Any]:
        """Build the format expected by EvmNormalizer from Alchemy transfer data."""
        transfers = info.get("transfers", [])

        native_value_wei = 0
        tx_from = ""
        tx_to = ""

        # Synthesize logs from token transfers
        logs = []

        for t in transfers:
            category = t.get("category", "")
            t_from = (t.get("from") or "").lower()
            t_to = (t.get("to") or "").lower()

            if category in ("external", "internal"):
                # Native ETH/MATIC transfer
                if not tx_from:
                    tx_from = t_from
                if not tx_to:
                    tx_to = t_to

                raw_contract = t.get("rawContract", {})
                value_hex = raw_contract.get("value")
                if value_hex:
                    try:
                        native_value_wei += int(value_hex, 16)
                    except (ValueError, TypeError):
                        pass

            elif category in ("erc20", "erc721", "erc1155"):
                # Token transfer -- synthesize a Transfer event log
                if not tx_from:
                    tx_from = t_from
                if not tx_to:
                    tx_to = t_to

                raw_contract = t.get("rawContract", {})
                contract_addr = (raw_contract.get("address") or "").lower()
                value_hex = raw_contract.get("value") or "0x0"

                if t_from and t_to and contract_addr:
                    from_topic = "0x" + t_from[2:].zfill(64) if t_from.startswith("0x") else ""
                    to_topic = "0x" + t_to[2:].zfill(64) if t_to.startswith("0x") else ""

                    try:
                        val_int = int(value_hex, 16) if value_hex.startswith("0x") else int(value_hex)
                        data_hex = "0x" + hex(val_int)[2:].zfill(64)
                    except (ValueError, TypeError):
                        data_hex = "0x" + "0" * 64

                    if from_topic and to_topic:
                        logs.append({
                            "address": contract_addr,
                            "topics": [_TRANSFER_TOPIC, from_topic, to_topic],
                            "data": data_hex,
                        })

        return {
            "hash": tx_hash,
            "block_number": info.get("block_num", 0),
            "block_time": info.get("block_time", 0),
            "from": tx_from,
            "to": tx_to,
            "value": hex(native_value_wei),
            "gas_price": "0x0",  # Not available from alchemy_getAssetTransfers
            "gas_used": "0x0",   # Not available from alchemy_getAssetTransfers
            "status": "0x1",     # Alchemy only returns successful transfers
            "logs": logs,
        }


def _parse_iso_timestamp(ts_str: str) -> int:
    """Parse ISO 8601 timestamp to unix epoch seconds."""
    if not ts_str:
        return 0
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return 0
