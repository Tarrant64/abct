"""
Solana Transaction Hydrator

Uses Helius enhanced transaction parsing or RPC getTransaction.
"""

import logging
from typing import Dict, Any, Optional

from engine.models import ChainId
from engine.hydration.base import TxHydrator
from services.http_client import get_client, fetch_with_retry
from services.api_key_manager import APIKeyManager
from config import HELIUS_BASE_URL, HELIUS_RPC_URL

logger = logging.getLogger(__name__)

_helius_keys = APIKeyManager("helius", "HELIUS_API_KEY")


class SolanaHydrator(TxHydrator):
    chain = ChainId.SOLANA
    provider_name = "helius"

    async def hydrate(self, tx_id: str) -> Optional[Dict[str, Any]]:
        api_key = await _helius_keys.get_api_key()

        # Try Helius enhanced transaction parsing first (much richer data)
        if api_key:
            client = get_client("helius", timeout=30.0)
            resp = await fetch_with_retry(
                client, "GET",
                f"{HELIUS_BASE_URL}/transactions",
                params={"api-key": api_key, "transactions": tx_id},
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    return data[0]

        # Fallback to standard RPC
        rpc_url = f"{HELIUS_RPC_URL}/?api-key={api_key}" if api_key else "https://api.mainnet-beta.solana.com"
        client = get_client("helius", timeout=30.0)

        resp = await fetch_with_retry(
            client, "POST", rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [tx_id, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
            },
        )
        if resp.status_code != 200:
            return None

        result = resp.json().get("result")
        if not result:
            return None

        meta = result.get("meta", {})
        return {
            "signature": tx_id,
            "slot": result.get("slot"),
            "block_time": result.get("blockTime"),
            "fee": meta.get("fee", 0),
            "pre_balances": meta.get("preBalances", []),
            "post_balances": meta.get("postBalances", []),
            "pre_token_balances": meta.get("preTokenBalances", []),
            "post_token_balances": meta.get("postTokenBalances", []),
            "account_keys": result.get("transaction", {}).get("message", {}).get("accountKeys", []),
            "instructions": result.get("transaction", {}).get("message", {}).get("instructions", []),
            "log_messages": meta.get("logMessages", []),
        }
