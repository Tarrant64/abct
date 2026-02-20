"""
Ankr EVM Transaction Indexer

Uses Ankr's Advanced API (ankr_getTransactionsByAddress + ankr_getTokenTransfers)
as a last-resort fallback indexer. Works without an API key (free tier).

Fallback chain: Alchemy (70) -> Etherscan (60) -> Ankr (40)

Advantages over Alchemy:
- Full gas data (gas_price, gas_used) for accurate fee calculations
- Works without API key (reduced rate)

Trade-offs:
- Lower throughput than Alchemy (3 req/s free tier)
- Rate limiting without API key
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from engine.models import TxIndexEntry, ChainId
from engine.indexing.base import TxIndexer
from services.http_client import get_client
from config import ANKR_API_KEY

logger = logging.getLogger(__name__)


async def _syslog(level: str, msg: str, **extra):
    """Write to the system logs page (LoggingService)."""
    try:
        from services.logging_service import get_logging_service
        svc = get_logging_service()
        if level == "error":
            await svc.error("ankr-indexer", msg, **extra)
        elif level == "warning":
            await svc.warning("ankr-indexer", msg, **extra)
        elif level == "info":
            await svc.info("ankr-indexer", msg, **extra)
        else:
            await svc.debug("ankr-indexer", msg, **extra)
    except Exception:
        pass


# ERC-20 Transfer(address,address,uint256) event signature
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Chain name mapping: our ChainId -> Ankr blockchain identifier
ANKR_CHAIN_MAP = {
    "ethereum": "eth",
    "polygon": "polygon",
    "base": "base",
}

ANKR_MULTICHAIN_URL = "https://rpc.ankr.com/multichain"


class AnkrEvmIndexer(TxIndexer):
    provider_name = "ankr"

    def __init__(self, chain: ChainId):
        self.chain = chain

    def _get_rpc_url(self) -> str:
        """Build RPC URL with optional API key."""
        if ANKR_API_KEY:
            return f"{ANKR_MULTICHAIN_URL}/{ANKR_API_KEY}"
        return ANKR_MULTICHAIN_URL

    async def index(self, user_id: int, account_id: str,
                    cursor_start: Optional[str] = None,
                    cursor_end: Optional[str] = None) -> List[TxIndexEntry]:
        ankr_chain = ANKR_CHAIN_MAP.get(self.chain.value)
        if not ankr_chain:
            await _syslog("error", f"No Ankr chain mapping for {self.chain.value}")
            return []

        rpc_url = self._get_rpc_url()
        client = get_client("ankr", timeout=30.0)

        entries: List[TxIndexEntry] = []
        normal_txs: Dict[str, Dict] = {}
        token_txs: Dict[str, List[Dict]] = {}

        # -- Fetch normal transactions -----------------------------------------
        page_token = ""
        while True:
            params: Dict[str, Any] = {
                "blockchain": ankr_chain,
                "address": [account_id],
                "pageSize": 1000,
                "includeLogs": True,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "ankr_getTransactionsByAddress",
                    "params": params,
                },
                timeout=30.0,
            )

            if resp.status_code != 200:
                await _syslog("error", f"Ankr getTransactions returned {resp.status_code} "
                              f"for {self.chain.value}")
                break

            data = resp.json()
            if "error" in data:
                err_msg = data["error"].get("message", "Unknown RPC error")
                await _syslog("error", f"Ankr RPC error: {err_msg}")
                break

            result = data.get("result", {})
            transactions = result.get("transactions", [])
            if not transactions:
                break

            seen_txids = {e.tx_id for e in entries}
            for tx in transactions:
                tx_hash = tx.get("hash", "")
                if not tx_hash:
                    continue

                block_time = _parse_block_time(tx.get("timestamp"))
                block_height = _parse_int(tx.get("blockNumber"))

                normal_txs[tx_hash] = tx

                if tx_hash not in seen_txids:
                    seen_txids.add(tx_hash)
                    entries.append(TxIndexEntry(
                        user_id=user_id,
                        chain=self.chain,
                        account_id=account_id,
                        tx_id=tx_hash,
                        block_height=block_height,
                        block_time=block_time,
                    ))

            page_token = result.get("nextPageToken", "")
            if not page_token:
                break

        # -- Fetch token transfers ---------------------------------------------
        page_token = ""
        while True:
            params: Dict[str, Any] = {
                "blockchain": [ankr_chain],
                "address": [account_id],
                "pageSize": 1000,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = await client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "ankr_getTokenTransfers",
                    "params": params,
                },
                timeout=30.0,
            )

            if resp.status_code != 200:
                await _syslog("warning", f"Ankr getTokenTransfers returned {resp.status_code} "
                              f"for {self.chain.value}")
                break

            data = resp.json()
            if "error" in data:
                break

            result = data.get("result", {})
            transfers = result.get("transfers", [])
            if not transfers:
                break

            seen_txids = {e.tx_id for e in entries}
            for t in transfers:
                tx_hash = t.get("transactionHash", "")
                if not tx_hash:
                    continue

                token_txs.setdefault(tx_hash, []).append(t)

                if tx_hash not in seen_txids:
                    seen_txids.add(tx_hash)
                    block_time = _parse_block_time(t.get("timestamp"))
                    block_height = _parse_int(t.get("blockHeight"))
                    entries.append(TxIndexEntry(
                        user_id=user_id,
                        chain=self.chain,
                        account_id=account_id,
                        tx_id=tx_hash,
                        block_height=block_height,
                        block_time=block_time,
                    ))

            page_token = result.get("nextPageToken", "")
            if not page_token:
                break

        # Pre-hydrate
        await self._pre_hydrate(normal_txs, token_txs)

        hydrated_count = len(set(normal_txs.keys()) | set(token_txs.keys()))
        await _syslog("info", f"Ankr({self.chain.value}) indexed {len(entries)} txs for "
                       f"{account_id[:12]}... (pre-hydrated {hydrated_count} tx_raw)")
        return entries

    # ------------------------------------------------------------------
    # Pre-hydration helpers
    # ------------------------------------------------------------------

    async def _pre_hydrate(self, normal_txs: Dict[str, Dict],
                           token_txs: Dict[str, List[Dict]]):
        """Convert Ankr data to normalizer-expected format and store as tx_raw."""
        from engine import db as engine_db

        all_tx_ids = set(normal_txs.keys()) | set(token_txs.keys())
        if not all_tx_ids:
            return

        batch = []
        for tx_id in all_tx_ids:
            normal = normal_txs.get(tx_id)
            tokens = token_txs.get(tx_id, [])
            raw_data = self._to_hydrated_format(tx_id, normal, tokens)
            batch.append({
                "chain": self.chain.value,
                "tx_id": tx_id,
                "raw_data": raw_data,
                "provider": "ankr",
            })

        await engine_db.upsert_tx_raw_batch(batch)
        logger.debug(f"Pre-hydrated {len(batch)} tx_raw entries from Ankr")

    def _to_hydrated_format(self, tx_id: str, normal: Optional[Dict],
                            tokens: List[Dict]) -> Dict[str, Any]:
        """Build the format expected by EvmNormalizer from Ankr data."""
        if normal:
            value_wei = _parse_hex_or_int(normal.get("value", "0x0"))
            gas_price = _parse_hex_or_int(normal.get("gasPrice", "0x0"))
            gas_used = _parse_hex_or_int(normal.get("gasUsed", "0x0"))
            tx_from = (normal.get("from") or "").lower()
            tx_to = (normal.get("to") or "").lower()
            block_number = _parse_int(normal.get("blockNumber"))
            block_time = _parse_block_time(normal.get("timestamp"))

            status_val = normal.get("status")
            if status_val is not None:
                status = "0x0" if status_val in (0, "0", "0x0") else "0x1"
            else:
                status = "0x1"
        else:
            # Token-only tx
            base = tokens[0] if tokens else {}
            value_wei = 0
            gas_price = 0
            gas_used = 0
            tx_from = (base.get("fromAddress") or "").lower()
            tx_to = (base.get("toAddress") or "").lower()
            block_number = _parse_int(base.get("blockHeight"))
            block_time = _parse_block_time(base.get("timestamp"))
            status = "0x1"

        # Synthesize Transfer event logs from token transfer data
        logs = []
        for t in tokens:
            from_addr = (t.get("fromAddress") or "").lower()
            to_addr = (t.get("toAddress") or "").lower()
            token_value = t.get("value", "0")
            contract = (t.get("contractAddress") or "").lower()

            try:
                val_int = int(token_value)
            except (ValueError, TypeError):
                val_int = 0

            from_topic = "0x" + from_addr[2:].zfill(64) if from_addr.startswith("0x") else ""
            to_topic = "0x" + to_addr[2:].zfill(64) if to_addr.startswith("0x") else ""
            data_hex = "0x" + hex(val_int)[2:].zfill(64)

            if from_topic and to_topic:
                logs.append({
                    "address": contract,
                    "topics": [_TRANSFER_TOPIC, from_topic, to_topic],
                    "data": data_hex,
                })

        return {
            "hash": tx_id,
            "block_number": block_number,
            "block_time": block_time,
            "from": tx_from,
            "to": tx_to,
            "value": hex(value_wei),
            "gas_price": hex(gas_price),
            "gas_used": hex(gas_used),
            "status": status,
            "logs": logs,
        }


# ------------------------------------------------------------------
# Parsing helpers
# ------------------------------------------------------------------

def _parse_block_time(value) -> int:
    """Parse timestamp from Ankr -- can be int, string int, hex, or ISO date."""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
        if value.startswith("0x"):
            try:
                return int(value, 16)
            except ValueError:
                pass
        try:
            ts_str = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts_str)
            return int(dt.timestamp())
        except (ValueError, TypeError):
            pass
    return 0


def _parse_int(value) -> int:
    """Parse integer from Ankr -- can be int, string int, or hex string."""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if value.startswith("0x"):
            try:
                return int(value, 16)
            except ValueError:
                return 0
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _parse_hex_or_int(value) -> int:
    """Parse a value that may be hex string, decimal string, or int."""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if value.startswith("0x"):
            try:
                return int(value, 16)
            except ValueError:
                return 0
        try:
            return int(value)
        except ValueError:
            return 0
    return 0
