"""
MuesliSwap DEX Adapter for Cardano.
Detects LP positions via MuesliSwap LP token policy ID.

MuesliSwap is a DEX on Cardano (~$248K TVL).
LP tokens are minted per pool; the token name encodes the trading pair.
"""

import logging
from typing import List

from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, PositionType, DetectionMethod
)
from services.defi_protocols.cardano.utils import check_token_in_wallet

logger = logging.getLogger(__name__)

LP_POLICY_ID = "af3d70acf4bd5b3abb319a7d75c89fb3e56eafcdd46b2e9b57a2999f"


class MuesliSwapAdapter(ProtocolAdapter):
    """Adapter for MuesliSwap LP positions on Cardano."""

    PROTOCOL_NAME = "MuesliSwap"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://muesliswap.com"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect MuesliSwap LP positions by scanning for LP tokens.

        Queries Blockfrost for assets with the MuesliSwap LP policy ID.
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
                    token_name="MuesliSwap LP",
                    amount=float(qty),
                    value_usd=0.0,
                ))

            if positions:
                logger.info(
                    f"[MuesliSwap] Found {len(positions)} LP position(s) for {address[:20]}..."
                )

        except Exception as e:
            logger.error(f"[MuesliSwap] Detection error: {e}")

        return positions
