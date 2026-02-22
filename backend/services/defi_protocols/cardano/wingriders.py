"""
WingRiders DEX Adapter for Cardano.
Detects LP positions via WingRiders LP token policy ID.

WingRiders is a DEX on Cardano (~$4.9M TVL).
LP tokens are minted per pool; the token name encodes the trading pair.
"""

import logging
from typing import List

from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, PositionType, DetectionMethod
)
from services.defi_protocols.cardano.utils import check_token_in_wallet

logger = logging.getLogger(__name__)

LP_POLICY_ID = "026a18d04a0c642759bb3d83b12e3344894e5c1c7b2aeb1a2113a570"


class WingRidersAdapter(ProtocolAdapter):
    """Adapter for WingRiders LP positions on Cardano."""

    PROTOCOL_NAME = "WingRiders"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://www.wingriders.com"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect WingRiders LP positions by scanning for LP tokens.

        Queries Blockfrost for assets with the WingRiders LP policy ID.
        Each matching token represents a liquidity position in a pool.

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            List of ProtocolPosition for each LP token held
        """
        if chain and chain != "cardano":
            return []

        positions = []
        try:
            matched = await check_token_in_wallet(address, LP_POLICY_ID)
            if not matched:
                return []

            for token in matched:
                qty = token["quantity"]
                asset_hex = token.get("asset_name_hex", "")
                try:
                    pair_name = bytes.fromhex(asset_hex).decode("utf-8", errors="replace")
                except Exception:
                    pair_name = "LP"

                positions.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain="cardano",
                    position_type=PositionType.LP_POSITION,
                    token_symbol=pair_name or "LP",
                    token_name="WingRiders LP",
                    amount=float(qty),
                    value_usd=0.0,
                ))

            if positions:
                logger.info(
                    f"[WingRiders] Found {len(positions)} LP position(s) for {address[:20]}..."
                )

        except Exception as e:
            logger.error(f"[WingRiders] Detection error: {e}")

        return positions
