"""
Indigo Protocol Adapter - Cardano synthetic asset platform.

Indigo Protocol enables users to:
- Stake INDY governance tokens for rewards
- Open CDPs (Collateralized Debt Positions) to mint iAssets (iUSD, iBTC, iETH, iSOL)
- Deposit iAssets in Stability Pools for liquidation premiums

This adapter DELEGATES to services.defi (DeFiService), the single Indigo
implementation: it already targets the current un-versioned analytics API
(/api/staking-positions, /api/cdps — the /api/v1/* paths this adapter used
to call are dead and return HTML 404) and carries the stake-account-wide
matching and confirmed-empty semantics. Only the mapping to
ProtocolPosition lives here, so web-dashboard registry consumers keep their
response shapes.
"""

import logging
from typing import List, Optional, Dict

from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, DetectionMethod, PositionType
)

logger = logging.getLogger(__name__)

# Indigo Protocol API (kept for reference/tests; requests happen in services.defi)
INDIGO_API_BASE = "https://analytics.indigoprotocol.io"

# Minimum collateral ratios per iAsset (Indigo governance parameters).
MIN_COLLATERAL_RATIO = {
    'iUSD': 150,  # 150%
    'iBTC': 150,
    'iETH': 150,
    'iSOL': 150,
}


class IndigoAdapter(ProtocolAdapter):
    """Adapter for Indigo Protocol on Cardano — staking, CDPs, and Stability Pool."""

    PROTOCOL_NAME = "Indigo"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.UTXO_SCAN
    PROTOCOL_URL = "https://app.indigoprotocol.io"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect all Indigo positions: staking, CDPs, and Stability Pool.

        Delegates to DeFiService (current API endpoints, shared semantics)
        and maps the results to ProtocolPosition objects.

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            List of ProtocolPosition for all detected Indigo positions
        """
        from services.defi import defi_service

        try:
            results: List[ProtocolPosition] = []

            staking = await defi_service.get_indigo_staking(address)
            if staking and staking.get('position_count'):
                results.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain="cardano",
                    position_type=PositionType.STAKING,
                    token_symbol="INDY",
                    token_name="Indigo",
                    amount=staking['total_staked_indy'],
                    extra={
                        'position_count': staking['position_count'],
                    }
                ))

            cdps = await defi_service.get_indigo_cdps(address)
            for cdp in ((cdps or {}).get('cdps') or []):
                asset = cdp.get('asset', 'iUSD')
                results.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain="cardano",
                    position_type=PositionType.CDP,
                    token_symbol=asset,
                    token_name=f"Indigo {asset} CDP",
                    amount=cdp.get('minted_amount', 0),
                    extra={
                        'cdp_type': 'mint',
                        'collateral_ada': cdp.get('collateral_ada', 0),
                        'minted_asset': asset,
                        'minted_amount': cdp.get('minted_amount', 0),
                        'min_collateral_ratio': cdp.get(
                            'min_collateral_ratio',
                            MIN_COLLATERAL_RATIO.get(asset, 150),
                        ),
                        'output_hash': cdp.get('output_hash', ''),
                    }
                ))

            # Stability pool detection is disabled in DeFiService (no
            # per-account endpoint on the current analytics API); this maps
            # whatever it returns so it lights up again when re-enabled
            sp = await defi_service.get_indigo_stability_pool(address)
            for pool in ((sp or {}).get('stability_pool') or []):
                asset = pool.get('asset', 'iUSD')
                results.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain="cardano",
                    position_type=PositionType.STABILITY_POOL,
                    token_symbol=asset,
                    token_name=f"Indigo {asset} Stability Pool",
                    amount=pool.get('deposited', 0),
                    extra={
                        'pool_asset': asset,
                        'deposited_amount': pool.get('deposited', 0),
                        'position_count': pool.get('position_count', 0),
                    }
                ))

            return results

        except Exception as e:
            logger.error(f"Error detecting Indigo positions: {e}")
            return []

    async def get_pending_rewards(
        self, address: str, chain: str = None
    ) -> Optional[dict]:
        """Get pending INDY and ADA rewards (delegates to DeFiService)."""
        from services.defi import defi_service
        return await defi_service.get_indigo_pending_rewards(address)

    async def get_cdp_positions(self, address: str) -> Optional[Dict]:
        """Get CDP positions for an address (delegates to DeFiService)."""
        from services.defi import defi_service
        result = await defi_service.get_indigo_cdps(address)
        if not result or result.get('confirmed_empty'):
            return None
        return result

    async def get_stability_pool_positions(self, address: str) -> Optional[Dict]:
        """Get Stability Pool positions (delegates to DeFiService)."""
        from services.defi import defi_service
        result = await defi_service.get_indigo_stability_pool(address)
        if not result or result.get('confirmed_empty'):
            return None
        return result

    async def get_apy(self) -> Optional[float]:
        """Fetch current Indigo staking APY (delegates to DeFiService;
        currently disabled — no stats endpoint on the current API)."""
        from services.defi import defi_service
        from services.http_client import get_client
        return await defi_service._get_indigo_apy(get_client("blockfrost"))
