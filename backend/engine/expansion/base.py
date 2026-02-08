"""
Base class for account expansion (Stage A).

An expander takes a wallet address and discovers all related accounts/sub-addresses.
"""

from abc import ABC, abstractmethod
from typing import List
from engine.models import AccountSubject, ChainId


class AccountExpander(ABC):
    """Abstract base class for wallet → account expansion."""

    chain: ChainId

    @abstractmethod
    async def expand(self, user_id: int, wallet_id: int, address: str) -> List[AccountSubject]:
        """
        Expand a wallet address into one or more account subjects.

        For simple chains (EVM), this returns the address itself.
        For UTXO chains (Bitcoin), this may derive child addresses from xpub.
        For Cardano, this may expand a stake key into all payment addresses.
        For Solana, this may enumerate associated token accounts.

        Args:
            user_id: The user who owns this wallet.
            wallet_id: The wallet DB id.
            address: The wallet address/key.

        Returns:
            List of AccountSubject instances.
        """
        ...
