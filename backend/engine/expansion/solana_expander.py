"""
Solana Account Expander

Expands an owner address into its associated token accounts.
Uses Helius/RPC to enumerate SPL token accounts.
"""

import logging
from typing import List

from engine.models import AccountSubject, ChainId, AccountType
from engine.expansion.base import AccountExpander
from services.http_client import get_client, fetch_with_retry
from services.api_key_manager import APIKeyManager
from config import HELIUS_RPC_URL

logger = logging.getLogger(__name__)

_helius_keys = APIKeyManager("helius", "HELIUS_API_KEY")


class SolanaExpander(AccountExpander):
    chain = ChainId.SOLANA

    async def expand(self, user_id: int, wallet_id: int, address: str) -> List[AccountSubject]:
        subjects = [AccountSubject(
            user_id=user_id,
            wallet_id=wallet_id,
            chain=ChainId.SOLANA,
            account_id=address,
            account_type=AccountType.PRIMARY,
        )]

        # Enumerate token accounts via RPC
        try:
            api_key = await _helius_keys.get_api_key()
            rpc_url = f"{HELIUS_RPC_URL}/?api-key={api_key}" if api_key else "https://api.mainnet-beta.solana.com"

            client = get_client("helius", timeout=30.0)
            resp = await fetch_with_retry(
                client, "POST", rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTokenAccountsByOwner",
                    "params": [
                        address,
                        {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                        {"encoding": "jsonParsed"}
                    ]
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                accounts = data.get("result", {}).get("value", [])
                for acct in accounts:
                    pubkey = acct.get("pubkey", "")
                    if pubkey:
                        subjects.append(AccountSubject(
                            user_id=user_id,
                            wallet_id=wallet_id,
                            chain=ChainId.SOLANA,
                            account_id=pubkey,
                            account_type=AccountType.TOKEN_ACCOUNT,
                            parent_account_id=address,
                        ))
                logger.info(
                    f"Solana expansion: {address[:12]}... → "
                    f"{len(subjects)} accounts ({len(accounts)} token accounts)"
                )
        except Exception as e:
            logger.error(f"Solana expansion error for {address}: {e}")

        return subjects
