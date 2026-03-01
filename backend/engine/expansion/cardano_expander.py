"""
Cardano Account Expander

Expands a stake address into all associated payment addresses,
or passes through a payment address directly.
Uses Blockfrost API via existing HTTP client pool.
"""

import logging
from typing import List

from engine.models import AccountSubject, ChainId, AccountType
from engine.expansion.base import AccountExpander
from services.http_client import get_client, fetch_with_retry, blockfrost_fetch
from services.api_key_manager import APIKeyManager
from config import BLOCKFROST_BASE_URL

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
                api_key = await _blockfrost_keys.get_api_key()
                if not api_key:
                    logger.warning("No Blockfrost API key for Cardano expansion")
                    return subjects

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

                    for entry in data:
                        pay_addr = entry.get("address", "")
                        if pay_addr and pay_addr != address:
                            subjects.append(AccountSubject(
                                user_id=user_id,
                                wallet_id=wallet_id,
                                chain=ChainId.CARDANO,
                                account_id=pay_addr,
                                account_type=AccountType.DERIVED,
                                parent_account_id=address,
                            ))

                    if len(data) < 100:
                        break
                    page += 1

                logger.info(
                    f"Cardano expansion: stake key {address[:20]}... → "
                    f"{len(subjects)} accounts"
                )

            except Exception as e:
                logger.error(f"Cardano expansion error for {address}: {e}")

        # If it's a payment address (addr1...), look up the stake key
        elif address.startswith("addr1"):
            try:
                api_key = await _blockfrost_keys.get_api_key()
                if api_key:
                    resp = await blockfrost_fetch(
                        f"/addresses/{address}",
                        headers={"project_id": api_key},
                        timeout=30.0
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        stake_addr = data.get("stake_address")
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
