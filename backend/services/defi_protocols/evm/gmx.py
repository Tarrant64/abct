"""
GMX Protocol Adapter

Detects staked GMX positions via the RewardTracker contracts.
- stakedAmounts(address) selector: 0xe0d23a0e
- claimable(address) selector: 0x402914f5

Checks staked GMX, esGMX, and GLP balances.
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

# GMX contracts per chain
GMX_CONTRACTS = {
    "arbitrum": {
        "staked_gmx_tracker": "0x908C4D94D34924765f1eDc22A1DD098397c59dD4",
        "staked_glp_tracker": "0x1aDDD80E6039594eE970E5872D247bf0414C8903",
        "fee_gmx_tracker": "0xd2D1162512F927a7e282Ef43a362659E4F2a728F",
        "fee_glp_tracker": "0x4e971a87900b931fF39d0Aad14697F36a4b62622",
    },
    "avalanche": {
        "staked_gmx_tracker": "0x2bD10f8E93B3669b6d42E74eEedC65dd1B0a1342",
        "staked_glp_tracker": "0x9e295B5B976a184B14aD8cd72413aD846C299660",
        "fee_gmx_tracker": "0x4d268a7d4C16ceB5a606c173Bd974984343fea13",
        "fee_glp_tracker": "0xd2D1162512F927a7e282Ef43a362659E4F2a728F",
    },
}

# Function selectors
STAKED_AMOUNTS = "0xe0d23a0e"
CLAIMABLE = "0x402914f5"


class GMXAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "GMX"
    SUPPORTED_CHAINS = list(GMX_CONTRACTS.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://gmx.io"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            contracts = GMX_CONTRACTS.get(c)
            if not contracts:
                continue

            # Check staked GMX and staked GLP in parallel
            gmx_staked, glp_staked = await asyncio.gather(
                self._get_staked_amount(c, contracts["staked_gmx_tracker"], address),
                self._get_staked_amount(c, contracts["staked_glp_tracker"], address),
            )

            if gmx_staked and gmx_staked > 0:
                positions.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain=c,
                    position_type=PositionType.STAKING,
                    token_symbol="GMX",
                    amount=gmx_staked / 1e18,
                    contract_address=contracts["staked_gmx_tracker"],
                ))

            if glp_staked and glp_staked > 0:
                positions.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain=c,
                    position_type=PositionType.STAKING,
                    token_symbol="GLP",
                    amount=glp_staked / 1e18,
                    contract_address=contracts["staked_glp_tracker"],
                ))

        return positions

    async def _get_staked_amount(
        self, chain: str, tracker: str, address: str
    ) -> int:
        """Call stakedAmounts(address) on a RewardTracker."""
        data = STAKED_AMOUNTS + self._encode_address(address)
        result = await self._eth_call(chain, tracker, data)
        if result and result != "0x":
            try:
                return int(result, 16)
            except ValueError:
                pass
        return 0


protocol_registry.register(GMXAdapter())
