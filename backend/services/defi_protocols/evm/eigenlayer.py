"""
EigenLayer Protocol Adapter

Detects restaking positions via the DelegationManager and StrategyManager.
- DelegationManager.delegatedTo(address) to check if delegated
  Selector: 0x65da1264
- StrategyManager.stakerStrategyShares(address, strategy) for share balances
  Selector: 0x7a7e0d92
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

# EigenLayer core contracts (Ethereum mainnet)
DELEGATION_MANAGER = "0x39053D51B77DC0d36036Fc1fCc8Cb819df8Ef37A"
STRATEGY_MANAGER = "0x858646372CC42E1A627fcE94aa7A7033e7CF075A"

# Major EigenLayer strategies and their underlying tokens
STRATEGIES = {
    "stETH": "0x93c4b944D05dfe6df7645A86cd2206016c51564D",
    "rETH": "0x1BeE69b7dFFfA4E2d53C2a2Df135C388AD25dCD2",
    "cbETH": "0x54945180dB7943c0ed0FEE7EdaB2Bd24620256bc",
    "wstETH": "0x0Fe4F44beE93503346A3Ac9EE5A26b130a5796d6",
    "swETH": "0x0Fe4F44beE93503346A3Ac9EE5A26b130a5796d6",
    "ETHx": "0x9d7eD45EE2E8FC5482fa2428f15C971e6369011d",
    "ankrETH": "0x13760F50a9d7377e4F20CB8CF9e4c26586c658ff",
    "OETH": "0xa4C637e40F1B0d5c17BC0940f417c4cAAdD58e4c",
    "osETH": "0x57ba429517c3473B6d34CA9aCd56c0e735b94c02",
    "sfrxETH": "0x8CA7A5d6f3acd3A7A8bC468a8CD0FB14B6BD28b6",
    "mETH": "0x298aFB19A105D59E74658C4C334F97aD1d772b75",
}

# Function selectors
DELEGATED_TO = "0x65da1264"
STAKER_STRATEGY_SHARES = "0x7a7e0d92"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


class EigenLayerAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "EigenLayer"
    SUPPORTED_CHAINS = ["ethereum"]
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://www.eigenlayer.xyz"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        if chain and chain != "ethereum":
            return []

        positions = []

        # Check all strategy shares in parallel
        tasks = []
        for token_name, strategy_addr in STRATEGIES.items():
            tasks.append((token_name, strategy_addr))

        results = await asyncio.gather(
            *[
                self._get_strategy_shares(address, strategy)
                for _, strategy in tasks
            ]
        )

        for (token_name, strategy_addr), shares in zip(tasks, results):
            if shares and shares > 0:
                positions.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain="ethereum",
                    position_type=PositionType.RESTAKING,
                    token_symbol=f"eigen-{token_name}",
                    amount=shares / 1e18,
                    contract_address=strategy_addr,
                ))

        return positions

    async def _get_strategy_shares(
        self, address: str, strategy: str
    ) -> int:
        """Call stakerStrategyShares(address, address) on StrategyManager."""
        data = (
            STAKER_STRATEGY_SHARES
            + self._encode_address(address)
            + self._encode_address(strategy)
        )
        result = await self._eth_call("ethereum", STRATEGY_MANAGER, data)
        if result and result != "0x":
            try:
                return int(result, 16)
            except ValueError:
                pass
        return 0


protocol_registry.register(EigenLayerAdapter())
