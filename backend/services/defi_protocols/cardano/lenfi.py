"""
Lenfi (ex-Aada) Lending Adapter for Cardano.
Detects lending supply positions via receipt token in wallet.

Lenfi (formerly Aada Finance) is a lending protocol on Cardano (~$255K TVL).
When users supply assets, they receive receipt tokens whose policy ID identifies
them as Lenfi lenders. The token name encodes position details.
"""

import logging
from typing import List

from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, PositionType, DetectionMethod
)
from services.defi_protocols.cardano.utils import check_token_in_wallet

logger = logging.getLogger(__name__)

# Lenfi receipt token policy ID
RECEIPT_TOKEN_POLICY_ID = "d4b1e603f382e42f63d6b4c61b1bfe756f2a3d2d1d0e3c3c33fabe42"


class LenfiAdapter(ProtocolAdapter):
    """Adapter for Lenfi (ex-Aada) lending supply positions on Cardano."""

    PROTOCOL_NAME = "Lenfi"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://lenfi.io"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect Lenfi lending positions via receipt token balance.

        Queries Blockfrost for assets with the Lenfi receipt token policy ID.
        Each matching token represents an active lending supply position.
        The token name encodes the pool and position details.

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            List of ProtocolPosition for each receipt token held
        """
        if chain and chain != "cardano":
            return []

        positions = []
        try:
            matched = await check_token_in_wallet(address, RECEIPT_TOKEN_POLICY_ID)
            if not matched:
                return []

            for token in matched:
                qty = token["quantity"]
                asset_hex = token.get("asset_name_hex", "")
                try:
                    position_label = bytes.fromhex(asset_hex).decode("utf-8", errors="replace").strip("\x00")
                except Exception:
                    position_label = "Receipt"

                positions.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain="cardano",
                    position_type=PositionType.LENDING_SUPPLY,
                    token_symbol=position_label or "LENFI-RECEIPT",
                    token_name="Lenfi Lending Receipt",
                    amount=float(qty),
                    value_usd=0.0,
                    extra={"receipt_token": token.get("unit", "")},
                ))

            if positions:
                logger.info(
                    f"[Lenfi] Found {len(positions)} lending position(s) for {address[:20]}..."
                )

        except Exception as e:
            logger.error(f"[Lenfi] Detection error: {e}")

        return positions
