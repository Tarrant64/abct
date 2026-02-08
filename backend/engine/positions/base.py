"""
Base class for DeFi position inference (Stage F).

A position inferrer analyzes canonical events to identify DeFi positions
(staking, LP, lending, etc.) and compute their current state.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from engine.models import ChainId


class PositionInferrer(ABC):
    """Abstract base class for DeFi position detection."""

    chain: ChainId

    @abstractmethod
    async def infer_positions(self, user_id: int, account_id: str,
                               events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze events to identify DeFi positions.

        Args:
            user_id: The owning user.
            account_id: The account to analyze.
            events: Canonical events for this account.

        Returns:
            List of position dicts with protocol, type, amount, etc.
        """
        ...
