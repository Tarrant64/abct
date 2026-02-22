"""
Djed Stablecoin Adapter for Cardano.
Detects DJED and SHEN token holdings as yield vault positions.

Djed is Cardano's overcollateralized stablecoin protocol (~$9.3M TVL).
DJED is the stablecoin; SHEN is the reserve coin (earns fees from DJED minting).
Holding SHEN represents a yield-bearing position in the protocol.
"""

import logging
from typing import List

from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, PositionType, DetectionMethod
)
from services.defi_protocols.cardano.utils import check_token_in_wallet

logger = logging.getLogger(__name__)

# Djed protocol policy IDs
DJED_POLICY_ID = "8db269c3ec630e06ae29f74bc39edd1f87c819f1056206e879a1cd61"
SHEN_POLICY_ID = "8db269c3ec630e06ae29f74bc39edd1f87c819f1056206e879a1cd61"

# Lovelace divisor for token amounts (Djed uses 6 decimal places)
DJED_DECIMALS = 1_000_000


class DjedAdapter(ProtocolAdapter):
    """Adapter for Djed stablecoin protocol positions on Cardano."""

    PROTOCOL_NAME = "Djed"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://djed.xyz"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect Djed protocol positions via DJED and SHEN token balances.

        Checks for both DJED (stablecoin) and SHEN (reserve coin) tokens.
        DJED holders have a stablecoin position; SHEN holders have a yield
        vault position that earns fees from the protocol.

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            List of ProtocolPosition for DJED and/or SHEN holdings
        """
        if chain and chain != "cardano":
            return []

        positions = []
        try:
            # Check for DJED tokens
            djed_tokens = await check_token_in_wallet(address, DJED_POLICY_ID)
            for token in djed_tokens:
                asset_hex = token.get("asset_name_hex", "")
                try:
                    token_name = bytes.fromhex(asset_hex).decode("utf-8", errors="replace").strip("\x00")
                except Exception:
                    token_name = ""

                # Filter to DJED token specifically (SHEN shares the same policy)
                if "DJED" in token_name.upper() or not token_name:
                    qty = token["quantity"]
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain="cardano",
                        position_type=PositionType.YIELD_VAULT,
                        token_symbol="DJED",
                        token_name="Djed Stablecoin",
                        amount=float(qty) / DJED_DECIMALS,
                        value_usd=0.0,
                    ))

            # Check for SHEN tokens (reserve coin — earns yield from protocol fees)
            shen_tokens = await check_token_in_wallet(address, SHEN_POLICY_ID)
            for token in shen_tokens:
                asset_hex = token.get("asset_name_hex", "")
                try:
                    token_name = bytes.fromhex(asset_hex).decode("utf-8", errors="replace").strip("\x00")
                except Exception:
                    token_name = ""

                if "SHEN" in token_name.upper():
                    qty = token["quantity"]
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain="cardano",
                        position_type=PositionType.YIELD_VAULT,
                        token_symbol="SHEN",
                        token_name="Djed Reserve Coin",
                        amount=float(qty) / DJED_DECIMALS,
                        value_usd=0.0,
                    ))

            if positions:
                logger.info(
                    f"[Djed] Found {len(positions)} position(s) for {address[:20]}..."
                )

        except Exception as e:
            logger.error(f"[Djed] Detection error: {e}")

        return positions
