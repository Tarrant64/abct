"""
Base class for transaction hydration (Stage C).

A hydrator fetches full transaction details given a transaction ID.
This is the "expensive" stage — full API calls per transaction.
Once hydrated, results are cached in engine_tx_raw and reusable by any provider.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from engine.models import ChainId


class TxHydrator(ABC):
    """Abstract base class for full transaction fetching."""

    chain: ChainId
    provider_name: str

    @abstractmethod
    async def hydrate(self, tx_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch full transaction details for a given tx ID.

        Args:
            tx_id: The transaction hash/signature.

        Returns:
            Raw transaction data as a dict, or None on failure.
            The raw_data should contain all information needed for normalization.
        """
        ...
