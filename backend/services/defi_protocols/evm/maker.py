"""
MakerDAO / Sky Protocol Adapter

Detects CDP (vault) positions via the Vat contract.
- Vat.urns(ilk, address) returns (ink, art) -- collateral and normalized debt
  Selector for urns(bytes32,address): 0x2424be5c

Also checks DSR (Dai Savings Rate) via the Pot contract.
- Pot.pie(address) returns normalized DSR balance
  Selector: 0x0bebac86

Enriched: Returns per-vault breakdown with collateral type, amount, debt,
and approximate collateral ratio (CR).
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

# MakerDAO core contracts (Ethereum mainnet only)
VAT_ADDRESS = "0x35D1b3F3D7966A1DFe207aa4514C12a259A0492B"
POT_ADDRESS = "0x197E90f9FAD81970bA7976f33CbD77088E5D7cf7"
JUG_ADDRESS = "0x19c0976f590D67707E62397C87829d896Dc0f1F1"
SPOT_ADDRESS = "0x65C79fcB50Ca1594B025960e539eD7A9a6D434A3"

# Common ilks (vault types) - bytes32 encoded
ILKS = {
    "ETH-A": "0x4554482d41000000000000000000000000000000000000000000000000000000",
    "ETH-B": "0x4554482d42000000000000000000000000000000000000000000000000000000",
    "ETH-C": "0x4554482d43000000000000000000000000000000000000000000000000000000",
    "WBTC-A": "0x574254432d410000000000000000000000000000000000000000000000000000",
    "WSTETH-A": "0x5753544554482d41000000000000000000000000000000000000000000000000",
    "WSTETH-B": "0x5753544554482d42000000000000000000000000000000000000000000000000",
    "RETH-A": "0x524554482d410000000000000000000000000000000000000000000000000000",
}

# Collateral token symbols for ilks
ILK_COLLATERAL = {
    "ETH-A": "ETH",
    "ETH-B": "ETH",
    "ETH-C": "ETH",
    "WBTC-A": "WBTC",
    "WSTETH-A": "wstETH",
    "WSTETH-B": "wstETH",
    "RETH-A": "rETH",
}

# Vat.urns(bytes32,address) selector
URNS_SELECTOR = "0x2424be5c"
# Pot.pie(address) selector
PIE_SELECTOR = "0x0bebac86"
# Vat.ilks(bytes32) selector - returns (Art, rate, spot, line, dust)
ILKS_SELECTOR = "0xd9638d36"
# Pot.chi() selector - returns DSR accrual multiplier
CHI_SELECTOR = "0xc92aecc4"


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

        # Check vaults for common ilks in parallel
        vault_tasks = [
            self._check_vault(address, ilk_name, ilk_bytes32)
            for ilk_name, ilk_bytes32 in ILKS.items()
        ]
        vault_results = await asyncio.gather(*vault_tasks, return_exceptions=True)

        for result in vault_results:
            if isinstance(result, Exception):
                continue
            if result:
                positions.extend(result)

        return positions

    async def _check_dsr(self, address: str) -> ProtocolPosition | None:
        """Check Dai Savings Rate balance via Pot.pie(address) and multiply by chi."""
        # Fetch pie and chi in parallel
        pie_data = PIE_SELECTOR + self._encode_address(address)
        pie_result, chi_result = await asyncio.gather(
            self._eth_call("ethereum", POT_ADDRESS, pie_data),
            self._eth_call("ethereum", POT_ADDRESS, CHI_SELECTOR),
        )

        if not pie_result or pie_result == "0x":
            return None

        pie = self._decode_uint256(pie_result, 0)
        if pie == 0:
            return None

        # chi is a ray (27 decimals) — represents DSR accrual multiplier
        chi = 1e27  # default
        if chi_result and chi_result != "0x":
            chi = self._decode_uint256(chi_result, 0)

        # Actual DAI balance = pie * chi / 1e27 / 1e18
        actual_dai = (pie * chi) / (1e27 * 1e18)

        return ProtocolPosition(
            protocol=self.PROTOCOL_NAME,
            chain="ethereum",
            position_type=PositionType.YIELD_VAULT,
            token_symbol="DSR-DAI",
            token_name="Dai Savings Rate",
            amount=actual_dai,
            value_usd=actual_dai,  # DAI ~ $1
            contract_address=POT_ADDRESS,
            extra={
                "underlying_token": "DAI",
            },
        )

    async def _check_vault(
        self, address: str, ilk_name: str, ilk_bytes32: str
    ) -> list:
        """Check a specific vault type via Vat.urns(ilk, address) and calculate CR."""
        # urns(bytes32 ilk, address usr) -> (uint256 ink, uint256 art)
        ilk_padded = ilk_bytes32[2:]  # Remove 0x prefix, already 64 chars
        urns_data = URNS_SELECTOR + ilk_padded + self._encode_address(address)

        # Fetch urn data and ilk parameters in parallel
        ilk_data = ILKS_SELECTOR + ilk_padded
        urn_result, ilk_result = await asyncio.gather(
            self._eth_call("ethereum", VAT_ADDRESS, urns_data),
            self._eth_call("ethereum", VAT_ADDRESS, ilk_data),
        )

        if not urn_result or urn_result == "0x":
            return []

        ink = self._decode_uint256(urn_result, 0)  # Collateral (wad, 18 decimals)
        art = self._decode_uint256(urn_result, 1)  # Normalized debt (wad, 18 decimals)

        if ink == 0 and art == 0:
            return []

        # Get rate and spot from ilk data to calculate actual debt and CR
        rate = 1e27  # Default 1.0 in ray
        spot_price = 0
        if ilk_result and ilk_result != "0x":
            rate = self._decode_uint256(ilk_result, 1)  # ray (27 decimals)
            spot_price = self._decode_uint256(ilk_result, 2)  # ray (27 decimals)

        # Actual debt in DAI = art * rate / 1e27 / 1e18
        actual_debt = (art * rate) / (1e27 * 1e18)
        collateral_amount = ink / 1e18

        # Collateral ratio calculation:
        # spot = price * liquidation_ratio in Vat (ray)
        # A rough CR = (ink * spot * 1.5) / (art * rate)  — but simpler:
        # If we have debt > 0 and spot > 0, CR ~ (ink * spot) / (art * rate) * 100
        collateral_ratio = None
        if actual_debt > 0 and spot_price > 0:
            collateral_value = (ink * spot_price) / (1e27 * 1e18)
            collateral_ratio = (collateral_value / actual_debt) * 100  # As percentage

        collateral_symbol = ILK_COLLATERAL.get(ilk_name, ilk_name.split("-")[0])

        positions = []
        if ink > 0:
            positions.append(ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain="ethereum",
                position_type=PositionType.CDP,
                token_symbol=ilk_name,
                token_name=f"Maker {ilk_name} Vault",
                amount=collateral_amount,
                contract_address=VAT_ADDRESS,
                extra={
                    "vault_type": ilk_name,
                    "collateral_token": collateral_symbol,
                    "collateral_amount": collateral_amount,
                    "debt_dai": actual_debt,
                    "collateral_ratio": round(collateral_ratio, 2) if collateral_ratio else None,
                },
            ))
        if art > 0:
            positions.append(ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain="ethereum",
                position_type=PositionType.LENDING_BORROW,
                token_symbol=f"{ilk_name}-DEBT",
                token_name=f"Maker {ilk_name} Debt",
                amount=actual_debt,
                value_usd=actual_debt,  # DAI ~ $1
                contract_address=VAT_ADDRESS,
                extra={
                    "vault_type": ilk_name,
                    "collateral_token": collateral_symbol,
                    "collateral_ratio": round(collateral_ratio, 2) if collateral_ratio else None,
                },
            ))

        return positions


protocol_registry.register(MakerAdapter())
