"""
PancakeSwap v3 Adapter

Detects concentrated liquidity NFT positions (Uniswap v3 fork pattern) and CAKE staking.

NonfungiblePositionManager:
- BSC: 0x46A15B0b27311cedF172AB29E4f4766fbE7F4364
- Ethereum: 0x427bF5b0f7888B65d0B5490Bf5aB8cdCBeB2e593

balanceOf(address) → count of LP NFTs owned
tokenOfOwnerByIndex(address, index) → token IDs

CAKE token staking (veCAKE) is also detected.
CAKE: 0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82 (BSC)
veCAKE: 0x5692DB8177a81A6c6afc8084C2976C9933EC1bAb (BSC)
"""

import asyncio
import logging
from typing import List, Optional
from services.defi_protocols.base_adapter import (
    DetectionMethod,
    PositionType,
    ProtocolPosition,
)
from services.defi_protocols.evm.base_evm_adapter import BaseEVMAdapter
from services.defi_protocols.registry import protocol_registry

logger = logging.getLogger(__name__)

POSITION_MANAGER = {
    "bsc": "0x46A15B0b27311cedF172AB29E4f4766fbE7F4364",
    "ethereum": "0x427bF5b0f7888B65d0B5490Bf5aB8cdCBeB2e593",
}

CAKE_TOKEN = {
    "bsc": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",
    "ethereum": "0x152649eA73beAb28c5b49B26eb48f7EAD6d4c898",
}

VE_CAKE = {
    "bsc": "0x5692DB8177a81A6c6afc8084C2976C9933EC1bAb",
}

# balanceOf(address) selector
BALANCE_OF = "0x70a08231"
# tokenOfOwnerByIndex(address, uint256) selector: 0x2f745c59
TOKEN_OF_OWNER_BY_INDEX = "0x2f745c59"
# lockedBalances(address) for veCAKE: 0x5f45601b
LOCKED_BALANCES = "0x5f45601b"

MAX_POSITIONS = 10  # cap to avoid excessive RPC calls


class PancakeSwapAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "PancakeSwap v3"
    SUPPORTED_CHAINS = list(POSITION_MANAGER.keys())
    DETECTION_METHOD = DetectionMethod.NFT_POSITION
    PROTOCOL_URL = "https://pancakeswap.finance"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            pm = POSITION_MANAGER.get(c)
            if not pm:
                continue

            try:
                # Count LP NFTs
                encoded = self._encode_address(address)
                balance_result = await self._eth_call(c, pm, f"{BALANCE_OF}{encoded}")
                if not balance_result or balance_result == "0x":
                    continue

                nft_count = self._decode_uint256(balance_result, 0)
                if nft_count == 0:
                    continue

                count = min(nft_count, MAX_POSITIONS)
                positions.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain=c,
                    position_type=PositionType.CONCENTRATED_LP,
                    token_symbol="CAKE-V3-LP",
                    token_name="PancakeSwap v3 LP",
                    amount=float(nft_count),
                    contract_address=pm,
                    extra={"nft_count": nft_count, "note": f"{nft_count} LP NFT(s) detected"},
                ))

            except Exception as e:
                logger.error(f"PancakeSwap LP NFT check error on {c}: {e}")

            # Check CAKE token balance
            cake = CAKE_TOKEN.get(c)
            if cake:
                try:
                    raw = await self._get_erc20_balance(c, cake, address)
                    if raw and raw > 0:
                        positions.append(ProtocolPosition(
                            protocol=self.PROTOCOL_NAME,
                            chain=c,
                            position_type=PositionType.STAKING,
                            token_symbol="CAKE",
                            token_name="PancakeSwap Token",
                            amount=raw / 1e18,
                            contract_address=cake,
                        ))
                except Exception as e:
                    logger.debug(f"PancakeSwap CAKE check error on {c}: {e}")

            # Check veCAKE locked balance
            ve = VE_CAKE.get(c)
            if ve:
                try:
                    encoded = self._encode_address(address)
                    result = await self._eth_call(c, ve, f"{LOCKED_BALANCES}{encoded}")
                    if result and result != "0x" and len(result) >= 66:
                        locked = self._decode_uint256(result, 0)
                        if locked > 0:
                            positions.append(ProtocolPosition(
                                protocol=self.PROTOCOL_NAME,
                                chain=c,
                                position_type=PositionType.GOVERNANCE,
                                token_symbol="veCAKE",
                                token_name="Vote-Escrowed CAKE",
                                amount=locked / 1e18,
                                contract_address=ve,
                            ))
                except Exception as e:
                    logger.debug(f"PancakeSwap veCAKE check error on {c}: {e}")

        return positions


protocol_registry.register(PancakeSwapAdapter())
