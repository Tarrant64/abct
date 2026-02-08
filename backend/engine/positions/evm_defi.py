"""
EVM DeFi Position Inferrer

Stub for Aave/Uniswap/Lido position detection.
Phase 5 implementation.
"""

import logging
from typing import List, Dict, Any

from engine.models import ChainId
from engine.positions.base import PositionInferrer

logger = logging.getLogger(__name__)


class EvmDefiInferrer(PositionInferrer):
    def __init__(self, chain: ChainId):
        self.chain = chain

    async def infer_positions(self, user_id: int, account_id: str,
                               events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze EVM events to identify DeFi positions.

        TODO: Phase 5 — Aave, Uniswap, Lido, etc.
        """
        return []
