"""
EVM Transaction Indexer

Uses Etherscan-compatible APIs (Etherscan, Basescan, Polygonscan) to collect tx IDs.
Supports Ethereum, Polygon, and Base via chain-parameterized configuration.

Pre-hydrates engine_tx_raw from Etherscan data so the hydration phase can skip
expensive RPC calls.  The raw data is stored in the same format the EvmNormalizer
expects (hex values, synthesized Transfer event logs).
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any

from engine.models import TxIndexEntry, ChainId
from engine.indexing.base import TxIndexer
from services.http_client import get_client, fetch_with_retry
from services.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)


async def _syslog(level: str, msg: str, **extra):
    """Write to the system logs page (LoggingService)."""
    try:
        from services.logging_service import get_logging_service
        svc = get_logging_service()
        if level == "error":
            await svc.error("evm-indexer", msg, **extra)
        elif level == "warning":
            await svc.warning("evm-indexer", msg, **extra)
        elif level == "info":
            await svc.info("evm-indexer", msg, **extra)
        else:
            await svc.debug("evm-indexer", msg, **extra)
    except Exception:
        pass

# Etherscan V2 unified API — single endpoint with chainid parameter
ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"
BLOCKSCOUT_PRO_URL = "https://api.blockscout.com/v2/api"

CHAIN_CONFIGS: Dict[str, Dict] = {
    "ethereum": {
        "base_url": ETHERSCAN_V2_URL,
        "chainid": 1,
        "client_name": "etherscan",
    },
    "polygon": {
        "base_url": ETHERSCAN_V2_URL,
        "chainid": 137,
        "client_name": "etherscan",
    },
    "base": {
        "base_url": ETHERSCAN_V2_URL,
        "chainid": 8453,
        "client_name": "etherscan",
    },
}

_etherscan_keys = APIKeyManager("etherscan", "ETHERSCAN_API_KEY")
_blockscout_keys = APIKeyManager("blockscout", "BLOCKSCOUT_API_KEY")

# ERC-20 Transfer(address,address,uint256) event signature
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Shared rate limiter: Etherscan free tier = 5 calls/sec with key, 1/5sec without.
# Use a lock + sleep to serialize calls across all concurrent indexer instances.
_api_lock = asyncio.Lock()
_MIN_CALL_INTERVAL = 0.35  # seconds between calls (~2.8/sec, safe margin for 3/sec limit)
_last_call_time = 0.0


async def _get_etherscan_compatible_provider() -> Optional[Dict[str, Any]]:
    """Prefer Blockscout PRO, then fall back to Etherscan."""
    blockscout_key = await _blockscout_keys.get_api_key()
    if blockscout_key:
        return {
            "name": "Blockscout PRO",
            "provider": "blockscout",
            "base_url": BLOCKSCOUT_PRO_URL,
            "chain_param": "chain_id",
            "client_name": "blockscout",
            "api_key": blockscout_key,
        }

    etherscan_key = await _etherscan_keys.get_api_key()
    if etherscan_key:
        return {
            "name": "Etherscan",
            "provider": "etherscan",
            "base_url": ETHERSCAN_V2_URL,
            "chain_param": "chainid",
            "client_name": "etherscan",
            "api_key": etherscan_key,
        }

    return None


async def _rate_limited_get(client, url, params):
    """Make an Etherscan API call with global rate limiting."""
    global _last_call_time
    async with _api_lock:
        now = asyncio.get_event_loop().time()
        wait = _MIN_CALL_INTERVAL - (now - _last_call_time)
        if wait > 0:
            await asyncio.sleep(wait)
        resp = await fetch_with_retry(client, "GET", url, params=params)
        _last_call_time = asyncio.get_event_loop().time()
        return resp


class EvmIndexer(TxIndexer):
    provider_name = "etherscan"

    def __init__(self, chain: ChainId):
        self.chain = chain

    async def index(self, user_id: int, account_id: str,
                    cursor_start: Optional[str] = None,
                    cursor_end: Optional[str] = None) -> List[TxIndexEntry]:
        config = CHAIN_CONFIGS.get(self.chain.value)
        if not config:
            await _syslog("error", f"No EVM config for chain {self.chain.value}")
            return []

        provider = await _get_etherscan_compatible_provider()
        if not provider:
            await _syslog("error", f"No Blockscout or Etherscan API key configured - "
                          f"cannot index {self.chain.value} transactions")
            return []

        client = get_client(provider["client_name"], timeout=30.0)
        entries: List[TxIndexEntry] = []

        # cursor_start/end may be block numbers (int-parseable) or ISO date strings
        # from incremental backfills. For EVM we need block numbers; default to full range.
        try:
            start_block = int(cursor_start) if cursor_start else 0
        except (ValueError, TypeError):
            start_block = 0  # ISO date string from orchestrator — fetch all blocks
        try:
            end_block = int(cursor_end) if cursor_end else 99999999
        except (ValueError, TypeError):
            end_block = 99999999

        # Collect raw Etherscan data for pre-hydration
        normal_txs: Dict[str, Dict] = {}   # tx_hash -> Etherscan txlist dict
        token_txs: Dict[str, List[Dict]] = {}  # tx_hash -> [tokentx dicts]

        # ── Fetch normal transactions ────────────────────────────────────
        page = 1
        while True:
            params = {
                provider["chain_param"]: config["chainid"],
                "module": "account",
                "action": "txlist",
                "address": account_id,
                "startblock": start_block,
                "endblock": end_block,
                "page": page,
                "offset": 10000,
                "sort": "asc",
                "apikey": provider["api_key"],
            }

            resp = await _rate_limited_get(client, provider["base_url"], params)
            if resp.status_code != 200:
                await _syslog("error", f"{provider['name']} txlist API returned {resp.status_code} "
                              f"for {self.chain.value}")
                break

            data = resp.json()
            result = data.get("result", [])
            # Etherscan returns error string in "result" on failure
            if isinstance(result, str):
                await _syslog("warning", f"{provider['name']} txlist: {data.get('message', '')} - {result}")
                break
            if not result:
                break

            for tx in result:
                tx_hash = tx.get("hash", "")
                entries.append(TxIndexEntry(
                    user_id=user_id,
                    chain=self.chain,
                    account_id=account_id,
                    tx_id=tx_hash,
                    block_height=int(tx.get("blockNumber", 0)),
                    block_time=int(tx.get("timeStamp", 0)),
                ))
                normal_txs[tx_hash] = tx

            if len(result) < 10000:
                break
            page += 1

        # ── Fetch internal transactions ──────────────────────────────────
        page = 1
        while True:
            params = {
                provider["chain_param"]: config["chainid"],
                "module": "account",
                "action": "txlistinternal",
                "address": account_id,
                "startblock": start_block,
                "endblock": end_block,
                "page": page,
                "offset": 10000,
                "sort": "asc",
                "apikey": provider["api_key"],
            }

            resp = await _rate_limited_get(client, provider["base_url"], params)
            if resp.status_code != 200:
                await _syslog("warning", f"{provider['name']} txlistinternal API returned {resp.status_code} "
                              f"for {self.chain.value}")
                break

            data = resp.json()
            result = data.get("result", [])
            if isinstance(result, str):
                break  # Error string, not a list — skip silently (internal txs are optional)
            if not result:
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
                # Store internal tx data if we don't have a normal tx for this hash
                if txid and txid not in normal_txs:
                    normal_txs[txid] = tx

            if len(result) < 10000:
                break
            page += 1

        # ── Fetch ERC-20 token transfers ─────────────────────────────────
        page = 1
        while True:
            params = {
                provider["chain_param"]: config["chainid"],
                "module": "account",
                "action": "tokentx",
                "address": account_id,
                "startblock": start_block,
                "endblock": end_block,
                "page": page,
                "offset": 10000,
                "sort": "asc",
                "apikey": provider["api_key"],
            }

            resp = await _rate_limited_get(client, provider["base_url"], params)
            if resp.status_code != 200:
                await _syslog("warning", f"{provider['name']} tokentx API returned {resp.status_code} "
                              f"for {self.chain.value}")
                break

            data = resp.json()
            result = data.get("result", [])
            if isinstance(result, str):
                await _syslog("warning", f"{provider['name']} tokentx: {data.get('message', '')} - {result}")
                break
            if not result:
                break

            seen_txids = {e.tx_id for e in entries}
            for tx in result:
                txid = tx.get("hash", "")
                # Accumulate ALL token transfers per tx_hash
                if txid:
                    token_txs.setdefault(txid, []).append(tx)
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

            if len(result) < 10000:
                break
            page += 1

        # ── Pre-hydrate: store Etherscan data as engine_tx_raw ───────────
        await self._pre_hydrate(normal_txs, token_txs, provider["provider"])

        hydrated_count = len(set(normal_txs.keys()) | set(token_txs.keys()))
        await _syslog("info", f"EVM({self.chain.value}) indexed {len(entries)} txs for "
                       f"{account_id[:12]}... (pre-hydrated {hydrated_count} tx_raw, "
                       f"{len(normal_txs)} normal, {len(token_txs)} token)")
        return entries

    # ------------------------------------------------------------------
    # Pre-hydration helpers
    # ------------------------------------------------------------------

    async def _pre_hydrate(self, normal_txs: Dict[str, Dict],
                           token_txs: Dict[str, List[Dict]], provider_name: str):
        """Convert Etherscan data to normalizer-expected format and store as tx_raw.

        This eliminates the need for Alchemy/RPC hydration calls.  The hydration
        phase will see existing tx_raw entries and skip them.
        """
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
                "provider": provider_name,
            })

        await engine_db.upsert_tx_raw_batch(batch)
        logger.debug(f"Pre-hydrated {len(batch)} tx_raw entries from Etherscan")

    def _to_hydrated_format(self, tx_id: str,
                            normal: Optional[Dict],
                            tokens: List[Dict]) -> Dict[str, Any]:
        """Build the format expected by EvmNormalizer from Etherscan data.

        Normalizer expects hex-encoded values matching eth_getTransactionByHash
        + eth_getTransactionReceipt output.
        """
        if normal:
            # We have the main transaction data
            value_wei = int(normal.get("value", "0"))
            gas_price = int(normal.get("gasPrice", "0"))
            gas_used = int(normal.get("gasUsed", "0"))
            is_error = normal.get("isError", "0") == "1"
            tx_from = normal.get("from", "")
            tx_to = normal.get("to", "")
            block_number = int(normal.get("blockNumber", "0"))
            block_time = int(normal.get("timeStamp", "0"))
        else:
            # Token-only tx (user received tokens but wasn't the tx sender).
            # Use first token transfer entry for metadata; native value is 0.
            base = tokens[0] if tokens else {}
            value_wei = 0  # No native ETH transfer from user's perspective
            gas_price = int(base.get("gasPrice", "0"))
            gas_used = int(base.get("gasUsed", "0"))
            is_error = False
            tx_from = base.get("from", "")
            tx_to = base.get("to", "")
            block_number = int(base.get("blockNumber", "0"))
            block_time = int(base.get("timeStamp", "0"))

        # Synthesize Transfer event logs from token transfer data
        logs = []
        for ttx in tokens:
            from_addr = (ttx.get("from", "") or "").lower()
            to_addr = (ttx.get("to", "") or "").lower()
            token_value = int(ttx.get("value", "0"))
            contract = (ttx.get("contractAddress", "") or "").lower()

            # Pad addresses to 32-byte log topics
            from_topic = "0x" + from_addr[2:].zfill(64) if from_addr.startswith("0x") else ""
            to_topic = "0x" + to_addr[2:].zfill(64) if to_addr.startswith("0x") else ""
            data_hex = "0x" + hex(token_value)[2:].zfill(64)

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
            "status": "0x0" if is_error else "0x1",
            "logs": logs,
        }
