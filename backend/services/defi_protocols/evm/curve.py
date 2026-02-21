"""
Curve Finance Protocol Adapter

Detects LP positions by checking gauge balances.
- Gauge.balanceOf(address) for staked LP tokens
  Selector: 0x70a08231 (standard ERC-20 balanceOf)

This adapter checks the most popular Curve gauges. Full coverage
would require querying the Curve gauge registry.
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

# Popular Curve gauge contracts: {chain: {pool_name: gauge_address}}
CURVE_GAUGES = {
    "ethereum": {
        "3pool": "0xbFcF63294aD7105dEa65aA58F8AE5BE2D9d0952A",
        "stETH": "0x182B723a58739a9c974cFDB385ceaDb237453c28",
        "frxETH": "0x2932a86df44Fe8D2A706d8e9c44b788b1C55F44e",
        "tricrypto2": "0xDeFd8FdD20e0f34115C7018CCfb655796F6B2168",
        "crvUSD-USDT": "0x4e6bB6B7447B7B2Aa268C16AB87F4Bb48BF57939",
        "crvUSD-USDC": "0x95f00391cB5EebCd190EB58728B4CE23DbFa6ac1",
    },
    "arbitrum": {
        "2pool": "0xCE5F24B7A95e9cBa7df4B54E911B4A3Dc8CDAf6f",
        "tricrypto": "0x97E2768e8E73511cA874545DC5Ff8067eB19B787",
    },
    "polygon": {
        "aave": "0x19793B454D3AfC7b454F206Ffe95aDE26cA6912c",
        "tricrypto": "0xb0a366b987d77b5eD5803cBd95C80bB6DEaB48C0",
    },
}

# LP token decimals (all Curve LP tokens are 18 decimals)
LP_DECIMALS = 18


class CurveAdapter(BaseEVMAdapter):
    """Curve Finance adapter - detects staked LP positions via gauges.

    NOTE: This checks a curated list of popular gauges. For full coverage,
    the Curve gauge registry or subgraph should be queried.
    """

    PROTOCOL_NAME = "Curve"
    SUPPORTED_CHAINS = list(CURVE_GAUGES.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://curve.fi"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            gauges = CURVE_GAUGES.get(c, {})
            if not gauges:
                continue

            # Check all gauges in parallel
            gauge_list = list(gauges.items())
            results = await asyncio.gather(
                *[
                    self._get_erc20_balance(c, gauge_addr, address)
                    for _, gauge_addr in gauge_list
                ]
            )

            for (pool_name, gauge_addr), balance in zip(gauge_list, results):
                if balance and balance > 0:
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.LP_POSITION,
                        token_symbol=f"CRV-{pool_name}",
                        amount=balance / (10 ** LP_DECIMALS),
                        contract_address=gauge_addr,
                    ))

        return positions


protocol_registry.register(CurveAdapter())
