"""
Base Solana Adapter - Shared helpers for Solana DeFi protocol adapters.

Provides Helius RPC helpers, SPL token balance checks, and program account parsing.
"""

import logging
from typing import Optional, List
from services.defi_protocols.base_adapter import ProtocolAdapter
from services.api_key_manager import APIKeyManager
from services.http_client import get_client

logger = logging.getLogger(__name__)

# API key manager for Helius (shared)
_helius_key_manager = APIKeyManager(api_name='helius', env_var='HELIUS_API_KEY')


async def get_helius_rpc_url() -> Optional[str]:
    """Get Helius RPC URL with API key."""
    api_key = await _helius_key_manager.get_api_key()
    if api_key:
        return f"https://mainnet.helius-rpc.com/?api-key={api_key}"
    return None


async def get_spl_token_balance(wallet: str, mint: str) -> Optional[float]:
    """Get SPL token balance for a specific mint.

    Uses getTokenAccountsByOwner RPC call.
    """
    rpc_url = await get_helius_rpc_url()
    if not rpc_url:
        return None

    try:
        client = get_client("helius", timeout=15.0)
        response = await client.post(rpc_url, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet,
                {"mint": mint},
                {"encoding": "jsonParsed"}
            ]
        })

        if response.status_code != 200:
            return None

        data = response.json()
        accounts = data.get('result', {}).get('value', [])

        total = 0.0
        for account in accounts:
            parsed = account.get('account', {}).get('data', {}).get('parsed', {})
            info = parsed.get('info', {})
            token_amount = info.get('tokenAmount', {})
            amount = float(token_amount.get('uiAmount', 0) or 0)
            total += amount

        return total if total > 0 else None

    except Exception as e:
        logger.error(f"Error getting SPL balance for {mint}: {e}")
        return None


async def get_program_accounts(program_id: str, filters: list = None) -> Optional[list]:
    """Fetch program accounts with optional filters.

    Args:
        program_id: Solana program ID
        filters: List of filter objects for getProgramAccounts

    Returns:
        List of account data or None on error
    """
    rpc_url = await get_helius_rpc_url()
    if not rpc_url:
        return None

    try:
        client = get_client("helius", timeout=30.0)
        params = [program_id, {"encoding": "jsonParsed"}]
        if filters:
            params[1]["filters"] = filters

        response = await client.post(rpc_url, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getProgramAccounts",
            "params": params
        })

        if response.status_code != 200:
            return None

        data = response.json()
        return data.get('result', [])

    except Exception as e:
        logger.error(f"Error fetching program accounts for {program_id}: {e}")
        return None


class BaseSolanaAdapter(ProtocolAdapter):
    """Base class for Solana DeFi protocol adapters with shared helpers."""

    async def _get_spl_balance(self, wallet: str, mint: str) -> Optional[float]:
        return await get_spl_token_balance(wallet, mint)

    async def _get_program_accounts(self, program_id: str, filters: list = None) -> Optional[list]:
        return await get_program_accounts(program_id, filters)
