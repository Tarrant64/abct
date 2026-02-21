"""
Indigo Protocol Adapter - Cardano synthetic asset platform with INDY staking.

Indigo Protocol enables users to create and trade synthetic assets (iUSD, iBTC, iETH)
on Cardano. Stakers earn both INDY and ADA rewards.

Detection: UTXO_SCAN via Indigo Analytics API (matches payment credential to staking positions)
"""

import logging
from typing import List, Optional

from services.http_client import get_client
from services.defi_protocols.base_adapter import (
    ProtocolAdapter, ProtocolPosition, DetectionMethod, PositionType
)
from services.defi_protocols.cardano.utils import get_payment_credential

logger = logging.getLogger(__name__)

# Indigo Protocol API
INDIGO_API_BASE = "https://analytics.indigoprotocol.io"


class IndigoAdapter(ProtocolAdapter):
    """Adapter for Indigo Protocol staking on Cardano."""

    PROTOCOL_NAME = "Indigo"
    SUPPORTED_CHAINS = ["cardano"]
    DETECTION_METHOD = DetectionMethod.UTXO_SCAN
    PROTOCOL_URL = "https://app.indigoprotocol.io"
    LOGO_URL = ""

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        """Detect Indigo staking positions by querying the Indigo Analytics API.

        Fetches all staking positions and filters by payment credential.

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            List of ProtocolPosition for staked INDY
        """
        try:
            payment_cred = get_payment_credential(address)
            if not payment_cred:
                return []

            client = get_client("blockfrost", timeout=15.0)

            # Fetch all staking positions from Indigo
            response = await client.get(
                f"{INDIGO_API_BASE}/api/v1/staking/positions"
            )

            if response.status_code != 200:
                logger.error(f"Indigo API error: {response.status_code}")
                return []

            positions = response.json()

            # Find positions matching this payment credential
            results = []
            total_staked = 0

            for pos in positions:
                if pos.get('owner') == payment_cred:
                    staked = pos.get('stakedIndy', 0)
                    total_staked += staked

            if total_staked <= 0:
                return []

            results.append(ProtocolPosition(
                protocol=self.PROTOCOL_NAME,
                chain="cardano",
                position_type=PositionType.STAKING,
                token_symbol="INDY",
                token_name="Indigo",
                amount=total_staked / 1_000_000,
                extra={
                    'position_count': sum(
                        1 for p in positions if p.get('owner') == payment_cred
                    )
                }
            ))

            return results

        except Exception as e:
            logger.error(f"Error getting Indigo staking: {e}")
            return []

    async def get_pending_rewards(
        self, address: str, chain: str = None
    ) -> Optional[dict]:
        """Get pending INDY and ADA rewards from Indigo Protocol.

        Uses Indigo Analytics API to fetch staking positions which include
        rewards data. Indigo stakers earn both INDY and ADA rewards.

        The lockedAmount may include accumulated rewards beyond staked principal.

        Args:
            address: Cardano bech32 address
            chain: Ignored (always Cardano)

        Returns:
            Dict with reward info or None
        """
        try:
            payment_cred = get_payment_credential(address)
            if not payment_cred:
                return None

            client = get_client("blockfrost", timeout=15.0)

            # Fetch staking positions which include rewards data
            response = await client.get(
                f"{INDIGO_API_BASE}/api/v1/staking/positions"
            )

            if response.status_code != 200:
                logger.warning(f"Indigo staking API returned {response.status_code}")
                return None

            positions_data = response.json()

            # Find user's positions and rewards
            total_staked = 0
            total_locked = 0
            snapshot_ada = 0

            for pos in positions_data:
                if pos.get('owner') == payment_cred:
                    staked = pos.get('stakedIndy', 0) / 1_000_000

                    # lockedAmount can be a dict or int
                    locked_raw = pos.get('lockedAmount', 0)
                    if isinstance(locked_raw, dict):
                        locked = sum(
                            v for v in locked_raw.values()
                            if isinstance(v, (int, float))
                        ) / 1_000_000
                    else:
                        locked = locked_raw / 1_000_000

                    ada_snapshot = pos.get('snapshotAda', 0) / 1_000_000

                    total_staked += staked
                    total_locked += locked
                    snapshot_ada += ada_snapshot

                    logger.info(
                        f"Indigo position: staked={staked:.2f}, "
                        f"locked={locked:.2f}, snapshotAda={ada_snapshot:.2f}"
                    )

            # snapshotAda is the ADA backing/collateral value, not pending rewards.
            # Actual pending rewards require epoch-based calculation not available via this API.
            pending_indy = max(0, total_locked - total_staked) if total_locked > 0 else 0

            return {
                'protocol': 'Indigo',
                'pending_indy': pending_indy,
                'pending_ada': 0,  # ADA rewards need to be checked in app
                'total_staked': total_staked,
                'ada_backing': snapshot_ada,
                'reward_tokens': ['INDY', 'ADA'],
                'rewards_url': 'https://app.indigoprotocol.io/earn'
            }

        except Exception as e:
            logger.error(f"Error fetching Indigo rewards: {e}")
            return None

    async def get_apy(self) -> Optional[float]:
        """Fetch current Indigo staking APY from protocol stats."""
        try:
            client = get_client("blockfrost", timeout=15.0)
            response = await client.get(f"{INDIGO_API_BASE}/api/v1/protocol/stats")
            if response.status_code == 200:
                stats = response.json()
                return stats.get('stakingApy', stats.get('apy'))
        except Exception as e:
            logger.warning(f"Could not fetch Indigo APY: {e}")
        return None
