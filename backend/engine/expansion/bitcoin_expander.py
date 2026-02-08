"""
Bitcoin Account Expander

For standard addresses (1xxx, 3xxx, bc1xxx), passes through directly.
xpub/ypub/zpub derivation is a future enhancement.
"""

import logging
from typing import List

from engine.models import AccountSubject, ChainId, AccountType
from engine.expansion.base import AccountExpander

logger = logging.getLogger(__name__)


class BitcoinExpander(AccountExpander):
    chain = ChainId.BITCOIN

    async def expand(self, user_id: int, wallet_id: int, address: str) -> List[AccountSubject]:
        # For now, standard Bitcoin addresses are a single account
        # TODO: xpub/ypub/zpub derivation in future phase
        return [AccountSubject(
            user_id=user_id,
            wallet_id=wallet_id,
            chain=ChainId.BITCOIN,
            account_id=address,
            account_type=AccountType.PRIMARY,
        )]
