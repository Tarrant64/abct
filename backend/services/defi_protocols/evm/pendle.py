"""
Pendle Finance Adapter

Detects PT (Principal Token) and YT (Yield Token) positions via token balance checks.
Pendle splits yield-bearing assets into principal and yield components.
PT/YT tokens are standard ERC-20 tokens held in the user's wallet.
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

# Known Pendle PT/YT token addresses per chain
# PT = Principal Token (fixed yield), YT = Yield Token (variable yield)
PENDLE_TOKENS = {
    "ethereum": [
        # PT tokens
        {"address": "0x6ee2b5E19ECBa773a352E5B21415Dc419A700d1d", "symbol": "PT-weETH", "name": "Pendle PT weETH", "position_type": PositionType.YIELD_VAULT},
        {"address": "0xc69Ad9baB1dEE23F4605a82b3354F8E40d1E5966", "symbol": "PT-wstETH", "name": "Pendle PT wstETH", "position_type": PositionType.YIELD_VAULT},
        {"address": "0x8A20b80f5Ac56e38c10F9B8Ec2f67e4cDf54DcEA", "symbol": "PT-USDe", "name": "Pendle PT USDe", "position_type": PositionType.YIELD_VAULT},
        # YT tokens
        {"address": "0x5dFAFe57BFb73E5d4a8f75F9dDe31B0E37E51d7e", "symbol": "YT-weETH", "name": "Pendle YT weETH", "position_type": PositionType.YIELD_VAULT},
        {"address": "0x5E03C94Fc5Fb2E21882000A96Df0b63d2c4312e2", "symbol": "YT-wstETH", "name": "Pendle YT wstETH", "position_type": PositionType.YIELD_VAULT},
    ],
    "arbitrum": [
        {"address": "0x1c27Ad8a19Ba026ADaBD615F6Bc77158130cfBE4", "symbol": "PT-weETH-ARB", "name": "Pendle PT weETH (Arbitrum)", "position_type": PositionType.YIELD_VAULT},
        {"address": "0xCbc72d92b2dc8187414F6734718563898740C0BC", "symbol": "PT-wstETH-ARB", "name": "Pendle PT wstETH (Arbitrum)", "position_type": PositionType.YIELD_VAULT},
        {"address": "0x3b3fB9C57858EF816Be417792f8D4B4a4D58905B", "symbol": "YT-weETH-ARB", "name": "Pendle YT weETH (Arbitrum)", "position_type": PositionType.YIELD_VAULT},
    ],
}


class PendleAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Pendle Finance"
    SUPPORTED_CHAINS = list(PENDLE_TOKENS.keys())
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://pendle.finance"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        async def _check(c: str, token_info: dict):
            try:
                raw = await self._get_erc20_balance(c, token_info["address"], address)
                if raw and raw > 0:
                    amount = raw / 1e18
                    return ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=token_info["position_type"],
                        token_symbol=token_info["symbol"],
                        token_name=token_info["name"],
                        amount=amount,
                        contract_address=token_info["address"],
                    )
            except Exception as e:
                logger.debug(f"Pendle balance check error on {c}/{token_info['symbol']}: {e}")
            return None

        tasks = [
            _check(c, t)
            for c in chains
            if c in PENDLE_TOKENS
            for t in PENDLE_TOKENS[c]
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, ProtocolPosition):
                positions.append(r)

        return positions


protocol_registry.register(PendleAdapter())
