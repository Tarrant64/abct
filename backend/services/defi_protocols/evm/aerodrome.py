"""
Aerodrome Finance Adapter (Base chain)

Detects veAERO (vote-escrowed AERO) locked positions and AERO staking.
veAERO is an NFT-based lock, but we detect the token balance of AERO and
staked positions via the voting escrow contract.

veAERO contract: 0xeBf418Fe2512e7E6bd9b87a8F0f294aCDC67e6B4
AERO token: 0x940181a94A35A4569E4529A3CDfB74e38FD98631
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

# Aerodrome contracts (Base chain only)
AERODROME_CONTRACTS = {
    "base": {
        "ve_aero": "0xeBf418Fe2512e7E6bd9b87a8F0f294aCDC67e6B4",
        "aero_token": "0x940181a94A35A4569E4529A3CDfB74e38FD98631",
    }
}

# balanceOf(address) selector
BALANCE_OF = "0x70a08231"
# locked(uint256) selector for NFT-based lock balance — we use balanceOf to get count
# lockedBalance(address) selector: 0x960baf04
LOCKED_BALANCE = "0x960baf04"


class AerodromeAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Aerodrome"
    SUPPORTED_CHAINS = list(AERODROME_CONTRACTS.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://aerodrome.finance"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            contracts = AERODROME_CONTRACTS.get(c)
            if not contracts:
                continue

            try:
                # Check AERO token balance
                aero_raw = await self._get_erc20_balance(c, contracts["aero_token"], address)
                if aero_raw and aero_raw > 0:
                    aero_amount = aero_raw / 1e18
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.STAKING,
                        token_symbol="AERO",
                        token_name="Aerodrome Token",
                        amount=aero_amount,
                        contract_address=contracts["aero_token"],
                    ))

                # Check veAERO locked balance via lockedBalance(address)
                encoded_addr = self._encode_address(address)
                result = await self._eth_call(c, contracts["ve_aero"], f"{LOCKED_BALANCE}{encoded_addr}")
                if result and result != "0x" and len(result) >= 66:
                    locked_amount = self._decode_uint256(result, 0)
                    if locked_amount > 0:
                        amount = locked_amount / 1e18
                        positions.append(ProtocolPosition(
                            protocol=self.PROTOCOL_NAME,
                            chain=c,
                            position_type=PositionType.GOVERNANCE,
                            token_symbol="veAERO",
                            token_name="Vote-Escrowed AERO",
                            amount=amount,
                            contract_address=contracts["ve_aero"],
                            extra={"lock_type": "vote_escrow"},
                        ))

            except Exception as e:
                logger.error(f"Aerodrome error on {c}: {e}")

        return positions


protocol_registry.register(AerodromeAdapter())
