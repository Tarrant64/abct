"""
Aave v3 Protocol Adapter

Detects lending/borrowing positions via getUserAccountData(address).
Selector: 0xbf92857c
Returns: totalCollateralBase, totalDebtBase, availableBorrowsBase,
         currentLiquidationThreshold, ltv, healthFactor (all uint256).
Values are denominated in the pool's base currency (USD with 8 decimals).
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

# Aave v3 Pool (LendingPool) addresses per chain
AAVE_V3_POOL = {
    "ethereum": "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
    "polygon": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "arbitrum": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "base": "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
    "avalanche": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "optimism": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
}

# getUserAccountData(address) selector
GET_USER_ACCOUNT_DATA = "0xbf92857c"
# Base currency decimals (USD with 8 decimals)
BASE_DECIMALS = 8


class AaveV3Adapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Aave v3"
    SUPPORTED_CHAINS = list(AAVE_V3_POOL.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://aave.com"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            pool = AAVE_V3_POOL.get(c)
            if not pool:
                continue

            data = GET_USER_ACCOUNT_DATA + self._encode_address(address)
            result = await self._eth_call(c, pool, data)
            if not result or result == "0x":
                continue

            total_collateral = self._decode_uint256(result, 0)
            total_debt = self._decode_uint256(result, 1)
            health_factor = self._decode_uint256(result, 5)

            if total_collateral > 0:
                collateral_usd = total_collateral / (10 ** BASE_DECIMALS)
                positions.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain=c,
                    position_type=PositionType.LENDING_SUPPLY,
                    token_symbol="AAVE-SUPPLY",
                    amount=collateral_usd,
                    value_usd=collateral_usd,
                    contract_address=pool,
                    extra={
                        "health_factor": health_factor / 1e18 if health_factor < 2**128 else None,
                    },
                ))

            if total_debt > 0:
                debt_usd = total_debt / (10 ** BASE_DECIMALS)
                positions.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain=c,
                    position_type=PositionType.LENDING_BORROW,
                    token_symbol="AAVE-DEBT",
                    amount=debt_usd,
                    value_usd=debt_usd,
                    contract_address=pool,
                ))

        return positions


protocol_registry.register(AaveV3Adapter())
