"""
Splash (ex-Spectrum) DEX Adapter for Cardano.
Detects LP positions via Splash LP token policy ID.

Splash Finance (formerly Spectrum Finance) is a DEX on Cardano (~$5.8M TVL).
LP tokens are minted per pool; the token name encodes the trading pair.
"""

import logging
from typing import List

from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, PositionType, DetectionMethod
)
from services.defi_protocols.cardano.utils import check_token_in_wallet

logger = logging.getLogger(__name__)

LP_POLICY_ID = "7aca4c98b65906a5d8e3dfa174dcaa72d190e0eae5ee279df6b87c5a"


class SplashAdapter(ProtocolAdapter):
    """Adapter for Splash LP positions on Cardano."""

    PROTOCOL_NAME = "Splash"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://splash.trade"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect Splash LP positions by scanning for LP tokens.

        Queries Blockfrost for assets with the Splash LP policy ID.
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
                    token_name="Splash LP",
                    amount=float(qty),
                    value_usd=0.0,
                ))

            if positions:
                logger.info(
                    f"[Splash] Found {len(positions)} LP position(s) for {address[:20]}..."
                )

        except Exception as e:
            logger.error(f"[Splash] Detection error: {e}")

        return positions
