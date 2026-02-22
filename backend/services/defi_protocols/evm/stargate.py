"""
Stargate Finance Adapter

Detects STG staking positions and LP token balances across chains.
STG staking contract (veSTG): 0xB0D502E938ed5f4df2E681fE6E419ff29631d62b (Ethereum)

Detection:
- STG token balance (cross-chain)
- veSTG locked position via locked(address) call
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

# STG token addresses per chain
STG_TOKEN = {
    "ethereum": "0xAf5191B0De278C7286d6C7CC6ab6BB8A73bA2Cd6",
    "arbitrum": "0x6694340fc020c5E6B96567843da2df01b2CE1eb6",
    "optimism": "0x296F55F8Fb28E498B858d0BcDA06D955B2Cb3f97",
    "polygon": "0x2F6F07CDcf3588944Bf4C42aC74ff24bF56e7590",
    "avalanche": "0x2F6F07CDcf3588944Bf4C42aC74ff24bF56e7590",
    "bsc": "0xB0D502E938ed5f4df2E681fE6E419ff29631d62b",
}

# veSTG staking contract (Ethereum only)
VE_STG_CONTRACT = {
    "ethereum": "0xB0D502E938ed5f4df2E681fE6E419ff29631d62b",
}

# locked(address) returns (int128 amount, uint256 end) — selector 0x4b0ee02a
LOCKED_SELECTOR = "0x4b0ee02a"


class StargateAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Stargate"
    SUPPORTED_CHAINS = list(STG_TOKEN.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://stargate.finance"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        async def _check_stg(c: str):
            try:
                token = STG_TOKEN.get(c)
                if not token:
                    return None
                raw = await self._get_erc20_balance(c, token, address)
                if raw and raw > 0:
                    return ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.STAKING,
                        token_symbol="STG",
                        token_name="Stargate Token",
                        amount=raw / 1e18,
                        contract_address=token,
                    )
            except Exception as e:
                logger.debug(f"Stargate STG check error on {c}: {e}")
            return None

        async def _check_ve_stg(c: str):
            try:
                ve_contract = VE_STG_CONTRACT.get(c)
                if not ve_contract:
                    return None
                encoded = self._encode_address(address)
                result = await self._eth_call(c, ve_contract, f"{LOCKED_SELECTOR}{encoded}")
                if result and result != "0x" and len(result) >= 66:
                    locked_amount = self._decode_uint256(result, 0)
                    if locked_amount > 0:
                        return ProtocolPosition(
                            protocol=self.PROTOCOL_NAME,
                            chain=c,
                            position_type=PositionType.GOVERNANCE,
                            token_symbol="veSTG",
                            token_name="Vote-Escrowed STG",
                            amount=locked_amount / 1e18,
                            contract_address=ve_contract,
                        )
            except Exception as e:
                logger.debug(f"Stargate veSTG check error on {c}: {e}")
            return None

        tasks = [_check_stg(c) for c in chains] + [_check_ve_stg(c) for c in chains]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, ProtocolPosition):
                positions.append(r)

        return positions


protocol_registry.register(StargateAdapter())
