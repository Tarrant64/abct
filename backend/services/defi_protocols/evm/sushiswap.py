"""
SushiSwap Adapter

Detects xSUSHI staking positions across chains.
xSUSHI is received when staking SUSHI in the SushiBar contract.

xSUSHI (SushiBar): 0x8798249c2E607446EfB7Ad49eC89dD1865Ff4272 (Ethereum only)
SUSHI token addresses per chain are also tracked.
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

# xSUSHI staking bar (Ethereum only)
XSUSHI_CONTRACT = {
    "ethereum": "0x8798249c2E607446EfB7Ad49eC89dD1865Ff4272",
}

# SUSHI token addresses for direct balance check
SUSHI_TOKEN = {
    "ethereum": "0x6B3595068778DD592e39A122f4f5a5cF09C90fE2",
    "polygon": "0x0b3F868E0BE5597D5DB7fEB59E1CADBb0fdDa50a",
    "arbitrum": "0xd4d42F0b6DEF4CE0383636770eF773390d85c61A",
}


class SushiSwapAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "SushiSwap"
    SUPPORTED_CHAINS = list(set(list(XSUSHI_CONTRACT.keys()) + list(SUSHI_TOKEN.keys())))
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://www.sushi.com"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        async def _check_xsushi(c: str):
            contract = XSUSHI_CONTRACT.get(c)
            if not contract:
                return None
            try:
                raw = await self._get_erc20_balance(c, contract, address)
                if raw and raw > 0:
                    return ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.STAKING,
                        token_symbol="xSUSHI",
                        token_name="SushiBar xSUSHI",
                        amount=raw / 1e18,
                        contract_address=contract,
                    )
            except Exception as e:
                logger.debug(f"SushiSwap xSUSHI check error on {c}: {e}")
            return None

        async def _check_sushi(c: str):
            token = SUSHI_TOKEN.get(c)
            if not token:
                return None
            try:
                raw = await self._get_erc20_balance(c, token, address)
                if raw and raw > 0:
                    return ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.STAKING,
                        token_symbol="SUSHI",
                        token_name="SushiSwap Token",
                        amount=raw / 1e18,
                        contract_address=token,
                    )
            except Exception as e:
                logger.debug(f"SushiSwap SUSHI check error on {c}: {e}")
            return None

        tasks = [_check_xsushi(c) for c in chains] + [_check_sushi(c) for c in chains]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, ProtocolPosition):
                positions.append(r)

        return positions


protocol_registry.register(SushiSwapAdapter())
