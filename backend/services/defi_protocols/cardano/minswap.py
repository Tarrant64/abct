"""
Minswap DEX Adapter for Cardano.
Detects LP positions via Minswap LP token policy ID.
Resolves underlying token amounts and USD value via pool reserve data.

Minswap is the largest DEX on Cardano by TVL (~$36M).
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

LP_POLICY_ID = "f5808c2c990d86da54bfc97d89cee6efa20cd8461616359478d96b4c"

# Minswap farm (yield farming) contract address
FARM_POLICY_ID = "e4214b7cce62ac6fbba385d164df48e157eae5863521b4b67ca71d86"


class MinswapAdapter(ProtocolAdapter):
    """Adapter for Minswap LP positions on Cardano."""

    PROTOCOL_NAME = "Minswap"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.TOKEN_BALANCE
    PROTOCOL_URL = "https://minswap.org"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect Minswap LP positions by scanning for LP tokens.

        Queries Blockfrost for assets with the Minswap LP policy ID,
        then resolves each LP token's underlying pool reserves and USD value
        using Blockfrost pool data and TapTools pricing.

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
                unit = token["unit"]
                qty = token["quantity"]
                valuation_tasks.append(resolve_lp_value(unit, qty, self.PROTOCOL_NAME))

            valuations = await asyncio.gather(*valuation_tasks, return_exceptions=True)

            for token, valuation in zip(matched, valuations):
                qty = token["quantity"]
                asset_hex = token.get("asset_name_hex", "")
                try:
                    pair_name = bytes.fromhex(asset_hex).decode("utf-8", errors="replace")
                except Exception:
                    pair_name = "LP"

                # Use valuation data if available
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
                    token_name="Minswap LP",
                    amount=float(qty),
                    value_usd=value_usd,
                    underlying_tokens=underlying,
                    extra=extra,
                ))

            if positions:
                total_val = sum(p.value_usd for p in positions)
                logger.info(
                    f"[Minswap] Found {len(positions)} LP position(s) for {address[:20]}... "
                    f"total=${total_val:.2f}"
                )

        except Exception as e:
            logger.error(f"[Minswap] Detection error: {e}")

        return positions
