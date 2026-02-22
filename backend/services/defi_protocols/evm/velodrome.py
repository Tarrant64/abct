"""
Velodrome Finance Adapter (Optimism chain)

Detects veVELO (vote-escrowed VELO) locked positions and VELO staking.
veVELO contract: 0xFAf8FD17D9840595845582fCB047DF13f006787d
VELO token: 0x9560e827aF36c94D2Ac33a39bCE1Fe78631088Db
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

VELODROME_CONTRACTS = {
    "optimism": {
        "ve_velo": "0xFAf8FD17D9840595845582fCB047DF13f006787d",
        "velo_token": "0x9560e827aF36c94D2Ac33a39bCE1Fe78631088Db",
    }
}

# lockedBalance(address) selector: 0x960baf04
LOCKED_BALANCE = "0x960baf04"


class VelodromeAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Velodrome"
    SUPPORTED_CHAINS = list(VELODROME_CONTRACTS.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://velodrome.finance"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            contracts = VELODROME_CONTRACTS.get(c)
            if not contracts:
                continue

            try:
                # Check VELO token balance
                velo_raw = await self._get_erc20_balance(c, contracts["velo_token"], address)
                if velo_raw and velo_raw > 0:
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.STAKING,
                        token_symbol="VELO",
                        token_name="Velodrome Token",
                        amount=velo_raw / 1e18,
                        contract_address=contracts["velo_token"],
                    ))

                # Check veVELO locked balance
                encoded_addr = self._encode_address(address)
                result = await self._eth_call(c, contracts["ve_velo"], f"{LOCKED_BALANCE}{encoded_addr}")
                if result and result != "0x" and len(result) >= 66:
                    locked_amount = self._decode_uint256(result, 0)
                    if locked_amount > 0:
                        positions.append(ProtocolPosition(
                            protocol=self.PROTOCOL_NAME,
                            chain=c,
                            position_type=PositionType.GOVERNANCE,
                            token_symbol="veVELO",
                            token_name="Vote-Escrowed VELO",
                            amount=locked_amount / 1e18,
                            contract_address=contracts["ve_velo"],
                            extra={"lock_type": "vote_escrow"},
                        ))

            except Exception as e:
                logger.error(f"Velodrome error on {c}: {e}")

        return positions


protocol_registry.register(VelodromeAdapter())
