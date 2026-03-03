"""
Cardano Account Expander

Expands a stake address into all associated payment addresses,
or passes through a payment address directly.
Triple fallback: SQL → Blockfrost RYO → Blockfrost.io
"""

import logging
from typing import List

from engine.models import AccountSubject, ChainId, AccountType
from engine.expansion.base import AccountExpander
from services.http_client import blockfrost_fetch
from services.api_key_manager import APIKeyManager
from services.cardano_query import cardano_query

logger = logging.getLogger(__name__)

_blockfrost_keys = APIKeyManager("blockfrost", "BLOCKFROST_API_KEY")


class CardanoExpander(AccountExpander):
    chain = ChainId.CARDANO

    async def expand(self, user_id: int, wallet_id: int, address: str) -> List[AccountSubject]:
        subjects = []

        # Always add the address itself as primary
        subjects.append(AccountSubject(
            user_id=user_id,
            wallet_id=wallet_id,
            chain=ChainId.CARDANO,
            account_id=address,
            account_type=AccountType.PRIMARY,
        ))

        # If it's a stake address (stake1...), find all associated payment addresses
        if address.startswith("stake1"):
            try:
                async def _sql():
                    from services.cardano_db_queries import get_stake_addresses
                    return await get_stake_addresses(address)

                async def _blockfrost():
                    api_key = await _blockfrost_keys.get_api_key()
                    if not api_key:
                        raise ValueError("No Blockfrost API key")
                    all_addrs = []
                    page = 1
                    while True:
                        resp = await blockfrost_fetch(
                            f"/accounts/{address}/addresses",
                            params={"count": 100, "page": page},
                            headers={"project_id": api_key},
                            timeout=30.0
                        )
                        if resp.status_code != 200:
                            break
                        data = resp.json()
                        if not data:
                            break
                        all_addrs.extend(data)
                        if len(data) < 100:
                            break
                        page += 1
                    return all_addrs

                data = await cardano_query(
                    sql_fn=_sql,
                    blockfrost_fn=_blockfrost,
                    operation=f"expand_stake({address[:20]}...)",
                )

                for entry in (data or []):
                    pay_addr = entry.get("address", "") if isinstance(entry, dict) else ""
                    if pay_addr and pay_addr != address:
                        subjects.append(AccountSubject(
                            user_id=user_id,
                            wallet_id=wallet_id,
                            chain=ChainId.CARDANO,
                            account_id=pay_addr,
                            account_type=AccountType.DERIVED,
                            parent_account_id=address,
                        ))

                logger.info(
                    f"Cardano expansion: stake key {address[:20]}... → "
                    f"{len(subjects)} accounts"
                )

            except Exception as e:
                logger.error(f"Cardano expansion error for {address}: {e}")

        # If it's a payment address (addr1...), look up the stake key
        elif address.startswith("addr1"):
            try:
                async def _sql():
                    from services.cardano_db_queries import get_address_stake_key
                    return await get_address_stake_key(address)

                async def _blockfrost():
                    api_key = await _blockfrost_keys.get_api_key()
                    if not api_key:
                        return None
                    resp = await blockfrost_fetch(
                        f"/addresses/{address}",
                        headers={"project_id": api_key},
                        timeout=30.0
                    )
                    if resp.status_code == 200:
                        return resp.json().get("stake_address")
                    return None

                stake_addr = await cardano_query(
                    sql_fn=_sql,
                    blockfrost_fn=_blockfrost,
                    operation=f"stake_lookup({address[:20]}...)",
                )

                if stake_addr:
                    subjects.append(AccountSubject(
                        user_id=user_id,
                        wallet_id=wallet_id,
                        chain=ChainId.CARDANO,
                        account_id=stake_addr,
                        account_type=AccountType.STAKE_KEY,
                        parent_account_id=address,
                    ))
            except Exception as e:
                logger.error(f"Cardano stake key lookup error for {address}: {e}")

        return subjects
