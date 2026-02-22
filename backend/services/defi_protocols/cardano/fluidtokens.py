"""
FluidTokens Lending Adapter for Cardano.
Detects lending supply positions via UTXO scanning at script addresses.

FluidTokens is a peer-to-peer lending protocol on Cardano (~$2.6M TVL).
User funds are locked at script addresses with the user's payment key hash
embedded in the UTXO datum.
"""

import logging
from typing import List

from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, PositionType, DetectionMethod
)
from services.defi_protocols.cardano.utils import (
    get_payment_credential, get_wallet_utxos_at_script
)

logger = logging.getLogger(__name__)

# Known FluidTokens script addresses (lending pool contracts)
FLUIDTOKENS_SCRIPT_ADDRESSES = [
    "addr1w9qzpelu9hn45pefc0xr4ac4kdxeswq7pndul2vuj59u8tqaxqh54",
    "addr1wxn9efv2f6w82hagxqtn62ju4m293tqvw0uhmdl64ch8uwc0h43gt",
]

LOVELACE_UNIT = "lovelace"
ADA_DECIMALS = 1_000_000


class FluidTokensAdapter(ProtocolAdapter):
    """Adapter for FluidTokens lending supply positions on Cardano."""

    PROTOCOL_NAME = "FluidTokens"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.UTXO_SCAN
    PROTOCOL_URL = "https://fluidtokens.com"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect FluidTokens lending positions via UTXO scan.

        Extracts the user's payment key hash then scans known FluidTokens
        script addresses for UTXOs whose datum contains that key hash.
        Matched UTXOs represent funds the user has supplied to the protocol.

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            List of ProtocolPosition for detected lending supply positions
        """
        if chain and chain != "cardano":
            return []

        positions = []
        try:
            payment_key_hash = get_payment_credential(address)
            if not payment_key_hash:
                logger.warning(f"[FluidTokens] Could not extract payment credential from {address[:20]}...")
                return []

            total_ada_locked = 0
            utxo_count = 0

            for script_address in FLUIDTOKENS_SCRIPT_ADDRESSES:
                utxos = await get_wallet_utxos_at_script(script_address, payment_key_hash)
                for utxo in utxos:
                    # Sum lovelace amounts from matched UTXOs
                    for asset in utxo.get("amount", []):
                        if asset.get("unit") == LOVELACE_UNIT:
                            total_ada_locked += int(asset.get("quantity", 0))
                            utxo_count += 1

            if total_ada_locked <= 0:
                return []

            ada_amount = total_ada_locked / ADA_DECIMALS
            logger.info(
                f"[FluidTokens] Found {utxo_count} UTXO(s), "
                f"{ada_amount:.6f} ADA locked for {address[:20]}..."
            )

            positions.append(ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain="cardano",
                position_type=PositionType.LENDING_SUPPLY,
                token_symbol="ADA",
                token_name="FluidTokens Supply",
                amount=ada_amount,
                value_usd=0.0,
                extra={"utxo_count": utxo_count},
            ))

        except Exception as e:
            logger.error(f"[FluidTokens] Detection error: {e}")

        return positions
