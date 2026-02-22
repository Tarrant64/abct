"""
Liquity Protocol Adapter (Ethereum)

Detects Trove (CDP) positions where users deposit ETH as collateral and borrow LUSD.
TroveManager: 0xA39739EF8b0231DbFA0DcdA07d7e29faAbCf4bb2

getTroveCollAndDebt(address) returns:
  - coll: ETH collateral (uint256, 18 decimals)
  - debt: LUSD debt (uint256, 18 decimals)
Selector: 0x7b9a14b9

Also detects LQTY staking via LQTYStaking contract.
LQTYStaking: 0x4f9Fbb3f1E99B56e0Fe2892e623Ed36A76Fc605d
stakes(address) selector: 0xe8e33700 → returns uint256 staked LQTY
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

CHAIN = "ethereum"
TROVE_MANAGER = "0xA39739EF8b0231DbFA0DcdA07d7e29faAbCf4bb2"
LQTY_STAKING = "0x4f9Fbb3f1E99B56e0Fe2892e623Ed36A76Fc605d"

# getTroveCollAndDebt(address) selector
GET_TROVE_COLL_AND_DEBT = "0x7b9a14b9"
# stakes(address) selector
STAKES_SELECTOR = "0xe8e33700"


class LiquityAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Liquity"
    SUPPORTED_CHAINS = [CHAIN]
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://www.liquity.org"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        if chain and chain != CHAIN:
            return positions

        encoded = self._encode_address(address)

        try:
            # Check Trove (CDP) position
            result = await self._eth_call(CHAIN, TROVE_MANAGER, f"{GET_TROVE_COLL_AND_DEBT}{encoded}")
            if result and result != "0x" and len(result) >= 130:
                coll = self._decode_uint256(result, 0)
                debt = self._decode_uint256(result, 1)

                if coll > 0:
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=CHAIN,
                        position_type=PositionType.LENDING_SUPPLY,
                        token_symbol="ETH-COLLATERAL",
                        token_name="Liquity ETH Collateral",
                        amount=coll / 1e18,
                        contract_address=TROVE_MANAGER,
                        extra={"trove": True},
                    ))

                if debt > 0:
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=CHAIN,
                        position_type=PositionType.LENDING_BORROW,
                        token_symbol="LUSD-DEBT",
                        token_name="Liquity LUSD Debt",
                        amount=debt / 1e18,
                        contract_address=TROVE_MANAGER,
                    ))

        except Exception as e:
            logger.error(f"Liquity Trove check error: {e}")

        try:
            # Check LQTY staking
            stakes_result = await self._eth_call(CHAIN, LQTY_STAKING, f"{STAKES_SELECTOR}{encoded}")
            if stakes_result and stakes_result != "0x":
                staked = self._decode_uint256(stakes_result, 0)
                if staked > 0:
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=CHAIN,
                        position_type=PositionType.STAKING,
                        token_symbol="LQTY",
                        token_name="Staked LQTY",
                        amount=staked / 1e18,
                        contract_address=LQTY_STAKING,
                    ))

        except Exception as e:
            logger.error(f"Liquity LQTY staking check error: {e}")

        return positions


protocol_registry.register(LiquityAdapter())
