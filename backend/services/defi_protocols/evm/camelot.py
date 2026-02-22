"""
Camelot DEX Adapter (Arbitrum)

Detects:
- xGRAIL staking positions (xGRAIL is the staked/governance version of GRAIL)
- GRAIL token balance

xGRAIL contract: 0x3CAaE25Ee616f2C8E13C74dA0813402eae3F496b
GRAIL token: 0x3d9907F9a368ad0a51Be60f7Da3Cb630272d80E2
"""

import asyncio
import logging
from typing import List
from services.defi_protocols.base_adapter import (
    DetectionMethod,
    PositionType,
    ProtocolPosition,
)
from services.defi_protocols.evm.base_evm_adapter import BaseEVMAdapter
from services.defi_protocols.registry import protocol_registry

logger = logging.getLogger(__name__)

CHAIN = "arbitrum"
XGRAIL_CONTRACT = "0x3CAaE25Ee616f2C8E13C74dA0813402eae3F496b"
GRAIL_TOKEN = "0x3d9907F9a368ad0a51Be60f7Da3Cb630272d80E2"


class CamelotAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Camelot"
    SUPPORTED_CHAINS = [CHAIN]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://app.camelot.exchange"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        if chain and chain != CHAIN:
            return positions

        async def _check_xgrail():
            try:
                raw = await self._get_erc20_balance(CHAIN, XGRAIL_CONTRACT, address)
                if raw and raw > 0:
                    return ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=CHAIN,
                        position_type=PositionType.STAKING,
                        token_symbol="xGRAIL",
                        token_name="Camelot xGRAIL",
                        amount=raw / 1e18,
                        contract_address=XGRAIL_CONTRACT,
                    )
            except Exception as e:
                logger.debug(f"Camelot xGRAIL check error: {e}")
            return None

        async def _check_grail():
            try:
                raw = await self._get_erc20_balance(CHAIN, GRAIL_TOKEN, address)
                if raw and raw > 0:
                    return ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=CHAIN,
                        position_type=PositionType.STAKING,
                        token_symbol="GRAIL",
                        token_name="Camelot GRAIL",
                        amount=raw / 1e18,
                        contract_address=GRAIL_TOKEN,
                    )
            except Exception as e:
                logger.debug(f"Camelot GRAIL check error: {e}")
            return None

        results = await asyncio.gather(_check_xgrail(), _check_grail(), return_exceptions=True)
        for r in results:
            if isinstance(r, ProtocolPosition):
                positions.append(r)

        return positions


protocol_registry.register(CamelotAdapter())
