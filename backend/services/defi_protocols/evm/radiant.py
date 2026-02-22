"""
Radiant Capital Adapter

Radiant is an Aave v2 fork with cross-chain lending.
Uses the same getUserAccountData(address) ABI as Aave.

Lending pool addresses:
- Arbitrum: 0xF4B1486DD74D07706052A33d31d7c0AAFD0659E1
- BSC: 0xd50Cf00b6e600Dd036Ba8eF475677d816d6c4281
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

RADIANT_POOL = {
    "arbitrum": "0xF4B1486DD74D07706052A33d31d7c0AAFD0659E1",
    "bsc": "0xd50Cf00b6e600Dd036Ba8eF475677d816d6c4281",
}

# getUserAccountData(address) — same as Aave v2/v3 selector
GET_USER_ACCOUNT_DATA = "0xbf92857c"
BASE_DECIMALS = 8


class RadiantAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Radiant"
    SUPPORTED_CHAINS = list(RADIANT_POOL.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://radiant.capital"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            pool = RADIANT_POOL.get(c)
            if not pool:
                continue

            try:
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
                        token_symbol="RADIANT-SUPPLY",
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
                        token_symbol="RADIANT-DEBT",
                        amount=debt_usd,
                        value_usd=debt_usd,
                        contract_address=pool,
                    ))

            except Exception as e:
                logger.error(f"Radiant error on {c}: {e}")

        return positions


protocol_registry.register(RadiantAdapter())
