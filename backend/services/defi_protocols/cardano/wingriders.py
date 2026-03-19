"""
WingRiders DEX Adapter for Cardano.
Detects LP positions via WingRiders LP token policy ID.
Resolves underlying token amounts and USD value via pool reserve data.

WingRiders is a DEX on Cardano (~$4.9M TVL).
LP tokens are minted per pool; the token name encodes the trading pair.
"""

import asyncio
import logging
from typing import List

from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, PositionType, DetectionMethod
)
from services.defi_protocols.cardano.utils import (
    check_token_in_wallet, resolve_lp_value,
)

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

        Queries Blockfrost for assets with the WingRiders LP policy ID,
        then resolves each LP token's underlying pool reserves and USD value.

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

            # Resolve LP values in parallel
            valuation_tasks = []
            for token in matched:
                valuation_tasks.append(
                    resolve_lp_value(token["unit"], token["quantity"], self.PROTOCOL_NAME)
                )

            valuations = await asyncio.gather(*valuation_tasks, return_exceptions=True)

            for token, valuation in zip(matched, valuations):
                qty = token["quantity"]
                asset_hex = token.get("asset_name_hex", "")
                try:
                    pair_name = bytes.fromhex(asset_hex).decode("utf-8", errors="replace")
                except Exception:
                    pair_name = "LP"

                value_usd = 0.0
                underlying = []
                extra = {}

                if isinstance(valuation, dict) and valuation:
                    value_usd = valuation["value_usd"]
                    pair_name = valuation.get("pair_name", pair_name)
                    underlying = [
                        {
                            "symbol": valuation["token_a"]["symbol"],
                            "amount": valuation["token_a"]["amount"],
                            "value_usd": valuation["token_a"]["value_usd"],
                        },
                        {
                            "symbol": valuation["token_b"]["symbol"],
                            "amount": valuation["token_b"]["amount"],
                            "value_usd": valuation["token_b"]["value_usd"],
                        },
                    ]
                    extra = {
                        "pool_share_pct": valuation["pool_share_pct"],
                        "value_ada": valuation["value_ada"],
                        "total_lp_supply": valuation["total_lp_supply"],
                        "pair_name": pair_name,
                    }

                positions.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain="cardano",
                    position_type=PositionType.LP_POSITION,
                    token_symbol=pair_name or "LP",
                    token_name="WingRiders LP",
                    amount=float(qty),
                    value_usd=value_usd,
                    underlying_tokens=underlying,
                    extra=extra,
                ))

            if positions:
                total_val = sum(p.value_usd for p in positions)
                logger.info(
                    f"[WingRiders] Found {len(positions)} LP position(s) for {address[:20]}... "
                    f"total=${total_val:.2f}"
                )

        except Exception as e:
            logger.error(f"[WingRiders] Detection error: {e}")

        return positions
