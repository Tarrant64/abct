"""
Synthetix Adapter

Detects SNX staking positions and sUSD/synth balances.
Stakers receive staking rewards by minting sUSD against their SNX collateral.

SNX token addresses:
- Ethereum: 0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6F
- Optimism:  0x8700dAec35aF8Ff88c16BdF0418774CB3D7599B4
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

SNX_TOKENS = {
    "ethereum": "0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6F",
    "optimism": "0x8700dAec35aF8Ff88c16BdF0418774CB3D7599B4",
}

# sUSD stablecoin (synth) addresses
SUSD_TOKENS = {
    "ethereum": "0x57Ab1ec28D129707052df4dF418D58a2D46d5f51",
    "optimism": "0x8c6f28f2F1A3C87F0f938b96d27520d9751ec8d9",
}

# SNX staking: collateral(address) selector: 0x9572c8aa
# Returns the user's staked SNX amount
COLLATERAL_SELECTOR = "0x9572c8aa"


class SynthetixAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Synthetix"
    SUPPORTED_CHAINS = list(SNX_TOKENS.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://synthetix.io"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        async def _check_snx_balance(c: str):
            token = SNX_TOKENS.get(c)
            if not token:
                return None
            try:
                raw = await self._get_erc20_balance(c, token, address)
                if raw and raw > 0:
                    return ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.STAKING,
                        token_symbol="SNX",
                        token_name="Synthetix Network Token",
                        amount=raw / 1e18,
                        contract_address=token,
                    )
            except Exception as e:
                logger.debug(f"Synthetix SNX check error on {c}: {e}")
            return None

        async def _check_susd_balance(c: str):
            token = SUSD_TOKENS.get(c)
            if not token:
                return None
            try:
                raw = await self._get_erc20_balance(c, token, address)
                if raw and raw > 0:
                    return ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.YIELD_VAULT,
                        token_symbol="sUSD",
                        token_name="Synthetix USD",
                        amount=raw / 1e18,
                        contract_address=token,
                        extra={"synth": True},
                    )
            except Exception as e:
                logger.debug(f"Synthetix sUSD check error on {c}: {e}")
            return None

        tasks = [_check_snx_balance(c) for c in chains] + [_check_susd_balance(c) for c in chains]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, ProtocolPosition):
                positions.append(r)

        return positions


protocol_registry.register(SynthetixAdapter())
