"""
Base class for event normalization (Stage D).

A normalizer converts raw transaction data into canonical events.
Each raw transaction may produce multiple events (e.g., multi-output UTXO tx).
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from engine.models import CanonicalEvent, ChainId


class EventNormalizer(ABC):
    """Abstract base class for raw tx → canonical event conversion."""

    chain: ChainId

    @abstractmethod
    async def normalize(self, user_id: int, account_id: str,
                        raw_data: Dict[str, Any]) -> List[CanonicalEvent]:
        """
        Convert a raw transaction into canonical events.

        Args:
            user_id: The owning user.
            account_id: The account perspective (determines in/out direction).
            raw_data: The full transaction data from hydration stage.

        Returns:
            List of CanonicalEvent instances. May be empty if the tx
            doesn't affect the account.
        """
        ...
