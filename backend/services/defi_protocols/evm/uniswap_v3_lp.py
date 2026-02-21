"""
Uniswap v3 LP Position Adapter

Detects concentrated liquidity positions via the NonfungiblePositionManager.
- balanceOf(address) to get the number of NFT positions (0x70a08231)
- tokenOfOwnerByIndex(address, index) to get each token ID (0x2f745c59)
- positions(uint256 tokenId) to get position details (0x99fbab88)

This is NFT-based detection: each LP position is an ERC-721 NFT.
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

# Uniswap v3 NonfungiblePositionManager addresses per chain
POSITION_MANAGER = {
    "ethereum": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
    "polygon": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
    "arbitrum": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
    "base": "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1",
    "optimism": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
}

# Function selectors
TOKEN_OF_OWNER_BY_INDEX = "0x2f745c59"  # tokenOfOwnerByIndex(address,uint256)
POSITIONS = "0x99fbab88"  # positions(uint256)

# Max positions to check per address (to avoid excessive RPC calls)
MAX_POSITIONS = 20


class UniswapV3LPAdapter(BaseEVMAdapter):
    """Uniswap v3 concentrated LP adapter.

    Detects NFT-based LP positions and extracts liquidity info.
    """

    PROTOCOL_NAME = "Uniswap v3"
    SUPPORTED_CHAINS = list(POSITION_MANAGER.keys())
    DETECTION_METHOD = DetectionMethod.NFT_POSITION
    PROTOCOL_URL = "https://app.uniswap.org"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            manager = POSITION_MANAGER.get(c)
            if not manager:
                continue

            # Get number of LP NFTs owned
            nft_count = await self._get_erc20_balance(c, manager, address)
            if not nft_count or nft_count == 0:
                continue

            count = min(nft_count, MAX_POSITIONS)

            # Get all token IDs in parallel
            token_ids = await asyncio.gather(
                *[
                    self._get_token_id(c, manager, address, i)
                    for i in range(count)
                ]
            )

            # Get position details for each token ID in parallel
            valid_ids = [tid for tid in token_ids if tid is not None]
            if not valid_ids:
                continue

            position_results = await asyncio.gather(
                *[self._get_position(c, manager, tid) for tid in valid_ids]
            )

            for tid, pos_data in zip(valid_ids, position_results):
                if pos_data and pos_data.get("liquidity", 0) > 0:
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.CONCENTRATED_LP,
                        token_symbol="UNI-V3-LP",
                        amount=pos_data["liquidity"] / 1e18,
                        contract_address=manager,
                        token_id=str(tid),
                        extra={
                            "tick_lower": pos_data.get("tick_lower"),
                            "tick_upper": pos_data.get("tick_upper"),
                            "token0": pos_data.get("token0"),
                            "token1": pos_data.get("token1"),
                        },
                    ))

        return positions

    async def _get_token_id(
        self, chain: str, manager: str, address: str, index: int
    ) -> int | None:
        """Call tokenOfOwnerByIndex(address, uint256) to get NFT token ID."""
        padded_index = hex(index)[2:].zfill(64)
        data = TOKEN_OF_OWNER_BY_INDEX + self._encode_address(address) + padded_index
        result = await self._eth_call(chain, manager, data)
        if result and result != "0x":
            try:
                return int(result, 16)
            except ValueError:
                pass
        return None

    async def _get_position(
        self, chain: str, manager: str, token_id: int
    ) -> dict | None:
        """Call positions(uint256) to get position details.

        Returns struct:
        (nonce, operator, token0, token1, fee, tickLower, tickUpper,
         liquidity, feeGrowthInside0LastX128, feeGrowthInside1LastX128,
         tokensOwed0, tokensOwed1)
        """
        padded_id = hex(token_id)[2:].zfill(64)
        data = POSITIONS + padded_id
        result = await self._eth_call(chain, manager, data)
        if not result or result == "0x" or len(result) < 770:
            return None

        try:
            # Decode position struct fields (each 32 bytes = 64 hex chars)
            token0_raw = self._decode_uint256(result, 2)
            token1_raw = self._decode_uint256(result, 3)
            tick_lower = self._decode_uint256(result, 5)
            tick_upper = self._decode_uint256(result, 6)
            liquidity = self._decode_uint256(result, 7)

            # Convert tick values (they're int24 stored as uint256)
            if tick_lower > 2**23:
                tick_lower = tick_lower - 2**24
            if tick_upper > 2**23:
                tick_upper = tick_upper - 2**24

            # Convert uint256 to address (last 20 bytes)
            token0 = "0x" + hex(token0_raw)[2:].zfill(40)[-40:]
            token1 = "0x" + hex(token1_raw)[2:].zfill(40)[-40:]

            return {
                "token0": token0,
                "token1": token1,
                "tick_lower": tick_lower,
                "tick_upper": tick_upper,
                "liquidity": liquidity,
            }
        except Exception as e:
            logger.debug(f"Error decoding Uniswap v3 position {token_id}: {e}")
            return None


protocol_registry.register(UniswapV3LPAdapter())
