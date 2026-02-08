"""
EVM Account Expander

Passthrough — an EVM address is a single account.
Works for Ethereum, Polygon, and Base.
"""

import logging
from typing import List

from engine.models import AccountSubject, ChainId, AccountType
from engine.expansion.base import AccountExpander

logger = logging.getLogger(__name__)


class EvmExpander(AccountExpander):
    def __init__(self, chain: ChainId):
        self.chain = chain

    async def expand(self, user_id: int, wallet_id: int, address: str) -> List[AccountSubject]:
        return [AccountSubject(
            user_id=user_id,
            wallet_id=wallet_id,
            chain=self.chain,
            account_id=address.lower(),  # Normalize to lowercase for EVM
            account_type=AccountType.PRIMARY,
        )]
