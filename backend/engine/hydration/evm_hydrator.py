"""
EVM Transaction Hydrator

Uses Alchemy/RPC eth_getTransactionReceipt + eth_getTransactionByHash
to fetch full transaction details including logs.
"""

import logging
from typing import Dict, Any, Optional

from engine.models import ChainId
from engine.hydration.base import TxHydrator
from services.http_client import get_client, fetch_with_retry
from services.api_key_manager import APIKeyManager

logger = logging.getLogger(__name__)

_alchemy_keys = APIKeyManager("alchemy", "ALCHEMY_API_KEY")

# RPC URLs per chain (Alchemy)
ALCHEMY_RPC_URLS = {
    "ethereum": "https://eth-mainnet.g.alchemy.com/v2",
    "polygon": "https://polygon-mainnet.g.alchemy.com/v2",
    "base": "https://base-mainnet.g.alchemy.com/v2",
}

# Public RPC fallbacks
PUBLIC_RPC_URLS = {
    "ethereum": "https://eth.llamarpc.com",
    "polygon": "https://polygon-rpc.com",
    "base": "https://mainnet.base.org",
}


class EvmHydrator(TxHydrator):
    provider_name = "alchemy"

    def __init__(self, chain: ChainId):
        self.chain = chain

    async def _get_rpc_url(self) -> str:
        api_key = await _alchemy_keys.get_api_key()
        chain_val = self.chain.value
        if api_key and chain_val in ALCHEMY_RPC_URLS:
            return f"{ALCHEMY_RPC_URLS[chain_val]}/{api_key}"
        return PUBLIC_RPC_URLS.get(chain_val, "")

    async def hydrate(self, tx_id: str) -> Optional[Dict[str, Any]]:
        rpc_url = await self._get_rpc_url()
        if not rpc_url:
            logger.warning(f"No RPC URL for {self.chain.value} hydration")
            return None

        client = get_client("alchemy", timeout=30.0)

        # Fetch transaction details
        tx_resp = await fetch_with_retry(
            client, "POST", rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_getTransactionByHash",
                "params": [tx_id],
            },
        )
        if tx_resp.status_code != 200:
            return None
        tx_data = tx_resp.json().get("result")
        if not tx_data:
            return None

        # Fetch receipt for logs
        receipt_resp = await fetch_with_retry(
            client, "POST", rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "eth_getTransactionReceipt",
                "params": [tx_id],
            },
        )
        receipt_data = None
        if receipt_resp.status_code == 200:
            receipt_data = receipt_resp.json().get("result")

        # Fetch block for timestamp
        block_number = tx_data.get("blockNumber")
        block_time = None
        if block_number:
            block_resp = await fetch_with_retry(
                client, "POST", rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "eth_getBlockByNumber",
                    "params": [block_number, False],
                },
            )
            if block_resp.status_code == 200:
                block_data = block_resp.json().get("result", {})
                ts_hex = block_data.get("timestamp", "0x0")
                block_time = int(ts_hex, 16) if ts_hex else None

        return {
            "hash": tx_id,
            "block_number": int(block_number, 16) if block_number else None,
            "block_time": block_time,
            "from": tx_data.get("from", ""),
            "to": tx_data.get("to", ""),
            "value": tx_data.get("value", "0x0"),
            "gas_price": tx_data.get("gasPrice", "0x0"),
            "gas_used": receipt_data.get("gasUsed", "0x0") if receipt_data else "0x0",
            "status": receipt_data.get("status", "0x1") if receipt_data else None,
            "logs": receipt_data.get("logs", []) if receipt_data else [],
        }
