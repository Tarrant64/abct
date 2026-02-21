"""
MakerDAO / Sky Protocol Adapter

Detects CDP (vault) positions via the Vat contract.
- Vat.urns(ilk, address) returns (ink, art) -- collateral and normalized debt
  Selector for urns(bytes32,address): 0x2424be5c

Also checks DSR (Dai Savings Rate) via the Pot contract.
- Pot.pie(address) returns normalized DSR balance
  Selector: 0x0bebac86
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

# MakerDAO core contracts (Ethereum mainnet only)
VAT_ADDRESS = "0x35D1b3F3D7966A1DFe207aa4514C12a259A0492B"
POT_ADDRESS = "0x197E90f9FAD81970bA7976f33CbD77088E5D7cf7"

# Common ilks (vault types) - bytes32 encoded
ILKS = {
    "ETH-A": "0x4554482d41000000000000000000000000000000000000000000000000000000",
    "ETH-B": "0x4554482d42000000000000000000000000000000000000000000000000000000",
    "ETH-C": "0x4554482d43000000000000000000000000000000000000000000000000000000",
    "WBTC-A": "0x574254432d410000000000000000000000000000000000000000000000000000",
    "WSTETH-A": "0x5753544554482d41000000000000000000000000000000000000000000000000",
}

# Vat.urns(bytes32,address) selector
URNS_SELECTOR = "0x2424be5c"
# Pot.pie(address) selector
PIE_SELECTOR = "0x0bebac86"


class MakerAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "MakerDAO"
    SUPPORTED_CHAINS = ["ethereum"]
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://makerdao.com"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        if chain and chain != "ethereum":
            return []

        positions = []

        # Check DSR position
        dsr_pos = await self._check_dsr(address)
        if dsr_pos:
            positions.append(dsr_pos)

        # Check vaults for common ilks
        for ilk_name, ilk_bytes32 in ILKS.items():
            pos = await self._check_vault(address, ilk_name, ilk_bytes32)
            if pos:
                positions.extend(pos)

        return positions

    async def _check_dsr(self, address: str) -> ProtocolPosition | None:
        """Check Dai Savings Rate balance via Pot.pie(address)."""
        data = PIE_SELECTOR + self._encode_address(address)
        result = await self._eth_call("ethereum", POT_ADDRESS, data)
        if not result or result == "0x":
            return None

        pie = self._decode_uint256(result, 0)
        if pie > 0:
            # pie is in wad (18 decimals), represents normalized DSR shares
            amount = pie / 1e18
            return ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain="ethereum",
                position_type=PositionType.YIELD_VAULT,
                token_symbol="DSR-DAI",
                amount=amount,
                contract_address=POT_ADDRESS,
            )
        return None

    async def _check_vault(
        self, address: str, ilk_name: str, ilk_bytes32: str
    ) -> list:
        """Check a specific vault type via Vat.urns(ilk, address)."""
        # urns(bytes32 ilk, address usr) -> (uint256 ink, uint256 art)
        # Data: selector + ilk (already 32 bytes) + padded address
        ilk_padded = ilk_bytes32[2:]  # Remove 0x prefix, already 64 chars
        data = URNS_SELECTOR + ilk_padded + self._encode_address(address)
        result = await self._eth_call("ethereum", VAT_ADDRESS, data)
        if not result or result == "0x":
            return []

        ink = self._decode_uint256(result, 0)  # Collateral (wad, 18 decimals)
        art = self._decode_uint256(result, 1)  # Normalized debt (wad, 18 decimals)

        positions = []
        if ink > 0:
            positions.append(ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain="ethereum",
                position_type=PositionType.LENDING_SUPPLY,
                token_symbol=ilk_name,
                amount=ink / 1e18,
                contract_address=VAT_ADDRESS,
                extra={"vault_type": ilk_name},
            ))
        if art > 0:
            positions.append(ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain="ethereum",
                position_type=PositionType.LENDING_BORROW,
                token_symbol=f"{ilk_name}-DEBT",
                amount=art / 1e18,
                contract_address=VAT_ADDRESS,
                extra={"vault_type": ilk_name},
            ))

        return positions


protocol_registry.register(MakerAdapter())
