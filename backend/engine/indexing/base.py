"""
Base class for transaction indexing (Stage B).

An indexer collects transaction IDs for a given account, optionally within a block range.
This is the "cheap" stage — we only need txids, not full transaction data.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from engine.models import TxIndexEntry, ChainId


class TxIndexer(ABC):
    """Abstract base class for transaction ID collection."""

    chain: ChainId
    provider_name: str

    @abstractmethod
    async def index(self, user_id: int, account_id: str,
                    cursor_start: Optional[str] = None,
                    cursor_end: Optional[str] = None) -> List[TxIndexEntry]:
        """
        Collect transaction IDs for an account.

        Args:
            user_id: The owning user.
            account_id: The account address to index.
            cursor_start: Start of range (chain-specific: block height, page token, etc.)
            cursor_end: End of range.

        Returns:
            List of TxIndexEntry with tx_id, block_height, block_time.
        """
        ...
