"""
Compound v3 (Comet) Protocol Adapter

Detects lending/borrowing positions via:
- balanceOf(address) for supply balance (selector: 0x70a08231)
- borrowBalanceOf(address) for borrow balance (selector: 0x374c49b4)

Each Comet market is a separate contract (e.g., cUSDCv3, cWETHv3).
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

# Compound v3 Comet contracts: {chain: {market_name: address}}
COMPOUND_V3_MARKETS = {
    "ethereum": {
        "cUSDCv3": "0xc3d688B66703497DAA19211EEdff47f25384cdc3",
        "cWETHv3": "0xA17581A9E3356d9A858b789D68B4d866e593aE94",
        "cUSDTv3": "0x3Afdc9BCA9213A35503b077a6072F3D0d5AB0840",
    },
    "polygon": {
        "cUSDCv3": "0xF25212E676D1F7F89Cd72fFEe66158f541246445",
    },
    "arbitrum": {
        "cUSDCv3": "0xA5EDBDD9646f8dFF606d7448e414884C7d905dCA",
        "cUSDC.ev3": "0x9c4ec768c28520B50860ea7a15bd7213a9fF58bf",
    },
    "base": {
        "cUSDCv3": "0xb125E6687d4313864e53df431d5425969c15Eb2F",
        "cUSDbCv3": "0x46e6b214b524310239732D51387075E0e70970bf",
        "cWETHv3": "0x46e6b214b524310239732D51387075E0e70970bf",
    },
}

# Market base token decimals
MARKET_DECIMALS = {
    "cUSDCv3": 6,
    "cUSDC.ev3": 6,
    "cUSDbCv3": 6,
    "cUSDTv3": 6,
    "cWETHv3": 18,
}

# borrowBalanceOf(address) selector
BORROW_BALANCE_OF = "0x374c49b4"


class CompoundV3Adapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Compound v3"
    SUPPORTED_CHAINS = list(COMPOUND_V3_MARKETS.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://compound.finance"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            markets = COMPOUND_V3_MARKETS.get(c, {})
            if not markets:
                continue

            for market_name, contract in markets.items():
                decimals = MARKET_DECIMALS.get(market_name, 6)

                # Check supply and borrow in parallel
                supply_balance, borrow_balance = await asyncio.gather(
                    self._get_erc20_balance(c, contract, address),
                    self._get_borrow_balance(c, contract, address),
                )

                if supply_balance and supply_balance > 0:
                    amount = supply_balance / (10 ** decimals)
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.LENDING_SUPPLY,
                        token_symbol=market_name,
                        amount=amount,
                        contract_address=contract,
                    ))

                if borrow_balance and borrow_balance > 0:
                    amount = borrow_balance / (10 ** decimals)
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.LENDING_BORROW,
                        token_symbol=f"{market_name}-DEBT",
                        amount=amount,
                        contract_address=contract,
                    ))

        return positions

    async def _get_borrow_balance(
        self, chain: str, contract: str, address: str
    ) -> int:
        """Call borrowBalanceOf(address) on a Comet contract."""
        data = BORROW_BALANCE_OF + self._encode_address(address)
        result = await self._eth_call(chain, contract, data)
        if result and result != "0x":
            try:
                return int(result, 16)
            except ValueError:
                pass
        return 0


protocol_registry.register(CompoundV3Adapter())
