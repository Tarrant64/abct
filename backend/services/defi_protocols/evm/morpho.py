"""
Morpho Protocol Adapter

Detects lending/borrowing positions on Morpho Blue.
- Uses position(bytes32 id, address user) to get supply/borrow shares
  Selector: 0x0317e182 (but the Morpho Blue contract uses a mapping)

Simpler approach: check supplyShares and borrowShares via the
Morpho Blue contract's position mapping.
position(bytes32,address) returns (supplyShares, borrowShares, collateral)
"""

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

# Morpho Blue main contract
MORPHO_BLUE = {
    "ethereum": "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",
    "base": "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",
}

# Popular market IDs on Morpho Blue (bytes32)
# These represent top markets by TVL
POPULAR_MARKETS = {
    "ethereum": [
        # wstETH/USDC market
        "0xb323495f7e4148be5643a4ea4a8221eef163e4bccfdedc2a6f4696baacbc86cc",
        # wstETH/WETH market
        "0xc54d7acf14de29e0e5527cabd7a576506870346a78a11a6762e2cca66322ec41",
        # WBTC/USDC market
        "0x3a85e619751152991742810df6ec69ce473daef99e28a64ab2340d7b7ccfee49",
    ],
}

# position(bytes32,address) -- supplyShares, borrowShares, collateral
# We use a simplified approach: check known market positions
POSITION_SELECTOR = "0x38d52e0f"  # placeholder -- see note below


class MorphoAdapter(BaseEVMAdapter):
    """Morpho Blue adapter - basic position detection.

    NOTE: Full Morpho position detection requires iterating market IDs
    or indexing events. This adapter checks the most popular markets
    for supply/borrow activity. Can be enhanced with a subgraph query.
    """

    PROTOCOL_NAME = "Morpho"
    SUPPORTED_CHAINS = list(MORPHO_BLUE.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://morpho.org"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            morpho = MORPHO_BLUE.get(c)
            if not morpho:
                continue

            markets = POPULAR_MARKETS.get(c, [])
            for market_id in markets:
                pos = await self._check_market_position(c, morpho, market_id, address)
                if pos:
                    positions.extend(pos)

        return positions

    async def _check_market_position(
        self, chain: str, morpho: str, market_id: str, address: str
    ) -> list:
        """Check position in a specific Morpho Blue market.

        Calls position(bytes32 id, address user) which returns
        (uint256 supplyShares, uint128 borrowShares, uint128 collateral).

        The actual function selector for position(bytes32,address) is 0x8bfa41ac.
        """
        # position(bytes32,address) selector = 0x8bfa41ac
        market_bytes = market_id[2:]  # Remove 0x, already 64 chars
        data = "0x8bfa41ac" + market_bytes + self._encode_address(address)
        result = await self._eth_call(chain, morpho, data)
        if not result or result == "0x" or len(result) < 130:
            return []

        supply_shares = self._decode_uint256(result, 0)
        borrow_shares = self._decode_uint256(result, 1)
        collateral = self._decode_uint256(result, 2)

        positions = []
        if supply_shares > 0:
            positions.append(ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain=chain,
                position_type=PositionType.LENDING_SUPPLY,
                token_symbol="MORPHO-SUPPLY",
                amount=supply_shares / 1e18,
                contract_address=morpho,
                extra={"market_id": market_id, "shares": True},
            ))

        if borrow_shares > 0:
            positions.append(ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain=chain,
                position_type=PositionType.LENDING_BORROW,
                token_symbol="MORPHO-DEBT",
                amount=borrow_shares / 1e18,
                contract_address=morpho,
                extra={"market_id": market_id, "shares": True},
            ))

        return positions


protocol_registry.register(MorphoAdapter())
