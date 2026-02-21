"""
Spark Protocol Adapter

Same ABI as Aave v3 (fork). Uses getUserAccountData(address).
Selector: 0xbf92857c
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

# Spark LendingPool addresses
SPARK_POOL = {
    "ethereum": "0xC13e21B648A5Ee794902342038FF3aDAB66BE987",
}

GET_USER_ACCOUNT_DATA = "0xbf92857c"
BASE_DECIMALS = 8


class SparkAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Spark"
    SUPPORTED_CHAINS = list(SPARK_POOL.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://spark.fi"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            pool = SPARK_POOL.get(c)
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
                    token_symbol="SPARK-SUPPLY",
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
                    token_symbol="SPARK-DEBT",
                    amount=debt_usd,
                    value_usd=debt_usd,
                    contract_address=pool,
                ))

        return positions


protocol_registry.register(SparkAdapter())
